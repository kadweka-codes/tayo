from odoo import api, fields, models

TYPE = [
    ('OPERATION_COST', 'Operation Cost'),
    ('SALES_TARGET', 'Sales Target'),
    ('CUSTOMER_RETENTION', 'Customer Retention'),
    ('COST_OF_SALE', 'Cost of Sale'),
    ('WAITER_COMMISSION', 'Waiter Commission'),
    ('COOK_COMMISSION', 'Cook Commission'),
]
DEPARTMENT_CHOICES = [
    ('FRONT_OFFICE', 'Front of house commission pool'),
    ('BACK_HOUSE', 'Back of house commission pool'),
    ('ADMINISTRATION', 'Administration commission pool'),
    ('SUBORDINATE', 'Subordinates commission pool')
]

class HrDepartmentPools(models.Model):
    _name = 'hr.department.pool'
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = 'HR Department Pools'

    name = fields.Char(string='Pool Name', tracking=True)
    percentage = fields.Float(string='Percentage', required=True, tracking=True)
    type = fields.Selection(TYPE, default='OPERATION_COST', required=True, tracking=True)


class Department(models.Model):
    _inherit = 'hr.department'
    _description = 'Department'

    commission_id = fields.Many2one('employee.commission', string='Commission', tracking=True, required=True)
    department_choice = fields.Selection(DEPARTMENT_CHOICES, string="Department Category", required=True,
                                         default='FRONT_OFFICE')