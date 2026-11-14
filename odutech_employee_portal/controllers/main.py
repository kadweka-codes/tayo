from odoo import http
from odoo.http import request


class OdutechPortalController(http.Controller):

    def _employee_from_token(self, token):
        if not token:
            return request.env['hr.employee']
        return request.env['hr.employee'].sudo().search([
            ('password_reset_token', '=', token),
        ], limit=1)

    @http.route(
        '/odutech/portal/set-password/<string:token>',
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=True,
        sitemap=False,
    )
    def set_password(self, token, password=None, password_confirm=None, **kwargs):
        employee = self._employee_from_token(token)
        expired = bool(employee) and not employee._portal_token_is_valid()
        invalid = not employee
        error = None

        if request.httprequest.method == 'POST' and employee and not expired:
            error = employee._set_portal_password(password, password_confirm)
            if not error:
                setup = employee._portal_company_setup()
                return request.render('odutech_employee_portal.portal_set_password_done', {
                    'employee_name': employee.name,
                    'portal_url': (setup.employee_portal_url or setup.portal_base_url()) if setup else '',
                    'company_name': employee.company_id.name,
                })

        return request.render('odutech_employee_portal.portal_set_password_form', {
            'token': token,
            'invalid': invalid,
            'expired': expired,
            'error': error,
            'employee_name': employee.name if employee and not invalid and not expired else '',
            'company_name': employee.company_id.name if employee and not invalid and not expired else '',
        })
