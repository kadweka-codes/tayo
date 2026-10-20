from odoo import models, fields, api
import secrets

class ResUsers(models.Model):
    _inherit = 'res.users'

    access_token = fields.Char(string="Access Token", readonly=True)

    def generate_access_token(self):
        """Generate and assign a new access token."""
        self.access_token = secrets.token_urlsafe(54)