from odoo import fields, models, api
from datetime import datetime

class WorkingSchedule(models.Model):
    _inherit = "resource.calendar"

    default_working_schedule = fields.Boolean(default=False,string="Default Working Schedule")


# ('verbal', 'Verbal Warning'),
# ('written_warning_1', 'Written warning 1'),
# ('written_warning_2', 'Written warning 2'),
# ('final_warning', 'Final Warning'),
# ('probation', 'Probation'),
# ('suspension', 'Suspension'),
# ('termination', 'Termination'),
class AttendanceReport(models.TransientModel):
    _name = 'dilek.biometric_attendance.report'
    _description = 'Attendance Report'

    def get_staff_reporting_data_check(self, **kwargs):
        # 1. Parse Parameters
        start_date_str = kwargs.get('startDate')
        end_date_str = kwargs.get('endDate')
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        employee_budget_number = self.env.company.employee_budget_number or 0
        actual_employee_budget_number = self.env['hr.employee'].search_count([('active', '=', True)])
        active_company_value = self.env.company
        month_start = fields.Date.today().replace(day=1)
        current_employees_under_verbal_warning = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'verbal'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_written_warning1 = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'written_warning_1'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_written_warning2 = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'written_warning_2'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_final_warning_warning = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'final_warning'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_probation = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'probation'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_suspension = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'suspension'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        current_employees_under_termination = len(self.env['hr.employee.warning'].search([('warning_type', '=', 'termination'), ('warning_date', '>=', start_dt), ('warning_date', '<=', end_dt)]).mapped('employee_id'))
        employees_currently_hired = self.env['hr.employee'].search_count([('create_date', '>=', month_start)])

        current_employees_on_paid_leave  = len(self.env['hr.leave'].search([('holiday_status_id.is_paid_leave', '=', True), ('date_from', '>=', start_dt), ('date_from', '<=', end_dt)]).mapped('employee_id'))
        current_employees_on_unpaid_leave  = len(self.env['hr.leave'].search([('holiday_status_id.is_unpaid_leave', '=', True), ('date_from', '>=', start_dt), ('date_from', '<=', end_dt)]).mapped('employee_id'))
        def format_farqi(val, unit="", is_int=False):
            res = round(val, 0) if is_int else round(val, 1)
            if val < 0:
                return f"({abs(res)}{unit})"
            return f"{res}{unit}"

        report_data0 = [
            {
                "CABBIRKA": "Total Number of Employees",
                "ODOROSKA": f"{employee_budget_number}",
                "DHABTA": f"{actual_employee_budget_number}",
                "FARQIGA": format_farqi(employee_budget_number - actual_employee_budget_number, "", True)
            },
            {
                "CABBIRKA": "Number Of New Employees",
                "ODOROSKA": f"0",
                "DHABTA": f"{employees_currently_hired}",
                "FARQIGA": format_farqi(employees_currently_hired - 0, " Emp")
            },
            # {
            #     "CABBIRKA": "Employees on Duty / Active Staff",
            #     "ODOROSKA": f"{active_company_value.employees_on_active_duty}",
            #     "DHABTA": f"{current_employees_under_first_disciplinary_warning - 0}",
            #     "FARQIGA": f"{active_company_value.employees_on_active_duty - current_employees_under_first_disciplinary_warning}"
            # },
            {
                "CABBIRKA": "Employees on Paid Leave",
                "ODOROSKA": f"{active_company_value.employees_on_paid_leave}",
                "DHABTA": f"{current_employees_on_paid_leave}",
                "FARQIGA": f"{active_company_value.employees_on_paid_leave - current_employees_on_paid_leave}"
            },
            {
                "CABBIRKA": "Employees on UnPaid Leave",
                "ODOROSKA": f"{active_company_value.employees_on_unpaid_leave}",
                "DHABTA": f"{current_employees_on_unpaid_leave}",
                "FARQIGA": f"{active_company_value.employees_on_unpaid_leave - current_employees_on_unpaid_leave}"
            },
            {
                "CABBIRKA": "Employees Suspended",
                "ODOROSKA": f"{active_company_value.employees_suspended}",
                "DHABTA": f"{current_employees_under_suspension}",
                "FARQIGA": f"{active_company_value.employees_suspended - current_employees_under_suspension}"
            },
        ]
        report_data1 = [
            {
                "CABBIRKA": "Total Number of Employees",
                "ODOROSKA": f"{employee_budget_number}",
                "DHABTA": f"{actual_employee_budget_number}",
                "FARQIGA": format_farqi(employee_budget_number - actual_employee_budget_number, "",True)
            },
            {
                "CABBIRKA": "Verbal Warnings",
                "ODOROSKA": f"{active_company_value.employee_on_verbal_warning}",
                "DHABTA": f"{current_employees_under_verbal_warning:,}",
                "FARQIGA": format_farqi((active_company_value.employee_on_verbal_warning - current_employees_under_verbal_warning), " Emp")
            },
            {
                "CABBIRKA": "Written Warnings 1",
                "ODOROSKA": f"{active_company_value.employee_on_written_warning_1}",
                "DHABTA": f"{current_employees_under_written_warning1}",
                "FARQIGA": f"{active_company_value.employee_on_written_warning_1 - current_employees_under_written_warning1}"
            },
            {
                "CABBIRKA": "Written Warnings 2",
                "ODOROSKA": f"{active_company_value.employee_on_written_warning_2}",
                "DHABTA": f"{current_employees_under_written_warning2}",
                "FARQIGA": f"{active_company_value.employee_on_written_warning_2 - current_employees_under_written_warning2}"
            },
            {
                "CABBIRKA": "Final Warning",
                "ODOROSKA": f"{active_company_value.employee_on_final_warning}",
                "DHABTA": f"{current_employees_under_final_warning_warning}",
                "FARQIGA": f"{active_company_value.employee_on_final_warning - current_employees_under_final_warning_warning}"
            },
            {
                "CABBIRKA": "Probation",
                "ODOROSKA": f"{active_company_value.employees_under_probation}",
                "DHABTA": f"{current_employees_under_probation}",
                "FARQIGA": f"{active_company_value.employees_under_probation - current_employees_under_probation}"
            },
            {
                "CABBIRKA": "Termination",
                "ODOROSKA": f"{active_company_value.employee_terminated_due_discipline}",
                "DHABTA": f"{current_employees_under_termination}",
                "FARQIGA": f"{active_company_value.employee_terminated_due_discipline - current_employees_under_termination}"
            }
        ]

        return report_data1,report_data0

    def get_attendance_report_analysis(self, **kwargs):
        # 1. Parse Parameters
        start_date_str = kwargs.get('startDate')
        end_date_str = kwargs.get('endDate')
        start_dt = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_dt = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        hours_per_day = 0
        # 2. Get Dynamic Active Staff Count
        # This query fetches the sum of all currently active employees
        active_staff_count = self.env['hr.employee'].search_count([('active', '=', True)])
        active_staff_working_houses_per_day = self.env['resource.calendar'].sudo().search([
            ('active', '=', True), ('default_working_schedule', '=', True),
        ], limit=1)
        hours_per_day = active_staff_working_houses_per_day.hours_per_day or 0
        active_company_value = self.env.company
        total_budget_days = (end_dt - start_dt).days + 1
        # Actual days are workdays in the range that have already passed (<= today)
        effective_end_for_actual = min(end_dt, today)
        actual_work_days = max(0, (effective_end_for_actual - start_dt).days + 1)
        # Budget = Total Days * Active Staff * 8
        budget_hours = total_budget_days * active_staff_count * hours_per_day
        # Actual = Days Passed * Active Staff * 8 (Adjusted by sample actuals if needed)
        actual_hours = actual_work_days * active_staff_count * hours_per_day
        # 5. Helper for Formatting Variance
        def format_farqi(val, unit="", is_int=False):
            res = round(val, 0) if is_int else round(val, 1)
            if val < 0:
                return f"({abs(res)}{unit})"
            return f"{res}{unit}"
        # 6. Construct Final Table
        report_data = [
            {
                "CABBIRKA": "Wadarta Maalamaha Shaqada (Total Workdays)",
                "ODOROSKA": f"{total_budget_days} days",
                "DHABTA": f"{actual_work_days} days",
                "FARQIGA": format_farqi(actual_work_days - total_budget_days, " days", True)
            },
            {
                "CABBIRKA": "Wadarta Saacada Shaqo (Total Work Hours)",
                "ODOROSKA": f"{budget_hours:,} Hrs",
                "DHABTA": f"{actual_hours:,} Hrs",
                "FARQIGA": format_farqi(actual_hours - budget_hours, " Hrs")
            },
            {
                "CABBIRKA": "Xadiga Xaadiriska (Overall Attendance Rate)",
                "ODOROSKA": f"{active_company_value.overall_default_attendance_rate}",
                "DHABTA": f"{int((actual_hours / budget_hours) * 100) if budget_hours > 0 else 0}%",
                "FARQIGA": format_farqi(((actual_hours / budget_hours) * 100 if budget_hours > 0 else 100) - 100, "%")
            },
            {
                "CABBIRKA": "Celceliska Xadirka Maalinta (Avg Daily Attendance)",
                "ODOROSKA": f"{active_staff_count * hours_per_day:,} Hrs",
                "DHABTA": f"{active_staff_count * hours_per_day:,} Hrs",
                "FARQIGA": "0 Hrs"
            },
            {
                "CABBIRKA": "Tirada Maqnaashaha (# of Absenteeism)",
                "ODOROSKA": "0 Staff",
                "DHABTA": "0 Staff",
                "FARQIGA": "0 Staff"
            },
            {
                "CABBIRKA": "Xadiga Maqnaashaha (Absenteeism Rate)",
                "ODOROSKA": "1%",
                "DHABTA": "0%",
                "FARQIGA": "1%"
            },
            {
                "CABBIRKA": "Soo Daahida (Late Arrivals)",
                "ODOROSKA": "25 Hrs",
                "DHABTA": "84 Hrs",
                "FARQIGA": "(59) Hrs"
            },
            {
                "CABBIRKA": "Horay U bixida (Early Departures)",
                "ODOROSKA": "0 Min",
                "DHABTA": "0 Min",
                "FARQIGA": "0 Min"
            }
        ]

        return report_data