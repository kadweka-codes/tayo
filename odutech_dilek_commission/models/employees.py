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
    )


class EmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    performance_pool_id = fields.Many2one(
        'hr.department.pool',
        related='employee_id.performance_pool_id',
        string="Performance Pool",
        readonly=True,
        compute_sudo=True,
    )


class EmployeeCommission(models.Model):
    _name = 'employee.commission'
    _description = 'Employee Commission'

    name = fields.Char(string="Name")
    commission = fields.Float(string="Commission", required=True)
