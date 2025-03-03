from odoo import models, fields, api # type: ignore
from odoo.exceptions import ValidationError, UserError # type: ignore
import base64
import qrcode # type: ignore
from io import BytesIO
#from odoo.addons.sms.models.sms_api import SMSAPI  # type: ignore # Para envío de SMS


# ====================================================
# Extensión de res.partner (clientes)
# ====================================================
class ResPartnerEvent(models.Model):
    _inherit = 'res.partner'
    
    is_event_customer = fields.Boolean(string="Cliente de Eventos", default=False)
    # Puedes agregar otros campos específicos para clientes de eventos si es necesario.

# ====================================================
# Extensión de calendar.event (Calendario de Eventos)
# ====================================================
class CalendarEventExtended(models.Model):
    _inherit = 'calendar.event'

    # Relación opcional para vincular el evento del calendario a una reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva")
    
    tipo_celebracion = fields.Selection([
        ('boda', 'Boda'),
        ('cumpleaños', 'Cumpleaños'),
        ('corporativo', 'Corporativo'),
        # Agrega otros tipos según la necesidad
    ], string="Tipo de Celebración")
    
    numero_personas = fields.Integer(string="Número de Personas")
    
    @api.constrains('numero_personas')
    def _check_numero_personas(self):
        for record in self:
            if record.numero_personas and record.numero_personas <= 0:
                raise ValidationError("El número de personas debe ser mayor a cero.")

