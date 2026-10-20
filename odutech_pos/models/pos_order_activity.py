from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PosOrder(models.Model):
    _name = 'pos.order'
    _inherit = ['pos.order', 'mail.thread', 'mail.activity.mixin']

    premier_wallet_number = fields.Char(string="Premier Wallet number")
    evc_plus_number = fields.Char(string="EVC Plus number")
    e_ahab_number = fields.Char(string="E-AHAB number")
    my_cash_number = fields.Char(string="MyCash number")
    t_plus_number = fields.Char(string="T-Plus number")
    e_besa = fields.Char(string="E-Besa Number")
    my_bank = fields.Char(string="My Bank")
    payment_confirmed = fields.Boolean(string="Payment Confirmed", tracking=True, default=False)
    transaction_matched = fields.Boolean(string="Transaction Matched", tracking=True, default=False, index=True)

    def confirm_payment_received(self):
        for rec in self:
            if rec.payment_confirmed:
                raise UserError(_("Payment has already been confirmed for order %s.") % rec.name)
            rec.write({"payment_confirmed": True})

    @api.model
    def get_pos_employee_info(self, order_id):
        order = self.search([
            '|', ('pos_reference', '=', order_id), ('name', '=', order_id),
        ], limit=1)
        if not order:
            return {}
        employee = order.employee_id if 'employee_id' in order._fields else self.env['hr.employee']
        if not employee and order.user_id:
            employee = self.env['hr.employee'].search([('user_id', '=', order.user_id.id)], limit=1)
        if not employee:
            return {}
        return employee.wallet_values()
