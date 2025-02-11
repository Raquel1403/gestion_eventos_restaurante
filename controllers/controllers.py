# -*- coding: utf-8 -*-
# from odoo import http


# class GestiónEventosRestaurante(http.Controller):
#     @http.route('/gestión_eventos_restaurante/gestión_eventos_restaurante', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/gestión_eventos_restaurante/gestión_eventos_restaurante/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('gestión_eventos_restaurante.listing', {
#             'root': '/gestión_eventos_restaurante/gestión_eventos_restaurante',
#             'objects': http.request.env['gestión_eventos_restaurante.gestión_eventos_restaurante'].search([]),
#         })

#     @http.route('/gestión_eventos_restaurante/gestión_eventos_restaurante/objects/<model("gestión_eventos_restaurante.gestión_eventos_restaurante"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('gestión_eventos_restaurante.object', {
#             'object': obj
#         })

