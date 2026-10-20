import json
import logging

from odoo import http, exceptions
from odoo.exceptions import AccessDenied, AccessError, UserError
from odoo.http import request, Response
from odoo.tools import date_utils
import base64
from datetime import datetime
from functools import wraps

_logger = logging.getLogger(__name__)


def authenticate(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            auth_header = request.httprequest.headers.get('Authorization')
            if not auth_header:
                return {
                    'jsonrpc': '2.0',
                    'id': None,
                        'code': 401,
                        'message': 'Unauthorized',
                        'data': {
                            'detail': 'Missing access token in Authorization header.'
                        }

                }
            token = auth_header.replace('Bearer ', '', 1).strip()
            user = request.env['res.users'].sudo().search([('access_token', '=', token)], limit=1)
            if not user:
                return {
                    'jsonrpc': '2.0',
                    'id': None,
                        'code': 401,
                        'message': 'Unauthorized',
                        'data': {
                            'detail': 'Invalid or expired access token.'

                    }
                }
            # Attach user to request context if needed
            # request.uid = user.id
            return func(*args, **kwargs)
        except Exception as e:
            _logger.exception("Authentication error")
            return {
                'jsonrpc': '2.0',
                'id': None,
                    'code': 500,
                    'message': 'Internal Server Error',
                    'data': {'detail': str(e)}

            }
    return wrapper