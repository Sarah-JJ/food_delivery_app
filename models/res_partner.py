from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Partner type for food delivery
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('restaurant', 'Restaurant'),
        ('courier', 'Courier')
    ], string='Partner Type')

    # External system IDs
    external_customer_id = fields.Integer('External Customer ID', index=True)
    external_restaurant_id = fields.Integer('External Restaurant ID', index=True)
    external_courier_id = fields.Integer('External Courier ID', index=True)

    # Location data
    location_lat = fields.Float('Latitude', digits=(10, 6))
    location_lng = fields.Float('Longitude', digits=(10, 6))

    # Restaurant specific fields
    restaurant_name = fields.Char('Restaurant Name')
    cuisine_type = fields.Char('Cuisine Type')

    # Courier specific fields
    courier_phone = fields.Char('Courier Phone')
    vehicle_type = fields.Selection([
        ('bike', 'Bicycle'),
        ('motorcycle', 'Motorcycle'),
        ('car', 'Car'),
        ('scooter', 'Scooter')
    ], string='Vehicle Type')

    settlement_ids = fields.One2many('food.delivery.settlement', 'partner_id', 'Settlements')

    @api.model
    def create_courier_partner(self, external_courier_id, name, phone=None, email=None):
        """Create partner for courier"""
        partner = self.create({
            'name': name,
            'phone': phone,
            'email': email,
            'partner_type': 'courier',
            'external_courier_id': external_courier_id,
            'supplier_rank': 1,  # Set as supplier for vendor bills
            'is_company': True,
        })
        return partner

    @api.model
    def create_restaurant_partner(self, external_restaurant_id, name, location_lat=None, location_lng=None):
        """Create partner for restaurant"""
        partner = self.create({
            'name': name,
            'restaurant_name': name,
            'partner_type': 'restaurant',
            'external_restaurant_id': external_restaurant_id,
            'location_lat': location_lat,
            'location_lng': location_lng,
            'supplier_rank': 1,  # Set as supplier for vendor bills
            'is_company': True,
        })
        return partner

    @api.model
    def create_customer_partner(self, external_customer_id, name, email=None, phone=None):
        """Create partner for customer"""
        partner = self.create({
            'name': name,
            'email': email,
            'phone': phone,
            'partner_type': 'customer',
            'external_customer_id': external_customer_id,
            'customer_rank': 1,  # Set as customer
        })
        return partner

    def get_settlement_summary(self):
        """Get settlement summary for partner"""
        if self.partner_type == 'courier':
            settlements = self.settlement_ids.filtered(lambda s: s.partner_type == 'courier')
            total_amount = sum(settlements.mapped('total_amount_due'))
            total_deliveries = sum(settlements.mapped('total_orders'))
            return {
                'total_settlements': len(settlements),
                'total_amount': total_amount,
                'total_deliveries': total_deliveries,
                'avg_per_delivery': total_amount / total_deliveries if total_deliveries else 0
            }
        elif self.partner_type == 'restaurant':
            settlements = self.settlement_ids.filtered(lambda s: s.partner_type == 'restaurant')
            total_orders = sum(settlements.mapped('total_orders'))
            total_amount = sum(settlements.mapped('total_amount_due'))
            return {
                'total_settlements': len(settlements),
                'total_orders': total_orders,
                'total_amount': total_amount,
                'avg_per_order': total_amount / total_orders if total_orders else 0
            }
        return {}