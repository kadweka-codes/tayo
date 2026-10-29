from odoo import api, fields, models


class PosPrepStage(models.Model):
    _inherit = 'pos.prep.stage'

    owner_role = fields.Selection([
        ('cook', 'Cook'),
        ('waiter', 'Waiter'),
    ], string='Assigned to', default='cook', required=True)
    send_whatsapp = fields.Boolean(string='Send WhatsApp')
    whatsapp_template_id = fields.Many2one('whatsapp.text.template', string='WhatsApp message')

    def init(self):
        super().init()
        self.env['pos.prep.display'].sudo().search([])._ensure_stage_roles()

    @api.model
    def _load_pos_preparation_data_fields(self):
        # An empty list means "every field", which already includes owner_role.
        fields_list = list(super()._load_pos_preparation_data_fields())
        if fields_list and 'owner_role' not in fields_list:
            fields_list.append('owner_role')
        return fields_list


class PosPrepState(models.Model):
    _inherit = 'pos.prep.state'

    entered_at = fields.Datetime(default=fields.Datetime.now)

    def change_state_stage(self, stages, prep_display_id):
        now = fields.Datetime.now()
        snapshots = []
        for state in self:
            line = state.prep_line_id.pos_order_line_id if state.prep_line_id else self.env['pos.order.line']
            snapshots.append((state, state.stage_id, state.entered_at or state.create_date or now, line.order_id))
        result = super().change_state_stage(stages, prep_display_id)
        counted = set()
        notified = set()
        handed_off = set()
        for state, old_stage, start, order in snapshots:
            if not old_stage or state.stage_id == old_stage:
                continue
            if order:
                key = (order.id, old_stage.id)
                if key not in counted:
                    counted.add(key)
                    minutes = max((now - start).total_seconds() / 60.0, 0.0)
                    order._add_stage_minutes(old_stage, minutes)
                if old_stage.owner_role != 'waiter' and state.stage_id.owner_role == 'waiter' and order.id not in handed_off:
                    handed_off.add(order.id)
                    order._handoff_to_waiter()
                sent_ids = order.notified_whatsapp_stage_ids or []
                if order.id not in notified or state.stage_id.id not in sent_ids:
                    notified.add(order.id)
                    order._send_stage_whatsapp(state.stage_id)
            state.entered_at = now
        return result


class PosPrepDisplay(models.Model):
    _inherit = 'pos.prep.display'

    def _ensure_stage_roles(self):
        for display in self:
            stages = display.stage_ids
            if 'sequence' in stages._fields:
                stages = stages.sorted(lambda stage: (stage.sequence, stage.id))
            if not stages or any(stage.owner_role == 'waiter' for stage in stages):
                continue
            stages[1:].write({'owner_role': 'waiter'})

    def _get_preparation_display_order_additional_info(self, prep_states, prep_lines, prep_orders):
        self.ensure_one()
        res = super()._get_preparation_display_order_additional_info(prep_states, prep_lines, prep_orders)
        orders = prep_orders.pos_order_id
        if orders and 'pos.order' in res:
            labels = {
                order.id: {
                    'cook_name': order.cook_name,
                    'waiter_name': order.waiter_name,
                    'cook_employee_id': order.cook_employee_id,
                    'waiter_employee_id': order.waiter_employee_id,
                }
                for order in orders
            }
            for row in res['pos.order']:
                row.update(labels.get(row['id'], {}))
        return res


class PosPrepOrder(models.Model):
    _inherit = 'pos.prep.order'

    @api.model
    def process_order(self, order_id, options=None):
        options = dict(options or {})
        order = self.env['pos.order'].browse(order_id)
        cancelled = options.get('cancelled')
        if order and not cancelled:
            order._ensure_order_waiter()
            order._assign_kitchen_staff()
            order._preparation_displays()._ensure_stage_roles()
        result = super().process_order(order_id, options)
        if order and not cancelled:
            order._notify_stage_entry()
        return result
