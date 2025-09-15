# -*- coding: utf-8 -*-
{
    'name': "Veterinary management",
    'summary': "Manage the animals that visit our veterinarian",

    'description': """
Manage the animals that visit our veterinarian
    """,

    'author': "Javier Diez",
    'website': "https://javierdiez.netlify.app/",
    'license': 'AGPL-3',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Animals',
    'version': '1.0',

    # any module necessary for this one to work correctly
    'depends': ['base','mail','contacts','product','account','account_accountant','stock'],

    # always loaded
    'data': [
        'security/vet_security.xml',
        'security/ir.model.access.csv',  # Security rules
        'security/vet_security.xml',
        'data/sequence_data.xml',
        'data/visit_sequence_data.xml',
        'data/treatment_product.xml',
        'data/vet_dashboard_data.xml',
        'views/vet_dashboard_views.xml',
        'views/animal_views.xml',
        'views/animal_doctor_views.xml',
        'views/animal_owner_views.xml',
        'views/res_partner_views.xml',
        'views/animal_appointment_views.xml',
        'views/animal_visits_views.xml',
        'views/report.xml',
        'views/animal_invoice_views.xml',
        'views/animal_history.xml',
        'views/service_views.xml',
        'views/menu_vet_views.xml',

    ],
'assets': {
    'web.report_assets_common': [
        'vet_new/static/src/img/logo.png',
    ]
},
'demo': [],
    'sequence':-999,
    'installable': True,
    'application': True,
    'auto_install': False,
}

