{
    'name': 'Dilek Restaurant Operations',
    'description': """
Restaurant floor operations: assign orders to cooks and waiters, track prep and
service delays, pull the people counter, and match n8n mobile-money payments to
POS orders. WhatsApp messages are sent by the WhatsApp Communication module.
""",
    'summary': 'Order assignment, IoT people counting, and n8n payment matching',
    'category': 'Point Of Sale',
    'version': '19.0.1.3.0',
    'author': 'Odutech Solutions',
    'company': 'Odutech Solutions',
    'maintainer': 'Odutech Solutions',
    'website': "https://www.odutechsolutions.com",
    'depends': ['point_of_sale', 'pos_restaurant', 'whatsapp_integration', 'hr', 'hr_attendance', 'mail'],
    'assets': {
        'point_of_sale._assets_pos': [
            'odutech_pos/static/src/css/style.css',
            'odutech_pos/static/src/js/odutech_order_receipt.js',
            'odutech_pos/static/src/js/BillReceiptScreen.js',
            'odutech_pos/static/src/js/PaymentScreen.js',
            'odutech_pos/static/src/xml/odutech_order_receipt.xml',
            'odutech_pos/static/src/xml/odutech_pos_ticket_screen.xml'
        ],
    },
    'data': [
        'security/security.xml',
        'views/pos_order.xml',
        'views/n8n_view.xml',
        'views/pos_order_extend.xml',
        'views/extend_config.xml',
        'views/employee_views.xml',
        'views/restaurant_table_views.xml',
        'data/ir_sequence.xml',
        'data/cron_jobs.xml',
        'views/iot_config_views.xml'
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': False,
}
