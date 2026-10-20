# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time, timedelta

import requests

from odoo import models, fields, _
from odoo.exceptions import UserError
from odoo.osv.expression import OR
import logging

_logger = logging.getLogger(__name__)


class WorkAttendance(models.Model):
    _name = "work.attendance.work"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    employee_id = fields.Many2one("hr.employee", string="Employee", tracking=True)
    department = fields.Many2one("hr.department", string="Department", tracking=True,
                                 related="employee_id.department_id")
    position = fields.Many2one("hr.job", string="Position", tracking=True, related="employee_id.job_id")
    punch_time = fields.Datetime(string="Punch Time", tracking=True)
    punch_state = fields.Char(string="Punch State", tracking=True)
    punch_state_display = fields.Char(string="Punch State Display", tracking=True)
    verify_type = fields.Char(string="Verify Type", tracking=True)
    verify_type_display = fields.Char(string="Verify Type Display")
    upload_time = fields.Datetime(string="Upload Time")
    terminal_alias = fields.Char(string="Terminal Alias")
    contra_entry_created = fields.Boolean(string='Contra Entry Created', default=False)
    contra_entry_id = fields.Integer(string='Contra Entry Id')
    transaction_id = fields.Integer(string='transaction_id')


class Attendance(models.Model):
    _name = 'attendance.attendance'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    ip_address = fields.Char(string="IP Address", tracking=True)
    port = fields.Char(string="Port", tracking=True)
    username = fields.Char(string="Username", tracking=True)
    password = fields.Char(string="Password")
    userId = fields.Many2one("res.users", string="User", default=lambda self: self.env.user)
    last_update_time = fields.Date(string="Last Update Time", tracking=True)
    confirmed = fields.Boolean(string='Confirmed', default=False)
    active = fields.Boolean(string='Active', default=True)
    page = fields.Integer(string="Page", tracking=True, default=1)
    limit = fields.Integer(string="Limit", tracking=True, default=100)
    last_pull_status = fields.Boolean(string='Last Sync Status', default=False, tracking=True)
    last_pull_message = fields.Char(string="Last Sync Message", tracking=True)
    last_sync_attempt = fields.Datetime(string="Last Attempt Time", tracking=True)

    def check_update_time(self):
        if self.last_update_time and self.last_update_time > fields.Date.today():
            raise UserError(_("You can only execute this when the current date is on or after the last update."))

    def _device_base_url(self):
        self.ensure_one()
        base = (self.ip_address or '').rstrip('/')
        port = (self.port or '').strip()
        if base and '://' not in base:
            base = f'http://{base}'
        if port and base:
            scheme, rest = base.split('://', 1)
            host = rest.split('/')[0]
            path = rest[len(host):]
            if ':' not in host:
                base = f'{scheme}://{host}:{port}{path}'
        return base

    def _auth_headers(self):
        self.ensure_one()
        credentials = f"{self.username or ''}:{self.password or ''}"
        token = base64.b64encode(credentials.encode()).decode()
        return {
            'Authorization': f'Basic {token}',
            'Content-Type': 'application/json',
        }

    def fetch_employee_data(self):
        devices = self if self else self.search([('active', '=', True)])
        Employee = self.env['hr.employee'].sudo()
        for device in devices:
            page = 1
            try:
                while page <= 20:
                    url = f"{device._device_base_url()}/personnel/api/employees/?page={page}&page_size=200"
                    response = requests.get(url, headers=device._auth_headers(), timeout=20)
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get('code') not in (0, None) and not payload.get('data'):
                        break
                    rows = payload.get('data') or []
                    for row in rows:
                        code = row.get('emp_code')
                        email = row.get('email')
                        if not code and not email:
                            continue
                        domains = []
                        if code:
                            domains.append([('employee_number', '=', code)])
                            if 'registration_number' in Employee._fields:
                                domains.append([('registration_number', '=', code)])
                        if email:
                            domains.append([('work_email', '=', email)])
                        employee = Employee.search(OR(domains), limit=1) if domains else Employee
                        if not employee:
                            continue
                        vals = {}
                        if code:
                            vals['employee_number'] = code
                            if 'registration_number' in employee._fields:
                                vals['registration_number'] = code
                        if email:
                            vals['work_email'] = email
                        if row.get('mobile'):
                            vals['mobile_phone'] = row['mobile']
                        if row.get('full_name'):
                            vals['name'] = row['full_name']
                        if vals:
                            employee.write(vals)
                    if len(rows) < 200:
                        break
                    page += 1
                device.write({
                    'last_pull_status': True,
                    'last_pull_message': 'Employee directory synced',
                    'last_sync_attempt': fields.Datetime.now(),
                })
            except Exception as error:
                _logger.exception("Employee sync failed for device %s", device.id)
                device.write({
                    'last_pull_status': False,
                    'last_pull_message': str(error)[:200],
                    'last_sync_attempt': fields.Datetime.now(),
                })
        return True

    def fetch_data(self):
        devices = self if self else self.search([('active', '=', True)])
        employees = self.env['hr.employee'].search([
            ('active', '=', True),
            ('employee_number', '!=', False),
        ])
        emp_map = {emp.employee_number: emp.id for emp in employees}
        Log = self.env['biometric.log'].sudo()

        for device in devices:
            device.write({'last_sync_attempt': fields.Datetime.now()})
            base_date = device.last_update_time or fields.Date.today()
            if base_date > fields.Date.today():
                base_date = fields.Date.today()
            page = device.page or 1
            page_size = min(device.limit or 100, 200)
            new_logs_count = 0
            day_finished = False
            try:
                for _step in range(5):
                    start_time = datetime.combine(base_date, time.min).strftime('%Y-%m-%d %H:%M:%S')
                    end_time = datetime.combine(base_date, time.max).strftime('%Y-%m-%d %H:%M:%S')
                    url = (
                        f"{device._device_base_url()}/iclock/api/transactions/"
                        f"?page={page}&page_size={page_size}&start_time={start_time}&end_time={end_time}"
                    )
                    response = requests.get(url, headers=device._auth_headers(), timeout=20)
                    response.raise_for_status()
                    rows = response.json().get('data') or []
                    tracking_ids = [str(row.get('id')) for row in rows if row.get('id') is not None]
                    existing = set(Log.search([('ztech_tracking', 'in', tracking_ids)]).mapped('ztech_tracking')) if tracking_ids else set()
                    for row in rows:
                        emp_id = emp_map.get(row.get('emp_code'))
                        tracking = str(row.get('id') or '')
                        if not emp_id or not tracking or tracking in existing:
                            continue
                        punch_state = str(row.get('punch_state')) if row.get('punch_state') is not None else False
                        if punch_state not in ('0', '1'):
                            punch_state = False
                        Log.create({
                            'employee_code': row.get('emp_code'),
                            'employee_id': emp_id,
                            'punch_time': row.get('punch_time'),
                            'punch_state': punch_state,
                            'ztech_tracking': tracking,
                        })
                        existing.add(tracking)
                        new_logs_count += 1
                    if len(rows) < page_size:
                        day_finished = True
                        break
                    page += 1
                vals = {
                    'page': 1 if day_finished else page,
                    'last_pull_status': True,
                    'last_pull_message': f"Synced {new_logs_count} logs for {base_date}.",
                    'confirmed': True,
                }
                if day_finished and base_date < fields.Date.today():
                    vals['last_update_time'] = base_date + timedelta(days=1)
                elif day_finished:
                    vals['last_update_time'] = base_date
                else:
                    vals['last_update_time'] = base_date
                device.write(vals)
            except Exception as error:
                _logger.exception("Attendance sync failed for device %s", device.id)
                device.write({
                    'page': page,
                    'last_pull_status': False,
                    'last_pull_message': f"Failed to sync {base_date}: {error}"[:200],
                })
        return True

    def process_attendance_logs(self):
        Log = self.env['biometric.log'].sudo()
        unmapped = Log.search([
            ('is_processed', '=', False),
            ('employee_id', '=', False),
            ('employee_code', '!=', False),
        ], limit=500)
        if unmapped:
            employees = self.env['hr.employee'].search([
                ('employee_number', 'in', list(set(unmapped.mapped('employee_code')))),
            ])
            mapping = {employee.employee_number: employee.id for employee in employees}
            for log in unmapped:
                employee_id = mapping.get(log.employee_code)
                if employee_id:
                    log.employee_id = employee_id

        logs = Log.search([
            ('is_processed', '=', False),
            ('employee_id', '!=', False),
            ('punch_time', '!=', False),
        ], order='punch_time asc', limit=1000)
        grouped = {}
        for log in logs:
            punch = fields.Datetime.to_datetime(log.punch_time)
            if not punch:
                continue
            grouped.setdefault((log.employee_id.id, punch.date()), []).append(log)

        AttendanceRecord = self.env['hr.attendance'].sudo()
        for (employee_id, log_date), day_logs in grouped.items():
            try:
                with self.env.cr.savepoint():
                    day_logs.sort(key=lambda item: item.punch_time)
                    check_ins = [log for log in day_logs if log.punch_state == '0']
                    check_outs = [log for log in day_logs if log.punch_state == '1']
                    check_in = (check_ins or day_logs)[0].punch_time
                    check_out = False
                    if check_outs:
                        check_out = check_outs[-1].punch_time
                    elif len(day_logs) > 1:
                        check_out = day_logs[-1].punch_time
                    if check_out and check_out <= check_in:
                        check_out = False
                    existing = AttendanceRecord.search([
                        ('employee_id', '=', employee_id),
                        ('check_in', '>=', datetime.combine(log_date, time.min)),
                        ('check_in', '<=', datetime.combine(log_date, time.max)),
                    ], limit=1)
                    open_attendances = AttendanceRecord.search([
                        ('employee_id', '=', employee_id),
                        ('check_out', '=', False),
                    ])
                    for open_attendance in open_attendances:
                        if existing and open_attendance == existing:
                            continue
                        if open_attendance.check_in and open_attendance.check_in < check_in:
                            open_attendance.check_out = check_in
                    vals = {'check_in': check_in}
                    if check_out:
                        vals['check_out'] = check_out
                    if existing:
                        write_vals = {}
                        if check_out:
                            write_vals['check_out'] = check_out
                        if write_vals:
                            existing.write(write_vals)
                    else:
                        AttendanceRecord.create({
                            'employee_id': employee_id,
                            **vals,
                        })
                    Log.browse([log.id for log in day_logs]).write({'is_processed': True})
            except Exception:
                _logger.exception(
                    "Attendance log processing failed for employee %s on %s", employee_id, log_date
                )
        return True
