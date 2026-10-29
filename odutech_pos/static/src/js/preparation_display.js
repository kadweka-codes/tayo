/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { PrepDisplay } from "@pos_enterprise/app/services/preparation_display_service";
import { PrepDisplay as PrepDisplayScreen } from "@pos_enterprise/app/components/preparation_display/preparation_display";
import { Order } from "@pos_enterprise/app/components/order/order";
import { onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function stageRole(display, stage) {
    if (!stage) {
        return "cook";
    }
    const roles = display.stageRoles || {};
    return roles[stage.id] || roles[String(stage.id)] || stage.owner_role || "cook";
}

function relationId(value) {
    if (!value) {
        return false;
    }
    if (Array.isArray(value)) {
        return value[0];
    }
    return value.id || value;
}

patch(PrepDisplay.prototype, {
    _odutechRole(stage) {
        return stageRole(this, stage);
    },

    _odutechOrderVisible(order) {
        const viewer = this.viewer;
        if (!viewer || viewer.see_all) {
            return true;
        }
        const role = this._odutechRole(order.stage);
        if (role !== viewer.role) {
            return false;
        }
        const posOrder = order.prepOrder?.pos_order_id;
        if (viewer.role === "cook") {
            return relationId(posOrder?.cook_employee_id) === viewer.employee_id
                || relationId(posOrder?.assigned_cook) === viewer.employee_id;
        }
        if (viewer.role === "waiter") {
            return relationId(posOrder?.waiter_employee_id) === viewer.employee_id
                || relationId(posOrder?.employee_id) === viewer.employee_id;
        }
        return false;
    },

    get filteredOrders() {
        const orders = super.filteredOrders || [];
        if (!this.viewer || this.viewer.see_all) {
            return orders;
        }
        return orders.filter((order) => this._odutechOrderVisible(order));
    },
});

patch(PrepDisplayScreen.prototype, {
    setup() {
        super.setup(...arguments);
        const orm = useService("orm");
        onWillStart(async () => {
            const [viewer, stageRoles] = await Promise.all([
                orm.call("pos.order", "kitchen_viewer", []),
                orm.call("pos.order", "kitchen_stage_roles", []),
            ]);
            this.prepDisplay.viewer = viewer;
            this.prepDisplay.stageRoles = stageRoles;
            if (!viewer?.see_all && viewer?.role) {
                const match = Object.entries(stageRoles).find(([, role]) => role === viewer.role);
                if (match) {
                    this.prepDisplay.selectedStageId = Number(match[0]);
                }
            }
        });
    },
});

patch(Order.prototype, {
    get assignmentLabel() {
        const stage = this.props.order.stage;
        const role = stageRole(this.prepDisplay, stage);
        const posOrder = this.order.pos_order_id;
        if (role === "waiter") {
            return `Waiter: ${posOrder?.waiter_name || "Unassigned"}`;
        }
        return `Cook: ${posOrder?.cook_name || "Unassigned"}`;
    },
});
