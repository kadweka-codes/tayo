#!/usr/bin/env python3
"""Pull master data from one Odoo database into another over XML-RPC.

Copies, in order:

1. Chart of accounts missing on the destination, matched by account code.
2. Journals missing on the destination, matched by journal code.
3. Customers, including their contacts, matched by reference, tax ID, email, then name.
4. Products, including variants, vendor prices, and extra gallery images.

Every stored field that exists on both databases is copied, including pictures
(image_1920 and, for variants, image_variant_1920). A customer or product that
already exists on the destination is left unchanged. Nothing is deleted on
either side.

Edit SOURCE_* and TARGET_* below, then run:

    python3 odoo_xmlrpc_pull.py --dry-run
    python3 odoo_xmlrpc_pull.py
"""

import argparse
import sys
import xmlrpc.client


SOURCE_URL = 'https://tayoltd.odoo.com'
SOURCE_DB = 'tayoltd'
SOURCE_USER = 'abdulahiomart@gmail.com'
SOURCE_PASSWORD = 'abdulahiomart'

TARGET_URL = 'https://erp.tayorestaurant.com'
TARGET_DB = 'erptayorestaurantcom'
TARGET_USER = 'tayorestaurant1@gmail.com'
TARGET_PASSWORD = '1X1FojSr2LgaK5ZWztYl'

PAGE = 200
IMAGE_PAGE = 5

SCALAR_TYPES = {
    'char', 'text', 'html', 'integer', 'float', 'monetary',
    'boolean', 'date', 'datetime', 'selection',
}
SKIP_FIELDS = {
    'id', 'display_name', 'create_uid', 'create_date', 'write_uid', 'write_date',
    'company_id', 'company_ids', 'currency_id', 'cost_currency_id', 'company_currency_id',
    'parent_path', 'complete_name', 'commercial_company_name', 'email_formatted',
    'partner_share', 'country_code', 'vat_label', 'tz_offset', 'active_lang_count',
    'uom_name', 'volume_uom_name', 'weight_uom_name', 'product_variant_count',
    'has_configurable_attributes', 'is_product_variant', 'is_dynamically_created',
    'product_tooltip', 'product_variant_id', 'can_image_1024_be_zoomed',
    'can_image_variant_1024_be_zoomed', 'opening_debit', 'opening_credit',
    'opening_balance', 'code_store', 'placeholder_code', 'internal_group',
    'include_initial_balance', 'used', 'root_id', 'group_id', 'alias_id',
    'alias_name', 'alias_domain', 'default_account_type', 'tax_string',
    'fiscal_country_codes', 'related_taxes_amount', 'current_balance',
    'display_mapping_tab', 'name_placeholder', 'import_attribute_values',
}
# Computed fields whose inverse is the real way to write them.
WRITABLE_UNSTORED = {
    'code', 'barcode', 'default_code', 'standard_price', 'weight', 'volume', 'company_registry',
}
SKIP_PREFIXES = (
    'message_', 'activity_', 'website_message_', 'rating_', 'seo_',
    'avatar_', 'signup_',
)
TEMPLATE_VARIANT_FIELDS = {'default_code', 'barcode', 'standard_price', 'weight', 'volume'}
JOURNAL_ACCOUNT_FIELDS = (
    'default_account_id', 'suspense_account_id', 'profit_account_id',
    'loss_account_id', 'non_deductible_account_id',
)
PARTNER_ACCOUNT_FIELDS = (
    'property_account_receivable_id', 'property_account_payable_id',
)
CATEGORY_ACCOUNT_FIELDS = (
    'property_account_income_categ_id', 'property_account_expense_categ_id',
)
PRODUCT_ACCOUNT_FIELDS = (
    'property_account_income_id', 'property_account_expense_id',
)


def transport_for(url):
    kind = xmlrpc.client.SafeTransport if url.startswith('https') else xmlrpc.client.Transport
    transport = kind()
    transport.timeout = None
    return transport


class Odoo:
    def __init__(self, url, db, user, password):
        self.url = url.rstrip('/')
        self.db = db
        self.password = password
        common = xmlrpc.client.ServerProxy(
            f'{self.url}/xmlrpc/2/common', allow_none=True, transport=transport_for(self.url),
        )
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            raise SystemExit(f'Login failed for {user} on {self.url} ({db})')
        self.models = xmlrpc.client.ServerProxy(
            f'{self.url}/xmlrpc/2/object', allow_none=True, transport=transport_for(self.url),
        )
        self._fields = {}

    def execute(self, model, method, *args, **kwargs):
        return self.models.execute_kw(
            self.db, self.uid, self.password, model, method, list(args), kwargs,
        )

    def fields(self, model):
        if model not in self._fields:
            self._fields[model] = self.execute(
                model, 'fields_get',
                attributes=['type', 'readonly', 'selection', 'relation', 'required', 'store'],
            )
        return self._fields[model]

    def has_model(self, model):
        try:
            self.fields(model)
            return True
        except xmlrpc.client.Fault:
            return False

    def search_read(self, model, domain, fields, context=None):
        rows = []
        offset = 0
        base_context = {'active_test': False}
        if context:
            base_context.update(context)
        while True:
            page = self.execute(
                model, 'search_read', domain,
                fields=fields, limit=PAGE, offset=offset, order='id',
                context=base_context,
            )
            rows.extend(page)
            if len(page) < PAGE:
                return rows
            offset += PAGE

    def read_chunks(self, model, ids, fields, size=PAGE, context=None):
        rows = {}
        id_list = list(ids)
        for start in range(0, len(id_list), size):
            chunk = id_list[start:start + size]
            kwargs = {'fields': fields}
            if context:
                kwargs['context'] = context
            for row in self.execute(model, 'read', chunk, **kwargs):
                rows[row['id']] = row
        return rows


