from odoo import models, fields, api  # Importa las herramientas principales de Odoo para modelos, campos y APIs
from odoo.exceptions import ValidationError, UserError  # Importa excepciones para manejar validaciones y errores de usuario
import base64  # Para codificar datos binarios como imágenes (usado en QR)
import qrcode  # Biblioteca para generar códigos QR
from io import BytesIO  # Para manejar flujos de bytes en memoria (usado en QR)
# from odoo.addons.sms.models.sms_api import SMSAPI  # Comentado: API para enviar SMS, no activa por ahora

# ====================================================
# Extensión de res.partner (clientes)
# ====================================================
class ResPartnerEvent(models.Model):
    _inherit = 'res.partner'  # Extiende el modelo nativo de Odoo para socios/clientes
    
    # Campo booleano para identificar si el cliente está relacionado con eventos
    is_event_customer = fields.Boolean(string="Cliente de Eventos", default=False)
    # Nota: Se pueden agregar más campos específicos para clientes de eventos si es necesario

# ====================================================
# Extensión de calendar.event (Calendario de Eventos)
# ====================================================
class CalendarEventExtended(models.Model):
    _inherit = 'calendar.event'  # Extiende el modelo nativo de eventos del calendario

    # Campo relacional que vincula un evento del calendario con una reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva")
    
    # Selección para definir el tipo de celebración del evento
    tipo_celebracion = fields.Selection([
        ('boda', 'Boda'),
        ('cumpleaños', 'Cumpleaños'),
        ('corporativo', 'Corporativo'),
        # Se pueden agregar más tipos según necesidades
    ], string="Tipo de Celebración")
    
    # Campo para registrar el número de personas esperadas en el evento
    numero_personas = fields.Integer(string="Número de Personas")
    
    # Validación para asegurar que el número de personas sea positivo
    @api.constrains('numero_personas')
    def _check_numero_personas(self):
        for record in self:
            if record.numero_personas and record.numero_personas <= 0:
                raise ValidationError("El número de personas debe ser mayor a cero.")

