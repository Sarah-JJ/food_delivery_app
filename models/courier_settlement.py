from odoo import models, fields, api
from odoo.exceptions import UserError
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class CourierSettlement(models.Model):
    _name = 'food.delivery.courier.settlement'
    _description = 'Weekly Courier Settlement'
    _order = 'settlement_date desc'

    name = fields.Char('Settlement Reference', compute='_compute_name', store=True)
    courier_id = fields.Many2one('food.delivery.courier', 'Courier', required=True)
    settlement_date = fields.Date('Settlement Date', required=True, default=fields.Date.today)
    week_start = fields.Date('Week Start Date', required=True)
    week_end = fields.Date('Week End Date', required=True)

    # Financial calculations
    total_deliveries = fields.Integer('Total Deliveries')
    total_amount_due = fields.Float('Total Amount Due', digits=(10, 2))
    high_volume_deliveries = fields.Integer('High Volume Deliveries')
    regular_deliveries = fields.Integer('Regular Deliveries')

    state = fields.Selection([
        ('awaiting_payment', 'Awaiting Payment'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], compute='_compute_settlement_state', default='awaiting_payment', required=True, tracking=True)

    # Creation tracking
    created_by = fields.Many2one('res.users', 'Created By', readonly=True, default=lambda self: self.env.user)
    created_date = fields.Datetime('Creation Date', readonly=True, default=fields.Datetime.now)

    # Vendor bill integration
    vendor_bill_id = fields.Many2one('account.move', 'Vendor Bill', readonly=True)
    vendor_bill_state = fields.Selection(related='vendor_bill_id.state', string='Bill Status', readonly=True)
    payment_state = fields.Selection(related='vendor_bill_id.payment_state', string='Payment Status', readonly=True)

    # Settlement lines
    settlement_line_ids = fields.One2many('food.delivery.courier.settlement.line', 'settlement_id', 'Settlement Lines',
                                          readonly=True)

    # Computed fields for better visibility
    can_be_paid = fields.Boolean('Can Be Paid', compute='_compute_payment_status')
    is_paid = fields.Boolean('Is Paid', compute='_compute_payment_status')

    @api.depends('courier_id', 'week_start', 'week_end')
    def _compute_name(self):
        for record in self:
            if record.courier_id and record.week_start and record.week_end:
                record.name = f"Settlement - {record.courier_id.display_name} - {record.week_start} to {record.week_end}"
            else:
                record.name = "New Settlement"

    @api.depends('vendor_bill_id.state', 'vendor_bill_id.payment_state')
    def _compute_settlement_state(self):
        for record in self:
            if not record.vendor_bill_id:
                record.state = 'awaiting_payment'
            elif record.vendor_bill_id.state == 'cancel':
                record.state = 'cancelled'
            elif record.vendor_bill_id.payment_state == 'paid':
                record.state = 'paid'
            else:
                record.state = 'awaiting_payment'

    @api.model
    def create(self, vals):
        """Override create to automatically generate vendor bill"""
        settlement = super().create(vals)

        # Automatically create vendor bill upon settlement creation
        try:
            vendor_bill = settlement._create_vendor_bill()
            settlement.write({
                'vendor_bill_id': vendor_bill.id,
                'state': 'bill_created'
            })
            _logger.info(f"Auto-created vendor bill {vendor_bill.name} for settlement {settlement.name}")
        except Exception as e:
            _logger.error(f"Failed to auto-create vendor bill for settlement {settlement.name}: {e}")
            # Don't fail the settlement creation, but log the error

        return settlement

    def action_view_vendor_bill(self):
        """Action to view the related vendor bill"""
        if not self.vendor_bill_id:
            raise UserError('No vendor bill associated with this settlement')

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'default_move_type': 'in_invoice'}
        }

    def _create_vendor_bill(self):
        """Create vendor bill for courier payment"""
        # Ensure courier has partner configured as supplier
        if not self.courier_id.partner_id.is_company:
            self.courier_id.partner_id.is_company = True
        self.courier_id.partner_id.supplier_rank = 1

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.courier_id.partner_id.id,
            'ref': f'Courier Settlement - Week {self.week_start} to {self.week_end}',
            'invoice_date': self.settlement_date,
            'invoice_line_ids': []
        }

        # Regular delivery commissions
        if self.regular_deliveries > 0:
            regular_amount = sum(
                self.settlement_line_ids.filtered(lambda l: not l.high_volume_bonus).mapped('courier_share'))
            bill_vals['invoice_line_ids'].append((0, 0, {
                'name': f'Delivery commissions - {self.regular_deliveries} deliveries (60%)',
                'quantity': self.regular_deliveries,
                'price_unit': regular_amount / self.regular_deliveries if self.regular_deliveries else 0,
                'account_id': self._get_commission_expense_account().id,
            }))

        # High volume bonus commissions
        if self.high_volume_deliveries > 0:
            bonus_amount = sum(self.settlement_line_ids.filtered(lambda l: l.high_volume_bonus).mapped('courier_share'))
            bill_vals['invoice_line_ids'].append((0, 0, {
                'name': f'High volume bonus - {self.high_volume_deliveries} deliveries (65%)',
                'quantity': self.high_volume_deliveries,
                'price_unit': bonus_amount / self.high_volume_deliveries if self.high_volume_deliveries else 0,
                'account_id': self._get_commission_expense_account().id,
            }))

        vendor_bill = self.env['account.move'].create(bill_vals)
        vendor_bill.action_post()

        return vendor_bill

    def _get_commission_expense_account(self):
        """Get commission expense account"""
        account = self.env['account.account'].search([
            ('code', '=', '501000')
        ], limit=1)
        if not account:
            # Fallback to default expense account
            account = self.env['account.account'].search([
                ('account_type', '=', 'expense')
            ], limit=1)
        return account