# ====================================================
# Modelo: Reserva
# ====================================================
class Reserva(models.Model):
    _name = 'restaurante.reserva'
    _description = 'Reserva para eventos'

    fecha_reserva = fields.Date(
        string="Fecha de Reserva", 
        required=True
    )
    tipo_evento = fields.Selection([
        ('cumpleaños', 'Cumpleaños'),
        ('boda', 'Boda'),
        ('corporativo', 'Corporativo'),
        ('otro', 'Otro')
    ], string="Tipo de Evento", required=True)
    estado = fields.Selection([
        ('reservado', 'Reservado'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado')
    ], string="Estado", default='reservado', required=True)
    color_disponibilidad = fields.Integer(
        string="Color de Disponibilidad",
        compute="_compute_color_disponibilidad",
        store=True
    )
    saldo_pendiente = fields.Float(
        string="Saldo Pendiente",
        compute="_compute_saldo_pendiente",
        store=True
    )

   
    lugar = fields.Char(string="Lugar", required=True)
    numero_personas = fields.Integer(string="Número de Personas", required=True)
    detalles_adicionales = fields.Text(string="Detalles Adicionales")
     # Nuevo campo para controlar la visibilidad de la pestaña "Eventos"
    mostrar_eventos = fields.Boolean(string="Mostrar Eventos", default=False)
    
    # Usamos res.partner nativo para los clientes
    cliente_id = fields.Many2one('res.partner', string="Cliente", required=True)
    email = fields.Char(related="cliente_id.email", string="Email", readonly=True)
    telefono = fields.Char(related="cliente_id.phone", string="Teléfono", readonly=True)
    # Vinculación con el calendario extendido (opcional)
    calendar_event_id = fields.Many2one('calendar.event', string="Evento en Calendario")
    
    # Relación con el modelo Evento (información adicional sobre el evento)
    evento_ids = fields.One2many('restaurante.evento', 'reserva_id', string="Eventos")
    
    # Relación con los pagos
    pago_ids = fields.One2many('restaurante.pago', 'reserva_id', string="Pagos")

    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    def action_generate_report_reservas(self):
        return self.env.ref('gestion_eventos_restaurante.action_report_reservas').report_action(self)
    
    @api.constrains('evento_ids')
    def _check_evento_unico(self):
        for reserva in self:
            if len(reserva.evento_ids) > 1:
                raise ValidationError("Solo se permite un evento por reserva.")

    @api.constrains('numero_personas')
    def _check_numero_personas(self):
        for reserva in self:
            if reserva.numero_personas <= 0:
                raise ValidationError("El número de personas debe ser mayor a cero.")

    @api.depends('fecha_reserva')
    def _compute_color_disponibilidad(self):
        """Define el color según la disponibilidad de la fecha"""
        fechas_ocupadas = self.env['restaurante.reserva'].search([]).mapped('fecha_reserva')

        for record in self:
           record.color_disponibilidad = 1 if record.fecha_reserva in fechas_ocupadas else 10

    

    @api.constrains('fecha_reserva')
    def _check_fecha_unica(self):
        """Evita que se creen reservas con la misma fecha"""
        for reserva in self:
            existe = self.env['restaurante.reserva'].search([
                ('fecha_reserva', '=', reserva.fecha_reserva),
                ('id', '!=', reserva.id)  # Evita conflicto al editar
            ])
            if existe:
                raise ValidationError("Ya existe una reserva para esta fecha. Por favor, elige otra.")
    
    def action_send_confirmation(self):
        """Método que se ejecuta al hacer clic en el botón para enviar el correo"""
        self.ensure_one()  # Asegura que solo se ejecute en un registro

        if not self.email or '@' not in self.email:
            raise UserError("El correo del cliente no es válido.")

        # Buscar la plantilla de correo
        template = self.env.ref('gestion_eventos_restaurante.confirmacion_reserva_email_template', raise_if_not_found=False)

        if not template:
            raise UserError("No se encontró la plantilla de correo.")

        # Enviar correo
        template.send_mail(self.id, force_send=True)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Correo de confirmación enviado.',
                'type': 'rainbow_man',
            }
        }
    
    def action_ver_calendario(self):
        """Abre la vista de calendario para ver las reservas con colores"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Calendario de Reservas',
            'view_mode': 'calendar',
            'res_model': 'restaurante.reserva',
            'view_id': self.env.ref('gestion_eventos_restaurante.view_reserva_calendar').id,
            'target': 'new',
        }


    @api.depends('pago_ids', 'evento_ids.budget')
    def _compute_saldo_pendiente(self):
        """Calcula el saldo pendiente restando los pagos completados al presupuesto estimado"""
        for reserva in self:
            presupuesto = sum(reserva.evento_ids.mapped('budget'))  # Obtiene el presupuesto total del evento
            total_pagado = sum(p.monto for p in reserva.pago_ids if p.estado_pago == 'completado')
            reserva.saldo_pendiente = max(presupuesto - total_pagado, 0)

    @api.constrains('monto', 'reserva_id')
    def _check_pago_no_supera_saldo(self):
        """Evita que se registre un pago que supere el saldo pendiente de la reserva"""
        for pago in self:
            if pago.reserva_id:
                saldo_pendiente = pago.reserva_id.saldo_pendiente
                if pago.monto > saldo_pendiente:
                    raise ValidationError(f"El monto del pago ({pago.monto}) no puede superar el saldo pendiente ({saldo_pendiente}).")
    # @api.model
    # def create(self, vals):
    #     """Cuando se crea una reserva, se envía un email y un SMS automáticamente."""
    #     reserva = super(Reserva, self).create(vals)

    #     # Enviar email de confirmación
    #     template = self.env.ref("gestion_eventos_restaurante.confirmacion_reserva_email_template")
    #     if template and reserva.email:
    #         template.send_mail(reserva.id, force_send=True)
    #         # Mostrar notificación en la interfaz
    #         #self.env.user.notify_info(message="Notificación de reserva enviada correctamente.", title="Éxito")

    #     # # Enviar SMS de confirmación
    #     # if reserva.telefono:
    #     #     mensaje = f"Hola {reserva.cliente_id.name}, tu reserva para {reserva.fecha_reserva} ha sido confirmada. ¡Te esperamos!"
    #     #     sms_api = SMSAPI(self.env)
    #     #     sms_api.send_sms(reserva.telefono, mensaje)

    #     return reserva




# ====================================================
# Modelo: Evento (Modificado)
# ====================================================
class Evento(models.Model):
    _name = 'restaurante.evento'
    _description = 'Evento asociado a una reserva'

    tipo_evento = fields.Selection([
        ('cumpleaños', 'Cumpleaños'),
        ('boda', 'Boda'),
        ('corporativo', 'Corporativo'),
        ('otro', 'Otro')
    ], string="Tipo de Evento", compute="_compute_tipo_evento", store=True, readonly=True)
    
    @api.depends('reserva_id.tipo_evento')
    def _compute_tipo_evento(self):
        for rec in self:
            rec.tipo_evento = rec.reserva_id.tipo_evento if rec.reserva_id else False

    
    # personalizacion = fields.Text(string="Personalización del Evento")
    agenda = fields.Text(string="Agenda / Cronograma")
    # Presupuesto total (suma de precios fijos)
    budget = fields.Float(string='Presupuesto Estimado', compute='_compute_budget', store=True)
    # Relación con los invitados
    invitado_ids = fields.One2many("restaurante.invitado", "evento_id", string="Lista de Invitados")
    # Relación con servicio
    servicio_ids = fields.Many2many('restaurante.servicio', string="Servicios")

    # ==============================
    # Nuevos campos para Menús Especiales
    # ==============================
    vegan_menu = fields.Integer(string="Menú Vegano", default=0)
    vegetarian_menu = fields.Integer(string="Menú Vegetariano", default=0)
    gluten_free_menu = fields.Integer(string="Menú Sin Gluten", default=0)
    lactose_free_menu = fields.Integer(string="Menú Sin Lactosa", default=0)
    kids_menu = fields.Integer(string="Menú Infantil", default=0)


    # Relación con la reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)
    
    # Relación con servicios y menús
    servicio_menu_ids = fields.One2many('restaurante.servicio_menu', 'evento_id', string="Servicios y Menús")

    # Relación con actividades (agenda detallada)
    actividad_ids = fields.One2many('restaurante.actividad', 'evento_id', string="Actividades")
    # Relación con los platos del menú
    entrantes_ids = fields.Many2many('restaurante.plato', string="Entrantes", domain=[('tipo_plato', '=', 'entrante')])
    primer_plato_id = fields.Many2one('restaurante.plato', string="Primer Plato", domain=[('tipo_plato', '=', 'principal')])
    segundo_plato_id = fields.Many2one('restaurante.plato', string="Segundo Plato", domain=[('tipo_plato', '=', 'secundario')])
    postre_id = fields.Many2one('restaurante.plato', string="Postre", domain=[('tipo_plato', '=', 'postre')])
    
    special_menu_total = fields.Integer(
        string="Total Menús Especiales", 
        compute="_compute_special_menu_total", 
        store=True
    )

    @api.depends('vegan_menu', 'vegetarian_menu', 'gluten_free_menu', 'lactose_free_menu', 'kids_menu')
    def _compute_special_menu_total(self):
        for rec in self:
            rec.special_menu_total = (
                rec.vegan_menu +
                rec.vegetarian_menu +
                rec.gluten_free_menu +
                rec.lactose_free_menu +
                rec.kids_menu
            )

    @api.constrains('vegan_menu', 'vegetarian_menu', 'gluten_free_menu', 'lactose_free_menu', 'kids_menu')
    def _check_special_menu_total(self):
        for rec in self:
            if rec.reserva_id and rec.special_menu_total > rec.reserva_id.numero_personas:
                raise ValidationError("La suma de los menús especiales no puede ser mayor que el número de personas en la reserva.")

    @api.depends('servicio_menu_ids', 'servicio_ids',
             'entrantes_ids', 'primer_plato_id', 'segundo_plato_id', 'postre_id',
             'reserva_id.numero_personas', 'vegan_menu', 'vegetarian_menu', 'gluten_free_menu', 'lactose_free_menu', 'kids_menu')
    def _compute_budget(self):
        """Calcula el presupuesto total del evento incluyendo:
        - Servicios y Menús
        - Iluminación, Música y Decoración
        - Entrantes ajustados por número de personas
        - Platos principales multiplicados por invitados menos menús especiales
        - Costos de menús especiales
        """
        for event in self:
            total = sum(servicio.precio for servicio in event.servicio_menu_ids)
            total += sum(servicio.price for servicio in event.servicio_ids)

            # Calcular costo de entrantes por número de personas ajustado
            if event.reserva_id and event.entrantes_ids:
                num_personas = event.reserva_id.numero_personas
                num_entrantes = len(event.entrantes_ids)

                if num_entrantes > 0:
                    total += sum((entrante.precio * num_personas) / num_entrantes for entrante in event.entrantes_ids)

            # Calcular costo de platos principales ajustados por menús especiales
            num_menus_especiales = event.vegan_menu + event.vegetarian_menu + event.gluten_free_menu + event.lactose_free_menu + event.kids_menu
            personas_restantes = max(event.reserva_id.numero_personas - num_menus_especiales, 0)  # Evita números negativos

            if event.primer_plato_id:
                total += event.primer_plato_id.precio * personas_restantes
            if event.segundo_plato_id:
                total += event.segundo_plato_id.precio * personas_restantes
            if event.postre_id:
                total += event.postre_id.precio * personas_restantes

            # **Añadir costos de menús especiales**
            total += (event.vegan_menu + event.vegetarian_menu + event.gluten_free_menu + event.lactose_free_menu) * 20
            total += event.kids_menu * 15

            event.budget = total


    def print_evento_report(self):
            return self.env.ref('gestion_eventos_restaurante.action_report_evento').report_action(self)

    def action_generate_actividad_report(self):
        return self.env.ref('gestion_eventos_restaurante.actividad_evento_report').report_action(self)
    
# ====================================================
# Modelo: Servicio personalizado
# ====================================================
class Servicio(models.Model):
    _name = 'restaurante.servicio'
    _description = 'Servicios del Evento'

    name = fields.Char(string="Servicio", required=True)
    tipo = fields.Selection([
        ('iluminacion', 'Iluminación'),
        ('musica', 'Música'),
        ('decoracion', 'Decoración'),
    ], string="Tipo de Servicio", required=True)
    price = fields.Float(string="Precio", required=True, readonly=True)  # Precio fijo

# ====================================================
# Modelo: Servicio y Menú
# ====================================================
class ServicioMenu(models.Model):
    _name = 'restaurante.servicio_menu'
    _description = 'Servicio y Menú para eventos'

    descripcion_servicio = fields.Text(string="Descripción del Servicio", required=True)
    opcion_menu = fields.Char(string="Opción de Menú", required=True)
    cantidad_calculada = fields.Float(string="Cantidad Calculada")
    precio = fields.Float(string="Precio Total", compute='_compute_precio_total', store=True)  # Ahora se calcula automáticamente
    
    # Relación con el evento
    evento_id = fields.Many2one('restaurante.evento', string="Evento", required=True)
    
    # Relación con los platos que componen el menú
    plato_ids = fields.One2many('restaurante.plato', 'servicio_menu_id', string="Platos")
    # Relación con los platos clasificados
    entrantes_ids = fields.Many2many('restaurante.plato', string="Entrantes", domain=[('tipo_plato', '=', 'entrante')])
    primer_plato_id = fields.Many2one('restaurante.plato', string="Primer Plato", domain=[('tipo_plato', '=', 'principal')])
    segundo_plato_id = fields.Many2one('restaurante.plato', string="Segundo Plato", domain=[('tipo_plato', '=', 'secundario')])
    postre_id = fields.Many2one('restaurante.plato', string="Postre", domain=[('tipo_plato', '=', 'postre')])

    @api.depends('entrantes_ids', 'primer_plato_id', 'segundo_plato_id', 'postre_id')
    def _compute_precio_total(self):
        """ Calcula el precio total del menú sumando los precios de los platos seleccionados """
        for servicio in self:
            total = sum(servicio.entrantes_ids.mapped('precio'))
            if servicio.primer_plato_id:
                total += servicio.primer_plato_id.precio
            if servicio.segundo_plato_id:
                total += servicio.segundo_plato_id.precio
            if servicio.postre_id:
                total += servicio.postre_id.precio
            servicio.precio = total

# ====================================================
# Modelo: Plato
# ====================================================
class Plato(models.Model):
    _name = 'restaurante.plato'
    _description = 'Plato perteneciente a un Servicio y Menú'
    _rec_name = 'nombre_plato'

    nombre_plato = fields.Char(string="Nombre del Plato", required=True)
    descripcion = fields.Text(string="Descripción")
    ingredientes = fields.Text(string="Ingredientes")
    tipo_plato = fields.Selection([
        ('entrante', 'Entrante'),
        ('principal', 'Plato Principal'),
        ('secundario', 'Plato Secundario'),
        ('postre', 'Postre'),
        ('bebida', 'Bebida')
    ], string="Tipo de Plato", required=True)

    precio = fields.Float(string="Precio", required=True)  # Ahora cada plato tiene un precio
    
    # Relación con el servicio/menú
    servicio_menu_id = fields.Many2one('restaurante.servicio_menu', string="Servicio y Menú", required=False)

    def name_get(self):
        """Muestra el nombre del plato en la selección en lugar del ID."""
        result = []
        for record in self:
            name = f"{record.nombre_plato} - ${record.precio}"
            print(f"DEBUG: name_get() ejecutado para {record.id} → {name}")  # <--- Depuración
            result.append((record.id, name))
        return result


# ====================================================
# Modelo: Actividad (Agenda Detallada)
# ====================================================
class Actividad(models.Model):
    _name = 'restaurante.actividad'
    _description = 'Actividad en la agenda del evento'

    nombre_actividad = fields.Char(string="Nombre de la Actividad", required=True)
    descripcion = fields.Text(string="Descripción")
    hora_inicio = fields.Char(string="Hora de Inicio", required=True)
    hora_fin = fields.Char(string="Hora de Fin", required=True)

    evento_id = fields.Many2one('restaurante.evento', string="Evento", required=True, ondelete="cascade")

    espacio = fields.Selection([
        ('salones', 'Salón de Eventos'),
        ('exterior', 'Exteriores'),
        ('recepcion', 'Área de Recepción'),
    ], string="Espacio del Evento", required=True)
    
    @api.constrains('hora_inicio', 'hora_fin')
    def _check_horario(self):
        for record in self:
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError("La hora de fin debe ser mayor que la hora de inicio.")
# ====================================================
# Modelo: Pago
# ====================================================
class Pago(models.Model):
    _name = 'restaurante.pago'
    _description = 'Pago realizado para reserva o evento'

    monto = fields.Float(string="Monto", required=True)
    fecha_pago = fields.Date(string="Fecha de Pago", default=fields.Date.context_today, required=True)
    metodo_pago = fields.Selection([
        ('tarjeta', 'Tarjeta de Crédito/Débito'),
        ('transferencia', 'Transferencia Bancaria'),
        ('digital', 'Pago Digital')
    ], string="Método de Pago", required=True)
    estado_pago = fields.Selection([
        ('completado', 'Completado'),
        ('pendiente', 'Pendiente')
    ], string="Estado del Pago", default='pendiente', required=True)

    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)

    numero_factura = fields.Char(string="Número de Factura", readonly=True)
    factura_generada = fields.Boolean(string="Factura Generada", default=False)

    @api.constrains('monto', 'reserva_id')
    def _check_pago_no_supera_presupuesto(self):
        """Evita que la suma total de los pagos supere el presupuesto total del evento"""
        for pago in self:
            if pago.reserva_id:
                total_pagado = sum(pago.reserva_id.pago_ids.mapped('monto'))
                presupuesto = sum(pago.reserva_id.evento_ids.mapped('budget'))

                if total_pagado > presupuesto:
                    raise ValidationError(
                        f"La suma total de los pagos ({total_pagado}) no puede superar el presupuesto total ({presupuesto})."
                    )

    

    def action_generar_imprimir_factura(self):
        self.ensure_one()

        if self.estado_pago != 'completado':
            raise UserError("No se puede generar la factura porque el pago aún no está completado.")

        # Si no hay factura, crearla y asignar el número al pago
        factura = self.env['restaurante.factura'].search([('pago_id', '=', self.id)], limit=1)
        if not factura:
            factura = self.env['restaurante.factura'].create({
                'numero_factura': f"FACT-{self.id:05d}",
                'fecha_emision': self.fecha_pago,
                'total': self.monto,
                'pago_id': self.id,
            })
            self.numero_factura = factura.numero_factura
            self.factura_generada = True  # Marcamos que la factura fue generada

        # Generar el informe PDF sobre `Pago`
        return self.env.ref('gestion_eventos_restaurante.action_report_factura').report_action(self)
    
   

# ====================================================
# Modelo: Factura
# ====================================================
class Factura(models.Model):
    _name = 'restaurante.factura'
    _description = 'Factura generada a partir de un pago'

    numero_factura = fields.Char(string="Número de Factura", required=True, readonly=True, copy=False, default='Nuevo')
    fecha_emision = fields.Date(string="Fecha de Emisión", default=fields.Date.context_today, required=True)
    total = fields.Float(string="Total", required=True)
    
    pago_id = fields.Many2one('restaurante.pago', string="Pago", required=True)

    def action_imprimir_factura(self):
        """Genera el informe PDF de la factura"""
        return self.env.ref('gestion_eventos_restaurante.action_report_factura').report_action(self)

# ====================================================
# Modelo: Invitados
# ====================================================

class RestauranteInvitado(models.Model):
    _name = "restaurante.invitado"
    _description = "Invitados del evento"

    nombre = fields.Char(string="Nombre y Apellidos", required=True)
    telefono = fields.Char(string="Teléfono")
    confirmado = fields.Boolean(string="Confirmado", default=False)
    evento_id = fields.Many2one("restaurante.evento", string="Evento", required=True)
    qr_code = fields.Binary(string="Código QR", compute="_generate_qr", store=True)

    @api.depends("nombre", "evento_id")
    def _generate_qr(self):
        for record in self:
            if record.nombre and record.evento_id:
                qr_data = f"Invitado: {record.nombre}\nEvento: {record.evento_id.id}\nTeléfono: {record.telefono}"
                qr = qrcode.QRCode(version=1, box_size=10, border=5)
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                img = qr.make_image(fill="black", back_color="white")
                temp = BytesIO()
                img.save(temp, format="PNG")
                record.qr_code = base64.b64encode(temp.getvalue())
