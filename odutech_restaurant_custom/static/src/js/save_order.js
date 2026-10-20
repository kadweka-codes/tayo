odoo.define('tremos_restaurant_custom.save_button', function(require) {
'use strict';
  const { Gui } = require('point_of_sale.Gui');
  const PosComponent = require('point_of_sale.PosComponent');
  const { identifyError } = require('point_of_sale.utils');
  const ProductScreen = require('point_of_sale.ProductScreen');
  const { useListener } = require("@web/core/utils/hooks");
  const Registries = require('point_of_sale.Registries');
  const PaymentScreen = require('point_of_sale.PaymentScreen');
  class CustomDemoButtons extends PosComponent {
      setup() {
          super.setup();
          useListener('click', this.onClick);
      }
     async onClick() {
               const { confirmed} = await
this.showPopup("ConfirmPopup", {
                      title: this.env._t('Title of the Popup?'),
                      body: this.env._t('Body of the popup'),
                  });
                 }
  }
CustomDemoButtons.template = 'CustomDemoButtons';
  ProductScreen.addControlButton({
      component: CustomDemoButtons,
      condition: function() {
          return this.env.pos;
      },
  });
  Registries.Component.add(CustomDemoButtons);
  return CustomDemoButtons;
});