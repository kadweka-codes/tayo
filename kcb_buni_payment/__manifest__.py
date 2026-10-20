{
    'name': 'KCB Buni Payments',
    'summary': 'Test payment links for KCB Buni M-Pesa, Airtel Money, and card',
    'description': """
Admin test desk for payment methods that have a KCB Buni integration.
Generate a test payment link together with a dummy invoice. The invoice can be
deleted after the test. Sections and columns follow the KCB Mpesa STK Push
specification.
""",
    'author': 'Odutech Solutions',
    'website': 'https://www.odutechsolutions.com',
    'category': 'Accounting',
    'version': '1.0.0',
    'depends': ['base', 'mail'],
    'data': [
        'security/ir.model.access.xml',
        'data/sequence.xml',
        'views/buni_config_views.xml',
        'views/buni_invoice_views.xml',
        'views/link_wizard_views.xml',
        'views/payment_link_templates.xml',
        'views/menus.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
}