# ====================================================
# Modelo: Reserva
# ====================================================
class Reserva(models.Model):
    _name = 'restaurante.reserva'  # Nombre del modelo en la base de datos
    _description = 'Reserva para eventos'  # Descripción del modelo

    # Campo para la fecha de la reserva, obligatorio
    fecha_reserva = fields.Date(
        string="Fecha de Reserva", 
        required=True
    )
    
    # Selección para el tipo de evento, obligatorio
    tipo_evento = fields.Selection([
        ('cumpleaños', 'Cumpleaños'),
        ('boda', 'Boda'),
        ('corporativo', 'Corporativo'),
        ('otro', 'Otro')
    ], string="Tipo de Evento", required=True)
    
    # Estado de la reserva con un valor por defecto
    estado = fields.Selection([
        ('reservado', 'Reservado'),
        ('confirmado', 'Confirmado'),
        ('cancelado', 'Cancelado')
    ], string="Estado", default='reservado', required=True)
    
    # Campo calculado para definir un color según disponibilidad
    color_disponibilidad = fields.Integer(
        string="Color de Disponibilidad",
        compute="_compute_color_disponibilidad",
        store=True  # Almacenado en la base de datos
    )
    
    # Campo calculado para el saldo pendiente
    saldo_pendiente = fields.Float(
        string="Saldo Pendiente",
        compute="_compute_saldo_pendiente",
        store=True
    )

    # Campo para el lugar del evento, obligatorio
    lugar = fields.Char(string="Lugar", required=True)
    
    # Número de personas para la reserva, obligatorio
    numero_personas = fields.Integer(string="Número de Personas", required=True)
    
    # Relación con el modelo res.partner para el cliente
    cliente_id = fields.Many2one('res.partner', string="Cliente", required=True)
    
    # Campos relacionados (heredados del cliente)
    email = fields.Char(related="cliente_id.email", string="Email", readonly=True)
    telefono = fields.Char(related="cliente_id.phone", string="Teléfono", readonly=True)
    
    # Relación opcional con un evento del calendario
    calendar_event_id = fields.Many2one('calendar.event', string="Evento en Calendario")
    
    # Relación uno-a-muchos con el modelo de eventos
    evento_ids = fields.One2many('restaurante.evento', 'reserva_id', string="Eventos")
    
    # Relación uno-a-muchos con los pagos
    pago_ids = fields.One2many('restaurante.pago', 'reserva_id', string="Pagos")

    # Campo para la compañía, usa la compañía actual por defecto
    company_id = fields.Many2one('res.company', string="Compañía", default=lambda self: self.env.company)

    # Método para generar un reporte de reservas
    def action_generate_report_reservas(self):
        return self.env.ref('gestion_eventos_restaurante.action_report_reservas').report_action(self)
    
    # Validación: Solo un evento por reserva
    @api.constrains('evento_ids')
    def _check_evento_unico(self):
        for reserva in self:
            if len(reserva.evento_ids) > 1:
                raise ValidationError("Solo se permite un evento por reserva.")

    # Validación: Número de personas debe ser mayor a cero
    @api.constrains('numero_personas')
    def _check_numero_personas(self):
        for reserva in self:
            if reserva.numero_personas <= 0:
                raise ValidationError("El número de personas debe ser mayor a cero.")

    # Cálculo del color de disponibilidad basado en fechas ocupadas
    @api.depends('fecha_reserva')
    def _compute_color_disponibilidad(self):
        fechas_ocupadas = self.env['restaurante.reserva'].search([]).mapped('fecha_reserva')
        for record in self:
            # 1 = ocupado (rojo), 10 = disponible (verde)
            record.color_disponibilidad = 1 if record.fecha_reserva in fechas_ocupadas else 10

    # Validación: No permitir reservas duplicadas en la misma fecha
    @api.constrains('fecha_reserva')
    def _check_fecha_unica(self):
        for reserva in self:
            existe = self.env['restaurante.reserva'].search([
                ('fecha_reserva', '=', reserva.fecha_reserva),
                ('id', '!=', reserva.id)  # Excluye el registro actual al editar
            ])
            if existe:
                raise ValidationError("Ya existe una reserva para esta fecha. Por favor, elige otra.")
    
    # Método para enviar un correo de confirmación
    def action_send_confirmation(self):
        self.ensure_one()  # Asegura que solo se aplique a un registro
        if not self.email or '@' not in self.email:
            raise UserError("El correo del cliente no es válido.")
        
        # Busca la plantilla de correo
        template = self.env.ref('gestion_eventos_restaurante.confirmacion_reserva_email_template', raise_if_not_found=False)
        if not template:
            raise UserError("No se encontró la plantilla de correo.")
        
        # Envía el correo y muestra una notificación visual
        template.send_mail(self.id, force_send=True)
        return {
            'effect': {
                'fadeout': 'slow',
                'message': 'Correo de confirmación enviado.',
                'type': 'rainbow_man',  # Efecto visual en la interfaz
            }
        }
    
    # Método para abrir la vista de calendario
    def action_ver_calendario(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Calendario de Reservas',
            'view_mode': 'calendar',
            'res_model': 'restaurante.reserva',
            'view_id': self.env.ref('gestion_eventos_restaurante.view_reserva_calendar').id,
            'target': 'new',  # Abre en una nueva ventana
        }

    # Cálculo del saldo pendiente
    @api.depends('pago_ids', 'evento_ids.budget')
    def _compute_saldo_pendiente(self):
        for reserva in self:
            presupuesto = sum(reserva.evento_ids.mapped('budget'))  # Suma los presupuestos de los eventos
            total_pagado = sum(p.monto for p in reserva.pago_ids if p.estado_pago == 'completado')  # Suma pagos completados
            reserva.saldo_pendiente = max(presupuesto - total_pagado, 0)  # Saldo no puede ser negativo

    # Validación para asegurar que un pago no exceda el saldo pendiente
    @api.constrains('monto', 'reserva_id')
    def _check_pago_no_supera_saldo(self):
        for pago in self:
            if pago.reserva_id:
                saldo_pendiente = pago.reserva_id.saldo_pendiente
                if pago.monto > saldo_pendiente:
                    raise ValidationError(f"El monto del pago ({pago.monto}) no puede superar el saldo pendiente ({saldo_pendiente}).")

