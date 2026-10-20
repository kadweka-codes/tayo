# -*- coding: utf-8 -*-
import base64
from email.policy import default

from odoo import models, fields, api, _
import requests
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    is_paid_leave = fields.Boolean(string="Paid Leave",default=False)
    is_unpaid_leave = fields.Boolean(string="Unpaid Leave",default=False)



class ResCompany(models.Model):
    _inherit = 'res.company'

    employee_budget_number = fields.Integer(string="Employee Budget Number",default=10)

    employee_on_verbal_warning = fields.Integer(string="Employee On Verbal Warning", default=10)
    employee_on_written_warning_1 = fields.Integer(string="Employee On Written Warning (One)", default=10)
    employee_on_written_warning_2 = fields.Integer(string="Employee On Written Warning (Two)", default=10)
    employees_suspended = fields.Integer(string="Employees Suspended", default=10)
    employees_under_probation = fields.Integer(string="Employees On Probation", default=10)

    employee_on_final_warning = fields.Integer(string="Employee On Verbal / Final Warning", default=10)
    employee_terminated_due_discipline = fields.Integer(string="Employee On Employee Termination Due to Discipline", default=10)
    number_of_new_hired_employees = fields.Integer(string="Number Of New Employees", default=10)

    employees_on_active_duty = fields.Integer(string="Employees on Duty / Active Staff", default=10)
    employees_on_paid_leave = fields.Integer(string="Employees on Paid Leave",default=10)
    employees_on_unpaid_leave = fields.Integer(string="Employees on UnPaid Leave", default=10)
    overall_default_attendance_rate = fields.Integer(string="Overall Attendance Rate", default=10)
    employee_late_arrivals_budget = fields.Integer(string="Late Arrivals", default=10)
    employee_absenteeism_rate = fields.Integer(string="Absenteeism Rate", default=10)

class Employee(models.Model):
    _inherit = 'hr.employee'

    employee_number = fields.Char(string="Employee Number", unique=True, tracking=True, groups='hr.group_hr_user,base.group_system')
    warning_ids= fields.One2many("hr.employee.warning","employee_id",string="Warning Type")


class HrEmployeeWarning(models.Model):
    _name = 'hr.employee.warning'
    _description = 'Employee Warning Record'
    _order = 'warning_date desc'

    warning_date = fields.Date(string="Date of Warning", default=fields.Date.context_today)
    employee_id = fields.Many2one('hr.employee', string="Employee", required=True)
    warning_type = fields.Selection([
        ('verbal', 'Verbal Warning'),
        ('written_warning_1', 'Written warning 1'),
        ('written_warning_2', 'Written warning 2'),
        ('final_warning', 'Final Warning'),
        ('probation', 'Probation'),
        ('suspension', 'Suspension'),
        ('termination', 'Termination'),
    ], string="Type of Warning", required=True)
    current_warning_state = fields.Selection([
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ],string="Current Warning State", required=True)
    description = fields.Text(string="Reason/Description")