def m2o_id(value):
    if not value:
        return False
    return value[0] if isinstance(value, (list, tuple)) else value


def text(value):
    return (value or '').strip() if isinstance(value, str) else ''


def fault_line(error):
    lines = [line.strip() for line in error.faultString.splitlines() if line.strip()]
    return lines[-1][:400] if lines else str(error)


def chunks(items, size):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def image_payload(value):
    if isinstance(value, xmlrpc.client.Binary):
        return xmlrpc.client.Binary(value.data)
    if isinstance(value, str) and len(value) >= 80:
        return value
    return False


class Pull:
    def __init__(self, source, target, dry_run):
        self.source = source
        self.target = target
        self.dry_run = dry_run
        self.currencies = {}
        self.countries = {}
        self.states = {}
        self.accounts = {}
        self.uoms = {}
        self.categories = {}
        self.taxes = None
        self.account_tags = {}
        self.product_tags = {}
        self.partner_categories = {}
        self.industries = {}
        self.fiscal_positions = {}
        self.partner_map = {}
        self.product_map = {}
        self.variant_map = {}
        self.combo_sources = []
        self.attributes = {}
        self.attribute_values = {}

    def source_fields(self, model):
        return self.source.fields(model)

    def target_fields(self, model):
        return self.target.fields(model)

    def has_field(self, model, name):
        return name in self.source_fields(model) and name in self.target_fields(model)

    def scalar_names(self, model):
        source_fields = self.source_fields(model)
        target_fields = self.target_fields(model)
        names = []
        for name, meta in source_fields.items():
            if name not in target_fields or name in SKIP_FIELDS or name.startswith(SKIP_PREFIXES):
                continue
            if 'token' in name or 'password' in name:
                continue
            if meta.get('type') not in SCALAR_TYPES:
                continue
            if meta.get('store') is False and name not in WRITABLE_UNSTORED:
                continue
            if meta.get('readonly') or target_fields[name].get('readonly'):
                continue
            names.append(name)
        return names

    def image_names(self, model):
        source_fields = self.source_fields(model)
        target_fields = self.target_fields(model)
        names = []
        for name, meta in source_fields.items():
            if name not in target_fields or meta.get('type') != 'binary':
                continue
            if meta.get('readonly') or target_fields[name].get('readonly'):
                continue
            if name.startswith('avatar_') or name.endswith(('_1024', '_512', '_256', '_128')):
                continue
            names.append(name)
        return names

    def scalar_values(self, model, row):
        target_fields = self.target_fields(model)
        values = {}
        for name in self.scalar_names(model):
            if name not in row:
                continue
            value = row.get(name)
            if value is None or value == '':
                value = False
            if target_fields[name].get('type') == 'selection' and value:
                allowed = {item[0] for item in target_fields[name].get('selection') or []}
                if allowed and value not in allowed:
                    if model == 'product.template' and name == 'type' and value == 'product' and 'consu' in allowed:
                        values['type'] = 'consu'
                        if self.has_field(model, 'is_storable') and not target_fields['is_storable'].get('readonly'):
                            values['is_storable'] = True
                    continue
            values[name] = value
        return values

    def save(self, model, record_id, values, label):
        values = dict(values)
        flagged = values.pop('_has_image', False)
        images = {key: value for key, value in values.items() if self._is_image(model, key) and value}
        data = {key: value for key, value in values.items() if key not in images}
        image_note = ' image=yes' if flagged or images else ''
        print(f'{label}{image_note}')
        if self.dry_run:
            return record_id or True
        try:
            record_id = self._write(model, record_id, data or images)
        except xmlrpc.client.Fault as error:
            if not images:
                print(f'FAILED {label}: {fault_line(error)}', file=sys.stderr)
                return False
            try:
                record_id = self._write(model, record_id, data)
            except xmlrpc.client.Fault as retry_error:
                print(f'FAILED {label}: {fault_line(retry_error)}', file=sys.stderr)
                return False
            print(f'FAILED {label} image: {fault_line(error)}', file=sys.stderr)
            images = {}
        if images and record_id and data:
            try:
                self.target.execute(model, 'write', [record_id], images)
            except xmlrpc.client.Fault as error:
                print(f'FAILED {label} image: {fault_line(error)}', file=sys.stderr)
        return record_id

    def _write(self, model, record_id, values):
        if record_id:
            self.target.execute(model, 'write', [record_id], values)
            return record_id
        return self.target.execute(model, 'create', values)

    def _is_image(self, model, name):
        meta = self.target_fields(model).get(name) or {}
        return meta.get('type') == 'binary'

    def attach_images(self, model, rows_by_id, values_for):
        names = self.image_names(model)
        if not names or not rows_by_id:
            return
        if self.dry_run:
            flags = self.source.read_chunks(
                model, rows_by_id, names, size=80, context={'bin_size': True},
            )
            for record_id, row in rows_by_id.items():
                if any(flags.get(record_id, {}).get(name) for name in names):
                    values_for(record_id)['_has_image'] = True
            return
        for name in names:
            images = self.source.read_chunks(model, rows_by_id, [name], size=IMAGE_PAGE)
            for record_id, row in images.items():
                payload = image_payload(row.get(name))
                if payload:
                    values_for(record_id)[name] = payload

    def currency_id(self, source_value):
        name = text(source_value[1]) if isinstance(source_value, (list, tuple)) and len(source_value) > 1 else ''
        if not name:
            record_id = m2o_id(source_value)
            if not record_id:
                return False
            found = self.source.execute('res.currency', 'read', [record_id], fields=['name'])
            name = text(found[0].get('name')) if found else ''
        if not name:
            return False
        if name not in self.currencies:
            found = self.target.execute('res.currency', 'search', [('name', '=', name)], limit=1)
            self.currencies[name] = found[0] if found else False
        return self.currencies[name]

    def country_id(self, source_value):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        if record_id not in self.countries:
            found = self.source.execute('res.country', 'read', [record_id], fields=['code'])
            code = text(found[0].get('code')) if found else ''
            target = self.target.execute('res.country', 'search', [('code', '=', code)], limit=1) if code else []
            self.countries[record_id] = target[0] if target else False
        return self.countries[record_id]

    def state_id(self, source_value):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        if record_id not in self.states:
            found = self.source.execute('res.country.state', 'read', [record_id], fields=['code', 'country_id'])
            code = text(found[0].get('code')) if found else ''
            country = self.country_id(found[0].get('country_id')) if found else False
            target = []
            if code and country:
                target = self.target.execute(
                    'res.country.state', 'search',
                    [('code', '=', code), ('country_id', '=', country)], limit=1,
                )
            self.states[record_id] = target[0] if target else False
        return self.states[record_id]

    def account_id(self, source_value):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        found = self.source.execute('account.account', 'read', [record_id], fields=['code'])
        return self.account_by_code(text(found[0].get('code')) if found else '')

    def account_by_code(self, code):
        code = text(code)
        if not code:
            return False
        if code not in self.accounts:
            found = self.target.execute('account.account', 'search', [('code', '=', code)], limit=1)
            self.accounts[code] = found[0] if found else False
        return self.accounts[code]

    def uom_id(self, source_value):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        if record_id not in self.uoms:
            found = self.source.execute('uom.uom', 'read', [record_id], fields=['name'])
            name = text(found[0].get('name')) if found else ''
            target = self.target.execute('uom.uom', 'search', [('name', '=', name)], limit=1) if name else []
            self.uoms[record_id] = target[0] if target else False
        return self.uoms[record_id]

    def load_taxes(self):
        if self.taxes is not None:
            return
        self.taxes = {}
        rows = self.target.search_read('account.tax', [], ['name', 'amount', 'type_tax_use'])
        for row in rows:
            self.taxes[(text(row.get('name')), round(row.get('amount') or 0.0, 4), row.get('type_tax_use'))] = row['id']

    def tax_ids(self, source_ids):
        self.load_taxes()
        if not source_ids:
            return []
        mapped = []
        details = self.source.read_chunks('account.tax', source_ids, ['name', 'amount', 'type_tax_use'])
        for record_id in source_ids:
            row = details.get(record_id) or {}
            key = (text(row.get('name')), round(row.get('amount') or 0.0, 4), row.get('type_tax_use'))
            target_id = self.taxes.get(key)
            if target_id:
                mapped.append(target_id)
        return mapped

    def account_tag_ids(self, source_ids):
        if not source_ids:
            return []
        details = self.source.read_chunks('account.account.tag', source_ids, ['name', 'applicability', 'color'])
        mapped = []
        for record_id in source_ids:
            row = details.get(record_id) or {}
            name = text(row.get('name'))
            applicability = row.get('applicability') or 'accounts'
            key = (name, applicability)
            if not name:
                continue
            if key not in self.account_tags:
                found = self.target.execute(
                    'account.account.tag', 'search',
                    [('name', '=', name), ('applicability', '=', applicability)], limit=1,
                )
                if found:
                    self.account_tags[key] = found[0]
                elif self.dry_run:
                    print(f'tag      create {name}')
                    self.account_tags[key] = True
                else:
                    try:
                        self.account_tags[key] = self.target.execute('account.account.tag', 'create', {
                            'name': name,
                            'applicability': applicability,
                            'color': row.get('color') or 0,
                        })
                    except xmlrpc.client.Fault as error:
                        print(f'FAILED tag {name}: {fault_line(error)}', file=sys.stderr)
                        self.account_tags[key] = False
            if self.account_tags[key] and self.account_tags[key] is not True:
                mapped.append(self.account_tags[key])
        return mapped

    def named_record(self, cache, model, source_value, extra=None, create=True):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        if record_id in cache:
            stored = cache[record_id]
            return False if stored is True else stored
        found = self.source.execute(model, 'read', [record_id], fields=['name'])
        name = text(found[0].get('name')) if found else ''
        if not name:
            cache[record_id] = False
            return False
        target = self.target.execute(model, 'search', [('name', '=', name)], limit=1)
        if target:
            cache[record_id] = target[0]
        elif not create:
            cache[record_id] = False
        elif self.dry_run:
            print(f'{model} create {name}')
            cache[record_id] = True
        else:
            values = {'name': name}
            if extra:
                values.update(extra)
            try:
                cache[record_id] = self.target.execute(model, 'create', values)
            except xmlrpc.client.Fault as error:
                print(f'FAILED {model} {name}: {fault_line(error)}', file=sys.stderr)
                cache[record_id] = False
        return cache[record_id] if cache[record_id] is not True else False

    def product_tag_ids(self, source_ids):
        mapped = []
        for record_id in source_ids or []:
            target_id = self.named_record(self.product_tags, 'product.tag', record_id)
            if target_id:
                mapped.append(target_id)
        return mapped

    def partner_category_ids(self, source_ids):
        mapped = []
        for record_id in source_ids or []:
            target_id = self.named_record(self.partner_categories, 'res.partner.category', record_id)
            if target_id:
                mapped.append(target_id)
        return mapped

    def map_account_fields(self, values, row, field_names):
        for name in field_names:
            if name not in row:
                continue
            account = self.account_id(row.get(name))
            if account:
                values[name] = account

    def ensure_category(self, source_id):
        if not source_id:
            return False
        if source_id in self.categories:
            stored = self.categories[source_id]
            return False if stored is True else stored
        fields = ['name', 'parent_id'] + [
            name for name in self.scalar_names('product.category') if name != 'name'
        ]
        for name in CATEGORY_ACCOUNT_FIELDS:
            if self.has_field('product.category', name):
                fields.append(name)
        row = self.source.execute('product.category', 'read', [source_id], fields=fields)[0]
        parent = self.ensure_category(m2o_id(row.get('parent_id')))
        name = text(row.get('name'))
        found = self.target.execute(
            'product.category', 'search',
            [('name', '=', name), ('parent_id', '=', parent or False)], limit=1,
        )
        values = self.scalar_values('product.category', row)
        values['name'] = name
        if parent:
            values['parent_id'] = parent
        self.map_account_fields(values, row, CATEGORY_ACCOUNT_FIELDS)
        image_values = {}
        self.attach_images('product.category', {source_id: row}, lambda _id: image_values)
        if image_values.get('_has_image'):
            values['_has_image'] = True
        image_values.pop('_has_image', None)
        values.update(image_values)
        label = f'category {"update" if found else "create"} {name}'
        record_id = found[0] if found else False
        saved = self.save('product.category', record_id, values, label)
        self.categories[source_id] = saved or False
        return self.categories[source_id]

    def pull_accounts(self):
        fields = ['code'] + self.scalar_names('account.account')
        if 'currency_id' in self.source_fields('account.account'):
            fields.append('currency_id')
        if self.has_field('account.account', 'tax_ids'):
            fields.append('tax_ids')
        if self.has_field('account.account', 'tag_ids'):
            fields.append('tag_ids')
        rows = self.source.search_read('account.account', [], list(dict.fromkeys(fields)))
        existing = {
            text(row.get('code')): row['id']
            for row in self.target.search_read('account.account', [], ['code'])
            if text(row.get('code'))
        }
        created = updated = skipped = 0
        for row in rows:
            code = text(row.get('code'))
            if not code:
                skipped += 1
                continue
            values = self.scalar_values('account.account', row)
            values['code'] = code
            currency = self.currency_id(row.get('currency_id'))
            if currency:
                values['currency_id'] = currency
            if row.get('tax_ids'):
                taxes = self.tax_ids(row['tax_ids'])
                if taxes:
                    values['tax_ids'] = [(6, 0, taxes)]
            if row.get('tag_ids'):
                tags = self.account_tag_ids(row['tag_ids'])
                if tags:
                    values['tag_ids'] = [(6, 0, tags)]
            current = existing.get(code)
            saved = self.save(
                'account.account', current, values,
                f'account  {"update" if current else "create"} {code} {row.get("name")}',
            )
            if saved and not current:
                self.accounts[code] = saved if saved is not True else False
                existing[code] = saved
                created += 1
            elif saved:
                self.accounts[code] = current
                updated += 1
            else:
                skipped += 1
        print(f'accounts: {created} created, {updated} updated, {skipped} skipped')

    def pull_journals(self):
        fields = self.scalar_names('account.journal') + ['code', 'currency_id', 'bank_id']
        for name in JOURNAL_ACCOUNT_FIELDS:
            if self.has_field('account.journal', name):
                fields.append(name)
        rows = self.source.search_read('account.journal', [], list(dict.fromkeys(fields)))
        existing = {
            text(row.get('code')): row['id']
            for row in self.target.search_read('account.journal', [], ['code'])
            if text(row.get('code'))
        }
        created = updated = skipped = 0
        for row in rows:
            code = text(row.get('code'))
            if not code:
                skipped += 1
                continue
            values = self.scalar_values('account.journal', row)
            values['code'] = code
            values['name'] = row.get('name') or code
            self.map_account_fields(values, row, JOURNAL_ACCOUNT_FIELDS)
            currency = self.currency_id(row.get('currency_id'))
            if currency:
                values['currency_id'] = currency
            if self.has_field('account.journal', 'bank_id'):
                bank = self.named_record({}, 'res.bank', row.get('bank_id'))
                if bank:
                    values['bank_id'] = bank
            current = existing.get(code)
            saved = self.save(
                'account.journal', current, values,
                f'journal  {"update" if current else "create"} {code} {row.get("name")}',
            )
            if saved and not current:
                existing[code] = saved
                created += 1
            elif saved:
                updated += 1
            else:
                skipped += 1
        print(f'journals: {created} created, {updated} updated, {skipped} skipped')

    def partner_key(self, row):
        for name in ('ref', 'vat', 'email'):
            value = text(row.get(name)).lower()
            if value:
                return name, value
        name = text(row.get('name')).lower()
        return ('name', name) if name else (False, False)

    def partner_rows(self):
        fields = ['parent_id', 'commercial_partner_id', 'category_id', 'country_id', 'state_id', 'industry_id']
        fields += self.scalar_names('res.partner')
        for name in PARTNER_ACCOUNT_FIELDS + ('property_account_position_id', 'title'):
            if self.has_field('res.partner', name):
                fields.append(name)
        domain = ['|', ('customer_rank', '>', 0), ('commercial_partner_id.customer_rank', '>', 0)]
        return self.source.search_read('res.partner', domain, list(dict.fromkeys(fields)))

    def match_partner(self, row, index):
        key_name, key = self.partner_key(row)
        if key_name and (key_name, key) in index:
            return index[(key_name, key)]
        name = text(row.get('name')).lower()
        return index.get(('name', name)) if name else False

    def ensure_partner(self, source_id, rows_by_id, index, visiting=None):
        if not source_id:
            return False
        if source_id in self.partner_map:
            stored = self.partner_map[source_id]
            return False if stored is True else stored
        visiting = visiting or set()
        if source_id in visiting:
            return False
        visiting.add(source_id)
        row = rows_by_id.get(source_id)
        if not row:
            fields = ['parent_id', 'category_id', 'country_id', 'state_id', 'industry_id']
            fields += self.scalar_names('res.partner')
            for name in PARTNER_ACCOUNT_FIELDS + ('property_account_position_id', 'title'):
                if self.has_field('res.partner', name):
                    fields.append(name)
            found = self.source.execute('res.partner', 'read', [source_id], fields=list(dict.fromkeys(fields)))
            if not found:
                return False
            row = found[0]
            rows_by_id[source_id] = row
        current = self.match_partner(row, index)
        if current:
            print(f'partner  skip {row.get("name")}')
            self.partner_map[source_id] = current
            self.partner_skipped += 1
            return current
        parent = self.ensure_partner(m2o_id(row.get('parent_id')), rows_by_id, index, visiting)
        values = self.scalar_values('res.partner', row)
        if not text(values.get('name')) and not text(row.get('name')):
            return False
        values['name'] = row.get('name') or values.get('name')
        if parent:
            values['parent_id'] = parent
        country = self.country_id(row.get('country_id'))
        if country:
            values['country_id'] = country
        state = self.state_id(row.get('state_id'))
        if state:
            values['state_id'] = state
        if self.has_field('res.partner', 'industry_id'):
            industry = self.named_record(self.industries, 'res.partner.industry', row.get('industry_id'))
            if industry:
                values['industry_id'] = industry
        if self.has_field('res.partner', 'title'):
            title = self.named_record({}, 'res.partner.title', row.get('title'))
            if title:
                values['title'] = title
        if row.get('category_id'):
            categories = self.partner_category_ids(row['category_id'])
            if categories:
                values['category_id'] = [(6, 0, categories)]
        self.map_account_fields(values, row, PARTNER_ACCOUNT_FIELDS)
        if self.has_field('res.partner', 'property_account_position_id'):
            position = self.named_record(
                self.fiscal_positions, 'account.fiscal.position', row.get('property_account_position_id'),
                create=False,
            )
            if position:
                values['property_account_position_id'] = position
        image_values = {}
        self.attach_images('res.partner', {source_id: row}, lambda _id: image_values)
        if image_values.get('_has_image'):
            values['_has_image'] = True
        image_values.pop('_has_image', None)
        values.update({key: value for key, value in image_values.items() if value})
        saved = self.save(
            'res.partner', False, values,
            f'partner  create {row.get("name")}',
        )
        if not saved:
            return False
        self.partner_created += 1
        self.partner_map[source_id] = saved if saved is not True else source_id
        key_name, key = self.partner_key(row)
        stored = saved if saved is not True else False
        if key_name and stored:
            index[(key_name, key)] = stored
        name = text(row.get('name')).lower()
        if name and stored:
            index[('name', name)] = stored
        return stored or self.partner_map[source_id]

    def pull_customers(self):
        self.partner_created = 0
        self.partner_skipped = 0
        rows = self.partner_rows()
        rows_by_id = {row['id']: row for row in rows}
        index = {}
        for row in self.target.search_read('res.partner', [], ['name', 'email', 'vat', 'ref']):
            key_name, key = self.partner_key(row)
            if key_name:
                index[(key_name, key)] = row['id']
            name = text(row.get('name')).lower()
            if name:
                index.setdefault(('name', name), row['id'])
        for row in rows:
            self.ensure_partner(row['id'], rows_by_id, index)
        print(f'customers: {self.partner_created} created, {self.partner_skipped} skipped')

    def ensure_attribute(self, source_value):
        record_id = m2o_id(source_value)
        if not record_id:
            return False
        if record_id in self.attributes:
            stored = self.attributes[record_id]
            return False if stored is True else stored
        fields = ['name', 'create_variant', 'display_type', 'sequence']
        fields = [name for name in fields if name in self.source_fields('product.attribute')]
        row = self.source.execute('product.attribute', 'read', [record_id], fields=fields)[0]
        name = text(row.get('name'))
        found = self.target.execute('product.attribute', 'search', [('name', '=', name)], limit=1)
        if found:
            self.attributes[record_id] = found[0]
            return found[0]
        values = {'name': name}
        target_fields = self.target_fields('product.attribute')
        for field_name in ('create_variant', 'display_type', 'sequence'):
            if field_name not in row or field_name not in target_fields or target_fields[field_name].get('readonly'):
                continue
            value = row[field_name]
            if target_fields[field_name].get('type') == 'selection' and value:
                allowed = {item[0] for item in target_fields[field_name].get('selection') or []}
                if allowed and value not in allowed:
                    continue
            values[field_name] = value
        print(f'attribute create {name}')
        if self.dry_run:
            self.attributes[record_id] = True
            return False
        try:
            self.attributes[record_id] = self.target.execute('product.attribute', 'create', values)
        except xmlrpc.client.Fault as error:
            print(f'FAILED attribute {name}: {fault_line(error)}', file=sys.stderr)
            self.attributes[record_id] = False
        return self.attributes[record_id]

    def ensure_attribute_value(self, source_id, attribute_id):
        key = (source_id, attribute_id)
        if key in self.attribute_values:
            return self.attribute_values[key]
        value_fields = ['name', 'sequence']
        if self.has_field('product.attribute.value', 'html_color'):
            value_fields.append('html_color')
        row = self.source.execute('product.attribute.value', 'read', [source_id], fields=value_fields)[0]
        name = text(row.get('name'))
        found = self.target.execute(
            'product.attribute.value', 'search',
            [('name', '=', name), ('attribute_id', '=', attribute_id)], limit=1,
        )
        if found:
            self.attribute_values[key] = found[0]
            return found[0]
        values = {'name': name, 'attribute_id': attribute_id}
        if row.get('sequence'):
            values['sequence'] = row['sequence']
        if row.get('html_color') and self.has_field('product.attribute.value', 'html_color'):
            values['html_color'] = row['html_color']
        if self.dry_run:
            print(f'value    create {name}')
            self.attribute_values[key] = True
            return False
        self.attribute_values[key] = self.target.execute('product.attribute.value', 'create', values)
        return self.attribute_values[key]

    def copy_attribute_lines(self, source_template_id, target_template_id):
        if self.dry_run or not target_template_id or target_template_id is True:
            return
        existing = self.target.execute(
            'product.template.attribute.line', 'search',
            [('product_tmpl_id', '=', target_template_id)], limit=1,
        )
        if existing:
            return
        lines = self.source.search_read(
            'product.template.attribute.line',
            [('product_tmpl_id', '=', source_template_id)],
            ['attribute_id', 'value_ids', 'sequence'],
        )
        for line in lines:
            attribute = self.ensure_attribute(line.get('attribute_id'))
            if not attribute or not line.get('value_ids'):
                continue
            value_ids = []
            for value_id in line['value_ids']:
                copied = self.ensure_attribute_value(value_id, attribute)
                if copied:
                    value_ids.append(copied)
            if not value_ids:
                continue
            try:
                self.target.execute('product.template.attribute.line', 'create', {
                    'product_tmpl_id': target_template_id,
                    'attribute_id': attribute,
                    'value_ids': [(6, 0, value_ids)],
                    'sequence': line.get('sequence') or 10,
                })
            except xmlrpc.client.Fault as error:
                print(f'FAILED attributes on template {target_template_id}: {fault_line(error)}', file=sys.stderr)

    def variant_key(self, odoo, value_ids):
        if not value_ids:
            return ()
        rows = odoo.read_chunks(
            'product.template.attribute.value', value_ids, ['name', 'attribute_id'],
        )
        pairs = []
        for value_id in value_ids:
            row = rows.get(value_id) or {}
            attribute = row.get('attribute_id')
            attribute_name = text(attribute[1]) if isinstance(attribute, (list, tuple)) and len(attribute) > 1 else ''
            pairs.append((attribute_name, text(row.get('name'))))
        return tuple(sorted(pairs))

    def copy_variants(self, source_template_id, target_template_id):
        if self.dry_run or not target_template_id or target_template_id is True:
            return
        source_rows = self.source.search_read(
            'product.product', [('product_tmpl_id', '=', source_template_id)],
            ['id', 'default_code', 'barcode', 'standard_price', 'weight', 'volume',
             'product_template_attribute_value_ids'],
        )
        target_rows = self.target.search_read(
            'product.product', [('product_tmpl_id', '=', target_template_id)],
            ['id', 'product_template_attribute_value_ids'],
        )
        target_by_key = {}
        for row in target_rows:
            target_by_key[self.variant_key(self.target, row.get('product_template_attribute_value_ids') or [])] = row['id']
        image_flags = {}
        if source_rows and 'image_variant_1920' in self.source_fields('product.product'):
            image_flags = self.source.read_chunks(
                'product.product', [row['id'] for row in source_rows], ['image_variant_128'],
                context={'bin_size': True},
            )
        for row in source_rows:
            key = self.variant_key(self.source, row.get('product_template_attribute_value_ids') or [])
            target_id = target_by_key.get(key)
            if not target_id:
                continue
            self.variant_map[row['id']] = target_id
            values = {}
            for name in ('default_code', 'barcode', 'standard_price', 'weight', 'volume'):
                if name in self.target_fields('product.product') and row.get(name) not in (None, False, ''):
                    values[name] = row.get(name)
            if image_flags.get(row['id'], {}).get('image_variant_128'):
                image = self.source.execute(
                    'product.product', 'read', [row['id']], fields=['image_variant_1920'],
                )
                payload = image_payload(image[0].get('image_variant_1920') if image else False)
                if payload and 'image_variant_1920' in self.target_fields('product.product'):
                    values['image_variant_1920'] = payload
            if not values:
                continue
            label = f'variant  update {row.get("default_code") or key or target_id}'
            self.save('product.product', target_id, values, label)

    def copy_suppliers(self, source_template_id, target_template_id, partner_index):
        if self.dry_run or not target_template_id or target_template_id is True:
            return
        if not self.source.has_model('product.supplierinfo') or not self.target.has_model('product.supplierinfo'):
            return
        supplier_fields = [
            name for name in (
                'partner_id', 'product_name', 'product_code', 'min_qty', 'price', 'delay',
                'discount', 'date_start', 'date_end', 'currency_id', 'product_uom_id',
            ) if name in self.source_fields('product.supplierinfo')
        ]
        rows = self.source.search_read(
            'product.supplierinfo', [('product_tmpl_id', '=', source_template_id)], supplier_fields,
        )
        for row in rows:
            partner = self.ensure_partner(m2o_id(row.get('partner_id')), {}, partner_index)
            if not partner or partner is True:
                continue
            values = {
                'partner_id': partner,
                'product_tmpl_id': target_template_id,
                'min_qty': row.get('min_qty') or 0.0,
                'price': row.get('price') or 0.0,
            }
            for name in ('product_name', 'product_code', 'delay', 'discount', 'date_start', 'date_end'):
                if row.get(name) not in (None, False, '') and self.has_field('product.supplierinfo', name):
                    values[name] = row[name]
            currency = self.currency_id(row.get('currency_id'))
            if currency:
                values['currency_id'] = currency
            uom = self.uom_id(row.get('product_uom_id'))
            if uom and self.has_field('product.supplierinfo', 'product_uom_id'):
                values['product_uom_id'] = uom
            found = self.target.execute('product.supplierinfo', 'search', [
                ('partner_id', '=', partner),
                ('product_tmpl_id', '=', target_template_id),
                ('min_qty', '=', values['min_qty']),
            ], limit=1)
            self.save(
                'product.supplierinfo', found[0] if found else False, values,
                f'vendor   {"update" if found else "create"} {row.get("partner_id")[1] if isinstance(row.get("partner_id"), list) else partner}',
            )

    def copy_gallery(self, source_template_id, target_template_id):
        if self.dry_run or not target_template_id or target_template_id is True:
            return
        if not self.source.has_model('product.image') or not self.target.has_model('product.image'):
            return
        if 'image_1920' not in self.source_fields('product.image') or 'image_1920' not in self.target_fields('product.image'):
            return
        rows = self.source.search_read(
            'product.image', [('product_tmpl_id', '=', source_template_id)],
            ['name', 'sequence'],
        )
        if not rows:
            return
        images = self.source.read_chunks('product.image', [row['id'] for row in rows], ['image_1920'], size=IMAGE_PAGE)
        for row in rows:
            payload = image_payload((images.get(row['id']) or {}).get('image_1920'))
            if not payload:
                continue
            name = row.get('name') or 'Image'
            found = self.target.execute('product.image', 'search', [
                ('product_tmpl_id', '=', target_template_id),
                ('name', '=', name),
            ], limit=1)
            values = {'name': name, 'product_tmpl_id': target_template_id, 'image_1920': payload}
            if row.get('sequence'):
                values['sequence'] = row['sequence']
            self.save('product.image', found[0] if found else False, values, f'gallery  {"update" if found else "create"} {name}')

    def match_product(self, row, codes, barcodes, names):
        code = text(row.get('default_code'))
        barcode = text(row.get('barcode'))
        name = text(row.get('name')).lower()
        if code and code in codes:
            return codes[code]
        if barcode and barcode in barcodes:
            return barcodes[barcode]
        if name and name in names:
            return names[name]
        return False

    def target_variant_id(self, source_variant_id):
        if not source_variant_id:
            return False
        if source_variant_id in self.variant_map:
            stored = self.variant_map[source_variant_id]
            return False if stored is True else stored
        found = self.source.execute(
            'product.product', 'read', [source_variant_id],
            fields=['product_tmpl_id', 'barcode', 'default_code'],
        )
        if not found:
            return False
        row = found[0]
        template_id = self.product_map.get(m2o_id(row.get('product_tmpl_id')))
        if not template_id or template_id is True:
            self.variant_map[source_variant_id] = False
            return False
        domain = [('product_tmpl_id', '=', template_id)]
        barcode = text(row.get('barcode'))
        code = text(row.get('default_code'))
        target = []
        if barcode:
            target = self.target.execute('product.product', 'search', domain + [('barcode', '=', barcode)], limit=1)
        if not target and code:
            target = self.target.execute('product.product', 'search', domain + [('default_code', '=', code)], limit=1)
        if not target:
            target = self.target.execute('product.product', 'search', domain, limit=2)
            if len(target) != 1:
                target = []
        self.variant_map[source_variant_id] = target[0] if target else False
        return self.variant_map[source_variant_id]

    def copy_combos(self):
        if not self.combo_sources or not self.has_field('product.template', 'combo_ids'):
            return
        if not self.source.has_model('product.combo') or not self.target.has_model('product.combo'):
            return
        for source_id in self.combo_sources:
            target_id = self.product_map.get(source_id)
            template = self.source.execute('product.template', 'read', [source_id], fields=['name', 'combo_ids'])
            name = template[0].get('name') if template else source_id
            if self.dry_run or not target_id or target_id is True:
                print(f'combo    link {name}')
                continue
            current = self.target.execute('product.template', 'read', [target_id], fields=['type', 'combo_ids'])
            if current and current[0].get('type') == 'combo' and current[0].get('combo_ids'):
                continue
            combo_ids = (template[0].get('combo_ids') if template else []) or []
            combos = self.source.read_chunks('product.combo', combo_ids, ['name', 'sequence', 'combo_item_ids'])
            created_ids = []
            for combo_id in combo_ids:
                combo = combos.get(combo_id) or {}
                item_ids = combo.get('combo_item_ids') or []
                items = self.source.read_chunks(
                    'product.combo.item', item_ids, ['product_id', 'extra_price'],
                ) if item_ids else {}
                commands = []
                for item_id in item_ids:
                    item = items.get(item_id) or {}
                    variant = self.target_variant_id(m2o_id(item.get('product_id')))
                    if not variant:
                        continue
                    commands.append((0, 0, {
                        'product_id': variant,
                        'extra_price': item.get('extra_price') or 0.0,
                    }))
                if not commands:
                    continue
                try:
                    created_ids.append(self.target.execute('product.combo', 'create', {
                        'name': combo.get('name') or name,
                        'sequence': combo.get('sequence') or 10,
                        'combo_item_ids': commands,
                    }))
                except xmlrpc.client.Fault as error:
                    print(f'FAILED combo {name}: {fault_line(error)}', file=sys.stderr)
            if not created_ids:
                print(f'FAILED combo {name}: no choices could be copied', file=sys.stderr)
                continue
            self.save('product.template', target_id, {
                'type': 'combo',
                'combo_ids': [(6, 0, created_ids)],
            }, f'combo    link {name}')

    def pull_products(self):
        fields = ['categ_id', 'uom_id', 'product_variant_count'] + self.scalar_names('product.template')
        for name in PRODUCT_ACCOUNT_FIELDS + (
            'taxes_id', 'supplier_taxes_id', 'product_tag_ids', 'uom_ids', 'optional_product_ids',
        ):
            if self.has_field('product.template', name):
                fields.append(name)
        rows = self.source.search_read('product.template', [], list(dict.fromkeys(fields)))
        codes, barcodes, names = {}, {}, {}
        for row in self.target.search_read('product.template', [], ['name', 'default_code', 'barcode']):
            if text(row.get('default_code')):
                codes[text(row.get('default_code'))] = row['id']
            if text(row.get('barcode')):
                barcodes[text(row.get('barcode'))] = row['id']
            if text(row.get('name')):
                names[text(row.get('name')).lower()] = row['id']
        partner_index = {}
        for row in self.target.search_read('res.partner', [], ['name', 'email', 'vat', 'ref']):
            key_name, key = self.partner_key(row)
            if key_name:
                partner_index[(key_name, key)] = row['id']
        optional_links = []
        created = skipped = 0
        for row in rows:
            name = text(row.get('name'))
            if not name:
                skipped += 1
                continue
            current = self.match_product(row, codes, barcodes, names)
            if current:
                print(f'product  skip {text(row.get("default_code")) or name}')
                self.product_map[row['id']] = current
                skipped += 1
                continue
            values = self.scalar_values('product.template', row)
            values['name'] = name
            several_variants = (row.get('product_variant_count') or 0) > 1
            if several_variants:
                for field_name in TEMPLATE_VARIANT_FIELDS:
                    values.pop(field_name, None)
            if values.get('type') == 'combo':
                # Combo products cannot be saved until their choices exist.
                values.pop('type')
                self.combo_sources.append(row['id'])
            category = self.ensure_category(m2o_id(row.get('categ_id')))
            if category:
                values['categ_id'] = category
            uom = self.uom_id(row.get('uom_id'))
            if uom:
                values['uom_id'] = uom
            if row.get('uom_ids') and self.has_field('product.template', 'uom_ids'):
                packagings = [self.uom_id(item) for item in row['uom_ids']]
                packagings = [item for item in packagings if item]
                if packagings:
                    values['uom_ids'] = [(6, 0, packagings)]
            self.map_account_fields(values, row, PRODUCT_ACCOUNT_FIELDS)
            if row.get('taxes_id'):
                taxes = self.tax_ids(row['taxes_id'])
                if taxes:
                    values['taxes_id'] = [(6, 0, taxes)]
            if row.get('supplier_taxes_id'):
                taxes = self.tax_ids(row['supplier_taxes_id'])
                if taxes:
                    values['supplier_taxes_id'] = [(6, 0, taxes)]
            if row.get('product_tag_ids') and self.has_field('product.template', 'product_tag_ids'):
                tags = self.product_tag_ids(row['product_tag_ids'])
                if tags:
                    values['product_tag_ids'] = [(6, 0, tags)]
            images = {}
            self.attach_images('product.template', {row['id']: row}, lambda _record_id: images)
            if images.get('_has_image'):
                values['_has_image'] = True
            images.pop('_has_image', None)
            values.update(images)
            saved = self.save(
                'product.template', False, values,
                f'product  create {text(row.get("default_code")) or name}',
            )
            if not saved:
                continue
            target_id = saved if saved is not True else False
            self.product_map[row['id']] = target_id
            if text(row.get('default_code')) and target_id:
                codes[text(row.get('default_code'))] = target_id
            if text(row.get('barcode')) and target_id:
                barcodes[text(row.get('barcode'))] = target_id
            if target_id:
                names[name.lower()] = target_id
            created += 1
            self.copy_attribute_lines(row['id'], target_id)
            self.copy_variants(row['id'], target_id)
            self.copy_suppliers(row['id'], target_id, partner_index)
            self.copy_gallery(row['id'], target_id)
            if row.get('optional_product_ids'):
                optional_links.append((target_id, row['optional_product_ids']))
        if self.has_field('product.template', 'optional_product_ids'):
            for target_id, source_ids in optional_links:
                if self.dry_run or not target_id or target_id is True:
                    continue
                mapped = [self.product_map.get(source_id) for source_id in source_ids]
                mapped = [item for item in mapped if item and item is not True]
                if mapped:
                    self.save(
                        'product.template', target_id,
                        {'optional_product_ids': [(6, 0, mapped)]},
                        f'product  options {target_id}',
                    )
        self.copy_combos()
        print(f'products: {created} created, {skipped} skipped')


def main():
    parser = argparse.ArgumentParser(description='Pull Odoo master data over XML-RPC.')
    parser.add_argument('--dry-run', action='store_true', help='Print what would be written without changing the target')
    args = parser.parse_args()
    source = Odoo(SOURCE_URL, SOURCE_DB, SOURCE_USER, SOURCE_PASSWORD)
    target = Odoo(TARGET_URL, TARGET_DB, TARGET_USER, TARGET_PASSWORD)
    print(f'Source uid {source.uid} -> target uid {target.uid}')
    pull = Pull(source, target, args.dry_run)
    pull.pull_accounts()
    pull.pull_journals()
    pull.pull_customers()
    pull.pull_products()


if __name__ == '__main__':
    try:
        main()
    except xmlrpc.client.Fault as error:
        print(fault_line(error), file=sys.stderr)
        sys.exit(1)
