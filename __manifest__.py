{
    'name': 'Food Delivery Integration',
    'version': '18.0.1.0.0',
    'category': 'Operations',
    'summary': 'Food delivery service integration with Odoo ERP',
    'description': """This module integrates a food delivery service with Odoo ERP""",
    'author': 'Sarah Juhain',
    'depends': [
        'base',
        'account',
        'contacts',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/system_parameters.xml',
        'data/account_data.xml',
        'data/cron_data.xml',
        'views/settlement_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
