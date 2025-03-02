# -*- coding: utf-8 -*-
{
    'name': "gestion_eventos_restaurante",

    'summary': "Gestión de eventos",

    'description': """
        Este módulo facilita la organización de eventos de principio a fin,
        ayudando a que todo fluya sin problemas. Desde la gestión de reservas
        y la personalización de detalles hasta el control de pagos y la logística,
        permite a los organizadores manejar cada aspecto de la celebración de forma sencilla
        y eficiente. Así, los clientes pueden disfrutar de su evento sin preocupaciones, y los
        organizadores tienen todo bajo control sin complicaciones.
    """,

    'author': "Fran, Manuel y Raquel",
    'website': "https://www.yourcompany.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'calendar'],

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/views.xml',
        'data/opciones_evento.xml',
        'data/platos_data.xml',
        'data/email_templates.xml',
        'report/report_reservas.xml',
        'report/report_evento.xml',
        'report/report_actividad_evento.xml',
    ],
    'assets': {},
    'application': True,
    'installable': True,
    'icon': '/restaurante/static/catering_icono.jpg',
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}

