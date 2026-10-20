{
    'name': 'Dilek Dummy Data',
    'summary': 'Sample products, employees, customers, and suppliers',
    'description': """
Loads sample records for a restaurant Point of Sale:
products available in POS, employees, customers, and suppliers.
""",
    'author': 'Odutech Solutions',
    'website': 'https://www.odutechsolutions.com',
    'category': 'Point of Sale',
    'version': '1.0.0',
    'depends': ['point_of_sale', 'hr', 'odutech_pos'],
    'data': [
        'data/pos_categories.xml',
        'data/products.xml',
        'data/employees.xml',
        'data/partners.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
}
