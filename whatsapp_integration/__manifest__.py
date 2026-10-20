{
    'name': "WhatsApp Communication",
    'author': 'Odutech Solutions',
    'category': 'Odutech',
    'company': 'Odutech Solutions',
    'maintainer': 'Odutech Solutions',
    'summary': 'WhatsApp templates for cooks, waiters, and floor alerts',
    'description': """
Sends WhatsApp template messages from the active configuration.
Restaurant order assignment and people-counting alerts call this module
instead of keeping their own tokens or HTTP clients.
""",
    'depends': ['point_of_sale', 'mail'],
    'data': [
        'security/whatsapp_security.xml',
        'data/text_templates.xml',
        'views/whatsapp_config.xml',
        'views/text_template_views.xml',
        'views/menu_actions.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
