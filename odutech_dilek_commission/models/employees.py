from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    commission_id = fields.Many2one('employee.commission', string='Dynamic Commission', tracking=True)
    last_month_sales = fields.Float(string="Last Month Sales")


class Employee(models.Model):
    _inherit = 'hr.employee'

    performance_pool_id = fields.Many2one(
        'hr.department.pool',
        string="Performance Pool",
        tracking=True,
        groups='hr.group_hr_user,base.group_system',
    )


class EmployeeCommission(models.Model):
    _name = 'employee.commission'
    _description = 'Employee Commission'

    name = fields.Char(string="Name")
    commission = fields.Float(string="Commission", required=True)
