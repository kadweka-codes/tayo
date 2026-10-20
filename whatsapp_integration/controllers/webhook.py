import hmac
import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


class WhatsAppWebhook(http.Controller):
    @http.route(['/whatsapp/webhook', '/whatsapp/webhook/'], type='http', auth='public', methods=['GET'], csrf=False)
    def verify(self, **kwargs):
        mode = self._query('hub.mode', 'hub_mode')
        challenge = self._query('hub.challenge', 'hub_challenge')
        token = self._query('hub.verify_token', 'hub_verify_token')
        config = self._config_for_token(token)
        if mode == 'subscribe' and config and challenge:
            response = request.make_response(challenge)
            response.status_code = 200
            return response
        _logger.warning(
            'WhatsApp verification rejected mode=%s challenge=%s token_matched=%s',
            mode, bool(challenge), bool(config),
        )
        return Response('Forbidden', status=403)

    @http.route(['/whatsapp/webhook', '/whatsapp/webhook/'], type='http', auth='public', methods=['POST'], csrf=False)
    def webhook(self):
        raw = request.httprequest.get_data() or b''
        try:
            payload = json.loads(raw.decode() or '{}')
        except (TypeError, ValueError, UnicodeDecodeError):
            return self._json({'ok': False, 'error': 'Invalid JSON'}, 400)
        if not isinstance(payload, dict):
            return self._json({'ok': False, 'error': 'Invalid JSON'}, 400)
        if payload.get('object') == 'whatsapp_business_account' or payload.get('entry'):
            config = request.env['whatsapp.config'].sudo().search([('active', '=', True)], limit=1)
            if config:
                return self._incoming(config, payload)
            return self._json({'ok': True})
        config = self._config_for_token(self._presented_token())
        if not config:
            return self._json({'ok': False, 'error': 'Verification token was not accepted'}, 403)
        if not config.active or config.state != 'connected':
            return self._json({'ok': False, 'error': 'WhatsApp configuration is not connected'}, 403)
        return self._send(config, payload)

    def _send(self, config, payload):
        phone = payload.get('phone') or payload.get('to')
        message = payload.get('message') or payload.get('text')
        if not phone or not str(message or '').strip():
            return self._json({'ok': False, 'error': 'phone and message are required'}, 400)
        sent = config.send_custom_message(phone, message)
        if sent:
            return self._json({'ok': True})
        return self._json({'ok': False, 'error': 'WhatsApp did not accept the message'}, 502)

    def _incoming(self, config, payload):
        for entry in payload.get('entry') or []:
            for change in entry.get('changes') or []:
                value = change.get('value') or {}
                for status in value.get('statuses') or []:
                    config.apply_delivery_status(
                        status.get('id'),
                        status.get('status'),
                        json.dumps(status),
                    )
                for item in value.get('messages') or []:
                    text = item.get('text') or {}
                    config.log_incoming_message(
                        item.get('from'),
                        text.get('body') or item.get('type') or '',
                        json.dumps(item),
                    )
        return self._json({'ok': True})

    def _query(self, *names):
        args = request.httprequest.args
        for name in names:
            value = args.get(name)
            if value:
                return value
        return ''

    def _presented_token(self):
        header = request.httprequest.headers.get('X-Webhook-Token') or ''
        authorization = request.httprequest.headers.get('Authorization') or ''
        if authorization.lower().startswith('bearer '):
            header = header or authorization[7:].strip()
        args = request.httprequest.args
        return header or args.get('verify_token') or args.get('hub.verify_token') or ''

    def _config_for_token(self, token):
        if not token:
            return request.env['whatsapp.config']
        configs = request.env['whatsapp.config'].sudo().search([('webhook_token', '!=', False)])
        for config in configs:
            stored = config.webhook_token or ''
            if stored and hmac.compare_digest(stored, token):
                return config
        return request.env['whatsapp.config']

    def _json(self, payload, status=200):
        return Response(json.dumps(payload), content_type='application/json', status=status)
