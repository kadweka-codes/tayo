import json

from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    employee_data_json = fields.Text(string="Employee Data", compute="_get_employee_data_json")

    @api.depends('current_user_id')
    def _get_employee_data_json(self):
        for record in self:
            current_user = record.current_user_id
            employee = self.env['hr.employee']
            if current_user:
                employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)
            record.employee_data_json = json.dumps(employee.wallet_values() if employee else {})

    @api.model
    def _load_pos_data_fields(self, config_id):
        parent = getattr(super(), '_load_pos_data_fields', None)
        fields_list = list(parent(config_id)) if parent else []
        if 'employee_data_json' not in fields_list:
            fields_list.append('employee_data_json')
        return fields_list
