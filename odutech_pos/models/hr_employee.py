from odoo import api, fields, models

WALLET_FIELDS = (
    'premier_wallet_number',
    'evc_plus_number',
    'e_ahab_number',
    'my_cash_number',
    't_plus_number',
    'e_besa',
    'my_bank',
)
RESTAURANT_ROLES = [
    ('cook', 'Cook'),
    ('waiter', 'Waiter'),
    ('security', 'Security'),
    ('Driver', 'Driver'),
    ('cleaner', 'Cleaner'),
    ('technician', 'Technician'),
    ('imam', 'Imam'),
    ('manager', 'Manager'),
]


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    employee_restaurant_role = fields.Selection(RESTAURANT_ROLES, tracking=True)
    premier_wallet_number = fields.Char(string="Premier Wallet number")
    evc_plus_number = fields.Char(string="EVC Plus number")
    e_ahab_number = fields.Char(string="E-AHAB number")
    my_cash_number = fields.Char(string="MyCash number")
    t_plus_number = fields.Char(string="T-Plus number")
    e_besa = fields.Char(string="E-Besa Number")
    my_bank = fields.Char(string="My Bank")

    def wallet_values(self):
        self.ensure_one()
        return {name: self[name] or False for name in WALLET_FIELDS}

    @api.model
    def _load_pos_data_fields(self, config_id):
        parent = getattr(super(), '_load_pos_data_fields', None)
        fields_list = list(parent(config_id)) if parent else []
        for name in list(WALLET_FIELDS) + ['employee_restaurant_role']:
            if name not in fields_list:
                fields_list.append(name)
        return fields_list


class HrEmployeePublic(models.Model):
    _inherit = 'hr.employee.public'

    # Related, not stored. hr.employee.public is a SQL view, so a stored
    # field would be missing until that view is rebuilt.
    employee_restaurant_role = fields.Selection(RESTAURANT_ROLES, related='employee_id.employee_restaurant_role', readonly=True, compute_sudo=True)
    premier_wallet_number = fields.Char(related='employee_id.premier_wallet_number', readonly=True, compute_sudo=True)
    evc_plus_number = fields.Char(related='employee_id.evc_plus_number', readonly=True, compute_sudo=True)
    e_ahab_number = fields.Char(related='employee_id.e_ahab_number', readonly=True, compute_sudo=True)
    my_cash_number = fields.Char(related='employee_id.my_cash_number', readonly=True, compute_sudo=True)
    t_plus_number = fields.Char(related='employee_id.t_plus_number', readonly=True, compute_sudo=True)
    e_besa = fields.Char(related='employee_id.e_besa', readonly=True, compute_sudo=True)
    my_bank = fields.Char(related='employee_id.my_bank', readonly=True, compute_sudo=True)
