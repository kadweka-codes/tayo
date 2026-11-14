from odoo import http

from ..models.hr_employee import PORTAL_PROFILE_PICTURE_FIELD, PORTAL_SELF_EDITABLE_FIELDS
from .auth import json_response, portal_auth, portal_license, read_json_body


def _employee_update_values():
    """JSON body, or a multipart upload whose file field is profile_picture."""
    incoming = http.request.httprequest
    if (incoming.mimetype or '').lower() == 'multipart/form-data':
        values = {}
        for key in PORTAL_SELF_EDITABLE_FIELDS:
            if key in incoming.form:
                values[key] = incoming.form.get(key)
        upload = incoming.files.get(PORTAL_PROFILE_PICTURE_FIELD)
        if upload is not None and upload.filename:
            values[PORTAL_PROFILE_PICTURE_FIELD] = upload.read()
        elif PORTAL_PROFILE_PICTURE_FIELD in incoming.form:
            values[PORTAL_PROFILE_PICTURE_FIELD] = incoming.form.get(PORTAL_PROFILE_PICTURE_FIELD)
        return values
    return read_json_body()


class EmployeePortalApi(http.Controller):

    @http.route(
        '/odutech/portal/api/employees',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def list_employees(self, **kwargs):
        employee = http.request.portal_employee
        coworkers = employee._portal_company_employees()
        return json_response({
            'status': 'success',
            'data': [coworker._portal_list_values(employee) for coworker in coworkers],
        })

    @http.route(
        '/odutech/portal/api/employees/listing',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def employee_listing(self, **kwargs):
        employee = http.request.portal_employee
        coworkers = employee._portal_company_employees()
        return json_response({
            'status': 'success',
            'data': [coworker._portal_listing_values() for coworker in coworkers],
        })

    @http.route(
        '/odutech/portal/api/employees',
        type='http',
        auth='public',
        methods=['PUT', 'PATCH'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def update_employee(self, **kwargs):
        employee = http.request.portal_employee
        body = _employee_update_values()
        if body is None:
            return json_response({'status': 'failed', 'message': 'Send a JSON object.'}, 400)
        if not body:
            return json_response({'status': 'failed', 'message': 'No values to update.'}, 400)

        message = employee._portal_update_own_information(body)
        if message:
            return json_response({'status': 'failed', 'message': message}, 400)
        return json_response({'status': 'success', 'data': employee._portal_api_values()})
