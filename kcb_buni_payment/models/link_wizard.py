from odoo import api, fields, models
from odoo.exceptions import UserError

from .buni_config import CHANNELS, PROVIDERS


class KcbBuniLinkWizard(models.TransientModel):
    _name = 'kcb.buni.link.wizard'
    _description = 'Generate a test payment link'

    config_id = fields.Many2one(
        'kcb.buni.config',
        string='Payment Method',
        required=True,
        domain=[('active', '=', True)],
        default=lambda self: self.env['kcb.buni.config'].search([('active', '=', True)], limit=1),
    )
    provider = fields.Selection(PROVIDERS, related='config_id.provider')
    payment_channel = fields.Selection(CHANNELS, string='Payment Channel', default='mpesa')
    phone_number = fields.Char(string='phoneNumber')
    amount = fields.Char(string='amount', required=True, default='1')
    transaction_description = fields.Char(string='transactionDescription', default='Test payment')

    @api.onchange('config_id')
    def _onchange_config_id(self):
        if self.provider == 'manual':
            self.payment_channel = False
            self.phone_number = False

    def action_generate(self):
        self.ensure_one()
        if not self.config_id:
            raise UserError('Create a payment method before generating a test payment link.')
        self.env['kcb.buni.invoice']._amount_text(self.amount)
        channel = False if self.provider == 'manual' else self.payment_channel
        phone = False if self.provider == 'manual' else self.phone_number
        if self.provider != 'manual':
            if not channel:
                raise UserError('Select M-Pesa, Airtel Money, or Card.')
            phone = self.env['kcb.buni.invoice']._normalize_phone(phone)
        invoice = self.env['kcb.buni.invoice'].create({
            'config_id': self.config_id.id,
            'payment_channel': channel,
            'phone_number': phone,
            'amount': self.amount,
            'transaction_description': self.transaction_description,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': invoice.invoice_number,
            'res_model': 'kcb.buni.invoice',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }
