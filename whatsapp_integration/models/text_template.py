from odoo import fields, models


class WhatsAppTextTemplate(models.Model):
    _name = 'whatsapp.text.template'
    _description = 'WhatsApp Text Message'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char(string='Template Code', required=True)
    send_to = fields.Selection([
        ('cook', 'Cook'),
        ('waiter', 'Waiter'),
    ], string='Send to', required=True, default='cook')
    body = fields.Text(string='Message', required=True)

    _code_unique = models.Constraint(
        'unique(code)',
        "The template code must be unique.",
    )
