from odoo import models, fields, api
from datetime import datetime, timedelta


class FoodDeliveryCourier(models.Model):
    _name = 'food.delivery.courier'
    _description = 'Delivery Courier'
    _rec_name = 'display_name'

    external_courier_id = fields.Integer('External Courier ID', required=True, index=True)
    partner_id = fields.Many2one('res.partner', 'Courier Contact', required=True)
    display_name = fields.Char('Name', compute='_compute_display_name', store=True)

    # Performance tracking
    active_deliveries_today = fields.Integer('Deliveries Today', default=0)
    hourly_delivery_count = fields.Integer('Deliveries This Hour', default=0)
    last_delivery_hour = fields.Datetime('Last Delivery Time')
    high_volume_active = fields.Boolean('High Volume Bonus Active', default=False)

    # Settlement tracking
    settlement_ids = fields.One2many('food.delivery.courier.settlement', 'courier_id', 'Settlements')
    total_settlements = fields.Integer('Total Settlements', compute='_compute_totals')
    total_amount_paid = fields.Float('Total Amount Paid', compute='_compute_totals')

    @api.depends('partner_id.name', 'external_courier_id')
    def _compute_display_name(self):
        for record in self:
            if record.partner_id:
                record.display_name = f"{record.partner_id.name} (#{record.external_courier_id})"
            else:
                record.display_name = f"Courier #{record.external_courier_id}"

    @api.depends('settlement_ids')
    def _compute_totals(self):
        for record in self:
            record.total_settlements = len(record.settlement_ids)
            record.total_amount_paid = sum(record.settlement_ids.mapped('total_amount_due'))

    def update_delivery_count(self):
        """Update courier delivery statistics for commission calculation"""
        current_hour = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)

        if self.last_delivery_hour and self.last_delivery_hour.replace(minute=0, second=0,
                                                                       microsecond=0) == current_hour:
            self.hourly_delivery_count += 1
        else:
            self.hourly_delivery_count = 1

        self.last_delivery_hour = fields.Datetime.now()
        self.active_deliveries_today += 1

        # Activate high volume bonus if threshold exceeded
        if self.hourly_delivery_count > 5:
            self.high_volume_active = True

    def reset_daily_counts(self):
        """Reset daily delivery counts - called by cron"""
        self.write({
            'active_deliveries_today': 0,
            'hourly_delivery_count': 0,
            'high_volume_active': False,
        })

    @api.model
    def reset_all_daily_counts(self):
        """Reset all courier daily counts"""
        couriers = self.search([])
        couriers.reset_daily_counts()