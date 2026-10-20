from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    travel_allowance = fields.Float(string="Travel Allowance")
    holiday_allowance = fields.Float(string="Holiday Pay")
    meal_allowance = fields.Float(string="Meal Allowance")
    medical_allowance = fields.Float(string="Medical Allowance")
    house_allowance = fields.Float(string="House Allowance")


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Shown on the employee form next to wage. Stored on the current hr.version.
    travel_allowance = fields.Float(related='version_id.travel_allowance', readonly=False)
    holiday_allowance = fields.Float(related='version_id.holiday_allowance', readonly=False)
    meal_allowance = fields.Float(related='version_id.meal_allowance', readonly=False)
    medical_allowance = fields.Float(related='version_id.medical_allowance', readonly=False)
    house_allowance = fields.Float(related='version_id.house_allowance', readonly=False)
