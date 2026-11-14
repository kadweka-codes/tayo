from odoo import fields, http
from odoo.exceptions import UserError

from .auth import json_response, portal_auth, portal_license, read_json_body

LEAVE_STATUS = {
    'confirm': 'To Approve',
    'refuse': 'Refused',
    'validate1': 'Second Approval',
    'validate': 'Approved',
    'cancel': 'Cancelled',
}
ALLOCATION_STATUS = {
    'confirm': 'To Approve',
    'refuse': 'Refused',
    'validate1': 'Second Approval',
    'validate': 'Approved',
}
REQUEST_UNITS = {'day', 'half_day', 'hour'}
VALIDATION_TYPES = {'no_validation', 'hr', 'manager', 'both'}
TYPE_FIELDS = {
    'name': 'name',
    'requires_allocation': 'requires_allocation',
    'request_unit': 'request_unit',
    'unpaid': 'unpaid',
    'active': 'active',
    'employee_requests': 'employee_requests',
    'support_document': 'support_document',
    'leave_validation_type': 'leave_validation_type',
    'allocation_validation_type': 'allocation_validation_type',
}


def _json_body():
    body = read_json_body()
    if body is None:
        raise UserError("Send a JSON object.")
    return body


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes')
    return bool(value)


def _as_date(value, label):
    if value in (None, False, ''):
        return False
    if not isinstance(value, str):
        raise UserError("%s must be a date like 2026-11-16." % label)
    try:
        return fields.Date.to_date(value)
    except ValueError as error:
        raise UserError("%s must be a date like 2026-11-16." % label) from error


def _as_float(value, label):
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise UserError("%s must be a number." % label) from error


def _as_int(value, label):
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise UserError("%s must be an id." % label) from error


def _choice(value, allowed, label):
    if value not in allowed:
        raise UserError("%s must be one of: %s." % (label, ', '.join(sorted(allowed))))
    return value


def _date_text(value):
    return fields.Date.to_string(value) if value else ''


def _employee():
    return http.request.portal_employee


def _missing():
    return json_response({'status': 'failed', 'message': 'Record not found.'}, 404)


def _leave_type_domain(employee):
    return [
        '|',
        ('company_id', '=', False),
        ('company_id', '=', employee.company_id.id),
    ]


def _leave_type(employee, type_id):
    record = http.request.env['hr.leave.type'].sudo().browse(type_id).exists()
    if not record or record.company_id and record.company_id.id != employee.company_id.id:
        return http.request.env['hr.leave.type']
    return record


def _own(model, employee, record_id):
    record = http.request.env[model].sudo().browse(record_id).exists()
    if not record or record.employee_id.id != employee.id:
        return http.request.env[model]
    return record


def _type_values(record):
    return {
        'id': record.id,
        'name': record.name or '',
        'requires_allocation': bool(record.requires_allocation),
        'request_unit': record.request_unit or '',
        'unpaid': bool(record.unpaid),
        'active': bool(record.active),
        'employee_requests': bool(record.employee_requests),
        'support_document': bool(record.support_document),
        'leave_validation_type': record.leave_validation_type or '',
        'allocation_validation_type': record.allocation_validation_type or '',
        'company_id': record.company_id.id or None,
        'company': record.company_id.name or '',
    }


def _allocation_values(record):
    return {
        'id': record.id,
        'name': record.name or '',
        'leave_type_id': record.holiday_status_id.id or None,
        'leave_type': record.holiday_status_id.name or '',
        'employee_id': record.employee_id.id,
        'date_from': _date_text(record.date_from),
        'date_to': _date_text(record.date_to),
        'number_of_days': record.number_of_days,
        'notes': record.notes or '',
        'state': record.state or '',
        'status': ALLOCATION_STATUS.get(record.state, record.state or ''),
    }


def _leave_values(record):
    return {
        'id': record.id,
        'name': record.sudo().private_name or record.name or '',
        'leave_type_id': record.holiday_status_id.id or None,
        'leave_type': record.holiday_status_id.name or '',
        'employee_id': record.employee_id.id,
        'request_date_from': _date_text(record.request_date_from),
        'request_date_to': _date_text(record.request_date_to),
        'number_of_days': record.number_of_days,
        'notes': record.notes or '',
        'state': record.state or '',
        'status': LEAVE_STATUS.get(record.state, record.state or ''),
    }


def _type_vals(body, creating):
    vals = {}
    if creating and not (body.get('name') or '').strip():
        raise UserError("name is required.")
    for key, field_name in TYPE_FIELDS.items():
        if key not in body:
            continue
        value = body[key]
        if field_name == 'name':
            value = (value or '').strip()
            if not value:
                raise UserError("name cannot be empty.")
        elif field_name in ('requires_allocation', 'unpaid', 'active', 'employee_requests', 'support_document'):
            value = _as_bool(value)
        elif field_name == 'request_unit':
            value = _choice(value, REQUEST_UNITS, 'request_unit')
        elif field_name in ('leave_validation_type', 'allocation_validation_type'):
            value = _choice(value, VALIDATION_TYPES, key)
        vals[field_name] = value
    if creating and not vals:
        raise UserError("No values to create.")
    return vals


