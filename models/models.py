from odoo import models, fields, api # type: ignore
from odoo.exceptions import ValidationError # type: ignore

# ====================================================
# Extensión de res.partner (clientes)
# ====================================================
class ResPartnerEvent(models.Model):
    _inherit = 'res.partner'
    
    is_event_customer = fields.Boolean(string="Cliente de Eventos", default=False)
    # Puedes agregar otros campos específicos para clientes de eventos si es necesario.

    # @api.model
    # def create(self, vals):
    #     partner = super(ResPartnerEvent, self).create(vals)
    #     portal_group = self.env.ref('base.group_portal')
    #     if partner.user_ids:
    #         partner.user_ids[0].groups_id |= portal_group
    #     return partner
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
    numero_personas = fields.Integer(string="Número de Personas", required=True)
    detalles_adicionales = fields.Text(string="Detalles Adicionales")
    
    
    # Usamos res.partner nativo para los clientes
    cliente_id = fields.Many2one('res.partner', string="Cliente", required=True)
    
    # Vinculación con el calendario extendido (opcional)
    calendar_event_id = fields.Many2one('calendar.event', string="Evento en Calendario")
    
    # Relación con el modelo Evento (información adicional sobre el evento)
    evento_ids = fields.One2many('restaurante.evento', 'reserva_id', string="Eventos")
    
    # Relación con los pagos
    pago_ids = fields.One2many('restaurante.pago', 'reserva_id', string="Pagos")

    @api.constrains('numero_personas')
    def _check_numero_personas(self):
        for reserva in self:
            if reserva.numero_personas <= 0:
                raise ValidationError("El número de personas debe ser mayor a cero.")

    @api.depends('fecha_reserva')
    def _compute_color_disponibilidad(self):
        reservas = self.env['restaurante.reserva'].search([])
        fechas_ocupadas = reservas.mapped('fecha_reserva')

        for record in self:
            if record.fecha_reserva in fechas_ocupadas:
                record.color_disponibilidad = 1  # Rojo (ocupado)
            else:
                record.color_disponibilidad = 10  # Verde (disponible)
# ====================================================
# Modelo: Iluminación (Opciones predefinidas)
# ====================================================
class Iluminacion(models.Model):
    _name = 'restaurante.iluminacion'
    _description = 'Opciones de Iluminación'
    
    name = fields.Char(string="Tipo de Iluminación", required=True)
    price = fields.Float(string="Precio", required=True, readonly=True)  # Precio fijo

# ====================================================
# Modelo: Música (Opciones predefinidas)
# ====================================================
class Musica(models.Model):
    _name = 'restaurante.musica'
    _description = 'Opciones de Música'

    name = fields.Char(string="Tipo de Música", required=True)
    price = fields.Float(string="Precio", required=True, readonly=True)  # Precio fijo

# ====================================================
# Modelo: Decoración (Opciones predefinidas)
# ====================================================
class Decoracion(models.Model):
    _name = 'restaurante.decoracion'
    _description = 'Opciones de Decoración'

    name = fields.Char(string="Tipo de Decoración", required=True)
    price = fields.Float(string="Precio", required=True, readonly=True)  # Precio fijo

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

    
    personalizacion = fields.Text(string="Personalización del Evento")
    agenda = fields.Text(string="Agenda / Cronograma")
    # Presupuesto total (suma de precios fijos)
    budget = fields.Float(string='Presupuesto Estimado', compute='_compute_budget', store=True)


    # ==============================
    # Nuevos campos para Menús Especiales
    # ==============================
    vegan_menu = fields.Integer(string="Menú Vegano", default=0)
    vegetarian_menu = fields.Integer(string="Menú Vegetariano", default=0)
    gluten_free_menu = fields.Integer(string="Menú Sin Gluten", default=0)
    lactose_free_menu = fields.Integer(string="Menú Sin Lactosa", default=0)
    kids_menu = fields.Integer(string="Menú Infantil", default=0)

    # Selección de múltiples opciones
    iluminacion_ids = fields.Many2many('restaurante.iluminacion', string="Iluminación")
    musica_ids = fields.Many2many('restaurante.musica', string="Música")
    decoracion_ids = fields.Many2many('restaurante.decoracion', string="Decoración")

    # Relación con la reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)
    
    # Relación con servicios y menús
    servicio_menu_ids = fields.One2many('restaurante.servicio_menu', 'evento_id', string="Servicios y Menús")

    # Relación con actividades (agenda detallada)
    actividad_ids = fields.One2many('restaurante.actividad', 'evento_id', string="Actividades")
    # Relación con los platos del menú
    entrantes_ids = fields.Many2many('restaurante.plato', string="Entrantes", domain=[('tipo_plato', '=', 'entrante')])
    primer_plato_id = fields.Many2one('restaurante.plato', string="Primer Plato", domain=[('tipo_plato', '=', 'principal')])
    segundo_plato_id = fields.Many2one('restaurante.plato', string="Segundo Plato", domain=[('tipo_plato', '=', 'principal')])
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

    @api.depends('servicio_menu_ids', 'iluminacion_ids', 'musica_ids', 'decoracion_ids')
    def _compute_budget(self):
        """Calcula el presupuesto total del evento sumando:
           - Servicios y Menús
           - Iluminación seleccionada (precios fijos)
           - Música seleccionada (precios fijos)
           - Decoración seleccionada (precios fijos)
        """
        for event in self:
            total = sum(servicio.precio for servicio in event.servicio_menu_ids)
            total += sum(iluminacion.price for iluminacion in event.iluminacion_ids)
            total += sum(musica.price for musica in event.musica_ids)
            total += sum(decoracion.price for decoracion in event.decoracion_ids)
            event.budget = total

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

# ====================================================
# Modelo: Actividad (Agenda Detallada)
# ====================================================
class Actividad(models.Model):
    _name = 'restaurante.actividad'
    _description = 'Actividad en la agenda del evento'

    nombre_actividad = fields.Char(string="Nombre de la Actividad", required=True)
    descripcion = fields.Text(string="Descripción")
    hora_inicio = fields.Float(string="Hora de Inicio", required=True)
    duracion = fields.Float(string="Duración (horas)", required=True)
    recursos_asignados = fields.Text(string="Recursos Asignados")
    
    # Relación con el evento
    evento_id = fields.Many2one('restaurante.evento', string="Evento", required=True)

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
    
    # Relación con la reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)
    
    # Relación con las facturas (en caso de pagos parciales o múltiples facturaciones)
    factura_ids = fields.One2many('restaurante.factura', 'pago_id', string="Facturas")
    
    @api.constrains('monto')
    def _check_monto(self):
        for pago in self:
            if pago.monto <= 0:
                raise ValidationError("El monto del pago debe ser mayor a cero.")

# ====================================================
# Modelo: Factura
# ====================================================
class Factura(models.Model):
    _name = 'restaurante.factura'
    _description = 'Factura generada a partir de un pago'

    numero_factura = fields.Char(string="Número de Factura", required=True)
    fecha_emision = fields.Date(string="Fecha de Emisión", default=fields.Date.context_today, required=True)
    total = fields.Float(string="Total", required=True)
    detalles = fields.Text(string="Detalles")
    
    # Relación con el pago
    pago_id = fields.Many2one('restaurante.pago', string="Pago", required=True)
