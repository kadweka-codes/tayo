# -*- coding: utf-8 -*-
from odoo import api, models, fields
from datetime import datetime,date,timedelta
from odoo.exceptions import UserError, ValidationError



class work_type(models.Model):
    _name = "ti.atten.policy"
    name = fields.Char(string="plicy")
    security = fields.Boolean(string="Time Plocy for Security")
    Driver = fields.Boolean(string="Time Plocy for Driver")
    cleaner = fields.Boolean(string="Time Plocy for Cleaner")
    technician = fields.Boolean(string="Time Plocy for Technician")
    imam = fields.Boolean(string="Time Plocy for imam")

    security_time = fields.Integer(string='Minutes For Security')
    Driver_time = fields.Integer(string='Minutes For Driver')
    cleaner_time = fields.Integer(string='Minutes For Cleaner')
    technician_time = fields.Integer(string='Minutes For Technician')
    imam_time = fields.Integer(string='Minutes For imam')

class work_type(models.Model):
    _name = "ti.work.type"
    _rec_name = 'name'
    name = fields.Char(string="Name")

class atteendance_roster(models.Model):
    _name = "ti.attendance.roster"
    _rec_name = 'user_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    date = fields.Date(string="Date",tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', readonly=True,tracking=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True,tracking=True)
    direct_line = fields.One2many('ti.attendance.roster.line', 'roster_id', string='roster_id')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
    ], string='Status', default='draft' ,tracking=True)
    def make_work(self):
        # self.direct_line.unlink()
        emps = self.env['hr.employee'].search([('company_id','=',self.company_id.id),('ti_employee_type','in',['cleaner','imam'])])
        pl = self.env['ti.atten.policy'].search([])
        for em in emps:
            tmmt = 0
            if em.ti_employee_type == 'security':
                if pl.security == True:
                    tmmt = pl.security_time
            elif em.ti_employee_type == 'Driver':
                if pl.Driver == True:
                    tmmt = pl.Driver_time
            elif em.ti_employee_type == 'cleaner':
                if pl.cleaner == True:
                    tmmt = pl.cleaner_time
            elif em.ti_employee_type == 'technician':
                if pl.technician == True:
                    tmmt = pl.technician_time
            elif em.ti_employee_type == 'imam':
                if pl.imam == True:
                    tmmt = pl.imam_time
            tmmt = int(tmmt)
            if em.ti_employee_type == 'cleaner':
                tm = 6.5
                th = 6
                tmm = 30 + tmmt
                for rec in range(30):
                    start_datetime = datetime.strftime(datetime.now(), f'%Y-%m-%d {th}:{tmm}:%S')
                    start_datetime = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                    start_datetime = start_datetime - timedelta(hours=5, minutes=0)
                    if tmmt <= 0:
                        start_datetime = start_datetime - timedelta(days=50, minutes=0)

                    self.env['ti.attendance.roster.line'].create({'datetime2':start_datetime,'roster_id':self.id,'time':tm,'employee_id':em.id,'ti_employee_type':em.ti_employee_type,'date':self.date})
                    tm = tm + 0.5
                    if tmm == 30 + tmmt:
                        tmm = tmmt
                        th += 1
                    else:
                        tmm = 30 + tmmt
            else:

                start_datetime = datetime.strftime(datetime.now(), f'%Y-%m-%d {4}:{tmmt}:%S')
                start_datetime = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                start_datetime = start_datetime - timedelta(hours=5, minutes=0)
                if tmmt <= 0:
                    start_datetime = start_datetime - timedelta(days=50, minutes=0)

                self.env['ti.attendance.roster.line'].create({'datetime2':start_datetime,'roster_id': self.id, 'time': 4, 'employee_id': em.id,'ti_employee_type': em.ti_employee_type,'date':self.date})
                start_datetime = datetime.strftime(datetime.now(), f'%Y-%m-%d {6}:{30+tmmt}:%S')
                print(start_datetime,5+tmmt,'rrrrrrrr',tmmt)
                start_datetime = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                start_datetime = start_datetime - timedelta(hours=5, minutes=0)
                if tmmt <= 0:
                    start_datetime = start_datetime - timedelta(days=50, minutes=0)
                self.env['ti.attendance.roster.line'].create({'datetime2':start_datetime,'roster_id': self.id, 'time': 6.5, 'employee_id': em.id,'ti_employee_type': em.ti_employee_type,'date':self.date})
                start_datetime = datetime.strftime(datetime.now(), f'%Y-%m-%d {8}:{30 + tmmt}:%S')
                print(start_datetime, 5 + tmmt, 'rrrrrrfffrrrrr', tmmt)
                start_datetime = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                start_datetime = start_datetime - timedelta(hours=5, minutes=0)
                if tmmt <= 0:
                    start_datetime = start_datetime - timedelta(days=50, minutes=0)
                self.env['ti.attendance.roster.line'].create({'datetime2':start_datetime,'roster_id': self.id, 'time': 8.5, 'employee_id': em.id,'ti_employee_type': em.ti_employee_type,'date':self.date})

        self.state = 'confirmed'
    def action_done(self):
        self.state = 'done'


