# -*- coding: utf-8 -*-
{
    'name': "ZKTeco | Biometrics",
    'summary': "Short (1 phrase/line) summary of the module's purpose",
    'description': """
        Long description of module's purpose
    """,

    'author': "Odutech Solutions",
    'website': "https://www.odutechsolutions.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'hr',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'mail', 'hr', 'hr_attendance', 'resource', 'hr_holidays'],

    # always loaded
    'data': [
        'security/ir.model.access.xml',
        'views/biometric_log.xml',
        'views/views.xml',
        'views/menus.xml',
        'views/employee.xml',
        'data/cron_jobs.xml',
        'views/dashboard_views.xml',
        "wizard/displinary_action_wizard_view.xml"
    ],
    'assets':{
        'web.assets_backend':[
            "biometric_attendance/static/src/components/home_dashboard/home_dashboard.js",
            "biometric_attendance/static/src/components/home_dashboard/home_dashboard.xml"
        ]
    }
}