class CourierSettlementLine(models.Model):
    _name = 'food.delivery.courier.settlement.line'
    _description = 'Courier Settlement Line Item'

    settlement_id = fields.Many2one('food.delivery.courier.settlement', 'Settlement', required=True, ondelete='cascade')
    external_order_id = fields.Integer('Order ID', required=True)
    delivery_date = fields.Datetime('Delivery Date', required=True)
    courier_share = fields.Float('Courier Share', digits=(10, 2), required=True)
    delivery_fee = fields.Float('Total Delivery Fee', digits=(10, 2), required=True)
    high_volume_bonus = fields.Boolean('High Volume Bonus Applied')


class SettlementAutomation(models.Model):
    _name = 'settlement.automation'
    _description = 'Automated Settlement Processing'

    def _get_external_db_connection(self):
        """Get connection to external PostgreSQL database"""
        config = self.env['ir.config_parameter'].sudo()
        return psycopg2.connect(
            host=config.get_param('external.db.host', 'localhost'),
            database=config.get_param('external.db.name', 'food_delivery'),
            user=config.get_param('external.db.user', 'odoo_user'),
            password=config.get_param('external.db.password', ''),
            port=config.get_param('external.db.port', '5432')
        )

    def _execute_external_query(self, query, params=None):
        """Execute query on external database"""
        conn = None
        try:
            conn = self._get_external_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params or ())

            if query.strip().upper().startswith('SELECT'):
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.rowcount

        except Exception as e:
            _logger.error(f"Database query error: {e}")
            if conn:
                conn.rollback()
            return []
        finally:
            if conn:
                conn.close()

    @api.model
    def generate_weekly_settlements(self):
        """Generate weekly settlements every Monday"""
        try:
            # Calculate previous week dates
            today = fields.Date.today()
            week_start = today - timedelta(days=today.weekday() + 7)  # Previous Monday
            week_end = week_start + timedelta(days=6)  # Previous Sunday

            _logger.info(f"Generating settlements for week {week_start} to {week_end}")

            # Get delivered orders from external database
            delivered_orders = self._get_weekly_deliveries(week_start, week_end)

            if not delivered_orders:
                _logger.info("No delivered orders found for settlement period")
                return

            # Process courier settlements
            courier_settlements = self._process_courier_settlements(delivered_orders, week_start, week_end)

            _logger.info(f"Generated {len(courier_settlements)} courier settlements with auto-created vendor bills")

        except Exception as e:
            _logger.error(f"Error generating settlements: {e}")

    def _get_weekly_deliveries(self, week_start, week_end):
        """Get delivered orders for settlement calculation"""
        query = """
        SELECT 
            o.order_id,
            o.courier_id,
            o.created_at,
            COALESCE(o.delivery_fee, 0) as delivery_fee,
            COALESCE(o.courier_share, 0) as courier_share,
            COALESCE(o.company_share, 0) as company_share,
            COALESCE(o.odoo_calculation_id, 0) as calculation_id
        FROM orders o
        WHERE o.order_status = 'delivered'
        AND DATE(o.created_at) BETWEEN %s AND %s
        ORDER BY o.courier_id, o.created_at
        """

        return self._execute_external_query(query, (week_start, week_end))

    def _process_courier_settlements(self, orders, week_start, week_end):
        """Process courier settlements from order data with auto-creation of missing couriers"""
        settlements = []

        # Group orders by courier
        courier_data = {}
        for order in orders:
            courier_id = order['courier_id']
            if courier_id not in courier_data:
                courier_data[courier_id] = {
                    'total_amount': 0,
                    'total_deliveries': 0,
                    'regular_deliveries': 0,
                    'high_volume_deliveries': 0,
                    'orders': []
                }

            courier_data[courier_id]['total_amount'] += float(order['courier_share'] or 0)
            courier_data[courier_id]['total_deliveries'] += 1
            courier_data[courier_id]['orders'].append(order)

        # Create settlement records (vendor bills will be auto-created)
        for external_courier_id, data in courier_data.items():
            # Find or create courier in Odoo
            courier = self._find_or_create_courier(external_courier_id)

            if not courier:
                _logger.error(f"Failed to find or create courier {external_courier_id}")
                continue

            # Calculate high volume vs regular deliveries
            regular_count = 0
            high_volume_count = 0

            for order in data['orders']:
                # Check if this delivery had high volume bonus
                if order.get('calculation_id'):
                    calc = self.env['food.delivery.fee.calculation'].browse(order['calculation_id'])
                    if calc.exists() and calc.high_volume_bonus:
                        high_volume_count += 1
                    else:
                        regular_count += 1
                else:
                    regular_count += 1

            # Create settlement (this will auto-create vendor bill)
            settlement = self.env['food.delivery.courier.settlement'].create({
                'courier_id': courier.id,
                'week_start': week_start,
                'week_end': week_end,
                'settlement_date': fields.Date.today(),
                'total_deliveries': data['total_deliveries'],
                'total_amount_due': data['total_amount'],
                'regular_deliveries': regular_count,
                'high_volume_deliveries': high_volume_count,
            })

            # Create settlement lines
            for order in data['orders']:
                # Check if high volume bonus was applied
                high_volume_bonus = False
                if order.get('calculation_id'):
                    calc = self.env['food.delivery.fee.calculation'].browse(order['calculation_id'])
                    if calc.exists():
                        high_volume_bonus = calc.high_volume_bonus

                self.env['food.delivery.courier.settlement.line'].create({
                    'settlement_id': settlement.id,
                    'external_order_id': order['order_id'],
                    'delivery_date': order['created_at'],
                    'courier_share': float(order['courier_share'] or 0),
                    'delivery_fee': float(order['delivery_fee'] or 0),
                    'high_volume_bonus': high_volume_bonus
                })

            settlements.append(settlement)

        return settlements

    def _find_or_create_courier(self, external_courier_id):
        """Find existing courier or create new one from external database"""
        # Try to find existing courier
        courier = self.env['food.delivery.courier'].search([
            ('external_courier_id', '=', external_courier_id)
        ], limit=1)

        if courier:
            return courier

        # Fetch courier details from external database
        courier_data = self._get_courier_details(external_courier_id)

        if not courier_data:
            _logger.error(f"Courier {external_courier_id} not found in external database")
            return None

        try:
            # Create partner for courier
            partner = self.env['res.partner'].sudo().create_courier_partner(
                external_courier_id=external_courier_id,
                name=courier_data['courier_full_name'],
                phone=None,  # Add phone if available in external DB
                email=None  # Add email if available in external DB
            )

            # Create courier record
            courier = self.env['food.delivery.courier'].create({
                'external_courier_id': external_courier_id,
                'partner_id': partner.id
            })

            _logger.info(f"Auto-created courier: {courier.display_name}")
            return courier

        except Exception as e:
            _logger.error(f"Failed to create courier {external_courier_id}: {e}")
            return None

    def _get_courier_details(self, external_courier_id):
        """Get courier details from external database"""
        query = """
        SELECT 
            courier_id,
            courier_full_name,
            courier_address,
            date_of_birth,
            gender
        FROM couriers 
        WHERE courier_id = %s
        """

        result = self._execute_external_query(query, (external_courier_id,))
        return result[0] if result else None