# ====================================================
# Modelo: Evento (Modificado)
# ====================================================
class Evento(models.Model):
    _name = 'restaurante.evento'  # Nombre del modelo
    _description = 'Evento asociado a una reserva'  # Descripción

    # Tipo de evento, calculado desde la reserva
    tipo_evento = fields.Selection([
        ('cumpleaños', 'Cumpleaños'),
        ('boda', 'Boda'),
        ('corporativo', 'Corporativo'),
        ('otro', 'Otro')
    ], string="Tipo de Evento", compute="_compute_tipo_evento", store=True, readonly=True)
    
    # Método para heredar el tipo de evento desde la reserva
    @api.depends('reserva_id.tipo_evento')
    def _compute_tipo_evento(self):
        for rec in self:
            rec.tipo_evento = rec.reserva_id.tipo_evento if rec.reserva_id else False
    
    # Presupuesto total calculado
    budget = fields.Float(string='Presupuesto Estimado', compute='_compute_budget', store=True)
    
    # Relación con los invitados
    invitado_ids = fields.One2many("restaurante.invitado", "evento_id", string="Lista de Invitados")
    
    # Relación con servicios adicionales
    servicio_ids = fields.Many2many('restaurante.servicio', string="Servicios")

    # Campos para menús especiales con valores por defecto en 0
    vegan_menu = fields.Integer(string="Menú Vegano", default=0)
    vegetarian_menu = fields.Integer(string="Menú Vegetariano", default=0)
    gluten_free_menu = fields.Integer(string="Menú Sin Gluten", default=0)
    lactose_free_menu = fields.Integer(string="Menú Sin Lactosa", default=0)
    kids_menu = fields.Integer(string="Menú Infantil", default=0)

    # Relación con la reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)
    
    # Relación con servicios y menús
    servicio_menu_ids = fields.One2many('restaurante.servicio_menu', 'evento_id', string="Servicios y Menús")

    # Relación con actividades (agenda)
    actividad_ids = fields.One2many('restaurante.actividad', 'evento_id', string="Actividades")
    
    # Relación con platos del menú
    entrantes_ids = fields.Many2many('restaurante.plato', string="Entrantes", domain=[('tipo_plato', '=', 'entrante')])
    primer_plato_id = fields.Many2one('restaurante.plato', string="Primer Plato", domain=[('tipo_plato', '=', 'principal')])
    segundo_plato_id = fields.Many2one('restaurante.plato', string="Segundo Plato", domain=[('tipo_plato', '=', 'secundario')])
    postre_id = fields.Many2one('restaurante.plato', string="Postre", domain=[('tipo_plato', '=', 'postre')])
    
    # Campo calculado para el total de menús especiales
    special_menu_total = fields.Integer(
        string="Total Menús Especiales", 
        compute="_compute_special_menu_total", 
        store=True
    )

    # Cálculo del total de menús especiales
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

    # Validación: El total de menús especiales no puede superar el número de personas
    @api.constrains('vegan_menu', 'vegetarian_menu', 'gluten_free_menu', 'lactose_free_menu', 'kids_menu')
    def _check_special_menu_total(self):
        for rec in self:
            if rec.reserva_id and rec.special_menu_total > rec.reserva_id.numero_personas:
                raise ValidationError("La suma de los menús especiales no puede ser mayor que el número de personas en la reserva.")

    # Cálculo del presupuesto total del evento
    @api.depends('servicio_menu_ids', 'servicio_ids',
                 'entrantes_ids', 'primer_plato_id', 'segundo_plato_id', 'postre_id',
                 'reserva_id.numero_personas', 'vegan_menu', 'vegetarian_menu', 'gluten_free_menu', 'lactose_free_menu', 'kids_menu')
    def _compute_budget(self):
        for event in self:
            total = sum(servicio.precio for servicio in event.servicio_menu_ids)  # Suma de servicios/menús
            total += sum(servicio.price for servicio in event.servicio_ids)  # Suma de servicios adicionales

            # Costo de entrantes ajustado por número de personas
            if event.reserva_id and event.entrantes_ids:
                num_personas = event.reserva_id.numero_personas
                num_entrantes = len(event.entrantes_ids)
                if num_entrantes > 0:
                    total += sum((entrante.precio * num_personas) / num_entrantes for entrante in event.entrantes_ids)

            # Ajuste por menús especiales
            num_menus_especiales = event.vegan_menu + event.vegetarian_menu + event.gluten_free_menu + event.lactose_free_menu + event.kids_menu
            personas_restantes = max(event.reserva_id.numero_personas - num_menus_especiales, 0)  # Evita negativos

            # Costo de platos principales para personas restantes
            if event.primer_plato_id:
                total += event.primer_plato_id.precio * personas_restantes
            if event.segundo_plato_id:
                total += event.segundo_plato_id.precio * personas_restantes
            if event.postre_id:
                total += event.postre_id.precio * personas_restantes

            # Costos fijos de menús especiales (20 por menú, 15 para infantil)
            total += (event.vegan_menu + event.vegetarian_menu + event.gluten_free_menu + event.lactose_free_menu) * 20
            total += event.kids_menu * 15

            event.budget = total  # Asigna el total al presupuesto

    # Método para imprimir un reporte del evento
    def print_evento_report(self):
        return self.env.ref('gestion_eventos_restaurante.action_report_evento').report_action(self)

    # Método para generar un reporte de actividades
    def action_generate_actividad_report(self):
        return self.env.ref('gestion_eventos_restaurante.actividad_evento_report').report_action(self)

