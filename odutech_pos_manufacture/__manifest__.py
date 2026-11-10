{
    'name': 'POS Manufacture on Payment',
    'summary': 'Complete a manufacturing order when a paid POS product has a bill of materials',
    'description': """
When a Point of Sale order is paid, each product line that has a manufacture
bill of materials is produced into the POS stock location before the sale is
delivered. Cooked meals and other manufactured products therefore leave stock
as finished goods instead of going negative.

See README.md in this module for setup and daily use.
""",
    'category': 'Point Of Sale',
    'version': '19.0.1.0.0',
    'author': 'Odutech Solutions',
    'company': 'Odutech Solutions',
    'maintainer': 'Odutech Solutions',
    'website': 'https://www.odutechsolutions.com',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'mrp',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
