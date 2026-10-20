import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DilekOdutechPosN8n(models.Model):
    """Older connection record. The scheduled pull uses its linked API sync."""
    _name = 'dilek.odutechpos.n8n'
    _description = 'n8n connection'
    _rec_name = 'name'

    name = fields.Char(required=True)
    base_url = fields.Char(required=True)
    token = fields.Char(required=True)
    view_id = fields.Char(required=True)
    offset = fields.Char(required=True, default='0')
    limit = fields.Char(required=True, default='50')
    availability = fields.Selection([
        ('PREPARATIONS', 'Preparations'),
        ('READY_TO_LAUNCH', 'Operational'),
    ])
    date = fields.Datetime(required=True, default=fields.Datetime.now)
    linked_pos = fields.Many2many(
        'pos.config',
        'dilek_odutechpos_n8n_pos_config_rel',
        'dilek_odutechpos_n8n_id',
        'pos_config_id',
        string='Linked POS',
    )

    def fetch_n8n_data(self):
        configs = self if self else self.search([])
        for config in configs:
            if config.availability and config.availability != 'READY_TO_LAUNCH':
                continue
            sync = self.env['external.api.sync'].sudo().search([
                ('url', '=', config.base_url),
            ], limit=1)
            values = {
                'name': config.name,
                'token': config.token,
                'view_id': config.view_id,
                'limit': int(config.limit or 50),
                'active': True,
            }
            if config.linked_pos:
                values['pos_config_ids'] = [(6, 0, config.linked_pos.ids)]
            if not sync:
                values.update({
                    'url': config.base_url,
                    'offset': int(config.offset or 0),
                })
                sync = self.env['external.api.sync'].sudo().create(values)
            else:
                sync.write(values)
            sync.cron_sync_data_from_online()
            config.write({
                'offset': str(sync.offset or 0),
                'date': fields.Datetime.now(),
            })


class ExternalAPISync(models.Model):
    _name = 'external.api.sync'
    _description = 'External API Sync Config'

    name = fields.Char(string='Name', required=True)
    url = fields.Char(string='API URL', required=True)
    token = fields.Char(string='API Token', required=True)
    view_id = fields.Char(string='View ID')
    date_field = fields.Char(string='Date column', default='date')
    offset = fields.Integer(string='Offset', default=0)
    limit = fields.Integer(string='Limit', default=50)
    last_data_sync = fields.Datetime(string='Last Data Sync', readonly=True)
    last_count = fields.Integer(string='Last fetched', readonly=True)
    last_error = fields.Text(string='Last error', readonly=True)
    webhook_token = fields.Char(string='Webhook token')
    webhook_url = fields.Char(string='Webhook URL', compute='_compute_webhook_url')
    pos_config_ids = fields.Many2many('pos.config', string='Point of Sale')
    active = fields.Boolean(string='Active', default=True)

    @api.depends('url')
    def _compute_webhook_url(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        for record in self:
            record.webhook_url = '%s/api/get_transactions' % base if base else '/api/get_transactions'

    def _request_rows(self, use_date_filter):
        self.ensure_one()
        limit = min(max(self.limit or 50, 1), 100)
        offset = max(self.offset or 0, 0)
        parts = urlsplit(self.url.strip())
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update({'offset': offset, 'limit': limit})
        if self.view_id:
            query['viewId'] = self.view_id
        if use_date_filter and self.last_data_sync:
            day = fields.Datetime.context_timestamp(self, self.last_data_sync).strftime('%Y-%m-%d')
            column = self.date_field or 'date'
            query['where'] = '(%s,gte,%s)' % (column, day)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))
        response = requests.get(
            url,
            headers={
                'xc-token': self.token,
                'Authorization': 'Bearer %s' % self.token,
                'Accept': 'application/json',
            },
            timeout=30,
        )
        if response.status_code == 400 and use_date_filter:
            return self._request_rows(False)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, list):
            rows = payload
            is_last = len(rows) < limit
        else:
            data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
            rows = payload.get('list') or payload.get('rows') or data.get('rows') or data.get('list') or []
            page_info = payload.get('pageInfo') or data.get('pageInfo') or {}
            is_last = bool(page_info.get('isLastPage')) or len(rows) < limit
        return rows, limit, is_last

    def action_test_connection(self):
        self.ensure_one()
        saved_offset = self.offset
        self.offset = 0
        try:
            rows, _limit, _is_last = self._request_rows(False)
        except (requests.RequestException, ValueError) as error:
            self.write({'offset': saved_offset, 'last_error': str(error)})
            return self._notify('n8n connection failed', str(error), 'danger')
        self.write({'offset': saved_offset, 'last_error': False})
        return self._notify('n8n connection works', 'The source returned %s row(s).' % len(rows), 'success')

    def _notify(self, title, message, level):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': level,
                'sticky': level == 'danger',
            },
        }

    def cron_sync_data_from_online(self):
        configs = self if self else self.search([('active', '=', True)])
        for rec in configs:
            fetched = 0
            error = False
            finished = False
            next_offset = rec.offset or 0
            for _page in range(20):
                try:
                    rows, limit, is_last = rec._request_rows(bool(rec.last_data_sync))
                except (requests.RequestException, ValueError) as exc:
                    error = str(exc)
                    _logger.warning('n8n sync failed for %s: %s', rec.name or rec.id, exc)
                    break
                useful = [
                    row for row in rows
                    if isinstance(row, dict) and (row.get('phone_number') or row.get('phone') or row.get('date') or row.get('credit') or row.get('debit'))
                ]
                if useful:
                    try:
                        with self.env.cr.savepoint():
                            self.env['odutech.n8n'].sudo().ingest_rows(useful, pos_config_ids=rec.pos_config_ids.ids)
                            fetched += len(useful)
                    except Exception as exc:
                        error = str(exc)
                        _logger.exception('n8n page skipped for sync %s', rec.id)
                        break
                if is_last or len(rows) < limit:
                    finished = True
                    break
                next_offset += len(rows)
                rec.offset = next_offset
            values = {
                'last_count': fetched,
                'last_error': error or False,
                'offset': 0 if finished and not error else next_offset,
            }
            if finished and not error:
                values['last_data_sync'] = fields.Datetime.now()
            rec.write(values)
        self.env['odutech.n8n'].sudo().action_process_order_lines()
