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

    # Workflow states
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], default='draft', required=True, tracking=True)

    # Approval tracking
    confirmed_by = fields.Many2one('res.users', 'Confirmed By', readonly=True)
    confirmed_date = fields.Datetime('Confirmation Date', readonly=True)
    paid_by = fields.Many2one('res.users', 'Paid By', readonly=True)
    paid_date = fields.Datetime('Payment Date', readonly=True)

    # Vendor bill integration
    vendor_bill_id = fields.Many2one('account.move', 'Vendor Bill', readonly=True)
    payment_id = fields.Many2one('account.payment', 'Payment Record', readonly=True)

    # Settlement lines
    settlement_line_ids = fields.One2many('food.delivery.courier.settlement.line', 'settlement_id', 'Settlement Lines')

    @api.depends('courier_id', 'week_start', 'week_end')
    def _compute_name(self):
        for record in self:
            if record.courier_id and record.week_start and record.week_end:
                record.name = f"Settlement - {record.courier_id.display_name} - {record.week_start} to {record.week_end}"
            else:
                record.name = "New Settlement"

    def action_confirm_settlement(self):
        """Finance team confirms settlement and creates vendor bill"""
        if self.state != 'draft':
            raise UserError('Only draft settlements can be confirmed')

        # Create vendor bill
        vendor_bill = self._create_vendor_bill()

        self.write({
            'state': 'confirmed',
            'confirmed_by': self.env.user.id,
            'confirmed_date': fields.Datetime.now(),
            'vendor_bill_id': vendor_bill.id
        })

        return True

    def action_mark_paid(self):
        """Register payment for vendor bill"""
        if self.state != 'confirmed' or not self.vendor_bill_id:
            raise UserError('Settlement must be confirmed with vendor bill before payment')

        # Create payment for vendor bill
        payment = self.env['account.payment'].create({
            'payment_type': 'outbound',
            'partner_type': 'supplier',
            'partner_id': self.courier_id.partner_id.id,
            'amount': self.total_amount_due,
            'journal_id': self._get_cash_journal().id,
            'ref': f'Payment - {self.vendor_bill_id.ref or self.name}'
        })

        payment.action_post()

        # Reconcile payment with vendor bill
        if self.vendor_bill_id.state == 'posted':
            lines_to_reconcile = payment.line_ids + self.vendor_bill_id.line_ids
            lines_to_reconcile = lines_to_reconcile.filtered(
                lambda l: l.account_id == payment.destination_account_id and not l.reconciled
            )
            lines_to_reconcile.reconcile()

        self.write({
            'state': 'paid',
            'payment_id': payment.id,
            'paid_by': self.env.user.id,
            'paid_date': fields.Datetime.now()
        })

        return True

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

    def _get_cash_journal(self):
        """Get cash journal for payments"""
        journal = self.env['account.journal'].search([
            ('type', '=', 'cash')
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'bank')
            ], limit=1)
        return journal


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

            _logger.info(f"Generated {len(courier_settlements)} courier settlements")

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
        """Process courier settlements from order data"""
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

        # Create settlement records
        for external_courier_id, data in courier_data.items():
            # Find courier in Odoo
            courier = self.env['food.delivery.courier'].search([
                ('external_courier_id', '=', external_courier_id)
            ], limit=1)

            if not courier:
                _logger.warning(f"Courier {external_courier_id} not found in Odoo")
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

            # Create settlement
            settlement = self.env['food.delivery.courier.settlement'].create({
                'courier_id': courier.id,
                'week_start': week_start,
                'week_end': week_end,
                'settlement_date': fields.Date.today(),
                'total_deliveries': data['total_deliveries'],
                'total_amount_due': data['total_amount'],
                'regular_deliveries': regular_count,
                'high_volume_deliveries': high_volume_count,
                'state': 'draft'
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