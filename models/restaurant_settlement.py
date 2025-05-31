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
    settlement_line_ids = fields.One2many('food.delivery.restaurant.settlement.line',
                                          'settlement_id', 'Settlement Lines')

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
            'partner_id': self.restaurant_id.id,
            'amount': self.net_amount_due,
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

            _logger.info(f"Generated {len(restaurant_settlements)} restaurant settlements")
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

        # Create settlement records
        for external_restaurant_id, data in restaurant_data.items():
            # Find restaurant partner
            restaurant = self.env['res.partner'].search([
                ('external_restaurant_id', '=', external_restaurant_id),
                ('partner_type', '=', 'restaurant')
            ], limit=1)

            if not restaurant:
                _logger.warning(f"Restaurant {external_restaurant_id} not found in Odoo")
                continue

            # Create settlement
            settlement = self.env['food.delivery.restaurant.settlement'].create({
                'restaurant_id': restaurant.id,
                'week_start': week_start,
                'week_end': week_end,
                'settlement_date': fields.Date.today(),
                'total_order_amount': data['total_order_amount'],
                'total_delivery_fees': data['total_delivery_fees'],
                'total_orders': data['total_orders'],
                'state': 'draft'
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