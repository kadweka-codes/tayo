from odoo import api, fields, models, _

CATEGORIES = [
    ('COST_OF_SALE_purchases', 'COST OF SALE(purchases)'),
    ('SALE_OF_GOODS_sales', 'SALE OF GOODS(sales)'),
    ('ADMINISTRATIVE_EXPENSES_Employee_cost', 'ADMINISTRATIVE EXPENSES'),
    ('GENERAL_ADMINISTRATIVE_COST', 'OPERATIONAL COST'),
    ('OTHER_ITEMS', 'OTHERS')
]


class AccountAccount(models.Model):
    _inherit = 'account.account'

    account_category = fields.Selection(CATEGORIES, string="Account Category", required=True, default='OTHER_ITEMS')