# ====================================================
# Modelo: Servicio personalizado
# ====================================================
class Servicio(models.Model):
    _name = 'restaurante.servicio'  # Nombre del modelo
    _description = 'Servicios del Evento'  # Descripción

    # Nombre del servicio, obligatorio
    name = fields.Char(string="Servicio", required=True)
    
    # Tipo de servicio con opciones predefinidas
    tipo = fields.Selection([
        ('iluminacion', 'Iluminación'),
        ('musica', 'Música'),
        ('decoracion', 'Decoración'),
    ], string="Tipo de Servicio", required=True)
    
    # Precio fijo del servicio, solo lectura
    price = fields.Float(string="Precio", required=True, readonly=True)

# ====================================================
# Modelo: Servicio y Menú
# ====================================================
class ServicioMenu(models.Model):
    _name = 'restaurante.servicio_menu'  # Nombre del modelo
    _description = 'Servicio y Menú para eventos'  # Descripción

    # Descripción detallada del servicio
    descripcion_servicio = fields.Text(string="Descripción del Servicio", required=True)
    
    # Nombre de la opción de menú
    opcion_menu = fields.Char(string="Opción de Menú", required=True)
    
    # Cantidad calculada (podría ser manual o automática)
    cantidad_calculada = fields.Float(string="Cantidad Calculada")
    
    # Precio total calculado automáticamente
    precio = fields.Float(string="Precio Total", compute='_compute_precio_total', store=True)
    
    # Relación con el evento
    evento_id = fields.Many2one('restaurante.evento', string="Evento", required=True)
    
    # Relación con los platos del menú
    plato_ids = fields.One2many('restaurante.plato', 'servicio_menu_id', string="Platos")
    
    # Relación con platos clasificados por tipo
    entrantes_ids = fields.Many2many('restaurante.plato', string="Entrantes", domain=[('tipo_plato', '=', 'entrante')])
    primer_plato_id = fields.Many2one('restaurante.plato', string="Primer Plato", domain=[('tipo_plato', '=', 'principal')])
    segundo_plato_id = fields.Many2one('restaurante.plato', string="Segundo Plato", domain=[('tipo_plato', '=', 'secundario')])
    postre_id = fields.Many2one('restaurante.plato', string="Postre", domain=[('tipo_plato', '=', 'postre')])

    # Cálculo del precio total del menú
    @api.depends('entrantes_ids', 'primer_plato_id', 'segundo_plato_id', 'postre_id')
    def _compute_precio_total(self):
        for servicio in self:
            total = sum(servicio.entrantes_ids.mapped('precio'))  # Suma de entrantes
            if servicio.primer_plato_id:
                total += servicio.primer_plato_id.precio
            if servicio.segundo_plato_id:
                total += servicio.segundo_plato_id.precio
            if servicio.postre_id:
                total += servicio.postre_id.precio
            servicio.precio = total  # Asigna el total

