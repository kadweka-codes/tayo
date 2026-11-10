# POS Manufacture on Payment

`odutech_pos_manufacture` produces a meal, or any other manufactured product, at the moment a Point of Sale order is paid. If the product has a **manufacture** bill of materials, the module creates a manufacturing order, completes it, and puts the finished quantity into the same location the POS sells from. The POS delivery then takes that quantity out.

The finished product does not go negative. Components are consumed by the manufacturing order. A product with no bill of materials is sold exactly as before.

## Install

1. Install **Manufacturing** (`mrp`) and **Point of Sale**.
2. Update the app list and install **POS Manufacture on Payment**.
3. Open each POS shop that should produce meals. Under the inventory operation type, leave **Manufacture products with a BoM** enabled. It is on by default. Clear it on a shop that must never create manufacturing orders.

## Prepare a meal

Do this once for each item that is cooked or assembled when it is sold.

1. Create the finished product, for example `Chicken Burger`. It must be a goods product, not a service. Put it on the POS menu.
2. Create the ingredient products, for example bun, patty, and sauce. Keep them as goods products and stock them in the location the POS uses as its source location.
3. Open **Manufacturing → Products → Bills of Materials** and create a bill of materials:
   - Product: `Chicken Burger`
   - BoM Type: **Manufacture** (not Kit)
   - Components: the ingredients and the quantity used for one burger
   - If the company is set, it must be the POS company, or leave the company empty so every company can use it
4. Confirm the POS operation type (Point of Sale → Configuration → the shop → Inventory) points at the warehouse and source location where those ingredients are stored. The manufacturing order consumes components from that location and receives the finished meal into that same location.

A **Kit** bill of materials is left to the normal POS delivery. This module does not create a manufacturing order for a kit.

## What happens on a sale

1. The cashier sells one or more products and validates the payment.
2. For each line with a quantity above zero and a manufacture bill of materials, Odoo creates one manufacturing order linked to that line.
3. The order is confirmed and marked done for the quantity sold.
4. Ingredients leave the POS source location. The finished meal enters that location.
5. The POS delivery then ships the finished meal to the customer.

Open the paid order in the backend. The **Manufacturing** button shows the orders, and each product line shows its manufacturing order.

Products without a manufacture bill of materials are ignored. Refunds are ignored: returning a meal puts the finished product back in stock and does not reverse the original manufacturing order. A serial-tracked product must be sold one unit at a time so a serial number can be created. Lot-tracked products receive one new lot for the quantity sold.

## Stock

| Stock | What changes |
| --- | --- |
| Finished meal | Produced, then delivered. On-hand stays flat when both steps use the same location. |
| Ingredients | Consumed by the manufacturing order. They go negative only when the location does not have enough on hand. |

Manufacturing runs when the order becomes **Paid**, before the POS delivery. That includes shops that update stock only when the session is closed: the meal is produced at payment, and the delivery takes it out when the session closes.

Paying the same order again does not create a second manufacturing order for a line that already has one.

## Turn it off

Clear **Manufacture products with a BoM** on the POS shop. New payments stop creating manufacturing orders. Orders already produced are left as they are.
