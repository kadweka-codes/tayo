import json
import logging

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request, Response

from odoo.addons.kcb_buni_payment.models.buni_config import CHANNELS

_logger = logging.getLogger(__name__)


class KcbBuniCallback(http.Controller):
    @http.route('/kcb_buni/callback', type='http', auth='public', methods=['POST'], csrf=False)
    def stk_callback(self):
        try:
            payload = json.loads(request.httprequest.data or b'{}')
        except (TypeError, ValueError):
            payload = {}
        callback = (payload.get('Body') or {}).get('stkCallback') or {}
        checkout = callback.get('CheckoutRequestID') or payload.get('CheckoutRequestID') or payload.get('checkoutRequestId')
        merchant = callback.get('MerchantRequestID') or payload.get('MerchantRequestID') or payload.get('MerchantTransactionReference')
        domain = []
        if checkout:
            domain = [('checkout_request_id', '=', checkout)]
        elif merchant:
            domain = [('merchant_request_id', '=', merchant)]
        invoice = request.env['kcb.buni.invoice']
        if domain:
            invoice = invoice.sudo().search(domain, limit=1)
        if invoice:
            invoice.apply_callback(payload)
            _logger.info('Buni callback applied to invoice %s', invoice.invoice_number)
        else:
            _logger.warning('Buni callback did not match a test invoice')
        body = json.dumps({'statusCode': '0', 'statusDescription': 'Accepted'})
        return Response(body, content_type='application/json', status=200)

    @http.route('/kcb_buni/pay/<string:token>', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def payment_link(self, token, **post):
        invoice = request.env['kcb.buni.invoice'].sudo().search([('access_token', '=', token)], limit=1)
        if not invoice:
            return request.render('kcb_buni_payment.payment_link_missing', {})
        message = False
        error = False
        if request.httprequest.method == 'POST' and invoice.state != 'completed':
            if invoice.provider == 'manual' and post.get('complete'):
                invoice.mark_manual_paid()
                message = 'Payment completed.'
            else:
                phone = (post.get('phoneNumber') or '').strip()
                if phone:
                    invoice.write({'phone_number': phone})
                try:
                    invoice._send_payment_request()
                    message = invoice.customer_message or invoice.header_status_description or 'Payment request sent.'
                except UserError as exc:
                    error = exc.args[0]
        if invoice.provider == 'manual' and invoice.manual_destination == 'paybill':
            channel = 'Paybill'
        elif invoice.provider == 'manual':
            channel = 'Till'
        else:
            channel = '%s · %s' % (
                dict(invoice._fields['provider'].selection).get(invoice.provider),
                dict(CHANNELS).get(invoice.payment_channel, ''),
            )
        return request.render('kcb_buni_payment.payment_link_page', {
            'invoice': invoice,
            'channel_label': channel,
            'message': message,
            'error': error,
        })
