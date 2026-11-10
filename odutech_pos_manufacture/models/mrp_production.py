from odoo import fields, models


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    pos_order_id = fields.Many2one(
        'pos.order',
        string="POS Order",
        index=True,
        copy=False,
        readonly=True,
    )
    pos_order_line_id = fields.Many2one(
        'pos.order.line',
        string="POS Order Line",
        index=True,
        copy=False,
        readonly=True,
    )
