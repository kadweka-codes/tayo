import base64
import logging
from datetime import timedelta

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

UAT_TOKEN_URL = 'https://uat.buni.kcbgroup.com/token?grant_type=client_credentials'
UAT_STK_URL = 'https://uat.buni.kcbgroup.com/mm/api/request/1.0.0/stkpush'
PROD_TOKEN_URL = 'https://buni.kcbgroup.com/token?grant_type=client_credentials'
PROD_STK_URL = 'https://buni.kcbgroup.com/mm/api/request/1.0.0/stkpush'

CHANNELS = [
    ('mpesa', 'M-Pesa'),
    ('airtel', 'Airtel Money'),
    ('card', 'Card'),
]
PROVIDERS = [
    ('buni', 'Buni'),
    ('saaspay', 'SaaSPay'),
    ('manual', 'Manual'),
]
DESTINATIONS = [
    ('till', 'Till'),
    ('paybill', 'Paybill'),
]
SAASPAY_NETWORKS = {
    'mpesa': '63902',
    'airtel': '63903',
}
SAASPAY_TOKEN_URL = 'https://sandbox.sasapay.app/api/v1/auth/token/?grant_type=client_credentials'
SAASPAY_REQUEST_URL = 'https://sandbox.sasapay.app/api/v1/payments/request-payment/'


