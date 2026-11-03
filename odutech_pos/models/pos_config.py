import json

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    employee_data_json = fields.Text(string="Employee Data", compute="_get_employee_data_json")

    @api.depends('current_user_id')
    def _get_employee_data_json(self):
        for record in self:
            employee = self.env['hr.employee']
            if record.current_user_id:
                employee = employee.search([('user_id', '=', record.current_user_id.id)], limit=1)
            values = employee.wallet_values() if len(employee) == 1 else {}
            record.employee_data_json = json.dumps(values)
