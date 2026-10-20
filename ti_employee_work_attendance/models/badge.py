from datetime import datetime,date,timedelta
import calendar
from odoo import fields, models, api
class HrContract(models.Model):
    _inherit = 'hr.employee'
    ti_employee_type = fields.Selection([('security', 'Security'), ('Driver', 'Driver'),('cleaner','Cleaner'),('technician','Technician'),('imam','Imam')], string="Type", groups='hr.group_hr_user,base.group_system')


    def action_grant_badge_ti(self):
        """Wizard action for sending a badge to a chosen user"""
        dat = date.today()
        first_day = dat.replace(day=1)
        date_list = []
        # Get the last day of the month
        last_day = dat.replace(day=calendar.monthrange(dat.year, dat.month)[1])

        BadgeUser = self.env['gamification.badge.user']
        emps = self.env['hr.employee'].search([('ti_employee_type','in',['cleaner'])])
        att_list = []
        date1 = fields.Date.from_string(first_day)
        date2 = fields.Date.from_string(last_day)

        delta = date2 - date1
        max_ml = 0
        for n1 in range(delta.days + 1):
            res = date1 + timedelta(days=n1)
            date_list.append(res)
        for rec in emps:
            if rec.ti_employee_type == 'cleaner':
                cou = 0
                for d in date_list:
                    present = self.env["ti.attendance.roster.line"].search_count(
                        [('employee_id', '=', rec.id),('date', '=', d),
                         ('work_id','!=',False)])
                    if present>5:
                        cou += 6
                if cou > max_ml:
                    max_ml = cou
                att_list.append({rec.id:cou})

        max_value = max(value for d in att_list for value in d.values())

        # Extract keys with the maximum value
        keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]
        att_list = []
        date_f = last_day
        m_f = 0
        for rec in keys_with_max_value:
            cou = 0
            for d in date_list:
                present = self.env["ti.attendance.roster.line"].search_count(
                    [('employee_id', '=', rec), ('date', '=', d),
                      ('work_id', '!=', False)])
                if present > 5:
                    cou += 6
                    if cou == max_ml:
                        if d < date_f:
                            date_f = d
                            m_f = rec




        #     if cou > max_ml:
        #         max_ml = cou
        #     att_list.append({rec.id: cou})
        #
        # max_value = max(value for d in att_list for value in d.values())
        #
        # # Extract keys with the maximum value
        # keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]

        emps = self.env['hr.employee'].search([('id','=',m_f),('user_id','!=',False)])
        print(keys_with_max_value)
        for rec in emps:
            print(att_list)
            past_badge = BadgeUser.search([('user_id','=', rec.user_id.id)])
            if past_badge:
                badge = self.env['gamification.badge'].search([('level','=','gold')])
            else:
                badge = self.env['gamification.badge'].search([('level','=','silver')])
            badge = self.env['gamification.badge'].search([('level','=','bronze')],limit=1)

            BadgeUser.create({
                'user_id': rec.user_id.id,
                'sender_id': 1,
                'badge_id': badge.id,
                'comment': 'Good Attendance',
            })._send_badge()
            # BadgeUser = self.env['gamification.badge.user'].search([]).unlink()

        emps = self.env['hr.employee'].search([('ti_employee_type', 'in', ['imam'])])
        # att_list = []
        # date1 = fields.Date.from_string(first_day)
        # date2 = fields.Date.from_string(last_day)
        #
        # delta = date2 - date1
        # max_ml = 0
        # for n1 in range(delta.days + 1):
        #     res = date1 + timedelta(days=n1)
        #     date_list.append(res)
        max_ml = 0
        for rec in emps:
            if rec.ti_employee_type == 'imam':
                cou = 0
                for d in date_list:
                    present = self.env["ti.attendance.roster.line"].search(
                        [('employee_id', '=', rec.id), ('date', '=', d),
                         ('work_id', '!=', False)])
                    if len(present) == 3:
                        cou += 10
                    else:
                        for tt in present:
                            if tt.time == 6.5:
                                cou += 2
                            else:
                                cou += 4

                if cou > max_ml:
                    max_ml = cou
                att_list.append({rec.id: cou})

        max_value = max(value for d in att_list for value in d.values())

        # Extract keys with the maximum value
        keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]
        att_list = []
        date_f = last_day
        m_f = 0
        for rec in keys_with_max_value:
            cou = 0
            for d in date_list:

                present = self.env["ti.attendance.roster.line"].search(
                    [('employee_id', '=', rec), ('date', '=', d),
                     ('work_id', '!=', False)])
                if len(present) == 3:
                    cou += 10
                else:
                    for tt in present:
                        if tt.time == 6.5:
                            cou += 2
                        else:
                            cou += 4
                if cou == max_ml:
                    if d < date_f:
                        date_f = d
                        m_f = rec

        #     if cou > max_ml:
        #         max_ml = cou
        #     att_list.append({rec.id: cou})
        #
        # max_value = max(value for d in att_list for value in d.values())
        #
        # # Extract keys with the maximum value
        # keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]

        emps = self.env['hr.employee'].search([('id', '=', m_f), ('user_id', '!=', False)])
        print(keys_with_max_value)
        for rec in emps:
            print(att_list)
            past_badge = BadgeUser.search([('user_id', '=', rec.user_id.id)])
            if past_badge:
                badge = self.env['gamification.badge'].search([('level', '=', 'gold')])
            else:
                badge = self.env['gamification.badge'].search([('level', '=', 'silver')])
            badge = self.env['gamification.badge'].search([('level','=','bronze')],limit=1)

            BadgeUser.create({
                'user_id': rec.user_id.id,
                'sender_id': 1,
                'badge_id': badge.id,
                'comment': 'Good Attendance',
            })._send_badge()
            # BadgeUser = self.env['gamification.badge.user'].search([]).unlink()

        emps = self.env['hr.employee'].search([('ti_employee_type', 'in', ['technician'])])
        att_list = []
        date1 = fields.Date.from_string(first_day)
        date2 = fields.Date.from_string(last_day)

        delta = date2 - date1
        max_ml = 0
        for n1 in range(delta.days + 1):
            res = date1 + timedelta(days=n1)
            date_list.append(res)
        for rec in emps:
            if rec.ti_employee_type == 'technician':
                cou = 0

                present = self.env["ti.attendance.roster.line"].search_count(

                    [('employee_id', '=', rec.id), ('date', '>=', first_day),
                     ('date', '<=', last_day),('work_id', '!=', False)])


                if present < 11:
                    cou += 6


                    emps = self.env['hr.employee'].search([('id', '=', rec.id), ('user_id', '!=', False)])
                    for rec in emps:
                        print(att_list)
                        past_badge = BadgeUser.search([('user_id', '=', rec.user_id.id)])
                        if past_badge:
                            badge = self.env['gamification.badge'].search([('level', '=','gold')])
                        else:
                            badge = self.env['gamification.badge'].search([('level', '=','silver')])
                        badge = self.env['gamification.badge'].search([('level', '=', 'bronze')], limit=1)

                        BadgeUser.create({
                            'user_id': rec.user_id.id,
                            'sender_id': 1,
                            'badge_id': badge.id,
                            'comment': 'Good Attendance',
                        })._send_badge()

    def action_grant_badge_ti_backup(self):
        """Wizard action for sending a badge to a chosen user"""
        dat = date.today()
        first_day = dat.replace(day=1)

        # Get the last day of the month
        last_day = dat.replace(day=calendar.monthrange(dat.year, dat.month)[1])

        BadgeUser = self.env['gamification.badge.user']
        emps = self.env['hr.employee'].search([])
        att_list = []
        for rec in emps:
            present = self.env["hr.attendance"].search_count(
                [('employee_id', '=', rec.id),('check_in', '>=', first_day),
                 ('check_in', '<=', last_day)])
            att_list.append({rec.id:present})

        max_value = max(value for d in att_list for value in d.values())

        # Extract keys with the maximum value
        keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]
        att_list = []
        for rec in keys_with_max_value:
            present = self.env["hr.attendance"].search(
                [('employee_id', '=', rec), ('check_in', '>=', first_day),
                 ('check_in', '<=', last_day)]).mapped('worked_hours')
            att_list.append({rec: sum(present)})
        max_value = max(value for d in att_list for value in d.values())

        # Extract keys with the maximum value
        keys_with_max_value = [key for d in att_list for key, value in d.items() if value == max_value]

        emps = self.env['hr.employee'].search([('id','in',keys_with_max_value),('user_id','!=',False)])
        print(keys_with_max_value)
        for rec in emps:
            print(att_list)
            past_badge = BadgeUser.search([('user_id','=', rec.user_id.id)])
            if past_badge:
                badge = self.env['gamification.badge'].search([('level','=','gold')])
            else:
                badge = self.env['gamification.badge'].search([('level','=','silver')])

            BadgeUser.create({
                'user_id': rec.user_id.id,
                'sender_id': 1,
                'badge_id': badge.id,
                'comment': 'Good Attendance',
            })._send_badge()
            # BadgeUser = self.env['gamification.badge.user'].search([]).unlink()


