import json
import logging
from functools import wraps

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

_AUTH_ERRORS = {
    'missing': (401, 'Authentication missing. Send Authorization: Bearer <token>.'),
    'invalid': (401, 'Invalid authentication token.'),
    'expired': (401, 'Your session has expired. Please log in again.'),
}


def json_response(payload, status=200):
    return Response(
        json.dumps(payload),
        status=status,
        mimetype='application/json',
    )


def read_json_body():
    data = request.httprequest.get_json(silent=True)
    if data is None:
        raw = request.httprequest.get_data(as_text=True) or ''
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _bearer_token():
    header = request.httprequest.headers.get('Authorization') or ''
    parts = header.strip().split()
    if len(parts) == 2 and parts[0].lower() == 'bearer' and parts[1]:
        return parts[1].strip()
    return ''


def portal_auth(func):
    """Authenticate the bearer token and keep the caller on their employee record."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        employee, error_code = request.env['hr.employee']._portal_from_access_token(_bearer_token())
        if error_code:
            status, message = _AUTH_ERRORS.get(error_code, (401, 'Authentication failed.'))
            return json_response({'status': 'failed', 'message': message}, status)
        request.portal_employee = employee
        try:
            return func(*args, **kwargs)
        except UserError as error:
            return json_response({'status': 'failed', 'message': str(error)}, 400)
        except Exception:
            _logger.exception('Portal API failed for employee %s', employee.id)
            return json_response({'status': 'failed', 'message': 'Unexpected server error.'}, 500)

    return wrapper


def portal_license(func):
    """Reject the call when the company subscription has expired or the paid seat count is exceeded."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        message = request.portal_employee._portal_license_message()
        if message:
            return json_response({'status': 'failed', 'message': str(message)}, 403)
        return func(*args, **kwargs)

    return wrapper


def authorize_own_employee(employee_id, message):
    """Return (employee, response). response is set when the record is not the caller's."""
    employee, reason = request.portal_employee._portal_authorize_record(employee_id)
    if reason == 'missing':
        return None, json_response({'status': 'failed', 'message': 'Employee not found.'}, 404)
    if reason == 'forbidden':
        return None, json_response({'status': 'failed', 'message': message}, 403)
    return employee, None


class PortalAuthController(http.Controller):

    @http.route(
        '/odutech/portal/api/auth/login',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    def login(self, **kwargs):
        body = read_json_body()
        if body is None:
            return json_response({'status': 'failed', 'message': 'Send a JSON object.'}, 400)
        try:
            employee = request.env['hr.employee']._portal_authenticate(
                body.get('email'),
                body.get('password'),
            )
        except Exception:
            _logger.exception('Portal login failed')
            return json_response({'status': 'failed', 'message': 'Unexpected server error.'}, 500)

        if not employee:
            return json_response({'status': 'failed', 'message': 'Invalid email or password.'}, 401)

        setup = employee._portal_company_setup()
        if not setup:
            return json_response({
                'status': 'failed',
                'message': 'Set up the company under EP.Portal before signing in.',
            }, 403)
        if not setup.has_custom_domain:
            customer_code = (body.get('customer_code') or body.get('login_code') or '').strip()
            if not customer_code:
                return json_response({'status': 'failed', 'message': 'Customer code is required.'}, 400)
            if customer_code != (setup.login_code or '').strip():
                return json_response({'status': 'failed', 'message': 'Invalid customer code.'}, 401)
        license_message = setup.portal_license_message()
        if license_message:
            return json_response({'status': 'failed', 'message': str(license_message)}, 403)

        token, expires = employee._portal_issue_access_token()
        return json_response({
            'status': 'success',
            'data': {
                'access_token': token,
                'token_type': 'Bearer',
                'expires_at': expires.strftime('%Y-%m-%d %H:%M:%S'),
                'employee': employee._portal_api_values(),
            },
        })

    @http.route(
        '/odutech/portal/api/auth/reset-password',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    def reset_password(self, **kwargs):
        body = read_json_body()
        if body is None:
            return json_response({'status': 'failed', 'message': 'Send a JSON object.'}, 400)
        email = (body.get('email') or '').strip()
        if not email:
            return json_response({'status': 'failed', 'message': 'Email is required.'}, 400)

        employee = request.env['hr.employee']._portal_find_by_email(email)
        if not employee:
            return json_response({
                'status': 'success',
                'message': 'If an account exists for this email, a password reset link has been sent.',
            })
        try:
            employee._portal_send_password_setup_email()
        except UserError as error:
            return json_response({'status': 'failed', 'message': str(error)}, 400)
        except Exception:
            _logger.exception('Portal password reset failed for employee %s', employee.id)
            return json_response({'status': 'failed', 'message': 'Unexpected server error.'}, 500)
        return json_response({
            'status': 'success',
            'message': 'A password reset link was sent.',
        })

    @http.route(
        '/odutech/portal/api/auth/set-password',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    def set_password(self, **kwargs):
        body = read_json_body()
        if body is None:
            return json_response({'status': 'failed', 'message': 'Send a JSON object.'}, 400)
        token = (body.get('token') or '').strip()
        if not token:
            return json_response({'status': 'failed', 'message': 'Token is required.'}, 400)

        employee = request.env['hr.employee']._portal_employee_from_reset_token(token)
        if not employee:
            return json_response({
                'status': 'failed',
                'message': 'This link is not valid. Ask your company to send a new one.',
            }, 400)
        try:
            error = employee._set_portal_password(body.get('password'), body.get('password_confirm'))
        except Exception:
            _logger.exception('Portal set-password failed for employee %s', employee.id)
            return json_response({'status': 'failed', 'message': 'Unexpected server error.'}, 500)
        if error:
            return json_response({'status': 'failed', 'message': str(error)}, 400)
        return json_response({'status': 'success', 'message': 'Password saved.'})

    @http.route(
        '/odutech/portal/api/auth/logout',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    def logout(self, **kwargs):
        request.portal_employee._portal_revoke_access_token()
        return json_response({'status': 'success', 'message': 'Logged out.'})
