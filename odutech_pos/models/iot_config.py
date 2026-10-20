import logging

import requests
from requests.auth import HTTPDigestAuth
import urllib3

from odoo import fields, models

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_logger = logging.getLogger(__name__)


class IotPeopleCounting(models.Model):
    _name = 'iot.people.counting'
    _description = 'Restaurant people counting'

    name = fields.Char(string="Api Name")
    url = fields.Char(string='Api Url')
    username = fields.Char(string='Api Username')
    port = fields.Char(string='Api Port')
    password = fields.Char(string='Api Password')
    active = fields.Boolean(default=True)
    last_data_sync = fields.Datetime(string="Last Data Sync", readonly=True)
    last_people_count = fields.Integer(string="Last People Count", readonly=True)
    last_alert_at = fields.Datetime(string="Last Waiter Alert", readonly=True)
    alert_cooldown_minutes = fields.Integer(string="Alert Cooldown (minutes)", default=5)

    def get_available_waiter(self):
        return self.env['pos.order']._least_busy_employee('waiter')

    def _people_count(self):
        self.ensure_one()
        base = (self.url or '').rstrip('/')
        port = (self.port or '').strip()
        if base and '://' not in base:
            base = f'http://{base}'
        if port and base:
            scheme, rest = base.split('://', 1)
            host = rest.split('/')[0]
            path = rest[len(host):]
            if ':' not in host:
                base = f'{scheme}://{host}:{port}{path}'
        endpoint = f"{base}/vb.htm?getppccurnumber"
        response = requests.get(
            endpoint,
            auth=HTTPDigestAuth(self.username or '', self.password or ''),
            verify=False,
            timeout=5,
        )
        response.raise_for_status()
        if "getppccurnumber=" not in response.text:
            return None
        return int(response.text.split('=')[-1].strip())

    def _should_alert(self, people_count, open_orders):
        self.ensure_one()
        if people_count <= open_orders:
            return False
        if not self.last_alert_at:
            return True
        elapsed = (fields.Datetime.now() - self.last_alert_at).total_seconds() / 60.0
        return elapsed >= (self.alert_cooldown_minutes or 5)

    def action_pull_people_counting_in_restaurant(self):
        configs = self if self else self.search([('active', '=', True)])
        for config in configs:
            try:
                people_count = config._people_count()
            except (requests.RequestException, ValueError) as error:
                _logger.warning("People counter %s failed: %s", config.name or config.url, error)
                continue
            if people_count is None:
                continue
            open_orders = self.env['pos.order'].search_count([
                ('state', 'not in', ('cancel', 'done', 'invoiced')),
                ('kitchen_state', '!=', 'served'),
            ])
            config.write({
                'last_people_count': people_count,
                'last_data_sync': fields.Datetime.now(),
            })
            if not config._should_alert(people_count, open_orders):
                continue
            waiter = config.get_available_waiter()
            phone = ''
            if waiter:
                phone = (waiter.mobile_phone or waiter.work_phone or '').strip()
            whatsapp = self.env['whatsapp.config'].sudo().search([('active', '=', True)], limit=1) if 'whatsapp.config' in self.env else False
            if not phone or not whatsapp:
                continue
            sent = whatsapp.send_text(
                phone,
                'There are %s people in the restaurant and %s open orders.' % (people_count, open_orders),
            )
            if sent:
                config.last_alert_at = fields.Datetime.now()
