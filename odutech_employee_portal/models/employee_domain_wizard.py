from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .portal_company import normalize_custom_domain


class EmployeeDomainWizard(models.TransientModel):
    _name = 'odutech.employee.domain.wizard'
    _description = 'Configure Custom Domain'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        readonly=True,
    )
    setup_id = fields.Many2one(
        'odutech.portal.company',
        string='Company Setup',
        readonly=True,
    )
    custom_domain = fields.Char(string='Custom Domain')
    domain_check_message = fields.Char(related='setup_id.domain_check_message', readonly=True)
    dns_verified = fields.Boolean(related='setup_id.dns_verified', readonly=True)
    line_ids = fields.One2many(
        'odutech.employee.domain.wizard.line',
        'wizard_id',
        string='DNS records',
    )
    has_dns_records = fields.Boolean(compute='_compute_has_dns_records')

    @api.depends('line_ids')
    def _compute_has_dns_records(self):
        for wizard in self:
            wizard.has_dns_records = bool(wizard.line_ids)

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add custom domain'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _reload_lines(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.write({
            'custom_domain': self.setup_id.custom_domain,
            'line_ids': [
                (0, 0, {
                    'record_type': record.record_type,
                    'host': record.host,
                    'dns_name': record.dns_name,
                    'value': record.value,
                    'verified': record.verified,
                })
                for record in self.setup_id.domain_record_ids
            ],
        })

    def action_fetch_dns(self):
        self.ensure_one()
        if not self.setup_id:
            raise UserError(_("Choose a company setup before requesting DNS records."))
        self.setup_id.action_fetch_custom_domain(self.custom_domain)
        self._reload_lines()
        return self._reopen()

    def action_validate_dns(self):
        self.ensure_one()
        if not self.setup_id:
            raise UserError(_("Choose a company setup before validating DNS."))
        domain = normalize_custom_domain(self.custom_domain)
        if domain != (self.setup_id.custom_domain or ''):
            raise UserError(_("Save the domain first so the DNS records can be created."))
        action = self.setup_id.action_validate_custom_domain()
        if self.setup_id.dns_verified:
            return action
        self._reload_lines()
        return self._reopen()

    def action_save(self):
        self.ensure_one()
        if not self.setup_id:
            raise UserError(_("Choose a company setup before saving the domain."))
        return self.action_fetch_dns()


class EmployeeDomainWizardLine(models.TransientModel):
    _name = 'odutech.employee.domain.wizard.line'
    _description = 'Custom Domain DNS Record'

    wizard_id = fields.Many2one(
        'odutech.employee.domain.wizard',
        required=True,
        ondelete='cascade',
    )
    record_type = fields.Char(string='Type', readonly=True)
    host = fields.Char(string='Host', readonly=True)
    dns_name = fields.Char(string='Name', readonly=True)
    value = fields.Text(string='Value', readonly=True)
    verified = fields.Boolean(string='Verified', readonly=True)
