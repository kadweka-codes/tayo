import json
import logging
import secrets

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from .buni_config import CHANNELS, DESTINATIONS, PROVIDERS

_logger = logging.getLogger(__name__)

PROVIDER_URL_KEYS = ('paymentUrl', 'redirectUrl', 'checkoutUrl', 'PaymentURL', 'payment_url')


class KcbBuniInvoice(models.Model):
    _name = 'kcb.buni.invoice'
    _description = 'KCB Buni test invoice'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'invoice_number'

    config_id = fields.Many2one(
        'kcb.buni.config',
        string='Setup',
        required=True,
        default=lambda self: self._default_config(),
    )
    provider = fields.Selection(PROVIDERS, string='Provider', default='buni', required=True)
    manual_destination = fields.Selection(DESTINATIONS, string='Destination')
    till_number = fields.Char(string='Till number')
    paybill_number = fields.Char(string='Paybill')
    account_number = fields.Char(string='Account')
    person_name = fields.Char(string='Name')
    payment_channel = fields.Selection(CHANNELS, string='Payment Channel', default='mpesa', tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('requested', 'Requested'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, required=True)
    access_token = fields.Char(copy=False, index=True, readonly=True)
    payment_link = fields.Char(string='Test Payment Link', compute='_compute_payment_link')

    phone_number = fields.Char(string='phoneNumber')
    amount = fields.Char(string='amount', required=True, default='1')
    account_reference = fields.Char(string='YOURACCREF')
    invoice_number = fields.Char(string='invoiceNumber', readonly=True, copy=False)
    shared_short_code = fields.Boolean(string='sharedShortCode')
    org_short_code = fields.Char(string='orgShortCode')
    org_pass_key = fields.Char(string='orgPassKey')
    transaction_description = fields.Char(string='transactionDescription', default='Test payment')
    callback_url = fields.Char(string='callbackUrl')

    header_status_code = fields.Char(string='statusCode', readonly=True)
    header_status_description = fields.Char(string='statusDescription', readonly=True)
    merchant_request_id = fields.Char(string='MerchantRequestID', readonly=True, index=True)
    response_code = fields.Char(string='ResponseCode', readonly=True)
    customer_message = fields.Char(string='CustomerMessage', readonly=True)
    checkout_request_id = fields.Char(string='CheckoutRequestID', readonly=True, index=True)
    response_description = fields.Char(string='ResponseDescription', readonly=True)
    provider_payment_url = fields.Char(string='Provider Payment URL', readonly=True)

    http_status = fields.Char(string='HTTP Response Code', readonly=True)
    fault_code = fields.Char(string='fault.code', readonly=True)
    fault_message = fields.Char(string='fault.message', readonly=True)
    fault_description = fields.Text(string='fault.description', readonly=True)

    result_code = fields.Char(string='ResultCode', readonly=True)
    result_desc = fields.Char(string='ResultDesc', readonly=True)
    callback_amount = fields.Char(string='Amount', readonly=True)
    mpesa_receipt_number = fields.Char(string='MpesaReceiptNumber', readonly=True)
    balance = fields.Char(string='Balance', readonly=True)
    transaction_date = fields.Char(string='TransactionDate', readonly=True)
    callback_phone = fields.Char(string='PhoneNumber', readonly=True)
    request_payload = fields.Text(string='Request Payload', readonly=True)
    response_payload = fields.Text(string='Response Payload', readonly=True)
    callback_payload = fields.Text(string='Callback Payload', readonly=True)

    @api.model
    def _default_config(self):
        return self.env['kcb.buni.config'].search([('active', '=', True)], limit=1)

    @api.depends('access_token')
    def _compute_payment_link(self):
        base = (self.env['ir.config_parameter'].sudo().get_param('web.base.url') or '').rstrip('/')
        for invoice in self:
            if invoice.access_token and base:
                invoice.payment_link = '%s/kcb_buni/pay/%s' % (base, invoice.access_token)
            else:
                invoice.payment_link = False

    @api.onchange('config_id')
    def _onchange_config_id(self):
        config = self.config_id
        if not config:
            return
        self.provider = config.provider
        self.manual_destination = config.manual_destination
        self.till_number = config.till_number
        self.paybill_number = config.paybill_number
        self.account_number = config.account_number
        self.person_name = config.person_name
        self.shared_short_code = config.shared_short_code
        self.org_short_code = config.org_short_code
        self.org_pass_key = config.org_pass_key
        self.callback_url = config.callback_url

    @api.model_create_multi
    def create(self, vals_list):
        config_model = self.env['kcb.buni.config']
        for vals in vals_list:
            config = config_model.browse(vals.get('config_id')) if vals.get('config_id') else self._default_config()
            if config:
                vals.setdefault('provider', config.provider)
                vals.setdefault('manual_destination', config.manual_destination)
                vals.setdefault('till_number', config.till_number)
                vals.setdefault('paybill_number', config.paybill_number)
                vals.setdefault('account_number', config.account_number)
                vals.setdefault('person_name', config.person_name)
                vals.setdefault('shared_short_code', config.shared_short_code)
                vals.setdefault('org_short_code', config.org_short_code)
                vals.setdefault('org_pass_key', config.org_pass_key)
                vals.setdefault('callback_url', config.callback_url)
            reference = vals.get('account_reference') or self.env['ir.sequence'].next_by_code('kcb.buni.invoice')
            if config and config.provider == 'manual' and config.manual_destination == 'paybill':
                prefix = config.paybill_number or 'PAYBILL'
            else:
                prefix = (config.till_number or config.org_short_code or 'KCBTILLNO') if config else 'KCBTILLNO'
            vals['account_reference'] = reference
            vals['invoice_number'] = ('%s-%s' % (prefix, reference))[:30]
            vals['access_token'] = vals.get('access_token') or secrets.token_urlsafe(24)
        return super().create(vals_list)

    def action_open_generate_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Generate Test Payment Link',
            'res_model': 'kcb.buni.link.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_open_payment_link(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.payment_link,
            'target': 'new',
        }

    def action_delete_invoice(self):
        action = self.env['ir.actions.act_window']._for_xml_id('kcb_buni_payment.action_kcb_buni_invoice')
        self.unlink()
        return action

    def action_request_payment(self):
        for invoice in self:
            invoice._send_payment_request()

    def mark_manual_paid(self):
        self.ensure_one()
        if self.provider != 'manual':
            raise UserError('Only a manual till or paybill can be marked paid from the payment page.')
        self.write({'state': 'completed'})

    def _send_payment_request(self):
        self.ensure_one()
        if self.state == 'completed':
            raise UserError('This invoice is already completed.')
        if self.provider == 'manual':
            raise UserError('This invoice uses a manual till or paybill. Confirm it on the payment link.')
        if self.provider == 'saaspay':
            return self._send_saaspay_request()
        config = self.config_id
        if not config:
            raise UserError('Choose a KCB Buni setup before requesting payment.')
        endpoint = config.endpoint_for(self.payment_channel)
        channel_name = dict(CHANNELS).get(self.payment_channel, self.payment_channel)
        if not endpoint:
            raise UserError('Set the %s URL on the KCB Buni setup before paying with this method.' % channel_name)
        if not self.callback_url:
            raise UserError('callbackUrl is required. Use a public HTTPS address KCB can reach.')
        phone = self._normalize_phone(self.phone_number)
        payload = {
            'phoneNumber': phone,
            'amount': self._amount_text(self.amount),
            'invoiceNumber': self.invoice_number,
            'sharedShortCode': bool(self.shared_short_code),
            'orgShortCode': self.org_short_code or '',
            'orgPassKey': self.org_pass_key or '',
            'callbackUrl': self.callback_url,
            'transactionDescription': (self.transaction_description or 'Test payment')[:30],
        }
        token = config._fetch_token()
        try:
            response = requests.post(
                endpoint,
                headers={
                    'Authorization': 'Bearer %s' % token,
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=20,
            )
        except requests.RequestException as error:
            _logger.warning('Buni payment request failed for %s: %s', self.invoice_number, error)
            self.write({
                'state': 'failed',
                'phone_number': phone,
                'request_payload': json.dumps(payload),
                'fault_description': str(error),
            })
            raise UserError('Could not reach the Buni payment URL.') from error
        body = response.json() if response.content else {}
        fault = body.get('fault') or {}
        header = body.get('header') or {}
        result = body.get('response') or {}
        checkout = result.get('CheckoutRequestID')
        provider_url = self._provider_url(body) or self._provider_url(result)
        self.write({
            'phone_number': phone,
            'request_payload': json.dumps(payload),
            'response_payload': json.dumps(body)[:8000],
            'http_status': str(response.status_code),
            'header_status_code': header.get('statusCode'),
            'header_status_description': header.get('statusDescription'),
            'merchant_request_id': result.get('MerchantRequestID'),
            'response_code': result.get('ResponseCode'),
            'customer_message': result.get('CustomerMessage'),
            'checkout_request_id': '' if checkout in (False, None) else str(checkout),
            'response_description': result.get('ResponseDescription'),
            'provider_payment_url': provider_url,
            'fault_code': str(fault.get('code') or ''),
            'fault_message': fault.get('message'),
            'fault_description': fault.get('description'),
            'state': 'requested' if response.ok and str(header.get('statusCode')) == '0' else 'failed',
        })

    def _send_saaspay_request(self):
        self.ensure_one()
        config = self.config_id
        if not config or not config.saaspay_request_url:
            raise UserError('Set the SaaSPay Request URL on this payment method.')
        if not config.merchant_code:
            raise UserError('Set MerchantCode on this SaaSPay method.')
        network = config.network_for(self.payment_channel)
        if not network:
            raise UserError('Set NetworkCode for this SaaSPay channel.')
        if not self.callback_url:
            raise UserError('callbackUrl is required. Use a public HTTPS address SaaSPay can reach.')
        phone = self._normalize_phone(self.phone_number)
        payload = {
            'MerchantCode': config.merchant_code,
            'NetworkCode': network,
            'Currency': 'KES',
            'Amount': self._amount_text(self.amount),
            'PhoneNumber': phone,
            'AccountReference': self.invoice_number,
            'TransactionDesc': (self.transaction_description or 'Test payment')[:30],
            'CallBackURL': self.callback_url,
        }
        token = config._fetch_saaspay_token()
        try:
            response = requests.post(
                config.saaspay_request_url,
                headers={
                    'Authorization': 'Bearer %s' % token,
                    'Content-Type': 'application/json',
                },
                json=payload,
                timeout=20,
            )
        except requests.RequestException as error:
            _logger.warning('SaaSPay request failed for %s: %s', self.invoice_number, error)
            self.write({
                'state': 'failed',
                'phone_number': phone,
                'request_payload': json.dumps(payload),
                'fault_description': str(error),
            })
            raise UserError('Could not reach the SaaSPay payment URL.') from error
        body = response.json() if response.content else {}
        checkout = self._pick(body, 'CheckoutRequestID', 'checkoutRequestId')
        response_code = self._pick(body, 'ResponseCode', 'responseCode', 'statusCode')
        accepted = response.ok and (
            str(response_code) in ('0', '00')
            or (response_code in (None, False) and body.get('status') is True)
        )
        self.write({
            'phone_number': phone,
            'request_payload': json.dumps(payload),
            'response_payload': json.dumps(body)[:8000],
            'http_status': str(response.status_code),
            'response_code': '' if response_code is None else str(response_code),
            'customer_message': self._pick(body, 'message', 'CustomerMessage', 'ResponseDescription'),
            'merchant_request_id': self._pick(body, 'MerchantRequestID', 'merchantReference', 'MerchantReference'),
            'checkout_request_id': '' if checkout in (False, None) else str(checkout),
            'response_description': self._pick(body, 'message', 'ResponseDescription'),
            'header_status_code': '' if response_code is None else str(response_code),
            'header_status_description': self._pick(body, 'message', 'statusDescription'),
            'state': 'requested' if accepted else 'failed',
        })

    def apply_callback(self, payload):
        self.ensure_one()
        callback = (payload.get('Body') or {}).get('stkCallback')
        if not callback and payload.get('ResultCode') is not None:
            return self._apply_saaspay_callback(payload)
        callback = callback or {}
        items = {
            item.get('Name'): item.get('Value')
            for item in ((callback.get('CallbackMetadata') or {}).get('Item') or [])
            if item.get('Name')
        }
        result_code = callback.get('ResultCode')
        self.write({
            'callback_payload': json.dumps(payload)[:8000],
            'merchant_request_id': callback.get('MerchantRequestID') or self.merchant_request_id,
            'checkout_request_id': callback.get('CheckoutRequestID') or self.checkout_request_id,
            'result_code': '' if result_code is None else str(result_code),
            'result_desc': callback.get('ResultDesc'),
            'callback_amount': '' if items.get('Amount') is None else str(items.get('Amount')),
            'mpesa_receipt_number': items.get('MpesaReceiptNumber'),
            'balance': '' if items.get('Balance') is None else str(items.get('Balance')),
            'transaction_date': '' if items.get('TransactionDate') is None else str(items.get('TransactionDate')),
            'callback_phone': '' if items.get('PhoneNumber') is None else str(items.get('PhoneNumber')),
            'state': 'completed' if str(result_code) == '0' else 'failed',
        })

    def _apply_saaspay_callback(self, payload):
        self.ensure_one()
        result_code = payload.get('ResultCode')
        completed = str(result_code) == '0'
        receipt = payload.get('SasaPayTransactionID') or payload.get('MpesaReceiptNumber')
        values = {
            'callback_payload': json.dumps(payload)[:8000],
            'merchant_request_id': payload.get('MerchantRequestID') or self.merchant_request_id,
            'checkout_request_id': payload.get('CheckoutRequestID') or self.checkout_request_id,
            'result_code': '' if result_code is None else str(result_code),
            'result_desc': payload.get('ResultDesc'),
            'callback_amount': '' if payload.get('TransactionAmount') is None else str(payload.get('TransactionAmount')),
            'mpesa_receipt_number': receipt,
            'balance': '' if payload.get('MerchantAccountBalance') is None else str(payload.get('MerchantAccountBalance')),
            'transaction_date': '' if payload.get('TransactionDate') is None else str(payload.get('TransactionDate')),
            'callback_phone': payload.get('SenderAccountNumber') or payload.get('RecipientAccountNumber') or self.callback_phone,
            'state': 'completed' if completed else 'failed',
        }
        if completed and payload.get('RecipientName') and not self.person_name:
            values['person_name'] = payload.get('RecipientName')
        self.write(values)

    @api.model
    def _pick(self, payload, *keys):
        for key in keys:
            value = payload.get(key) if isinstance(payload, dict) else None
            if value not in (None, ''):
                return value
        return False

    @api.model
    def _provider_url(self, payload):
        if not isinstance(payload, dict):
            return False
        for key in PROVIDER_URL_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.startswith('https://'):
                return value
        return False

    @api.model
    def _normalize_phone(self, phone):
        digits = ''.join(character for character in str(phone or '') if character.isdigit())
        if digits.startswith('0') and len(digits) == 10:
            digits = '254' + digits[1:]
        if not digits:
            raise UserError('phoneNumber is required.')
        return digits[:20]

    @api.model
    def _amount_text(self, amount):
        text = str(amount or '').replace(',', '').strip()
        if not text:
            raise UserError('amount is required.')
        try:
            number = float(text)
        except ValueError as error:
            raise UserError('amount must be a number.') from error
        if number <= 0:
            raise UserError('amount must be greater than zero.')
        if number == int(number):
            return str(int(number))
        return ('%.2f' % number).rstrip('0').rstrip('.')
