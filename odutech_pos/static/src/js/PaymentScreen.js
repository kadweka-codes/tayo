/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

patch(PaymentScreen.prototype, {
    async validateOrder(isForceValidate) {
        if (this.currentOrder && typeof this.currentOrder.setWalletNumbers === "function") {
            this.currentOrder.setWalletNumbers();
        }
        return super.validateOrder(...arguments);
    },
});
