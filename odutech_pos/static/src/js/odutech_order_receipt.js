/** @odoo-module */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

const WALLET_KEYS = [
    "premier_wallet_number",
    "evc_plus_number",
    "e_ahab_number",
    "my_cash_number",
    "t_plus_number",
    "e_besa",
    "my_bank",
];

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(...arguments);
        for (const key of WALLET_KEYS) {
            this[key] = vals[key] || false;
        }
        this.setWalletNumbers();
    },

    setWalletNumbers() {
        const data = this._walletSource();
        if (!data) {
            return;
        }
        for (const key of WALLET_KEYS) {
            if (data[key]) {
                this[key] = data[key];
            }
        }
    },

    _walletSource() {
        const pos = this.pos;
        if (!pos) {
            return null;
        }
        const cashier = typeof pos.getCashier === "function" ? pos.getCashier() : pos.cashier;
        if (cashier && (cashier.premier_wallet_number || cashier.evc_plus_number || cashier.my_bank)) {
            return cashier;
        }
        const employees = pos.models?.["hr.employee"]?.getAll?.() || [];
        if (cashier && employees.length) {
            const employee = employees.find((emp) => emp.id === cashier.id);
            if (employee && (employee.premier_wallet_number || employee.evc_plus_number || employee.my_bank)) {
                return employee;
            }
        }
        const raw = pos.config && pos.config.employee_data_json;
        if (!raw) {
            return null;
        }
        if (typeof raw === "string") {
            try {
                return JSON.parse(raw);
            } catch (_error) {
                return null;
            }
        }
        return raw;
    },
});
