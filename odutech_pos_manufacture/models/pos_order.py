import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    manufacturing_order_ids = fields.One2many(
        'mrp.production',
        'pos_order_id',
        string="Manufacturing Orders",
        readonly=True,
    )
    manufacturing_order_count = fields.Integer(compute='_compute_manufacturing_order_count')

    @api.depends('manufacturing_order_ids')
    def _compute_manufacturing_order_count(self):
        for order in self:
            order.manufacturing_order_count = len(order.manufacturing_order_ids)

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        self._create_pos_manufacturing_orders()
        return res

    def action_view_manufacturing_orders(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manufacturing Orders'),
            'res_model': 'mrp.production',
            'view_mode': 'list,form',
            'domain': [('pos_order_id', '=', self.id)],
            'context': {'create': False},
        }

    def _create_pos_manufacturing_orders(self):
        """Produce every sold product that has a manufacture bill of materials.

        The manufacturing order is completed before the POS delivery is created,
        so the finished meal is in the POS location when the sale leaves stock.
        """
        for order in self:
            if not order.config_id.manufacture_bom_products or order.is_refund:
                continue
            lines = order.lines.filtered(
                lambda line: line.qty > 0 and not line.manufacturing_order_id and line.product_id
            )
            if not lines:
                continue
            boms = self.env['mrp.bom']._bom_find(
                lines.product_id,
                company_id=order.company_id.id,
                bom_type='normal',
            )
            warehouse, location = order._pos_manufacturing_stock()
            if not warehouse.manu_type_id:
                raise UserError(_(
                    "Point of Sale %(pos)s cannot manufacture %(order)s because warehouse "
                    "%(warehouse)s has no manufacturing operation type.",
                    pos=order.config_id.display_name,
                    order=order.name,
                    warehouse=warehouse.display_name,
                ))
            for line in lines:
                bom = boms.get(line.product_id)
                if not bom:
                    continue
                order._produce_pos_line(line, bom, warehouse, location)

    def _pos_manufacturing_stock(self):
        self.ensure_one()
        picking_type = self.config_id.picking_type_id
        warehouse = picking_type.warehouse_id
        if not warehouse:
            raise UserError(_(
                "Point of Sale %(pos)s has no warehouse on its operation type, "
                "so %(order)s cannot create a manufacturing order.",
                pos=self.config_id.display_name,
                order=self.name,
            ))
        location = picking_type.default_location_src_id or warehouse.lot_stock_id
        if not location:
            raise UserError(_(
                "Point of Sale %(pos)s has no source location, so %(order)s cannot "
                "create a manufacturing order.",
                pos=self.config_id.display_name,
                order=self.name,
            ))
        return warehouse, location

    def _produce_pos_line(self, line, bom, warehouse, location):
        self.ensure_one()
        production = self.env['mrp.production'].sudo().with_company(self.company_id).create({
            'product_id': line.product_id.id,
            'bom_id': bom.id,
            'picking_type_id': warehouse.manu_type_id.id,
            'company_id': self.company_id.id,
            'origin': self.name,
            'pos_order_id': self.id,
            'pos_order_line_id': line.id,
        })
        production.write({
            'product_qty': line.qty,
            'location_src_id': location.id,
            'location_dest_id': location.id,
        })
        self._complete_pos_manufacturing_order(production)
        line.manufacturing_order_id = production.id
        _logger.info(
            "POS order %s produced %s x %s on %s",
            self.name, line.qty, line.product_id.display_name, production.name,
        )

    def _complete_pos_manufacturing_order(self, production):
        if production.product_tracking == 'serial' and production.product_qty != 1:
            raise UserError(_(
                "%(product)s is tracked by serial number. Sell it one unit at a time "
                "so the POS can finish manufacturing order %(mo)s.",
                product=production.product_id.display_name,
                mo=production.name,
            ))
        production.action_confirm()
        if production.product_tracking in ('lot', 'serial') and not production.lot_producing_ids:
            production.action_generate_serial()
        production.qty_producing = production.product_qty
        production.with_context(
            skip_consumption=True,
            skip_backorder=True,
            skip_redirection=True,
        ).button_mark_done()
        if production.state != 'done':
            raise UserError(_(
                "Manufacturing order %(mo)s for %(product)s could not be completed.",
                mo=production.name,
                product=production.product_id.display_name,
            ))


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    manufacturing_order_id = fields.Many2one(
        'mrp.production',
        string="Manufacturing Order",
        copy=False,
        readonly=True,
    )
