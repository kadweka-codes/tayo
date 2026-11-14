from odoo import api, fields, models, release,_
from odoo.exceptions import UserError
import logging
import requests

ODUTECH_AUTHORIZATION_PORTAL_API = "https://odoogrid.com/api/enterprise-suit/authorize"
ODUTECH_DOMAINS_API = "https://odoogrid.com/api/enterprise-suit/domains"
ODUTECH_DOMAINS_VERIFY_API = "https://odoogrid.com/api/enterprise-suit/domains/verify"
_logger = logging.getLogger(__name__)


def normalize_custom_domain(domain):
    domain = (domain or '').strip().lower()
    for prefix in ('https://', 'http://'):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split('/')[0].strip().rstrip('.')
    if domain and (' ' in domain or '.' not in domain):
        raise UserError(_("Enter a domain such as portal.example.com."))
    return domain

class OdutechPortalCompany(models.Model):
    _name = 'odutech.portal.company'
    _description = 'Portal Company Setup'
    _order = 'company_name, id'
    _rec_name = 'company_name'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        ondelete='restrict',
        index=True,
    )
    company_name = fields.Char(string='Company Name', required=True, readonly=True)
    email = fields.Char(string='Email', readonly=True)
    theme = fields.Char(string='Theme', readonly=True)
    country_id = fields.Many2one('res.country', string='Country', readonly=True)
    city = fields.Char(string='City', readonly=True)
    odoo_erp_link = fields.Char(string='Odoo ERP Link', readonly=True)
    mobile = fields.Char(string='Mobile', readonly=True)
    employee_count = fields.Integer(string='Employee Count', readonly=True)
    billing_period = fields.Selection(
        selection=[
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        string='Billing Period',
        default='yearly',
        required=True,
        readonly=True,
    )
    allow_employee_portal = fields.Boolean(string='Allow Employee Portal', readonly=True)
    employee_portal_url = fields.Char(string='Employee Portal URL', readonly=True)
    odoo_version = fields.Char(string='Odoo Version', readonly=True)
    amount_payable = fields.Monetary(string='Amount Payable', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    client_key = fields.Char(string='Client Key', copy=False)
    client_secret = fields.Char(string='Client Secret', copy=False)
    subscription_type = fields.Char(
        string='Subscription Type',
        readonly=True,
        copy=False,
    )
    portal_subscription_code = fields.Char(
        string='Portal Subscription Code',
        readonly=True,
        copy=False,
    )
    authorization_token = fields.Char(
        string='Authorization Token',
        readonly=True,
        copy=False,
    )
    subscription_expiry = fields.Date(string='Subscription Expiry', readonly=True)
    login_code = fields.Char(string='Login Portal Code', readonly=True, copy=False)
    has_custom_domain = fields.Boolean(string='Has Custom Domain', readonly=True)
    custom_domain = fields.Char(string='Custom Domain', copy=False)
    dns_verified = fields.Boolean(string='DNS Verified', copy=False)
    domain_check_message = fields.Char(string='DNS status', readonly=True, copy=False)
    domain_record_ids = fields.One2many(
        'odutech.portal.domain.record',
        'setup_id',
        string='DNS records',
    )
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('connected', 'Connected'),
            ('expired', 'Expired'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    auto_create_bill = fields.Boolean(string='Auto-create a bill')
    invoice_ids = fields.One2many(
        'odutech.portal.invoice',
        'setup_id',
        string='Invoices',
    )

    _company_setup_unique = models.Constraint(
        'unique (company_id)',
        'This company already has a portal setup.',
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id
        if not company:
            return
        self.company_name = company.name
        self.email = company.email
        self.country_id = company.country_id
        self.city = company.city
        self.mobile = company.phone
        self.employee_count = self.env['hr.employee'].search_count([
            ('company_id', '=', company.id),
            ('active', '=', True),
        ])
        self.odoo_erp_link = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        self.odoo_version = release.series

    def portal_base_url(self):
        self.ensure_one()
        return (self.odoo_erp_link or self.employee_portal_url or '').strip().rstrip('/')

    def portal_license_message(self):
        """Return a block message when the subscription is expired or over the paid seats."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.status == 'expired' or (self.subscription_expiry and self.subscription_expiry < today):
            return _("Subscription has expired.")
        paid_employees = self.employee_count or 0
        self.env.cr.execute(
            """
            SELECT count(*)
              FROM hr_employee
             WHERE company_id = %s
               AND active IS TRUE
            """,
            [self.company_id.id],
        )
        active_employees = self.env.cr.fetchone()[0]
        if active_employees > paid_employees:
            return _("License employee limit is reached.")
        return None

    def action_configure_custom_domain(self):
        self.ensure_one()
        if self.status != 'connected' or self.dns_verified:
            raise UserError(_("The custom domain wizard is not available."))
        wizard = self.env['odutech.employee.domain.wizard'].create({
            'setup_id': self.id,
            'custom_domain': self.custom_domain or '',
        })
        if self.custom_domain:
            wizard.action_fetch_dns()
        return wizard._reopen()

    def _post_domain_api(self, url, domain):
        self.ensure_one()
        token = (self.authorization_token or '').strip()
        if not token:
            raise UserError(_("Connect to the portal before adding a custom domain."))
        payload = {'token': token, 'domain': domain}
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Bearer %s' % token,
            'X-License-Token': token,
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            response.raise_for_status()
            result = response.json()
        except requests.exceptions.RequestException as error:
            message = str(error)
            response = getattr(error, 'response', None)
            if response is not None:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                message = body.get('error') or 'Status %s: %s' % (response.status_code, response.text)
            raise UserError(_("Custom domain request failed: %s") % message) from error
        except ValueError as error:
            raise UserError(_("Custom domain request returned an unreadable response.")) from error
        if not isinstance(result, dict):
            raise UserError(_("Custom domain request returned an unexpected response."))
        if result.get('error'):
            raise UserError(_("Custom domain request failed: %s") % result['error'])
        return result

    def _apply_domain_api_result(self, result, fallback_domain):
        self.ensure_one()
        domain = (result.get('domain') or fallback_domain or '').strip().lower()
        verified = bool(result.get('verified'))
        records = result.get('records')
        organization = result.get('organization') if isinstance(result.get('organization'), dict) else {}
        portal_url = result.get('employeePortalUrl') or organization.get('employeePortalUrl')
        if verified and domain and not (isinstance(portal_url, str) and portal_url.strip()):
            portal_url = 'https://%s' % domain
        vals = {
            'custom_domain': domain or False,
            'dns_verified': verified,
            'domain_check_message': (
                _("DNS records are verified.")
                if verified else
                _("DNS is not verified yet. Add every record at your DNS provider, then click Validate.")
            ),
        }
        if verified and isinstance(portal_url, str) and portal_url.strip():
            vals['employee_portal_url'] = portal_url.strip()
            vals['domain_check_message'] = _(
                "DNS records are verified. Employee Portal URL is now %s."
            ) % vals['employee_portal_url']
        if isinstance(records, list):
            commands = [(5, 0, 0)]
            for record in records:
                if not isinstance(record, dict):
                    continue
                commands.append((0, 0, {
                    'domain': domain,
                    'record_type': record.get('type') or '',
                    'host': record.get('host') or '',
                    'dns_name': record.get('name') or '',
                    'value': record.get('value') or '',
                    'verified': bool(record.get('verified', verified)),
                }))
            vals['domain_record_ids'] = commands
        self.write(vals)
        if not isinstance(records, list):
            self.domain_record_ids.write({'verified': verified})

    def action_fetch_custom_domain(self, domain):
        self.ensure_one()
        domain = normalize_custom_domain(domain)
        if not domain:
            raise UserError(_("Enter a domain such as portal.example.com."))
        if self.dns_verified:
            raise UserError(_("DNS is already verified, so the custom domain can no longer be changed."))
        result = self._post_domain_api(ODUTECH_DOMAINS_API, domain)
        self._apply_domain_api_result(result, domain)
        return result

    def action_validate_custom_domain(self):
        self.ensure_one()
        if self.dns_verified:
            raise UserError(_("DNS is already verified."))
        domain = normalize_custom_domain(self.custom_domain)
        if not domain:
            raise UserError(_("Add a custom domain first."))
        result = self._post_domain_api(ODUTECH_DOMAINS_VERIFY_API, domain)
        self._apply_domain_api_result(result, domain)
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def authorize_enterprise_suite(self):
        """Portal connection. Logic is intentionally empty for now."""
        self.ensure_one()
        for es in self:
            if not es.client_key or not es.client_secret:
                raise UserError(
                    _("Client Key and Client Secret are required for authorization.")
                )
            payload = {
                "clientId": es.client_key,
                "clientSecret": es.client_secret,
                "taxId": "",
                "street": es.company_id.street,
                "street2": es.company_id.street2,
                "zip": es.company_id.zip,
                "website": es.company_id.website,
                "social": {
                    "xAccount": "odutech",
                    "facebookAccount": "odutech",
                    "githubAccount": "odutech",
                    "linkedinAccount": getattr(es.company_id, 'social_twitter', False),
                    "youtubeAccount": getattr(es.company_id, 'social_youtube', False),
                    "instagramAccount": "odutech",
                    "tiktokAccount": "odutech",
                    "discordAccount": "254754625698"
                }
            }
            headers = {
                "Content-Type": "application/json",
                "X-Client-Id": es.client_key,
                "X-Client-Secret": es.client_secret,
            }
            try:
                response = requests.post(
                    ODUTECH_AUTHORIZATION_PORTAL_API, json=payload, headers=headers, timeout=15
                )
                # Raise for status first (throws an exception on 4xx/5xx errors)
                response.raise_for_status()

                # Parse the JSON response into a dictionary
                result = response.json()

                _logger.error(f"Authorization portal api response {response.text}")

                # Extract nested organization data safely
                org_data = result.get("organization") or {}
                _logger.error(f"ORGANIZATION DATA {response.text}")
                company_code = result.get("companyCode") or org_data.get("companyCode")

                # Write the returned values to the Odoo record fields
                es.with_context(odutech_portal_system_write=True).write({
                    "authorization_token": result.get("token"),
                    "subscription_expiry": result.get("expiresAt"),
                    "portal_subscription_code": org_data.get("subscriptionCode"),
                    "status": "connected",
                    "login_code": company_code or False,
                    "subscription_type": org_data.get("plan"),
                })
                return {
                    "type": "ir.actions.client",
                    "tag": "reload",
                }

            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                if hasattr(e, "response") and e.response is not None:
                    error_msg = f"Status {e.response.status_code}: {e.response.text}"
                raise UserError(_("Failed to connect to authorization portal: %s") % error_msg)


    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('odutech_portal_system_write'):
            vals_list = [
                {
                    key: value
                    for key, value in vals.items()
                    if key not in ('login_code', 'has_custom_domain')
                }
                for vals in vals_list
            ]
        records = super().create(vals_list)
        records.filtered('auto_create_bill')._create_payable_invoice()
        return records

    def write(self, vals):
        if not self.env.context.get('odutech_portal_system_write'):
            vals = {
                key: value
                for key, value in vals.items()
                if key not in ('login_code', 'has_custom_domain')
            }
        result = super().write(vals)
        if vals.get('auto_create_bill'):
            self.filtered('auto_create_bill')._create_payable_invoice()
        return result

    def _create_payable_invoice(self):
        invoices = self.env['odutech.portal.invoice']
        for setup in self:
            if setup.invoice_ids.filtered('auto_created'):
                continue
            invoices.create({
                'setup_id': setup.id,
                'amount': setup.amount_payable,
                'billing_period': setup.billing_period,
                'invoice_date': fields.Date.context_today(self),
                'state': 'payable',
                'auto_created': True,
            })


class OdutechPortalDomainRecord(models.Model):
    _name = 'odutech.portal.domain.record'
    _description = 'Portal DNS Record'
    _order = 'id'

    setup_id = fields.Many2one(
        'odutech.portal.company',
        string='Company Setup',
        required=True,
        ondelete='cascade',
        index=True,
    )
    domain = fields.Char(string='Domain', readonly=True)
    record_type = fields.Char(string='Type', readonly=True)
    host = fields.Char(string='Host', readonly=True)
    dns_name = fields.Char(string='Name', readonly=True)
    value = fields.Text(string='Value', readonly=True)
    verified = fields.Boolean(string='Verified', readonly=True)


class OdutechPortalInvoice(models.Model):
    _name = 'odutech.portal.invoice'
    _description = 'Portal Invoice'
    _order = 'invoice_date desc, id desc'
    _rec_name = 'name'

    setup_id = fields.Many2one(
        'odutech.portal.company',
        string='Company Setup',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='setup_id.company_id',
        store=True,
        readonly=True,
    )
    name = fields.Char(string='Number', required=True, copy=False, default='New')
    amount = fields.Monetary(string='Amount', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        related='setup_id.currency_id',
        store=True,
        readonly=True,
    )
    billing_period = fields.Selection(
        selection=[
            ('monthly', 'Monthly'),
            ('yearly', 'Yearly'),
        ],
        string='Billing Period',
        required=True,
    )
    invoice_date = fields.Date(string='Invoice Date', required=True, default=fields.Date.context_today)
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('payable', 'Payable'),
            ('paid', 'Paid'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    auto_created = fields.Boolean(string='Created automatically', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('odutech.portal.invoice') or 'New'
        return super().create(vals_list)