class atteendance_roster(models.Model):
    _name = "ti.attendance.roster.line"

    ti_employee_type = fields.Selection([('security', 'Security'), ('Driver', 'Driver'),('cleaner','Cleaner'),('technician','Technician'),('imam','Imam')],related='employee_id.ti_employee_type', string="Type")

    display_type = fields.Selection(
        selection=[
            ('line_section', "Section"),
            ('line_note', "Note"),
        ],
        default=False)

    name = fields.Date('section')
    date = fields.Char('Date')
    datetime2 = fields.Datetime(string="Date Time")
    attendance_marked = fields.Datetime(string="Marked Time")
    attendance_marked_str = fields.Char(string="Marked Time")

    datetimecheck = fields.Boolean(string="Date Time")
    employee_id = fields.Many2one('hr.employee',string="Employee",tracking=True)
    work_id = fields.Many2one('ti.work.type',string="Work")
    roster_id = fields.Many2one('ti.attendance.roster',string="Name")
    time = fields.Float(string="Time")
    user_id = fields.Many2one('res.users', string='Marked By', readonly=True)

    @api.onchange('work_id')
    def onchange_duration(self):
        for rec in self:

            # attendance_marked_str = attendance_marked.strftime('%H:%M')

            # if rec.employee_id.ti_employee_type == 'cleaner':
            if rec.datetime2:
                rec.user_id = self.env.user.id
                attendance_marked = datetime.now()
                if datetime.now() > rec.datetime2:
                    rec.work_id = False
                    rec.datetimecheck = True
                    # raise ValidationError("You cannot mark after 10 minutes of scheduled time")

    @api.constrains('time')
    def get_time(self):
        for rec in self:
            planned_exit_time_str = str(rec.time)
            h = 0
            s = 0

            pl = self.env['ti.atten.policy'].search([])
            for em in rec.employee_id:
                tmmt = 0
                if em.ti_employee_type == 'security':
                    if pl.security == True:
                        tmmt = pl.security_time
                elif em.ti_employee_type == 'Driver':
                    if pl.Driver == True:
                        tmmt = pl.Driver_time
                elif em.ti_employee_type == 'cleaner':
                    if pl.cleaner == True:
                        tmmt = pl.cleaner_time
                elif em.ti_employee_type == 'technician':
                    if pl.technician == True:
                        tmmt = pl.technician_time
                elif em.ti_employee_type == 'imam':
                    if pl.imam == True:
                        tmmt = pl.imam_time
                tmmt = int(tmmt)
            if tmmt > 0:
                for i in planned_exit_time_str:
                    h = h + 1
                    if i == '.':
                        hour = planned_exit_time_str[0:h - 1]
                        if len(hour) == 1:
                            hour = '0' + hour

                        mints = planned_exit_time_str[h:]
                        mints = float(mints) * 6
                        mints = str(int(mints))
                        if len(mints) == 1:
                            mints = '0' + mints
                        if len(mints) > 2:
                            mints = mints[:2]

                        # start_datetime = datetime.strftime(rec.check_out, f'%Y-%m-%d {hour}:{mints + tmmt}:%S')
                        print(hour,mints,tmmt)
                        start_datetime = datetime.strftime(datetime.now(), f'%Y-%m-%d {hour}:{int(mints) + tmmt}:%S')
                        start_datetime = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
                        start_datetime = start_datetime - timedelta(hours=5, minutes=0)
                        if tmmt <= 0:
                            start_datetime = start_datetime - timedelta(days=50, minutes=0)


                        rec.datetime2 = start_datetime


