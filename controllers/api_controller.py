from odoo import http
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class FoodDeliveryAPIController(http.Controller):

    @http.route('/api/delivery/calculate_fee', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def calculate_delivery_fee(self, **kwargs):
        """Calculate delivery fee and commission split"""
        try:
            # Validate input parameters
            distance = kwargs.get('distance_km')
            courier_id = kwargs.get('courier_id')

            if not distance or not courier_id:
                return {'error': 'Missing required parameters: distance_km, courier_id'}

            distance = float(distance)
            courier_id = int(courier_id)

            if distance <= 0 or distance > 100:  # Maximum 100km delivery
                return {'error': 'Invalid distance value'}

            if courier_id <= 0:
                return {'error': 'Invalid courier ID'}

            # Find courier by external ID
            courier = request.env['food.delivery.courier'].sudo().search([
                ('external_courier_id', '=', courier_id)
            ], limit=1)

            if not courier:
                return {'error': f'Courier {courier_id} not found'}

            # Calculate fee
            fee_calc = request.env['food.delivery.fee.calculation'].sudo()
            result = fee_calc.calculate_delivery_fee(distance, courier.id)

            return {
                'success': True,
                'delivery_fee': result.delivery_fee,
                'company_share': result.company_share,
                'courier_share': result.courier_share,
                'calculation_id': result.id,
                'high_volume_bonus': result.high_volume_bonus
            }

        except ValueError as e:
            _logger.error(f"Validation error in calculate_delivery_fee: {e}")
            return {'error': 'Invalid input parameters'}
        except Exception as e:
            _logger.error(f"Error in calculate_delivery_fee: {e}")
            return {'error': 'Internal server error'}

    @http.route('/api/delivery/order_completed', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def order_completed(self, **kwargs):
        """Record order completion"""
        try:
            external_order_id = kwargs.get('external_order_id')
            calculation_id = kwargs.get('calculation_id')
            order_total = kwargs.get('order_total', 0)

            if not external_order_id or not calculation_id:
                return {'error': 'Missing required parameters: external_order_id, calculation_id'}

            external_order_id = int(external_order_id)
            calculation_id = int(calculation_id)
            order_total = float(order_total)

            # Update calculation with external order ID
            fee_calc = request.env['food.delivery.fee.calculation'].sudo().browse(calculation_id)
            if not fee_calc.exists():
                return {'error': f'Calculation {calculation_id} not found'}

            # Mark order as delivered
            fee_calc.mark_order_delivered(external_order_id, order_total)

            return {'success': True, 'message': 'Order marked as delivered'}

        except ValueError as e:
            _logger.error(f"Validation error in order_completed: {e}")
            return {'error': 'Invalid input parameters'}
        except Exception as e:
            _logger.error(f"Error in order_completed: {e}")
            return {'error': 'Internal server error'}

    @http.route('/api/delivery/courier/create', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def create_courier(self, **kwargs):
        """Create courier record"""
        try:
            external_courier_id = kwargs.get('external_courier_id')
            name = kwargs.get('name')
            phone = kwargs.get('phone')
            email = kwargs.get('email')

            if not external_courier_id or not name:
                return {'error': 'Missing required parameters: external_courier_id, name'}

            external_courier_id = int(external_courier_id)

            # Check if courier already exists
            existing_courier = request.env['food.delivery.courier'].sudo().search([
                ('external_courier_id', '=', external_courier_id)
            ], limit=1)

            if existing_courier:
                return {'error': f'Courier {external_courier_id} already exists'}

            # Create partner for courier
            partner = request.env['res.partner'].sudo().create_courier_partner(
                external_courier_id, name, phone, email
            )

            # Create courier record
            courier = request.env['food.delivery.courier'].sudo().create({
                'external_courier_id': external_courier_id,
                'partner_id': partner.id
            })

            return {
                'success': True,
                'courier_id': courier.id,
                'partner_id': partner.id,
                'message': f'Courier {name} created successfully'
            }

        except ValueError as e:
            _logger.error(f"Validation error in create_courier: {e}")
            return {'error': 'Invalid input parameters'}
        except Exception as e:
            _logger.error(f"Error in create_courier: {e}")
            return {'error': 'Internal server error'}

    @http.route('/api/delivery/restaurant/create', type='json', auth='public',
                methods=['POST'], csrf=False, cors='*')
    def create_restaurant(self, **kwargs):
        """Create restaurant record"""
        try:
            external_restaurant_id = kwargs.get('external_restaurant_id')
            name = kwargs.get('name')
            location_lat = kwargs.get('location_lat')
            location_lng = kwargs.get('location_lng')

            if not external_restaurant_id or not name:
                return {'error': 'Missing required parameters: external_restaurant_id, name'}

            external_restaurant_id = int(external_restaurant_id)

            # Check if restaurant already exists
            existing_restaurant = request.env['res.partner'].sudo().search([
                ('external_restaurant_id', '=', external_restaurant_id),
                ('partner_type', '=', 'restaurant')
            ], limit=1)

            if existing_restaurant:
                return {'error': f'Restaurant {external_restaurant_id} already exists'}

            # Create restaurant partner
            partner = request.env['res.partner'].sudo().create_restaurant_partner(
                external_restaurant_id, name, location_lat, location_lng
            )

            return {
                'success': True,
                'partner_id': partner.id,
                'message': f'Restaurant {name} created successfully'
            }

        except ValueError as e:
            _logger.error(f"Validation error in create_restaurant: {e}")
            return {'error': 'Invalid input parameters'}
        except Exception as e:
            _logger.error(f"Error in create_restaurant: {e}")
            return {'error': 'Internal server error'}

    @http.route('/api/delivery/health', type='http', auth='public',
                methods=['GET'], csrf=False, cors='*')
    def health_check(self):
        """Health check endpoint"""
        try:
            # Test database connection
            request.env['food.delivery.courier'].sudo().search_count([])

            return json.dumps({
                'status': 'healthy',
                'message': 'Food delivery API is operational',
                'timestamp': str(request.env.cr.now())
            })
        except Exception as e:
            _logger.error(f"Health check failed: {e}")
            return json.dumps({
                'status': 'unhealthy',
                'message': str(e)
            })