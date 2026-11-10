from odoo import fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    manufacture_bom_products = fields.Boolean(
        string="Manufacture products with a BoM",
        default=True,
        help="When a POS order is paid, each product that has a manufacture "
             "bill of materials is produced immediately into the POS stock "
             "location, then the sale takes that quantity out.",
    )