def _require_own_type(employee, record):
    if not record.company_id or record.company_id.id != employee.company_id.id:
        raise UserError("This leave type is shared and cannot be changed from the portal.")


class LeavePortalApi(http.Controller):

    @http.route(
        '/odutech/portal/api/leave-types',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def list_leave_types(self, **kwargs):
        employee = _employee()
        records = http.request.env['hr.leave.type'].sudo().search(
            _leave_type_domain(employee),
            order='sequence, id',
        )
        return json_response({
            'status': 'success',
            'data': [_type_values(record) for record in records],
        })

    @http.route(
        '/odutech/portal/api/leave-types/<int:type_id>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def get_leave_type(self, type_id, **kwargs):
        record = _leave_type(_employee(), type_id)
        if not record:
            return _missing()
        return json_response({'status': 'success', 'data': _type_values(record)})

    @http.route(
        '/odutech/portal/api/leave-types',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def create_leave_type(self, **kwargs):
        employee = _employee()
        vals = _type_vals(_json_body(), creating=True)
        vals['company_id'] = employee.company_id.id
        record = http.request.env['hr.leave.type'].sudo().create(vals)
        return json_response({'status': 'success', 'data': _type_values(record)})

    @http.route(
        '/odutech/portal/api/leave-types/<int:type_id>',
        type='http',
        auth='public',
        methods=['PUT', 'PATCH'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def update_leave_type(self, type_id, **kwargs):
        employee = _employee()
        record = _leave_type(employee, type_id)
        if not record:
            return _missing()
        _require_own_type(employee, record)
        vals = _type_vals(_json_body(), creating=False)
        if not vals:
            raise UserError("No values to update.")
        record.write(vals)
        return json_response({'status': 'success', 'data': _type_values(record)})

    @http.route(
        '/odutech/portal/api/leave-types/<int:type_id>',
        type='http',
        auth='public',
        methods=['DELETE'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def delete_leave_type(self, type_id, **kwargs):
        employee = _employee()
        record = _leave_type(employee, type_id)
        if not record:
            return _missing()
        _require_own_type(employee, record)
        record.unlink()
        return json_response({'status': 'success', 'message': 'Deleted.'})

    @http.route(
        '/odutech/portal/api/leave-allocations',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def list_allocations(self, **kwargs):
        employee = _employee()
        domain = [('employee_id', '=', employee.id)]
        status = (http.request.params.get('status') or http.request.params.get('state') or '').strip()
        if status:
            _choice(status, set(ALLOCATION_STATUS), 'status')
            domain.append(('state', '=', status))
        records = http.request.env['hr.leave.allocation'].sudo().search(domain, order='id desc')
        return json_response({
            'status': 'success',
            'data': [_allocation_values(record) for record in records],
        })

    @http.route(
        '/odutech/portal/api/leave-allocations/<int:allocation_id>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def get_allocation(self, allocation_id, **kwargs):
        record = _own('hr.leave.allocation', _employee(), allocation_id)
        if not record:
            return _missing()
        return json_response({'status': 'success', 'data': _allocation_values(record)})

    @http.route(
        '/odutech/portal/api/leave-allocations',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def create_allocation(self, **kwargs):
        employee = _employee()
        body = _json_body()
        leave_type = _leave_type(employee, _as_int(body.get('leave_type_id'), 'leave_type_id'))
        if not leave_type:
            return _missing()
        vals = {
            'name': (body.get('name') or '').strip() or leave_type.name,
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'date_from': _as_date(body.get('date_from'), 'date_from') or fields.Date.context_today(employee),
            'number_of_days': _as_float(body.get('number_of_days', 1), 'number_of_days'),
            'allocation_type': 'regular',
        }
        if 'date_to' in body:
            vals['date_to'] = _as_date(body.get('date_to'), 'date_to')
        if 'notes' in body:
            vals['notes'] = body.get('notes') or False
        record = http.request.env['hr.leave.allocation'].sudo().create(vals)
        return json_response({'status': 'success', 'data': _allocation_values(record)})

    @http.route(
        '/odutech/portal/api/leave-allocations/<int:allocation_id>',
        type='http',
        auth='public',
        methods=['PUT', 'PATCH'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def update_allocation(self, allocation_id, **kwargs):
        employee = _employee()
        record = _own('hr.leave.allocation', employee, allocation_id)
        if not record:
            return _missing()
        if record.state != 'confirm':
            raise UserError("Only an allocation that is To Approve can be changed.")
        body = _json_body()
        vals = {}
        if 'leave_type_id' in body:
            leave_type = _leave_type(employee, _as_int(body.get('leave_type_id'), 'leave_type_id'))
            if not leave_type:
                return _missing()
            vals['holiday_status_id'] = leave_type.id
        if 'name' in body:
            vals['name'] = (body.get('name') or '').strip()
        if 'date_from' in body:
            vals['date_from'] = _as_date(body.get('date_from'), 'date_from')
        if 'date_to' in body:
            vals['date_to'] = _as_date(body.get('date_to'), 'date_to')
        if 'number_of_days' in body:
            vals['number_of_days'] = _as_float(body.get('number_of_days'), 'number_of_days')
        if 'notes' in body:
            vals['notes'] = body.get('notes') or False
        if not vals:
            raise UserError("No values to update.")
        record.write(vals)
        return json_response({'status': 'success', 'data': _allocation_values(record)})

    @http.route(
        '/odutech/portal/api/leave-allocations/<int:allocation_id>',
        type='http',
        auth='public',
        methods=['DELETE'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def delete_allocation(self, allocation_id, **kwargs):
        record = _own('hr.leave.allocation', _employee(), allocation_id)
        if not record:
            return _missing()
        record.unlink()
        return json_response({'status': 'success', 'message': 'Deleted.'})

    @http.route(
        '/odutech/portal/api/leaves',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def list_leaves(self, **kwargs):
        employee = _employee()
        domain = [('employee_id', '=', employee.id)]
        status = (http.request.params.get('status') or http.request.params.get('state') or '').strip()
        if status:
            _choice(status, set(LEAVE_STATUS), 'status')
            domain.append(('state', '=', status))
        records = http.request.env['hr.leave'].sudo().search(domain, order='id desc')
        return json_response({
            'status': 'success',
            'data': [_leave_values(record) for record in records],
        })

    @http.route(
        '/odutech/portal/api/leaves/<int:leave_id>',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def get_leave(self, leave_id, **kwargs):
        record = _own('hr.leave', _employee(), leave_id)
        if not record:
            return _missing()
        return json_response({'status': 'success', 'data': _leave_values(record)})

    @http.route(
        '/odutech/portal/api/leaves',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def create_leave(self, **kwargs):
        employee = _employee()
        body = _json_body()
        leave_type = _leave_type(employee, _as_int(body.get('leave_type_id'), 'leave_type_id'))
        if not leave_type:
            return _missing()
        date_from = _as_date(body.get('request_date_from'), 'request_date_from')
        date_to = _as_date(body.get('request_date_to'), 'request_date_to')
        if not date_from or not date_to:
            raise UserError("request_date_from and request_date_to are required.")
        vals = {
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': date_from,
            'request_date_to': date_to,
        }
        if body.get('name'):
            vals['name'] = str(body['name']).strip()
        if 'notes' in body:
            vals['notes'] = body.get('notes') or False
        record = http.request.env['hr.leave'].sudo().create(vals)
        return json_response({'status': 'success', 'data': _leave_values(record)})

    @http.route(
        '/odutech/portal/api/leaves/<int:leave_id>',
        type='http',
        auth='public',
        methods=['PUT', 'PATCH'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def update_leave(self, leave_id, **kwargs):
        employee = _employee()
        record = _own('hr.leave', employee, leave_id)
        if not record:
            return _missing()
        if record.state != 'confirm':
            raise UserError("Only a leave that is To Approve can be changed.")
        body = _json_body()
        vals = {}
        if 'leave_type_id' in body:
            leave_type = _leave_type(employee, _as_int(body.get('leave_type_id'), 'leave_type_id'))
            if not leave_type:
                return _missing()
            vals['holiday_status_id'] = leave_type.id
        if 'name' in body:
            vals['name'] = (body.get('name') or '').strip()
        if 'request_date_from' in body:
            vals['request_date_from'] = _as_date(body.get('request_date_from'), 'request_date_from')
        if 'request_date_to' in body:
            vals['request_date_to'] = _as_date(body.get('request_date_to'), 'request_date_to')
        if 'notes' in body:
            vals['notes'] = body.get('notes') or False
        if not vals:
            raise UserError("No values to update.")
        record.write(vals)
        return json_response({'status': 'success', 'data': _leave_values(record)})

    @http.route(
        '/odutech/portal/api/leaves/<int:leave_id>',
        type='http',
        auth='public',
        methods=['DELETE'],
        csrf=False,
        sitemap=False,
    )
    @portal_auth
    @portal_license
    def delete_leave(self, leave_id, **kwargs):
        record = _own('hr.leave', _employee(), leave_id)
        if not record:
            return _missing()
        if record.state not in ('confirm', 'validate1', 'cancel'):
            raise UserError("Approved or refused leave can only be removed by an administrator.")
        if record.date_from and record.date_from.date() < fields.Datetime.now().date():
            raise UserError("You can't delete a time off request that is in the past.")
        record.unlink()
        return json_response({'status': 'success', 'message': 'Deleted.'})
