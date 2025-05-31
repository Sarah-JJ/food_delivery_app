from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class DeliveryFeeCalculation(models.Model):
    _name = 'food.delivery.fee.calculation'
    _description = 'Delivery Fee Calculation'
    _order = 'calculation_date desc'

    external_order_id = fields.Integer('External Order ID', index=True)
    distance_km = fields.Float('Distance (km)', required=True, digits=(8, 2))
    delivery_fee = fields.Float('Delivery Fee', required=True, digits=(10, 2))
    company_share = fields.Float('Company Share', digits=(10, 2))
    courier_share = fields.Float('Courier Share', digits=(10, 2))
    courier_id = fields.Many2one('food.delivery.courier', 'Courier', required=True)
    calculation_date = fields.Datetime('Calculated At', default=fields.Datetime.now)
    high_volume_bonus = fields.Boolean('High Volume Bonus Applied')

    @api.model
    def calculate_delivery_fee(self, distance_km, courier_id):
        """Calculate delivery fee based on business rules"""

        # Distance-based fee calculation
        if distance_km < 5:
            base_fee = 2.0
        elif distance_km < 7:
            base_fee = 3.0
        else:
            base_fee = 5.0

        # Get courier record
        courier = self.env['food.delivery.courier'].browse(courier_id)
        if not courier.exists():
            raise ValueError(f"Courier {courier_id} not found")

        # Update courier delivery count
        courier.update_delivery_count()

        # Commission calculation with high-volume bonus
        if courier.high_volume_active:
            company_percentage = 35
            courier_percentage = 65
            high_volume_bonus = True
        else:
            company_percentage = 40
            courier_percentage = 60
            high_volume_bonus = False

        company_share = base_fee * (company_percentage / 100)
        courier_share = base_fee * (courier_percentage / 100)

        # Create calculation record
        calculation = self.create({
            'distance_km': distance_km,
            'delivery_fee': base_fee,
            'company_share': company_share,
            'courier_share': courier_share,
            'courier_id': courier_id,
            'high_volume_bonus': high_volume_bonus
        })

        _logger.info(
            f"Fee calculated: {base_fee} for {distance_km}km, courier {courier.display_name}, bonus: {high_volume_bonus}")

        return calculation

    def mark_order_delivered(self, external_order_id, order_total):
        """Mark calculation as delivered and create accounting entry"""
        self.external_order_id = external_order_id

        # Log the delivery completion
        _logger.info(f"Order {external_order_id} delivered, total: {order_total}")

        return True