import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class N8nTransactionController(http.Controller):
    @http.route('/api/get_transactions', type='http', auth='public', methods=['POST'], csrf=False)
    def get_transactions(self, **kwargs):
        try:
            payload = json.loads(request.httprequest.data or b'{}')
        except (TypeError, ValueError):
            return request.make_json_response({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        if isinstance(payload, dict) and payload.get('jsonrpc') and isinstance(payload.get('params'), dict):
            payload = payload['params']
        if not self._authorized(payload):
            return request.make_json_response({'status': 'error', 'message': 'Invalid webhook token'}, status=403)
        rows = self._rows(payload)
        if 'odutech.n8n' not in request.env:
            return request.make_json_response({'status': 'error', 'message': 'n8n matching is not installed'}, status=404)
        created = request.env['odutech.n8n'].sudo().ingest_rows(rows)
        _logger.info('n8n webhook stored %s of %s transactions', len(created), len(rows))
        return request.make_json_response({'status': 'ok', 'count': len(rows), 'created': len(created)})

    def _authorized(self, payload):
        configs = request.env['external.api.sync'].sudo().search([
            ('active', '=', True),
            ('webhook_token', '!=', False),
        ])
        tokens = [config.webhook_token for config in configs if config.webhook_token]
        if not tokens:
            return True
        presented = request.httprequest.headers.get('X-Webhook-Token') or ''
        if not presented and isinstance(payload, dict):
            presented = str(payload.get('token') or '')
        authorization = request.httprequest.headers.get('Authorization') or ''
        if not presented and authorization.lower().startswith('bearer '):
            presented = authorization[7:].strip()
        return any(hmac.compare_digest(presented, token) for token in tokens)

    def _rows(self, payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        data = payload.get('data')
        if isinstance(data, dict):
            rows = data.get('rows') or data.get('list')
            if rows:
                return rows
        if isinstance(data, list):
            return data
        rows = payload.get('rows') or payload.get('list')
        if rows:
            return rows
        if payload.get('phone_number') or payload.get('phone') or payload.get('credit') or payload.get('debit'):
            return [payload]
        return []