# ====================================================
# Modelo: Plato
# ====================================================
class Plato(models.Model):
    _name = 'restaurante.plato'  # Nombre del modelo
    _description = 'Plato perteneciente a un Servicio y Menú'  # Descripción
    _rec_name = 'nombre_plato'  # Campo usado como nombre en vistas

    # Nombre del plato, obligatorio
    nombre_plato = fields.Char(string="Nombre del Plato", required=True)
    
    # Descripción opcional del plato
    descripcion = fields.Text(string="Descripción")
    
    # Lista de ingredientes
    ingredientes = fields.Text(string="Ingredientes")
    
    # Tipo de plato con opciones predefinidas
    tipo_plato = fields.Selection([
        ('entrante', 'Entrante'),
        ('principal', 'Plato Principal'),
        ('secundario', 'Plato Secundario'),
        ('postre', 'Postre')   
    ], string="Tipo de Plato", required=True)

    # Precio del plato, obligatorio
    precio = fields.Float(string="Precio", required=True)
    
    # Relación opcional con el servicio/menú
    servicio_menu_id = fields.Many2one('restaurante.servicio_menu', string="Servicio y Menú", required=False)

    # Método para personalizar cómo se muestra el nombre en selecciones
    def name_get(self):
        result = []
        for record in self:
            name = f"{record.nombre_plato} - ${record.precio}"  # Muestra nombre y precio
            print(f"DEBUG: name_get() ejecutado para {record.id} → {name}")  # Depuración
            result.append((record.id, name))
        return result

# ====================================================
# Modelo: Actividad (Agenda Detallada)
# ====================================================
class Actividad(models.Model):
    _name = 'restaurante.actividad'  # Nombre del modelo
    _description = 'Actividad en la agenda del evento'  # Descripción

    # Nombre de la actividad, obligatorio
    nombre_actividad = fields.Char(string="Nombre de la Actividad", required=True)
    
    # Descripción opcional
    descripcion = fields.Text(string="Descripción")
    
    # Horarios de inicio y fin, obligatorios
    hora_inicio = fields.Char(string="Hora de Inicio", required=True)
    hora_fin = fields.Char(string="Hora de Fin", required=True)

    # Relación con el evento, con eliminación en cascada
    evento_id = fields.Many2one('restaurante.evento', string="Evento", required=True, ondelete="cascade")

    # Espacio donde se realiza la actividad
    espacio = fields.Selection([
        ('salones', 'Salón de Eventos'),
        ('exterior', 'Exteriores'),
        ('recepcion', 'Área de Recepción'),
    ], string="Espacio del Evento", required=True)
    
    # Validación: La hora de fin debe ser posterior a la de inicio
    @api.constrains('hora_inicio', 'hora_fin')
    def _check_horario(self):
        for record in self:
            if record.hora_inicio >= record.hora_fin:
                raise ValidationError("La hora de fin debe ser mayor que la hora de inicio.")

