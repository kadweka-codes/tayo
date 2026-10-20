import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

COOK_MINUTES = 15.0
SERVE_MINUTES = 10.0
OPEN_KITCHEN_STATES = ('pending', 'assigned', 'preparing', 'ready')


class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    sequence = fields.Char(string="Seq", readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('sequence'):
                vals['sequence'] = self.env['ir.sequence'].next_by_code('restaurant.table')
        return super().create(vals_list)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    state = fields.Selection(selection_add=[
        ('assigned', 'Assigned To Cook'),
        ('kitchen', 'Being Prepared'),
        ('ready', 'Await Waiter'),
        ('served', 'Meal Served'),
    ], ondelete={
        'assigned': 'set default',
        'kitchen': 'set default',
        'ready': 'set default',
        'served': 'set default',
    })

    kitchen_state = fields.Selection([
        ('pending', 'Pending'),
        ('assigned', 'Assigned To Cook'),
        ('preparing', 'Being Prepared'),
        ('ready', 'Awaiting Waiter'),
        ('served', 'Served'),
    ], default='pending', tracking=True, index=True)
    assigned_cook = fields.Many2one('hr.employee', string="Cook", tracking=True, index=True)
    cook_assigned_at = fields.Datetime(string="Assigned At")
    cook_started_at = fields.Datetime(string="Prep Started")
    ready_at = fields.Datetime(string="Ready At")
    served_at = fields.Datetime(string="Served At")
    cook_stage_minutes = fields.Float(string="Cook time (minutes)")
    waiter_stage_minutes = fields.Float(string="Waiter time (minutes)")
    cook_used_time = fields.Float(string="Cook Delay (minutes)")
    waiter_used_time = fields.Float(string="Waiter Delay (minutes)")
    cook_delayed = fields.Boolean(string="Cook Delayed", index=True)
    waiter_delayed = fields.Boolean(string="Waiter Delayed", index=True)
    cook_notified = fields.Boolean(string="Cook Notified")
    waiter_notified = fields.Boolean(string="Waiter Notified")
    # Stage ids that already triggered a WhatsApp notice. Stored as JSON so the
    # order model does not require the Enterprise model pos.prep.stage.
    notified_whatsapp_stage_ids = fields.Json(string='WhatsApp stages sent', copy=False)
    cook_name = fields.Char(compute='_compute_kitchen_labels')
    waiter_name = fields.Char(compute='_compute_kitchen_labels')
    cook_employee_id = fields.Integer(compute='_compute_kitchen_labels')
    waiter_employee_id = fields.Integer(compute='_compute_kitchen_labels')

    @api.depends('assigned_cook', 'user_id')
    def _compute_kitchen_labels(self):
        for order in self:
            order.cook_name = order.assigned_cook.name or ''
            order.cook_employee_id = order.assigned_cook.id or 0
            order.waiter_name = order._waiter_display_name()
            employee = order._order_employee()
            order.waiter_employee_id = employee.id if employee else 0

    @api.model
    def _load_pos_preparation_data_fields(self):
        parent = getattr(super(), '_load_pos_preparation_data_fields', None)
        fields_list = list(parent()) if parent else []
        for name in (
            'cook_name', 'waiter_name', 'cook_employee_id', 'waiter_employee_id',
            'assigned_cook', 'employee_id',
        ):
            if name in self._fields and name not in fields_list:
                fields_list.append(name)
        return fields_list

    @api.model
    def kitchen_viewer(self):
        return self._kitchen_viewer()

    @api.model
    def kitchen_stage_roles(self):
        if 'pos.prep.stage' not in self.env or 'owner_role' not in self.env['pos.prep.stage']._fields:
            return {}
        stages = self.env['pos.prep.stage'].sudo().search([])
        return {stage.id: stage.owner_role or 'cook' for stage in stages}

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._copy_wallet_numbers()
            if order._is_restaurant_order() and order.lines:
                order._assign_kitchen_staff()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'lines' in vals or 'employee_id' in vals:
            for order in self:
                if 'employee_id' in vals:
                    order._copy_wallet_numbers()
                if order._is_restaurant_order() and order.lines and order.kitchen_state == 'pending':
                    order._assign_kitchen_staff()
        return res

    def _copy_wallet_numbers(self):
        for order in self:
            employee = order.employee_id if 'employee_id' in order._fields else self.env['hr.employee']
            if not employee and order.user_id:
                employee = self.env['hr.employee'].search([('user_id', '=', order.user_id.id)], limit=1)
            if employee:
                order.with_context(skip_kitchen_assign=True).write(employee.wallet_values())

    def _is_restaurant_order(self):
        self.ensure_one()
        config = self.session_id.config_id
        return bool(getattr(self, 'table_id', False) or (config and config.module_pos_restaurant))

    def _assign_kitchen_staff(self):
        if self.env.context.get('skip_kitchen_assign'):
            return
        for order in self:
            if order.state == 'cancel' or order.kitchen_state in ('ready', 'served'):
                continue
            if not order._is_restaurant_order() or not order.lines:
                continue
            if order.assigned_cook:
                continue
            cook = order._least_busy_employee('cook')
            if not cook:
                continue
            order.with_context(skip_kitchen_assign=True).write({
                'assigned_cook': cook.id,
                'kitchen_state': 'assigned',
                'cook_assigned_at': fields.Datetime.now(),
            })

    def _least_busy_employee(self, role):
        employees = self.env['hr.employee'].sudo().search([
            ('employee_restaurant_role', '=', role),
            ('active', '=', True),
        ])
        if not employees:
            return self.env['hr.employee']
        open_attendance = self.env['hr.attendance'].sudo().search([
            ('employee_id', 'in', employees.ids),
            ('check_out', '=', False),
        ])
        pool = open_attendance.employee_id or employees
        field_name = 'assigned_cook' if role == 'cook' else 'employee_id'
        groups = self.env['pos.order']._read_group(
            domain=[
                (field_name, 'in', pool.ids),
                ('kitchen_state', 'in', ('assigned', 'preparing', 'ready')),
                ('state', '!=', 'cancel'),
            ],
            groupby=[field_name],
            aggregates=['__count'],
        )
        counts = {employee.id: count for employee, count in groups if employee}
        return min(pool, key=lambda employee: counts.get(employee.id, 0))

    def _employee_phone(self, employee):
        return (employee.mobile_phone or employee.work_phone or '').strip()

    @api.model
    def _kitchen_viewer(self):
        user = self.env.user
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        role = employee.employee_restaurant_role if employee else False
        see_all = (
            user.has_group('base.group_system')
            or user.has_group('point_of_sale.group_pos_manager')
            or role == 'manager'
        )
        return {
            'see_all': see_all,
            'role': role if role in ('cook', 'waiter') else False,
            'employee_id': employee.id if employee else False,
            'employee_name': employee.name if employee else user.name,
        }

    def _order_reference(self):
        self.ensure_one()
        return self.pos_reference or self.name or str(self.id)

    def _ordered_stages(self, stages):
        if stages and 'sequence' in stages._fields:
            return stages.sorted(lambda stage: (stage.sequence, stage.id))
        return stages

    def _add_stage_minutes(self, stage, minutes):
        self.ensure_one()
        minutes = round(max(minutes, 0.0), 2)
        if not minutes:
            return
        if stage.owner_role == 'waiter':
            field_name = 'waiter_stage_minutes'
        else:
            field_name = 'cook_stage_minutes'
        self.with_context(skip_kitchen_assign=True).write({
            field_name: round(self[field_name] + minutes, 2),
        })

    def _notify_stage_entry(self):
        for order in self:
            if 'pos.prep.display' not in order.env:
                continue
            for display in order._preparation_displays():
                stage = order._ordered_stages(display.stage_ids)[:1]
                if stage:
                    order._send_stage_whatsapp(stage)

    def _send_stage_whatsapp(self, stage):
        self.ensure_one()
        if not stage or 'send_whatsapp' not in stage._fields or not stage.send_whatsapp:
            return False
        template = stage.whatsapp_template_id
        sent_ids = list(self.notified_whatsapp_stage_ids or [])
        if not template or stage.id in sent_ids:
            return False
        employee = self.assigned_cook if template.send_to == 'cook' else self._order_employee()
        sent = self._send_staff_notice(employee, self._render_whatsapp_template(template))
        if sent or not self._employee_phone(employee):
            sent_ids.append(stage.id)
            vals = {'notified_whatsapp_stage_ids': sent_ids}
            if template.send_to == 'cook':
                vals['cook_notified'] = True
            else:
                vals['waiter_notified'] = True
            self.with_context(skip_kitchen_assign=True).write(vals)
        return sent

    def _handoff_to_waiter(self):
        now = fields.Datetime.now()
        ready = self.filtered(lambda order: order.kitchen_state not in ('ready', 'served'))
        if ready:
            ready.with_context(skip_kitchen_assign=True).write({
                'kitchen_state': 'ready',
                'ready_at': now,
            })

    def _ensure_order_waiter(self):
        for order in self:
            if 'employee_id' not in order._fields or order.employee_id:
                continue
            employee = order._order_employee()
            if employee:
                order.with_context(skip_kitchen_assign=True).write({'employee_id': employee.id})

    def _order_employee(self):
        self.ensure_one()
        Employee = self.env['hr.employee'].sudo()
        if 'employee_id' in self._fields and self.employee_id:
            return self.employee_id
        users = (self.user_id | self.env.user).filtered(lambda user: user)
        for user in users:
            employee = Employee.search([('user_id', '=', user.id)], limit=1)
            if employee:
                return employee
        for user in users:
            employee = Employee.search([('name', '=', user.name)], limit=1)
            if employee:
                return employee
        return Employee

    def _waiter_display_name(self):
        self.ensure_one()
        employee = self._order_employee()
        if employee:
            return employee.name
        return (self.user_id.name if self.user_id else '') or self.env.user.name or ''

    def _preparation_displays(self):
        self.ensure_one()
        if 'pos.prep.display' not in self.env:
            return []
        category_ids = self.lines.product_id.pos_categ_ids.ids
        display_model = self.env['pos.prep.display'].sudo()
        if hasattr(display_model, '_get_preparation_displays'):
            return display_model._get_preparation_displays(self, category_ids)
        domain = [
            '|', ('pos_config_ids', '=', False), ('pos_config_ids', 'in', self.config_id.ids),
        ]
        if category_ids:
            domain = ['&'] + domain + ['|', ('category_ids', '=', False), ('category_ids', 'in', category_ids)]
        else:
            domain = ['&'] + domain + [('category_ids', '=', False)]
        return display_model.search(domain)

    def _render_whatsapp_template(self, template):
        self.ensure_one()
        values = self._whatsapp_placeholder_values()
        body = template.body or ''
        for key, value in values.items():
            body = body.replace('{{%s}}' % key, value)
            body = body.replace('{{ %s }}' % key, value)
        lines = [line.rstrip() for line in body.splitlines()]
        cleaned = []
        blank = False
        for line in lines:
            if line:
                cleaned.append(line)
                blank = False
            elif not blank:
                cleaned.append('')
                blank = True
        return '\n'.join(cleaned).strip()

    def _whatsapp_placeholder_values(self):
        self.ensure_one()
        items, instructions = self._kitchen_message_lines()
        special = ''
        if instructions:
            special = 'Special instructions\n%s' % '\n'.join(instructions)
        return {
            'NameOfCook': self.assigned_cook.name or '',
            'OrderNumber': self._order_reference(),
            'TableNumber': self._table_number(),
            'Items': '\n'.join(items) or '- No items',
            'SpecialInstructions': special,
            'NameOfWaiterOrCashier': self._cashier_name(),
            'NameOfWaiterWhoPlacedOrder': self._cashier_name(),
            'NameOfWaiter': self._cashier_name(),
        }

    def _table_number(self):
        self.ensure_one()
        table = self.table_id if 'table_id' in self._fields else False
        if not table:
            return '-'
        if 'table_number' in table._fields:
            return str(table.table_number or '-')
        return table.display_name or '-'

    def _cashier_name(self):
        self.ensure_one()
        return self._waiter_display_name()

    def _kitchen_message_lines(self):
        self.ensure_one()
        items = []
        instructions = []
        order_note = ''
        if 'general_customer_note' in self._fields and self.general_customer_note:
            order_note = self.general_customer_note
        elif 'note' in self._fields and self.note:
            order_note = self.note
        if order_note:
            instructions.append('- %s' % order_note)
        for line in self.lines.filtered(lambda item: item.qty > 0):
            name = line.full_product_name or line.product_id.display_name
            qty = int(line.qty) if line.qty == int(line.qty) else line.qty
            items.append('- %s' % name if qty == 1 else '- %s x %s' % (qty, name))
            note = line.customer_note if 'customer_note' in line._fields else False
            if note:
                instructions.append('- %s: %s' % (name, note))
        return items, instructions

    def _send_staff_notice(self, employee, message):
        self.ensure_one()
        if 'whatsapp.config' not in self.env or not employee:
            return False
        phone = self._employee_phone(employee)
        if not phone:
            return False
        config = self.env['whatsapp.config'].sudo().search([('active', '=', True), ('state', '=', 'connected')], limit=1)
        if not config:
            return False
        try:
            return config.send_text(phone, message)
        except Exception:
            _logger.exception("WhatsApp notice failed for order %s", self.id)
            return False

    def _sync_kitchen_times(self):
        if 'pos.prep.state' not in self.env:
            return
        now = fields.Datetime.now()
        states = self.env['pos.prep.state'].sudo()
        for order in self:
            open_states = states.search([
                ('prep_line_id.pos_order_line_id.order_id', '=', order.id),
            ])
            if not open_states:
                if order.kitchen_state != 'served':
                    order.action_mark_served()
                continue
            cook_minutes = order.cook_stage_minutes
            waiter_minutes = order.waiter_stage_minutes
            seen = set()
            for state in open_states:
                if not state.stage_id or not state.entered_at or state.stage_id.id in seen:
                    continue
                seen.add(state.stage_id.id)
                minutes = max((now - state.entered_at).total_seconds() / 60.0, 0.0)
                if state.stage_id.owner_role == 'waiter':
                    waiter_minutes += minutes
                else:
                    cook_minutes += minutes
            open_states.write({'entered_at': False})
            cook_minutes = round(cook_minutes, 2)
            waiter_minutes = round(waiter_minutes, 2)
            order.with_context(skip_kitchen_assign=True).write({
                'cook_stage_minutes': cook_minutes,
                'waiter_stage_minutes': waiter_minutes,
                'cook_delayed': cook_minutes > COOK_MINUTES,
                'waiter_delayed': waiter_minutes > SERVE_MINUTES,
                'cook_used_time': round(max(cook_minutes - COOK_MINUTES, 0.0), 2),
                'waiter_used_time': round(max(waiter_minutes - SERVE_MINUTES, 0.0), 2),
                'kitchen_state': 'served',
                'served_at': order.served_at or now,
            })

    def action_pos_order_paid(self):
        result = super().action_pos_order_paid()
        self._sync_kitchen_times()
        return result

    def _notify_staff(self, employee, template_name):
        self.ensure_one()
        phone = self._employee_phone(employee) if employee else ''
        if not phone or not template_name:
            return False
        return self.env['whatsapp.config'].sudo().send_template(phone, template_name)

    def action_start_preparing(self):
        self.filtered(lambda order: order.kitchen_state in ('pending', 'assigned')).write({
            'kitchen_state': 'preparing',
            'cook_started_at': fields.Datetime.now(),
        })

    def action_mark_ready(self):
        self.filtered(lambda order: order.kitchen_state != 'served').write({
            'kitchen_state': 'ready',
            'ready_at': fields.Datetime.now(),
        })

    def action_mark_served(self):
        now = fields.Datetime.now()
        for order in self:
            vals = {'kitchen_state': 'served', 'served_at': now}
            if order.ready_at:
                elapsed = (now - order.ready_at).total_seconds() / 60.0
                if elapsed > SERVE_MINUTES:
                    vals.update({
                        'waiter_delayed': True,
                        'waiter_used_time': round(elapsed - SERVE_MINUTES, 2),
                    })
            if order.cook_assigned_at:
                elapsed = (now - order.cook_assigned_at).total_seconds() / 60.0
                if elapsed > COOK_MINUTES:
                    vals.update({
                        'cook_delayed': True,
                        'cook_used_time': round(elapsed - COOK_MINUTES, 2),
                    })
            order.with_context(skip_kitchen_assign=True).write(vals)

    @api.model
    def cron_progress_kitchen(self):
        orders = self.search([
            ('kitchen_state', 'in', OPEN_KITCHEN_STATES),
            ('state', '!=', 'cancel'),
        ], limit=200)
        orders._assign_kitchen_staff()
        now = fields.Datetime.now()
        config = self.env['whatsapp.config'].sudo().search([('active', '=', True)], limit=1) if 'whatsapp.config' in self.env else False
        notifications = 0
        for order in orders:
            if order.state in ('paid', 'done', 'invoiced') and order.kitchen_state != 'served':
                order._sync_kitchen_times()
                continue
            vals = {}
            if order.kitchen_state in ('assigned', 'preparing') and order.cook_assigned_at:
                elapsed = (now - order.cook_assigned_at).total_seconds() / 60.0
                if elapsed > COOK_MINUTES:
                    vals.update({
                        'cook_delayed': True,
                        'cook_used_time': round(elapsed - COOK_MINUTES, 2),
                    })
            if order.kitchen_state == 'ready' and order.ready_at:
                elapsed = (now - order.ready_at).total_seconds() / 60.0
                if elapsed > SERVE_MINUTES:
                    vals.update({
                        'waiter_delayed': True,
                        'waiter_used_time': round(elapsed - SERVE_MINUTES, 2),
                    })
            if vals:
                order.with_context(skip_kitchen_assign=True).write(vals)
            if not config or notifications >= 30:
                continue
            if not order.cook_notified:
                order._notify_stage_entry()
                notifications += 1