class KcbBuniConfig(models.Model):
    _name = 'kcb.buni.config'
    _description = 'KCB Buni setup'
    _rec_name = 'name'

    name = fields.Char(default='KCB Buni', required=True)
    active = fields.Boolean(default=True)
    provider = fields.Selection(PROVIDERS, default='buni', required=True)
    manual_destination = fields.Selection(DESTINATIONS, string='Destination')
    paybill_number = fields.Char(string='Paybill')
    account_number = fields.Char(string='Account')
    person_name = fields.Char(string='Name', help='Shown when the payment is complete.')
    environment = fields.Selection([
        ('uat', 'UAT sandbox'),
        ('production', 'Production'),
    ], default='uat', required=True)
    merchant_code = fields.Char(string='MerchantCode')
    network_code = fields.Char(string='NetworkCode')
    saaspay_client_id = fields.Char(string='Client ID')
    saaspay_client_secret = fields.Char(string='Client Secret')
    saaspay_token_url = fields.Char(string='SaaSPay Token URL', default=SAASPAY_TOKEN_URL)
    saaspay_request_url = fields.Char(string='SaaSPay Request URL', default=SAASPAY_REQUEST_URL)
    token_url = fields.Char(string='Token URL', required=True, default=UAT_TOKEN_URL)
    consumer_key = fields.Char(string='Consumer Key')
    consumer_secret = fields.Char(string='Consumer Secret')
    grant_type = fields.Char(string='grant_type', default='client_credentials', required=True)
    stk_push_url = fields.Char(string='M-Pesa Express URL', default=UAT_STK_URL)
    airtel_url = fields.Char(string='Airtel Money URL')
    card_url = fields.Char(string='Card Payment URL')
    shared_short_code = fields.Boolean(string='sharedShortCode', default=True)
    org_short_code = fields.Char(string='orgShortCode')
    org_pass_key = fields.Char(string='orgPassKey')
    callback_url = fields.Char(string='callbackUrl')
    till_number = fields.Char(string='Till number')
    access_token = fields.Char(copy=False)
    token_expires_at = fields.Datetime(copy=False)

    @api.onchange('environment', 'provider')
    def _onchange_environment(self):
        if self.provider == 'saaspay':
            if self.environment != 'production':
                self.saaspay_token_url = SAASPAY_TOKEN_URL
                self.saaspay_request_url = SAASPAY_REQUEST_URL
            return
        if self.environment == 'production':
            self.token_url = PROD_TOKEN_URL
            self.stk_push_url = PROD_STK_URL
        else:
            self.token_url = UAT_TOKEN_URL
            self.stk_push_url = UAT_STK_URL

    @api.constrains('provider', 'manual_destination', 'till_number', 'paybill_number', 'account_number', 'person_name')
    def _check_manual_destination(self):
        for method in self:
            if method.provider != 'manual':
                continue
            if method.manual_destination == 'till':
                if not method.till_number or not method.person_name:
                    raise ValidationError('A till needs a till number and a name.')
            elif method.manual_destination == 'paybill':
                if not method.paybill_number or not method.account_number or not method.person_name:
                    raise ValidationError('A paybill needs a paybill, an account, and the name of the person.')
            else:
                raise ValidationError('Select Till or Paybill.')

    def endpoint_for(self, channel):
        self.ensure_one()
        if channel == 'airtel':
            return self.airtel_url
        if channel == 'card':
            return self.card_url
        return self.stk_push_url

    def action_generate_test_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Test Payment Link',
            'res_model': 'kcb.buni.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_config_id': self.id},
        }

    def write(self, vals):
        if {'provider', 'consumer_key', 'consumer_secret', 'saaspay_client_id', 'saaspay_client_secret'} & set(vals):
            vals = dict(vals, access_token=False, token_expires_at=False)
        return super().write(vals)

    def network_for(self, channel):
        self.ensure_one()
        return self.network_code or SAASPAY_NETWORKS.get(channel)

    def action_test_token(self):
        self.ensure_one()
        if self.provider == 'manual':
            raise UserError('A manual till or paybill does not use an authentication token.')
        if self.provider == 'saaspay':
            self._fetch_saaspay_token(force=True)
        else:
            self._fetch_token(force=True)
        expires = fields.Datetime.to_string(self.token_expires_at) if self.token_expires_at else ''
        message = 'Token received.'
        if expires:
            message = 'Token received until %s.' % expires
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Authentication Token',
                'message': message,
                'type': 'success',
                'sticky': False,
            },
        }

    def _fetch_token(self, force=False):
        self.ensure_one()
        now = fields.Datetime.now()
        if not force and self.access_token and self.token_expires_at and self.token_expires_at > now:
            return self.access_token
        if not self.consumer_key or not self.consumer_secret or not self.token_url:
            raise UserError('Set the Consumer Key, Consumer Secret, and Token URL under Authentication Token.')
        raw = ('%s:%s' % (self.consumer_key, self.consumer_secret)).encode()
        try:
            response = requests.post(
                self.token_url,
                headers={
                    'Authorization': 'Basic %s' % base64.b64encode(raw).decode(),
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                data={'grant_type': self.grant_type or 'client_credentials'},
                timeout=15,
            )
        except requests.RequestException as error:
            _logger.warning('Buni token request failed: %s', error)
            raise UserError('Could not reach the Buni token URL.') from error
        if response.status_code != 200:
            raise UserError('Authentication Token failed with HTTP %s.' % response.status_code)
        payload = response.json() if response.content else {}
        token = payload.get('access_token')
        if not token:
            raise UserError('Buni did not return an access token.')
        expires_in = int(payload.get('expires_in') or 3600)
        self.write({
            'access_token': token,
            'token_expires_at': now + timedelta(seconds=max(expires_in - 60, 30)),
        })
        return token

    def _fetch_saaspay_token(self, force=False):
        self.ensure_one()
        now = fields.Datetime.now()
        if not force and self.access_token and self.token_expires_at and self.token_expires_at > now:
            return self.access_token
        if not self.saaspay_client_id or not self.saaspay_client_secret or not self.saaspay_token_url:
            raise UserError('Set the SaaSPay Client ID, Client Secret, and Token URL.')
        raw = ('%s:%s' % (self.saaspay_client_id, self.saaspay_client_secret)).encode()
        try:
            response = requests.post(
                self.saaspay_token_url,
                headers={'Authorization': 'Basic %s' % base64.b64encode(raw).decode()},
                data={'grant_type': 'client_credentials'},
                timeout=15,
            )
        except requests.RequestException as error:
            _logger.warning('SaaSPay token request failed: %s', error)
            raise UserError('Could not reach the SaaSPay token URL.') from error
        if response.status_code != 200:
            raise UserError('SaaSPay authentication failed with HTTP %s.' % response.status_code)
        payload = response.json() if response.content else {}
        token = payload.get('access_token')
        if not token:
            raise UserError('SaaSPay did not return an access token.')
        expires_in = int(payload.get('expires_in') or 3600)
        self.write({
            'access_token': token,
            'token_expires_at': now + timedelta(seconds=max(expires_in - 60, 30)),
        })
        return token
