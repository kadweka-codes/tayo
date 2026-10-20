/** @odoo-module */

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";

patch(OrderReceipt.prototype, {
    setup() {
        super.setup(...arguments);
        const order = this.props.order;
        if (order && typeof order.setWalletNumbers === "function") {
            order.setWalletNumbers();
        }
    },
});
