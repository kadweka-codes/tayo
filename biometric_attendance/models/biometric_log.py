
from odoo import models, fields

class BiometricLog(models.Model):
    _name = 'biometric.log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Raw Biometric Attendance Log'

    employee_code = fields.Char(string='Employee Code', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee')
    punch_time = fields.Datetime(string='Punch Time', required=True)
    punch_state = fields.Selection([('0', 'Check In'), ('1', 'Check Out')], string='Punch State')
    is_processed = fields.Boolean(string='Processed', default=False)
    ztech_tracking = fields.Char(string='ZTEch Tracking')