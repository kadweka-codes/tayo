import json
import logging
import secrets

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class WhatsAppConfig(models.Model):
    _name = 'whatsapp.config'
    _description = 'WhatsApp Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'base_url'

    active = fields.Boolean(default=False)
    type = fields.Selection([
        ('sandbox', 'Sandbox'),
        ('production', 'Production'),
    ], string='Type', default='sandbox', required=True, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('connected', 'Connected'),
        ('error', 'Error'),
    ], default='draft', required=True, copy=False, tracking=True)
    state_message = fields.Text(string='Status', readonly=True, copy=False)
    base_url = fields.Char(string="Messages URL")
    token = fields.Char(string="WhatsApp Token")
    webhook_token = fields.Char(string="Verification Token", copy=False)
    webhook_url = fields.Char(string="Webhook URL", compute='_compute_webhook_url')
    test_phone = fields.Char(string="Test Phone")
    test_message = fields.Text(string="Custom Message")
    language_code = fields.Char(string="Template Language", default='en_US', required=True)
    log_ids = fields.One2many('whatsapp.message', 'config_id', string='Logs')

    @api.depends()
    def _compute_webhook_url(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        for config in self:
            config.webhook_url = '%s/whatsapp/webhook' % base if base else '/whatsapp/webhook'

    def action_generate_verification_token(self):
        for config in self:
            config.write({'webhook_token': secrets.token_urlsafe(32)})
            config.message_post(
                body='Verification token generated. It does not expire until you generate another one.',
                subtype_xmlid='mail.mt_note',
            )
        return True

    def send_custom_message(self, phone, message):
        self.ensure_one()
        text = (message or '').strip()
        if not text or not phone:
            return False
        sent = self._send_custom_text(phone, text)
        self.message_post(
            body='Custom message %s to %s.\n%s' % ('waiting for confirmation' if sent else 'failed', phone, text),
            subtype_xmlid='mail.mt_note',
        )
        return sent

    def log_incoming_message(self, phone, message, raw):
        self.ensure_one()
        self._log(phone, 'incoming', 'received', (raw or '')[:500], body=message)
        self.message_post(
            body='Incoming message from %s.\n%s' % (phone or 'unknown', message or ''),
            subtype_xmlid='mail.mt_note',
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered('active')._deactivate_other_configs()
        return records

    def write(self, vals):
        vals = dict(vals)
        if any(key in vals for key in ('base_url', 'token', 'type')) and 'state' not in vals:
            vals['state'] = 'draft'
            vals['state_message'] = False
        res = super().write(vals)
        if vals.get('active'):
            self.filtered('active')._deactivate_other_configs()
        return res

    def action_test_authentication(self):
        for config in self:
            config._test_authentication()
        return True

    def action_test_messaging(self):
        for config in self:
            config._test_messaging()
        return True

    def action_reset_to_draft(self):
        records = self.filtered(lambda config: config.state == 'error')
        records.write({
            'state': 'draft',
            'state_message': False,
        })
        for config in records:
            config.message_post(body='Reset to draft.', subtype_xmlid='mail.mt_note')
        return True

    def action_go_to_production(self):
        records = self.filtered(lambda config: config.type == 'sandbox')
        records.write({
            'type': 'production',
            'state': 'draft',
            'state_message': 'Switched to production. Set the live messages URL and token, then test authentication.',
        })
        for config in records:
            config.message_post(
                body='Switched to production. Set the live messages URL and token, then test authentication.',
                subtype_xmlid='mail.mt_note',
            )
        return True

    def _test_authentication(self):
        self.ensure_one()
        if not self.base_url or not self.token:
            self.write({
                'state_message': 'Set the messages URL and token before testing authentication.',
            })
            self._log('', 'authentication', 'failed', 'Set the messages URL and token before testing authentication.', is_test=True)
            return
        headers = {'Authorization': 'Bearer %s' % self.token}
        try:
            response = requests.get(self._auth_url(), headers=headers, timeout=8)
        except requests.RequestException as error:
            _logger.warning("WhatsApp authentication failed: %s", error)
            self.write({
                'state': 'error',
                'state_message': str(error),
            })
            self._log('', 'authentication', 'failed', str(error), is_test=True)
            return
        body = (response.text or '')[:500]
        if response.ok:
            self.write({
                'state': 'connected',
                'state_message': 'Authentication succeeded.',
            })
            self._log('', 'authentication', 'sent', 'Authentication succeeded.', is_test=True)
            return
        detail = body or 'Authentication failed (%s).' % response.status_code
        self.write({
            'state': 'error',
            'state_message': detail,
        })
        self._log('', 'authentication', 'failed', detail, is_test=True)

    def _test_messaging(self):
        self.ensure_one()
        if not self.test_phone:
            detail = 'Set a test phone number, then test messaging again.'
            self.write({'state_message': detail})
            self._log('', 'text', 'failed', detail, body=self.test_message, is_test=True)
            return
        message = (self.test_message or '').strip()
        if not message:
            detail = 'Write a custom message, then test messaging again.'
            self.write({'state_message': detail})
            self._log(self.test_phone, 'text', 'failed', detail, is_test=True)
            return
        sent = self._send_custom_text(self.test_phone, message, is_test=True)
        if sent:
            self.write({
                'state': 'connected',
                'state_message': 'Waiting for WhatsApp to confirm the message.',
            })
            return
        last = self.env['whatsapp.message'].sudo().search([('config_id', '=', self.id)], limit=1)
        self.write({
            'state': 'error',
            'state_message': (last.response if last else '') or 'Test message failed.',
        })

    def _auth_url(self):
        self.ensure_one()
        url = (self.base_url or '').strip().rstrip('/')
        if url.endswith('/messages'):
            url = url[:-len('/messages')]
        if '?' not in url:
            url = '%s?fields=id,display_phone_number,verified_name' % url
        return url

    def _deactivate_other_configs(self):
        if not self:
            return
        others = self.search([('id', 'not in', self.ids), ('active', '=', True)])
        if others:
            others.write({'active': False})

    @api.model
    def send_template(self, phone, template_name, language_code=None):
        config = self.search([('active', '=', True), ('state', '=', 'connected')], limit=1)
        if not config:
            _logger.warning("WhatsApp template %s skipped: no connected configuration", template_name)
            return False
        return config._post_template(phone, template_name, language_code or config.language_code)

    @api.model
    def send_text(self, phone, message):
        config = self.search([('active', '=', True), ('state', '=', 'connected')], limit=1)
        if not config:
            _logger.warning("WhatsApp text skipped: no connected configuration")
            return False
        return config._send_custom_text(phone, message or '')

    def _send_custom_text(self, phone, message, is_test=False):
        self.ensure_one()
        text = (message or '').strip()
        return self._post_payload(self._normalize_phone(phone), {
            "messaging_product": "whatsapp",
            "to": self._normalize_phone(phone),
            "type": "text",
            "text": {"body": text},
        }, template_name='text', body=text, is_test=is_test)

    def _post_template(self, phone, template_name, language_code):
        self.ensure_one()
        normalized = self._normalize_phone(phone)
        if not normalized or not template_name:
            self._log(normalized, template_name, 'failed', 'Missing phone or template')
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": normalized,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code or self.language_code or 'en_US'},
            },
        }
        return self._post_payload(normalized, payload, template_name)

    def _post_payload(self, phone, payload, template_name, is_test=False, body=None, update_message=None):
        self.ensure_one()
        if body is None and isinstance(payload, dict):
            body = (payload.get('text') or {}).get('body')
        if not self.base_url or not self.token:
            self._log(phone, template_name, 'failed', 'Configuration is missing the URL or token', body=body, is_test=is_test)
            return False
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }
        try:
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=8)
        except requests.RequestException as error:
            _logger.warning("WhatsApp request failed: %s", error)
            self._log(phone, template_name, 'failed', str(error), body=body, is_test=is_test)
            return False
        response_text = response.text or ''
        response_body = response_text[:500]
        if response.ok:
            wa_message_id = self._whatsapp_message_id(response_text)
            state = 'waiting' if wa_message_id else 'sent'
            if update_message:
                update_message.write({
                    'state': state,
                    'response': response_body,
                    'template_name': template_name,
                    'wa_message_id': wa_message_id,
                })
                return True
            self._log(phone, template_name, state, response_body, body=body, is_test=is_test, wa_message_id=wa_message_id)
            return True
        _logger.warning("WhatsApp API returned %s", response.status_code)
        if update_message:
            update_message.write({'state': 'failed', 'response': response_body, 'template_name': template_name})
            return False
        self._log(phone, template_name, 'failed', response_body, body=body, is_test=is_test)
        return False

    @api.model
    def _normalize_phone(self, phone):
        return ''.join(ch for ch in str(phone or '') if ch.isdigit())

    def _whatsapp_message_id(self, response_body):
        try:
            payload = json.loads(response_body or '{}')
        except (TypeError, ValueError):
            return False
        messages = payload.get('messages') if isinstance(payload, dict) else None
        if not messages:
            return False
        return messages[0].get('id') or False

    def apply_delivery_status(self, wa_message_id, status, detail):
        self.ensure_one()
        if not wa_message_id:
            return False
        message = self.env['whatsapp.message'].sudo().search([
            ('config_id', '=', self.id),
            ('wa_message_id', '=', wa_message_id),
        ], limit=1)
        if not message:
            return False
        reason = self._status_reason(detail)
        if status == 'failed':
            new_state = 'failed'
        elif status in ('sent', 'delivered', 'read'):
            new_state = 'sent'
        else:
            return message
        message.write({
            'state': new_state,
            'response': reason,
        })
        message.message_post(
            body=reason or ('WhatsApp reported this message as %s.' % status),
            subtype_xmlid='mail.mt_note',
        )
        return message

    def _status_reason(self, detail):
        payload = self._status_payload(detail)
        errors = payload.get('errors') or []
        if not errors:
            status = payload.get('status')
            return 'WhatsApp reported this message as %s.' % status if status else (detail or '')[:500]
        error = errors[0]
        text = (error.get('error_data') or {}).get('details') or error.get('message') or error.get('title')
        return (text or detail or '')[:500]

    def _status_payload(self, detail):
        try:
            payload = json.loads(detail or '{}')
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _log(self, phone, template_name, state, response, body=None, is_test=False, wa_message_id=False):
        message = self.env['whatsapp.message'].sudo().create({
            'config_id': self.id,
            'phone': phone,
            'template_name': template_name,
            'state': state,
            'response': response,
            'body': body,
            'is_test': is_test,
            'wa_message_id': wa_message_id,
        })
        if not is_test:
            return message
        outcome = {'waiting': 'waiting', 'sent': 'sent'}.get(state, 'failed')
        note = '%s %s to %s.' % (
            'Test' if template_name != 'authentication' else 'Authentication',
            outcome,
            phone or 'the API',
        )
        if body:
            note = '%s\n%s' % (note, body)
        if response and response != body:
            note = '%s\n%s' % (note, response)
        self.message_post(body=note, subtype_xmlid='mail.mt_note')
        message.message_post(body=note, subtype_xmlid='mail.mt_note')
        return message


class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'template_name'

    config_id = fields.Many2one('whatsapp.config', readonly=True)
    phone = fields.Char(readonly=True)
    body = fields.Text(string='Message', readonly=True)
    template_name = fields.Char(readonly=True)
    is_test = fields.Boolean(string='Test', readonly=True)
    wa_message_id = fields.Char(string='WhatsApp Message Id', readonly=True, index=True, copy=False)
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('received', 'Received'),
    ], readonly=True, tracking=True)
    response = fields.Text(readonly=True)
