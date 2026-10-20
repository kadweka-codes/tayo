# wizard/hr_warning_wizard.py
from odoo import models, fields, api

class HrWarningWizard(models.TransientModel):
    _name = 'hr.warning.wizard'
    _description = 'Send Warning to Employees'

    warning_date = fields.Date(string="Date of Warning", default=fields.Date.context_today, required=True)
    employee_ids = fields.Many2many('hr.employee', string="Select Employees", required=True)
    warning_type = fields.Selection([
        ('verbal', 'Verbal Warning'),
        ('written_warning_1', 'Written warning 1'),
        ('written_warning_2', 'Written warning 2'),
        ('final_warning', 'Final Warning'),
        ('probation', 'Probation'),
        ('suspension', 'Suspension'),
        ('termination', 'Termination'),
    ], string="Type of Warning", required=True)
    reason = fields.Text(string="Warning Reason")

    def action_confirm_warning(self):
        for employee in self.employee_ids:
            existing_warning = self.env['hr.employee.warning'].sudo().search([('employee_id', '=', employee.id), ('current_warning_state', '!=', 'inactive')])
            for warning in existing_warning:
                warning.sudo().write({"current_warning_state": "inactive"})
            warning = self.env['hr.employee.warning'].create({
                'warning_date': self.warning_date,
                'employee_id': employee.id,
                'warning_type': self.warning_type,
                'description': self.reason,
                'current_warning_state':"active"
            })
            if warning and warning.warning_type == 'termination' or warning.warning_type == 'employee_resigned' or warning.warning_type == 'employee_suspended':
                warning.employee_id.user_id.sudo().write({'active': False})
        return {'type': 'ir.actions.act_window_close'}