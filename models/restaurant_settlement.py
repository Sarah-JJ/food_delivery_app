from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class RestaurantSettlement(models.Model):
    _name = 'food.delivery.restaurant.settlement'
    _description = 'Weekly Restaurant Settlement'
    _order = 'settlement_date desc'

    name = fields.Char('Settlement Reference', compute='_compute_name', store=True)
    restaurant_id = fields.Many2one('res.partner', 'Restaurant',
                                    domain=[('partner_type', '=', 'restaurant')], required=True)
    settlement_date = fields.Date('Settlement Date', required=True, default=fields.Date.today)
    week_start = fields.Date('Week Start Date', required=True)
    week_end = fields.Date('Week End Date', required=True)

    # Financial calculations
    total_order_amount = fields.Float('Total Order Amount', digits=(10, 2))
    total_delivery_fees = fields.Float('Total Delivery Fees Deducted', digits=(10, 2))
    net_amount_due = fields.Float('Net Amount Due', compute='_compute_net_amount',
                                  digits=(10, 2), store=True)
    total_orders = fields.Integer('Total Orders')

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
    settlement_line_ids = fields.One2many('food.delivery.restaurant.settlement.line',
                                          'settlement_id', 'Settlement Lines', readonly=True)

    @api.depends('restaurant_id', 'week_start', 'week_end')
    def _compute_name(self):
        for record in self:
            if record.restaurant_id and record.week_start and record.week_end:
                record.name = f"Settlement - {record.restaurant_id.name} - {record.week_start} to {record.week_end}"
            else:
                record.name = "New Settlement"

    @api.depends('total_order_amount', 'total_delivery_fees')
    def _compute_net_amount(self):
        for record in self:
            record.net_amount_due = record.total_order_amount - record.total_delivery_fees

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
            _logger.info(f"Auto-created vendor bill {vendor_bill.name} for restaurant settlement {settlement.name}")
        except Exception as e:
            _logger.error(f"Failed to auto-create vendor bill for restaurant settlement {settlement.name}: {e}")
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
        """Create vendor bill for restaurant payment"""
        # Ensure restaurant is configured as supplier
        self.restaurant_id.supplier_rank = 1

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.restaurant_id.id,
            'ref': f'Restaurant Settlement - Week {self.week_start} to {self.week_end}',
            'invoice_date': self.settlement_date,
            'invoice_line_ids': [
                (0, 0, {
                    'name': f'Food order revenue share - {self.total_orders} orders (Week {self.week_start})',
                    'quantity': 1,
                    'price_unit': self.net_amount_due,
                    'account_id': self._get_restaurant_expense_account().id,
                })
            ]
        }

        vendor_bill = self.env['account.move'].create(bill_vals)
        vendor_bill.action_post()

        return vendor_bill

    def _get_restaurant_expense_account(self):
        """Get restaurant payment expense account"""
        account = self.env['account.account'].search([
            ('code', '=', '502000')
        ], limit=1)
        if not account:
            # Fallback to default expense account
            account = self.env['account.account'].search([
                ('account_type', '=', 'expense')
            ], limit=1)
        return account


class RestaurantSettlementLine(models.Model):
    _name = 'food.delivery.restaurant.settlement.line'
    _description = 'Restaurant Settlement Line Item'

    settlement_id = fields.Many2one('food.delivery.restaurant.settlement', 'Settlement',
                                    required=True, ondelete='cascade')
    external_order_id = fields.Integer('Order ID', required=True)
    order_date = fields.Datetime('Order Date', required=True)
    order_amount = fields.Float('Order Amount', digits=(10, 2), required=True)
    delivery_fee = fields.Float('Delivery Fee Deducted', digits=(10, 2), required=True)
    net_amount = fields.Float('Net Amount', compute='_compute_net_amount', digits=(10, 2))

    @api.depends('order_amount', 'delivery_fee')
    def _compute_net_amount(self):
        for line in self:
            line.net_amount = line.order_amount - line.delivery_fee


class RestaurantSettlementAutomation(models.Model):
    _name = 'restaurant.settlement.automation'
    _inherit = 'settlement.automation'
    _description = 'Restaurant Settlement Automation'

    def generate_restaurant_settlements(self, week_start, week_end):
        """Generate restaurant settlements for the week"""
        try:
            # Get delivered orders from external database
            delivered_orders = self._get_weekly_restaurant_orders(week_start, week_end)

            if not delivered_orders:
                _logger.info("No delivered orders found for restaurant settlement")
                return []

            # Process restaurant settlements
            restaurant_settlements = self._process_restaurant_settlements(delivered_orders, week_start, week_end)

            _logger.info(
                f"Generated {len(restaurant_settlements)} restaurant settlements with auto-created vendor bills")
            return restaurant_settlements

        except Exception as e:
            _logger.error(f"Error generating restaurant settlements: {e}")
            return []

    def _get_weekly_restaurant_orders(self, week_start, week_end):
        """Get delivered orders for restaurant settlement calculation"""
        query = """
        SELECT 
            o.order_id,
            o.restaurant_id,
            o.created_at,
            CAST(o.items::json->>'total_amount' AS DECIMAL) as order_total,
            COALESCE(o.delivery_fee, 0) as delivery_fee
        FROM orders o
        WHERE o.order_status = 'delivered'
        AND DATE(o.created_at) BETWEEN %s AND %s
        ORDER BY o.restaurant_id, o.created_at
        """

        return self._execute_external_query(query, (week_start, week_end))

    def _process_restaurant_settlements(self, orders, week_start, week_end):
        """Process restaurant settlements from order data"""
        settlements = []

        # Group orders by restaurant
        restaurant_data = {}
        for order in orders:
            restaurant_id = order['restaurant_id']
            if restaurant_id not in restaurant_data:
                restaurant_data[restaurant_id] = {
                    'total_order_amount': 0,
                    'total_delivery_fees': 0,
                    'total_orders': 0,
                    'orders': []
                }

            restaurant_data[restaurant_id]['total_order_amount'] += float(order['order_total'] or 0)
            restaurant_data[restaurant_id]['total_delivery_fees'] += float(order['delivery_fee'] or 0)
            restaurant_data[restaurant_id]['total_orders'] += 1
            restaurant_data[restaurant_id]['orders'].append(order)

        # Create settlement records (vendor bills will be auto-created)
        for external_restaurant_id, data in restaurant_data.items():
            # Find restaurant partner
            restaurant = self.env['res.partner'].search([
                ('external_restaurant_id', '=', external_restaurant_id),
                ('partner_type', '=', 'restaurant')
            ], limit=1)

            if not restaurant:
                _logger.warning(f"Restaurant {external_restaurant_id} not found in Odoo")
                continue

            # Create settlement (this will auto-create vendor bill)
            settlement = self.env['food.delivery.restaurant.settlement'].create({
                'restaurant_id': restaurant.id,
                'week_start': week_start,
                'week_end': week_end,
                'settlement_date': fields.Date.today(),
                'total_order_amount': data['total_order_amount'],
                'total_delivery_fees': data['total_delivery_fees'],
                'total_orders': data['total_orders'],
            })

            # Create settlement lines
            for order in data['orders']:
                self.env['food.delivery.restaurant.settlement.line'].create({
                    'settlement_id': settlement.id,
                    'external_order_id': order['order_id'],
                    'order_date': order['created_at'],
                    'order_amount': float(order['order_total'] or 0),
                    'delivery_fee': float(order['delivery_fee'] or 0)
                })

            settlements.append(settlement)

        return settlements