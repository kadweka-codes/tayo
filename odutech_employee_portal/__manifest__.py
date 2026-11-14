{
    'name': 'EP.Portal',
    'version': '19.0.2.1.0',
    'category': 'Human Resources',
    'summary': 'Employee portal and company portal setup',
    'description': """
        Standalone portal app for employee access and company setup.
        Company connection, billing, and payable invoices live on their own tables.
        Portal users sign in to the API and can only edit their own employee record.
    """,
    'author': 'Odutech Solutions',
    'website': 'https://www.odutechsolutions.com',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_holidays',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/mail_template.xml',
        'views/portal_company_views.xml',
        'views/hr_employee_views.xml',
        'views/employee_domain_wizard_views.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
