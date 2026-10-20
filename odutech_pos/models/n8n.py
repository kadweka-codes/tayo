import logging
import re
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

_AMOUNT_RE = re.compile(r'-?\d+(?:\.\d+)?')


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _amount(value):
    if value in (None, False, ''):
        return 0.0
    if isinstance(value, (int, float)):
        return abs(float(value))
    text = str(value).replace(',', '').strip()
    match = _AMOUNT_RE.search(text)
    if not match:
        return 0.0
    try:
        return abs(float(match.group(0)))
    except ValueError:
        return 0.0


def _row_amount(row):
    credit = _amount(row.get('credit'))
    return credit or _amount(row.get('debit'))


def _parse_date(value):
    if hasattr(value, 'year') and not hasattr(value, 'hour'):
        return value
    if hasattr(value, 'date') and hasattr(value, 'hour'):
        return value.date()
    text = str(value or '').strip()
    if not text:
        return None
    text = text.replace('T', ' ').split('.')[0].split('+')[0].strip()
    for fmt in ('%d/%m/%y', '%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _transaction_key(row):
    tx_id = row.get('Id') or row.get('id') or row.get('transaction_id')
    try:
        return int(tx_id) if tx_id not in (None, False, '') else False
    except (TypeError, ValueError):
        return False


class OdutechN8N(models.Model):
    _name = 'odutech.n8n'
    _description = 'n8n payment transaction'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    phone_number = fields.Char(string='Phone Number', readonly=True)
    debit = fields.Char(string='Debit', readonly=True)
    credit = fields.Char(string='Credit', readonly=True)
    balance = fields.Char(string='Balance', readonly=True)
    amount = fields.Float(string='Amount', readonly=True, digits=(16, 2))
    pos_order = fields.Many2one('pos.order', string='POS Order', tracking=True)
    datetime = fields.Datetime(string='Datetime', readonly=True)
    transaction_date = fields.Char(string='Transaction Date', readonly=True)
    existing_partner_id = fields.Many2one('res.partner', string='Existing Partner', readonly=True)
    related_n8n_id = fields.Many2one('dilek.odutechpos.n8n', string='N8N Config', readonly=True)
    related_line_ids = fields.One2many('odutech.n8n.lines', 'related_transaction', string='Related lines', readonly=True)
    transaction_id = fields.Integer(string='Transaction ID', readonly=True, index=True)
    match_note = fields.Char(string='Match note', readonly=True)
    processing_status = fields.Selection(
        [
            ('queue', 'In Queue'),
            ('done', 'Done'),
            ('failed', 'Failed'),
        ],
        string='Processing Status',
        default='queue',
        required=True,
        tracking=True,
        index=True,
    )

    _transaction_id_unique = models.Constraint(
        'unique(transaction_id)',
        "This n8n transaction was already imported.",
    )

    def write(self, vals):
        res = super().write(vals)
        if vals.get('pos_order') and not self.env.context.get('skip_n8n_lines'):
            self.filtered(lambda record: record.pos_order and record.processing_status != 'done')._create_lines()
        return res

    @api.model
    def ingest_rows(self, rows, pos_config_ids=None):
        rows = [row for row in (rows or []) if isinstance(row, dict)]
        if not rows:
            return self.browse()
        keys = [key for key in (_transaction_key(row) for row in rows) if key]
        existing = set()
        if keys:
            existing = set(self.sudo().search([('transaction_id', 'in', keys)]).mapped('transaction_id'))
        created = self.browse()
        for row in rows:
            tx_id = _transaction_key(row)
            if tx_id and tx_id in existing:
                continue
            phone = str(row.get('phone_number') or row.get('phone') or '').strip()
            tx_date = row.get('date') or row.get('transaction_date') or row.get('datetime') or ''
            amount = _row_amount(row)
            if not tx_id and phone and tx_date:
                duplicate = self.search_count([
                    ('phone_number', '=', phone),
                    ('transaction_date', '=', str(tx_date)),
                    ('credit', '=', str(row.get('credit') or '')),
                    ('debit', '=', str(row.get('debit') or '')),
                ])
                if duplicate:
                    continue
            day = _parse_date(tx_date)
            if amount <= 0 or not day:
                status = 'failed'
                note = 'The transaction has no amount.' if amount <= 0 else 'The transaction has no date.'
                order = self.env['pos.order']
            else:
                order = self._match_pos_order(phone, amount, day, pos_config_ids=pos_config_ids)
                status = 'queue'
                note = 'Matched to %s.' % (order.pos_reference or order.name) if order else 'Waiting for a POS order with this amount.'
            partner = order.partner_id if order else self._partner_from_phone(phone)
            try:
                with self.env.cr.savepoint():
                    record = self._create_transaction(tx_id, phone, row, amount, tx_date, day, order, partner, status, note)
            except Exception:
                _logger.exception('n8n row skipped for phone %s', phone)
                continue
            if tx_id:
                existing.add(tx_id)
            created |= record
        return created

    def _create_transaction(self, tx_id, phone, row, amount, tx_date, day, order, partner, status, note):
        record = self.create({
            'existing_partner_id': partner.id if partner else False,
            'phone_number': phone,
            'debit': row.get('debit') or '',
            'transaction_id': tx_id or False,
            'pos_order': order.id if order else False,
            'credit': row.get('credit') or '',
            'balance': row.get('balance') or '',
            'amount': amount,
            'transaction_date': str(tx_date or ''),
            'datetime': self._noon_utc(day) if day else False,
            'processing_status': status,
            'match_note': note,
        })
        if order:
            record._create_lines()
        return record

    @api.model
    def _timezone(self):
        name = self.env.company.partner_id.tz or self.env.user.tz or 'Africa/Nairobi'
        try:
            return pytz.timezone(name)
        except pytz.UnknownTimeZoneError:
            return pytz.timezone('Africa/Nairobi')

    @api.model
    def _noon_utc(self, day):
        local = self._timezone().localize(datetime.combine(day, time(12, 0)))
        return local.astimezone(pytz.utc).replace(tzinfo=None)

    @api.model
    def _day_window(self, day):
        zone = self._timezone()
        start = zone.localize(datetime.combine(day, time.min)) - timedelta(hours=6)
        end = zone.localize(datetime.combine(day, time.max)) + timedelta(hours=6)
        return (
            start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _partner_from_phone(self, phone):
        digits = _digits(phone)
        if not digits:
            return self.env['res.partner']
        partner = self.env['res.partner'].sudo().search([
            '|', ('phone', '=', phone), ('mobile', '=', phone),
        ], limit=1)
        if partner:
            return partner
        tail = digits[-9:]
        if len(tail) < 7:
            return self.env['res.partner']
        candidates = self.env['res.partner'].sudo().search([
            '|', ('phone', 'ilike', tail), ('mobile', 'ilike', tail),
        ], limit=10)
        return candidates.filtered(
            lambda item: tail in _digits((item.phone or '') + (item.mobile or ''))
        )[:1]

    @api.model
    def _match_pos_order(self, phone, amount, day, pos_config_ids=None):
        if not day or amount <= 0:
            return self.env['pos.order']
        start, end = self._day_window(day)
        domain = [
            ('date_order', '>=', start),
            ('date_order', '<=', end),
            ('state', '!=', 'cancel'),
            ('transaction_matched', '=', False),
        ]
        if pos_config_ids:
            domain.append(('config_id', 'in', list(pos_config_ids)))
        orders = self.env['pos.order'].sudo().search(domain, limit=80)
        tail = _digits(phone)[-9:]
        ranked = []
        for order in orders:
            targets = [order.amount_total]
            payments = order.payment_ids if 'payment_ids' in order._fields else order.env['pos.payment']
            targets.extend(abs(payment.amount) for payment in payments)
            gap = min(abs(target - amount) for target in targets) if targets else amount
            if gap > 1.0:
                continue
            phone_hit = bool(
                tail and order.partner_id and tail in _digits((order.partner_id.phone or '') + (order.partner_id.mobile or ''))
            )
            paid = order.state in ('paid', 'done', 'invoiced')
            if not phone_hit and not paid:
                continue
            ranked.append((0 if phone_hit else 1, 0 if paid else 1, gap, order.id, order))
        if not ranked:
            return self.env['pos.order']
        ranked.sort(key=lambda item: item[:4])
        if ranked[0][0] == 0:
            return ranked[0][4]
        paid_hits = [item for item in ranked if item[1] == 0 and item[2] <= 1.0]
        if len(paid_hits) == 1:
            return paid_hits[0][4]
        return self.env['pos.order']

    def _cashier(self, order):
        if hasattr(order, '_order_employee'):
            return order._order_employee()
        if 'employee_id' in order._fields and order.employee_id:
            return order.employee_id
        return self.env['hr.employee']

    def _create_lines(self):
        for rec in self:
            order = rec.pos_order
            if not order:
                continue
            if rec.related_line_ids:
                rec.with_context(skip_n8n_lines=True).write({
                    'processing_status': 'done',
                    'match_note': 'Matched to %s.' % (order.pos_reference or order.name),
                })
                if not order.transaction_matched:
                    order.sudo().write({'transaction_matched': True})
                continue
            cashier = rec._cashier(order)
            vals_list = []
            for line in order.lines.filtered(lambda item: item.qty > 0):
                vals_list.append({
                    'related_transaction': rec.id,
                    'pos_order_product': line.product_id.id,
                    'pos_order_quantity': line.qty,
                    'phone_number': rec.phone_number,
                    'pos_order_amount': line.price_subtotal_incl,
                    'pos_order_customer': order.partner_id.id,
                    'pos_order_cashier': cashier.id if cashier else False,
                })
            if vals_list:
                self.env['odutech.n8n.lines'].sudo().create(vals_list)
            order.sudo().write({'transaction_matched': True})
            rec.with_context(skip_n8n_lines=True).write({
                'processing_status': 'done',
                'existing_partner_id': order.partner_id.id or rec.existing_partner_id.id,
                'match_note': 'Matched to %s.' % (order.pos_reference or order.name),
            })

    def action_process_order_lines(self):
        if self:
            records = self.filtered(lambda record: record.processing_status != 'done')
        else:
            cutoff = fields.Datetime.now() - timedelta(days=14)
            records = self.search([
                ('processing_status', 'in', ('queue', 'failed')),
                ('create_date', '>=', cutoff),
            ], limit=200, order='id desc')
        expired = fields.Datetime.now() - timedelta(days=7)
        for rec in records:
            try:
                with self.env.cr.savepoint():
                    if not rec.pos_order and rec.amount:
                        day = _parse_date(rec.transaction_date) or (rec.datetime.date() if rec.datetime else None)
                        order = self._match_pos_order(rec.phone_number, rec.amount, day) if day else self.env['pos.order']
                        if order:
                            rec.with_context(skip_n8n_lines=True).write({'pos_order': order.id})
                    if rec.pos_order:
                        rec._create_lines()
                    elif rec.create_date and rec.create_date < expired:
                        rec.with_context(skip_n8n_lines=True).write({
                            'processing_status': 'failed',
                            'match_note': 'No POS order matched this payment.',
                        })
            except Exception:
                _logger.exception('Failed to build n8n lines for transaction %s', rec.id)
                rec.with_context(skip_n8n_lines=True).write({
                    'processing_status': 'failed',
                    'match_note': 'Could not build the order lines.',
                })

    def action_rematch(self):
        self.filtered(lambda record: record.processing_status != 'done').action_process_order_lines()


class OdutechN8NLines(models.Model):
    _name = 'odutech.n8n.lines'
    _description = 'n8n payment transaction line'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    related_transaction = fields.Many2one('odutech.n8n', index=True, ondelete='cascade')
    pos_order_product = fields.Many2one('product.product', string='Pos Order Product', readonly=True)
    pos_order_quantity = fields.Float(string='Pos Order Quantity', readonly=True)
    pos_order_amount = fields.Float(string='Pos Order Amount', readonly=True, digits=(16, 2))
    pos_order_customer = fields.Many2one('res.partner', string='Pos Order Customer', readonly=True)
    pos_order_cashier = fields.Many2one('hr.employee', string='Pos Order Cashier', readonly=True)
    phone_number = fields.Char(string='Phone Number', readonly=True)

    def update_missing_phone_number(self):
        for rec in self:
            transaction = rec.related_transaction
            if not transaction:
                continue
            vals = {}
            if not rec.phone_number and transaction.phone_number:
                vals['phone_number'] = transaction.phone_number
            partner = transaction.existing_partner_id or self.env['odutech.n8n']._partner_from_phone(transaction.phone_number)
            if partner and rec.pos_order_customer != partner:
                vals['pos_order_customer'] = partner.id
            if vals:
                rec.write(vals)