# ====================================================
# Modelo: Pago
# ====================================================
class Pago(models.Model):
    _name = 'restaurante.pago'  # Nombre del modelo
    _description = 'Pago realizado para reserva o evento'  # Descripción

    # Monto del pago, obligatorio
    monto = fields.Float(string="Monto", required=True)
    
    # Fecha del pago, por defecto la fecha actual
    fecha_pago = fields.Date(string="Fecha de Pago", default=fields.Date.context_today, required=True)
    
    # Método de pago con opciones predefinidas
    metodo_pago = fields.Selection([
        ('tarjeta', 'Tarjeta de Crédito/Débito'),
        ('transferencia', 'Transferencia Bancaria'),
        ('digital', 'Pago Digital')
    ], string="Método de Pago", required=True)
    
    # Estado del pago, por defecto pendiente
    estado_pago = fields.Selection([
        ('completado', 'Completado'),
        ('pendiente', 'Pendiente')
    ], string="Estado del Pago", default='pendiente', required=True)

    # Relación con la reserva
    reserva_id = fields.Many2one('restaurante.reserva', string="Reserva", required=True)

    # Campos para la factura
    numero_factura = fields.Char(string="Número de Factura", readonly=True)
    factura_generada = fields.Boolean(string="Factura Generada", default=False)

    # Validación: La suma de pagos no debe superar el presupuesto
    @api.constrains('monto', 'reserva_id')
    def _check_pago_no_supera_presupuesto(self):
        for pago in self:
            if pago.reserva_id:
                total_pagado = sum(pago.reserva_id.pago_ids.mapped('monto'))
                presupuesto = sum(pago.reserva_id.evento_ids.mapped('budget'))
                if total_pagado > presupuesto:
                    raise ValidationError(
                        f"La suma total de los pagos ({total_pagado}) no puede superar el presupuesto total ({presupuesto})."
                    )

    # Método para generar e imprimir factura
    def action_generar_imprimir_factura(self):
        self.ensure_one()  # Solo un registro
        if self.estado_pago != 'completado':
            raise UserError("No se puede generar la factura porque el pago aún no está completado.")

        # Busca o crea una factura asociada
        factura = self.env['restaurante.factura'].search([('pago_id', '=', self.id)], limit=1)
        if not factura:
            factura = self.env['restaurante.factura'].create({
                'numero_factura': f"FACT-{self.id:05d}",  # Genera un número único
                'fecha_emision': self.fecha_pago,
                'total': self.monto,
                'pago_id': self.id,
            })
            self.numero_factura = factura.numero_factura
            self.factura_generada = True  # Marca como generada

        # Devuelve el reporte PDF
        return self.env.ref('gestion_eventos_restaurante.action_report_factura').report_action(self)

# ====================================================
# Modelo: Factura
# ====================================================
class Factura(models.Model):
    _name = 'restaurante.factura'  # Nombre del modelo
    _description = 'Factura generada a partir de un pago'  # Descripción

    # Número de factura, generado automáticamente
    numero_factura = fields.Char(string="Número de Factura", required=True, readonly=True, copy=False, default='Nuevo')
    
    # Fecha de emisión, por defecto la fecha actual
    fecha_emision = fields.Date(string="Fecha de Emisión", default=fields.Date.context_today, required=True)
    
    # Total de la factura
    total = fields.Float(string="Total", required=True)
    
    # Relación con el pago
    pago_id = fields.Many2one('restaurante.pago', string="Pago", required=True)

    # Método para imprimir la factura
    def action_imprimir_factura(self):
        return self.env.ref('gestion_eventos_restaurante.action_report_factura').report_action(self)

# ====================================================
# Modelo: Invitados
# ====================================================
class RestauranteInvitado(models.Model):
    _name = "restaurante.invitado"  # Nombre del modelo
    _description = "Invitados del evento"  # Descripción

    # Nombre del invitado, obligatorio
    nombre = fields.Char(string="Nombre y Apellidos", required=True)
    
    # Teléfono opcional
    telefono = fields.Char(string="Teléfono")
    
    # Estado de confirmación
    confirmado = fields.Boolean(string="Confirmado", default=False)
    
    # Relación con el evento
    evento_id = fields.Many2one("restaurante.evento", string="Evento", required=True)
    
    # Código QR generado automáticamente
    qr_code = fields.Binary(string="Código QR", compute="_generate_qr", store=True)

    # Generación del código QR
    @api.depends("nombre", "evento_id")
    def _generate_qr(self):
        for record in self:
            if record.nombre and record.evento_id:
                # Datos para el QR
                qr_data = f"Invitado: {record.nombre}\nEvento: {record.evento_id.id}\nTeléfono: {record.telefono}"
                qr = qrcode.QRCode(version=1, box_size=10, border=5)  # Configuración del QR
                qr.add_data(qr_data)
                qr.make(fit=True)
                
                # Genera la imagen del QR
                img = qr.make_image(fill="black", back_color="white")
                temp = BytesIO()
                img.save(temp, format="PNG")
                record.qr_code = base64.b64encode(temp.getvalue())  # Codifica en base64