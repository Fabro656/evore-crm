# models.py — All SQLAlchemy models + DB init
from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date as date_type
import json, secrets, os, logging

__all__ = ['Company', 'UserCompany', 'ChatRoom', 'ChatParticipant', 'ChatMessage', 'User', 'ContactoCliente', 'Cliente', 'OrdenCompra', 'OrdenCompraItem', 'Proveedor', 'VentaProducto', 'Venta', 'PagoVenta', 'Aprobacion', 'TareaAsignado', 'TareaComentario', 'Tarea', 'Producto', 'MarcaProducto', 'CompraMateria', 'CotizacionProveedor', 'CotizacionGranel', 'DocumentoLegal', 'CuentaPUC', 'AsientoContable', 'MovimientoBancario', 'NotaContable', 'LineaAsiento', 'ReglaTributaria', 'GastoOperativo', 'Nota', 'Actividad', 'ConfigEmpresa', 'Evento', 'CotizacionItem', 'Cotizacion', 'LoteProducto', 'MateriaPrima', 'MateriaPrimaProducto', 'LoteMateriaPrima', 'RecetaProducto', 'RecetaItem', 'ReservaProduccion', 'OrdenProduccion', 'MovimientoInventario', 'Notificacion', 'Empleado', 'HoraExtra', 'Comision', 'Incapacidad', 'VacacionTomada', 'Requisicion', 'UserSesion', 'PreCotizacionItem', 'PreCotizacion', 'Servicio', 'EmpaqueSecundario', 'HistorialPrecio', 'HistorialCotizacion', 'CompanyRelationship', 'Suscripcion', 'ForoPublicacion', 'ForoValoracion', 'ForoApelacion', 'ForoBanner', 'CapCurso', 'CapLeccion', 'CapPregunta', 'CapProgreso', 'CapEvaluacion', 'Proyecto', 'ProyectoFase', 'ProyectoTarea', 'ProyectoComentario', 'ProyectoGasto', 'load_user', '_migrate', 'init_db']


# ══════════════════════════════════════════════════════════════════
# MULTI-TENANCY FOUNDATION
# ══════════════════════════════════════════════════════════════════

class Company(db.Model):
    """Cada empresa/tenant en la plataforma."""
    __tablename__ = 'companies'
    id              = db.Column(db.Integer, primary_key=True)
    nombre          = db.Column(db.String(200), nullable=False)
    slug            = db.Column(db.String(100), unique=True)
    tipo_documento  = db.Column(db.String(10), default='NIT')  # NIT, CC, CE, PP, TI
    nit             = db.Column(db.String(30))  # stores NIT or CC number
    logo_url        = db.Column(db.String(500))
    plan            = db.Column(db.String(20), default='free')  # free, starter, pro
    max_users       = db.Column(db.Integer, default=3)  # limite de usuarios, controlado por admin Evore
    activo          = db.Column(db.Boolean, default=True)
    es_principal    = db.Column(db.Boolean, default=False)  # True solo para Evore (Company #1)
    industria       = db.Column(db.String(100))  # Foro: industria de la empresa
    config          = db.Column(db.Text, default='{}')  # JSON: pais, moneda, parametros
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por      = db.Column(db.Integer, nullable=True)

class UserCompany(db.Model):
    """Relacion user↔company con rol y permisos en esa empresa."""
    __tablename__ = 'user_companies'
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    company_id          = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    rol                 = db.Column(db.String(20), default='usuario')
    roles_asignados     = db.Column(db.Text, default='[]')
    modulos_permitidos  = db.Column(db.Text, default='[]')
    activo              = db.Column(db.Boolean, default=True)
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    user                = db.relationship('User', backref=db.backref('company_memberships', lazy=True))
    company             = db.relationship('Company', backref=db.backref('members', lazy=True))
    __table_args__      = (db.UniqueConstraint('user_id', 'company_id', name='uq_user_company'),)

class CompanyRelationship(db.Model):
    """Relacion entre empresas (cliente/proveedor)."""
    __tablename__ = 'company_relationships'
    id              = db.Column(db.Integer, primary_key=True)
    company_from_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    company_to_id   = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    tipo            = db.Column(db.String(20), default='cliente')  # cliente, proveedor, ambos
    cliente_id      = db.Column(db.Integer, nullable=True)  # FK lógico al cliente en company_from
    proveedor_id    = db.Column(db.Integer, nullable=True)  # FK lógico al proveedor en company_from
    activo          = db.Column(db.Boolean, default=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    company_from    = db.relationship('Company', foreign_keys=[company_from_id])
    company_to      = db.relationship('Company', foreign_keys=[company_to_id])


class ChatRoom(db.Model):
    """Sala de chat — interna o inter-empresa."""
    __tablename__ = 'chat_rooms'
    id              = db.Column(db.Integer, primary_key=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    tipo            = db.Column(db.String(20), default='interno')  # interno, cliente, proveedor
    nombre          = db.Column(db.String(200))
    company_relationship_id = db.Column(db.Integer, db.ForeignKey('company_relationships.id'), nullable=True)
    activo          = db.Column(db.Boolean, default=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por      = db.Column(db.Integer, nullable=True)
    participants    = db.relationship('ChatParticipant', backref='room', lazy=True, cascade='all, delete-orphan')
    messages        = db.relationship('ChatMessage', backref='room', lazy=True, cascade='all, delete-orphan')

class ChatParticipant(db.Model):
    """Participante de un chat room."""
    __tablename__ = 'chat_participants'
    id              = db.Column(db.Integer, primary_key=True)
    room_id         = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False, index=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    rol             = db.Column(db.String(20), default='miembro')  # miembro, admin, observador
    activo          = db.Column(db.Boolean, default=True)
    agregado_en     = db.Column(db.DateTime, default=datetime.utcnow)
    agregado_por    = db.Column(db.Integer, nullable=True)
    user            = db.relationship('User', foreign_keys=[user_id])
    __table_args__  = (db.UniqueConstraint('room_id', 'user_id', name='uq_chat_participant'),)

class ChatMessage(db.Model):
    """Mensaje en un chat room."""
    __tablename__ = 'chat_messages'
    id              = db.Column(db.Integer, primary_key=True)
    room_id         = db.Column(db.Integer, db.ForeignKey('chat_rooms.id'), nullable=False, index=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    contenido       = db.Column(db.Text, nullable=False)
    tipo            = db.Column(db.String(20), default='texto')  # texto, archivo, sistema
    leido_por       = db.Column(db.Text, default='[]')  # JSON list of user_ids
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user            = db.relationship('User', foreign_keys=[user_id])


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id                  = db.Column(db.Integer, primary_key=True)
    nombre              = db.Column(db.String(100), nullable=False)
    email               = db.Column(db.String(120), unique=True, nullable=False)
    password_hash       = db.Column(db.String(256), nullable=False)
    rol                 = db.Column(db.String(20), default='usuario')
    activo              = db.Column(db.Boolean, default=True)
    company_id          = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)  # default company
    modulos_permitidos  = db.Column(db.Text, default='[]')   # JSON list
    roles_asignados     = db.Column(db.Text, default='[]')   # JSON list: roles multiples asignados
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    onboarding_dismissed = db.Column(db.Boolean, default=False)
    onboarding_step      = db.Column(db.Integer, default=0)
    onboarding_role_config = db.Column(db.Text, default='{}')
    cliente_id           = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    proveedor_id        = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class ContactoCliente(db.Model):
    __tablename__ = 'contactos_cliente'
    id         = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    nombre     = db.Column(db.String(100), nullable=False)
    cargo      = db.Column(db.String(100))
    email      = db.Column(db.String(120))
    telefono   = db.Column(db.String(20))
    es_demo    = db.Column(db.Boolean, default=False)

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id              = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre          = db.Column(db.String(100), nullable=False)
    empresa         = db.Column(db.String(100))
    nit             = db.Column(db.String(30))
    estado_relacion = db.Column(db.String(30), default='prospecto')
    dir_comercial   = db.Column(db.Text)
    dir_entrega     = db.Column(db.Text)
    notas           = db.Column(db.Text)
    estado          = db.Column(db.String(20), default='activo')
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en  = db.Column(db.DateTime, default=datetime.utcnow)
    banco_nombre    = db.Column(db.String(120))
    banco_cuenta    = db.Column(db.String(80))
    banco_tipo      = db.Column(db.String(40))
    banco_titular   = db.Column(db.String(120))
    info_legal      = db.Column(db.Text)
    sales_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    anticipo_pct     = db.Column(db.Float, default=50.0)
    minimo_pedido    = db.Column(db.Integer, default=1)
    envio_responsable = db.Column(db.String(20), default='cliente')  # 'cliente' = ellos recogen, 'empresa' = nosotros enviamos
    transportista_preferido_id = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    contrato_id      = db.Column(db.Integer, db.ForeignKey('documentos_legales.id'), nullable=True)
    es_demo          = db.Column(db.Boolean, default=False)
    tier             = db.Column(db.String(20), default='standard')  # standard, bronze, silver, gold
    # DIAN — facturación electrónica (schema prep)
    tipo_documento       = db.Column(db.String(10), default='NIT')          # NIT, CC, CE, PP, TI
    digito_verificacion  = db.Column(db.String(1))
    regimen_fiscal       = db.Column(db.String(50))                         # Responsable IVA, No responsable, etc.
    municipio_dane       = db.Column(db.String(10))                         # DANE municipality code
    contactos       = db.relationship('ContactoCliente', backref='cliente_rel', lazy=True, cascade='all, delete-orphan')
    ventas          = db.relationship('Venta', backref='cliente', lazy=True)
    sales_manager    = db.relationship('User', foreign_keys=[sales_manager_id])
    transportista_preferido = db.relationship('Proveedor', foreign_keys=[transportista_preferido_id])
    contrato         = db.relationship('DocumentoLegal', foreign_keys=[contrato_id])

class OrdenCompra(db.Model):
    __tablename__ = 'ordenes_compra'
    id                      = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero                  = db.Column(db.String(20))               # OC-YYYY-NNN
    proveedor_id            = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    cotizacion_id           = db.Column(db.Integer, db.ForeignKey('cotizaciones_proveedor.id'), nullable=True)
    transportista_id        = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    estado                  = db.Column(db.String(30), default='borrador', index=True)  # borrador, anticipo_pagado, pagado, en_espera_producto, recibida_parcial, recibida, cancelada
    fecha_emision           = db.Column(db.Date)
    fecha_esperada          = db.Column(db.Date)   # fecha entrega esperada (calculada desde cotización)
    fecha_estimada_pago     = db.Column(db.Date)   # fecha estimada de pago al proveedor
    fecha_estimada_recogida = db.Column(db.Date)   # fecha estimada para recoger con transportista
    subtotal                = db.Column(db.Float, default=0)
    iva                     = db.Column(db.Float, default=0)
    total                   = db.Column(db.Float, default=0)
    notas                   = db.Column(db.Text)
    creado_por              = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en               = db.Column(db.DateTime, default=datetime.utcnow)
    estado_proveedor        = db.Column(db.String(30), default='pendiente')  # pendiente, confirmada, anticipo_enviado, anticipo_recibido
    confirmado_en           = db.Column(db.DateTime, nullable=True)
    confirmado_por          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    es_demo                 = db.Column(db.Boolean, default=False)
    fecha_anticipo_real     = db.Column(db.Date, nullable=True)  # v30
    # v36 — nuevos campos flujo OC ↔ contable
    monto_pagado            = db.Column(db.Float, default=0)  # acumulado de pagos confirmados
    estado_recepcion        = db.Column(db.String(30), default='pendiente')  # pendiente, parcial, recibida
    cantidad_recibida       = db.Column(db.Float, default=0)
    tiene_problema_calidad  = db.Column(db.Boolean, default=False)
    venta_origen_id         = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    pendiente_aprobacion    = db.Column(db.Boolean, default=False)  # v37 bloqueo por aprobacion
    proveedor               = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    transportista           = db.relationship('Proveedor', foreign_keys=[transportista_id])
    cotizacion_ref          = db.relationship('CotizacionProveedor', foreign_keys=[cotizacion_id])
    items                   = db.relationship('OrdenCompraItem', backref='orden', lazy=True, cascade='all, delete-orphan')

class OrdenCompraItem(db.Model):
    __tablename__ = 'ordenes_compra_items'
    id              = db.Column(db.Integer, primary_key=True)
    orden_id        = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=False)
    cotizacion_id   = db.Column(db.Integer, db.ForeignKey('cotizaciones_proveedor.id'), nullable=True)
    nombre_item     = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text)
    cantidad        = db.Column(db.Float, default=1)
    unidad          = db.Column(db.String(30), default='unidades')
    precio_unit     = db.Column(db.Float, default=0)
    subtotal        = db.Column(db.Float, default=0)

class Proveedor(db.Model):
    __tablename__ = 'proveedores'
    id         = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre     = db.Column(db.String(100), nullable=False)
    empresa    = db.Column(db.String(100))
    nit        = db.Column(db.String(30))
    email      = db.Column(db.String(200))
    telefono   = db.Column(db.String(50))
    direccion  = db.Column(db.Text)
    categoria  = db.Column(db.String(100))
    contacto_nombre = db.Column(db.String(100))
    tipo       = db.Column(db.String(20), default='proveedor')  # proveedor, transportista, ambos
    notas      = db.Column(db.Text)
    activo     = db.Column(db.Boolean, default=True)
    capacidad_vehiculo_kg = db.Column(db.Float, default=0)  # Max kg for transport
    capacidad_vehiculo_m3 = db.Column(db.Float, default=0)  # Max volume for transport
    tipo_vehiculo = db.Column(db.String(50))  # camion, furgon, van, moto
    envia_material = db.Column(db.Boolean, default=True)
    # Evaluacion de proveedor
    score_calidad   = db.Column(db.Float, default=5.0)   # 1-10
    score_entrega   = db.Column(db.Float, default=5.0)   # 1-10
    score_precio    = db.Column(db.Float, default=5.0)   # 1-10
    total_oc        = db.Column(db.Integer, default=0)    # OC totales
    total_rechazos  = db.Column(db.Integer, default=0)    # rechazos calidad
    deleted_at      = db.Column(db.DateTime, nullable=True)  # soft delete
    creado_en  = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo    = db.Column(db.Boolean, default=False)

class VentaProducto(db.Model):
    __tablename__ = 'venta_productos'
    id          = db.Column(db.Integer, primary_key=True)
    venta_id    = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    servicio_id = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=True)  # v30
    nombre_prod = db.Column(db.String(200))
    cantidad    = db.Column(db.Float, default=1)
    precio_unit = db.Column(db.Float, default=0)
    subtotal    = db.Column(db.Float, default=0)
    es_servicio = db.Column(db.Boolean, default=False)    # v30
    unidad      = db.Column(db.String(30), default='unidades')  # v30
    marca_id    = db.Column(db.Integer, db.ForeignKey('marcas_producto.id'), nullable=True)
    costo_unitario = db.Column(db.Float, default=0)  # Cost from recipe at time of sale
    servicio    = db.relationship('Servicio', foreign_keys=[servicio_id])  # v30
    marca       = db.relationship('MarcaProducto', foreign_keys=[marca_id])

class Venta(db.Model):
    __tablename__ = 'ventas'
    id                  = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    titulo              = db.Column(db.String(200), nullable=False)
    cliente_id          = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    subtotal            = db.Column(db.Float, default=0)
    iva                 = db.Column(db.Float, default=0)
    total               = db.Column(db.Float, default=0)
    porcentaje_anticipo = db.Column(db.Float, default=0)
    monto_anticipo      = db.Column(db.Float, default=0)
    saldo               = db.Column(db.Float, default=0)
    monto_pagado_total  = db.Column(db.Float, default=0)
    monto_anticipo_recibido = db.Column(db.Float, default=0)  # v36 — real recibido via asiento contable
    pendiente_aprobacion = db.Column(db.Boolean, default=False)  # v37 bloqueo por aprobacion
    transportista_id    = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)  # v38
    enviado_en          = db.Column(db.DateTime, nullable=True)  # v38
    estado_cliente_pago = db.Column(db.String(30), default='pendiente')  # pendiente, enviado, recibido
    # v41 — Tracking de envio
    guia_transporte     = db.Column(db.String(100), nullable=True)
    estado_envio        = db.Column(db.String(30), default='pendiente')  # pendiente, preparando, en_transito, entregado
    estado              = db.Column(db.String(30), default='prospecto', index=True)
    fecha_anticipo      = db.Column(db.Date)
    dias_entrega        = db.Column(db.Integer, default=30)
    fecha_entrega_est   = db.Column(db.Date)
    notas               = db.Column(db.Text)
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    numero              = db.Column(db.String(20))               # v12.3 VNT-YYYY-NNN
    cliente_informado_en= db.Column(db.DateTime, nullable=True)  # v12.2
    entregado_en        = db.Column(db.DateTime, nullable=True)   # v12.2
    cotizacion_id       = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)  # v32
    es_demo             = db.Column(db.Boolean, default=False)
    # DIAN — facturación electrónica (schema prep)
    numero_factura      = db.Column(db.String(30))                          # DIAN authorized consecutive
    cufe                = db.Column(db.String(200))                         # Codigo Unico de Factura Electronica
    estado_dian         = db.Column(db.String(20))                          # pendiente, enviada, validada, rechazada
    xml_factura         = db.Column(db.Text)                                # XML UBL 2.1 signed
    medio_pago          = db.Column(db.String(10), default='10')            # DIAN code: 10=efectivo, 31=transferencia, 42=consignacion
    items               = db.relationship('VentaProducto', backref='venta', lazy=True, cascade='all, delete-orphan')
    ordenes_produccion  = db.relationship('OrdenProduccion', foreign_keys='OrdenProduccion.venta_id', lazy=True, back_populates='venta')
    cotizacion_origen   = db.relationship('Cotizacion', foreign_keys='Venta.cotizacion_id')
    transportista       = db.relationship('Proveedor', foreign_keys=[transportista_id])
    pagos               = db.relationship('PagoVenta', backref='venta', lazy=True, cascade='all, delete-orphan')

class PagoVenta(db.Model):
    __tablename__ = 'pagos_venta'
    id          = db.Column(db.Integer, primary_key=True)
    venta_id    = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    monto       = db.Column(db.Float, nullable=False)
    tipo        = db.Column(db.String(30), default='anticipo')  # anticipo, parcial, saldo
    metodo_pago = db.Column(db.String(30), default='transferencia')  # transferencia, efectivo, cheque, tarjeta
    referencia  = db.Column(db.String(100))  # nro transacción / comprobante
    fecha       = db.Column(db.Date, nullable=False)
    notas       = db.Column(db.Text)
    creado_por  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)

class Aprobacion(db.Model):
    """Sistema de aprobaciones que bloquean flujo de OC/ventas/cotizaciones/asientos."""
    __tablename__ = 'aprobaciones'
    id             = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    tipo_accion    = db.Column(db.String(50), nullable=False)  # orden_compra, venta, cotizacion, asiento_manual
    descripcion    = db.Column(db.String(300))
    monto          = db.Column(db.Float, default=0)
    datos_json     = db.Column(db.Text)
    estado         = db.Column(db.String(20), default='pendiente')  # pendiente, aprobado, revision, rechazado
    solicitado_por = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    aprobado_por   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    notas_aprobador= db.Column(db.Text)
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    resuelto_en    = db.Column(db.DateTime, nullable=True)
    # v37 — vincular a entidad especifica
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    venta_id        = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    cotizacion_id   = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)
    asiento_id      = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=True)
    solicitante    = db.relationship('User', foreign_keys=[solicitado_por])
    aprobador      = db.relationship('User', foreign_keys=[aprobado_por])
    orden_compra   = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])
    venta          = db.relationship('Venta', foreign_keys=[venta_id])

class TareaAsignado(db.Model):
    __tablename__ = 'tarea_asignados'
    id       = db.Column(db.Integer, primary_key=True)
    tarea_id = db.Column(db.Integer, db.ForeignKey('tareas.id'), nullable=False)
    user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user     = db.relationship('User', foreign_keys=[user_id])

class TareaComentario(db.Model):
    __tablename__ = 'tarea_comentarios'
    id        = db.Column(db.Integer, primary_key=True)
    tarea_id  = db.Column(db.Integer, db.ForeignKey('tareas.id'), nullable=False)
    autor_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mensaje   = db.Column(db.Text, nullable=False)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    autor     = db.relationship('User', foreign_keys=[autor_id])

class Tarea(db.Model):
    __tablename__ = 'tareas'
    id                = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    titulo            = db.Column(db.String(200), nullable=False)
    descripcion       = db.Column(db.Text)
    estado            = db.Column(db.String(20), default='pendiente', index=True)
    prioridad         = db.Column(db.String(10), default='media')
    fecha_vencimiento = db.Column(db.Date)
    asignado_a        = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)
    cotizacion_id     = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)
    tarea_tipo        = db.Column(db.String(50), nullable=True)   # comprar_materias, verificar_abono
    tarea_pareja_id   = db.Column(db.Integer, db.ForeignKey('tareas.id'), nullable=True)
    es_demo           = db.Column(db.Boolean, default=False)
    # v36 — vincular tickets a entidades
    orden_compra_id   = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    venta_id          = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    categoria         = db.Column(db.String(50), nullable=True)  # calidad, logistica, pago, general
    asignado_user     = db.relationship('User', foreign_keys=[asignado_a], backref='tareas_asignadas')
    creador           = db.relationship('User', foreign_keys=[creado_por])
    asignados         = db.relationship('TareaAsignado', backref='tarea', lazy=True, cascade='all, delete-orphan')
    comentarios       = db.relationship('TareaComentario', backref='tarea', lazy=True, cascade='all, delete-orphan', order_by='TareaComentario.creado_en')

class Producto(db.Model):
    __tablename__ = 'productos'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre       = db.Column(db.String(200), nullable=False)
    descripcion  = db.Column(db.Text)
    sku          = db.Column(db.String(50))
    nso          = db.Column(db.String(50))
    precio       = db.Column(db.Float, default=0)
    costo        = db.Column(db.Float, default=0)
    stock        = db.Column(db.Integer, default=0)
    stock_reservado = db.Column(db.Integer, default=0)
    stock_minimo    = db.Column(db.Integer, default=5)
    categoria       = db.Column(db.String(100))
    activo          = db.Column(db.Boolean, default=True)
    fecha_caducidad = db.Column(db.Date, nullable=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    costo_receta    = db.Column(db.Float, default=0)  # Auto-calculated from recipe + MP costs
    es_demo         = db.Column(db.Boolean, default=False)
    # DIAN — facturación electrónica (schema prep)
    codigo_unspsc       = db.Column(db.String(20))                          # UNSPSC product code for DIAN
    venta_items     = db.relationship('VentaProducto', backref='producto', lazy=True)

class HistorialPrecio(db.Model):
    """Registra cada cambio de precio de un producto con fecha y origen."""
    __tablename__ = 'historial_precios'
    id           = db.Column(db.Integer, primary_key=True)
    producto_id  = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    precio_anterior = db.Column(db.Float, default=0)
    precio_nuevo    = db.Column(db.Float, default=0)
    origen       = db.Column(db.String(100))  # 'receta', 'cotizacion COT-2026-001', 'manual'
    usuario_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    producto     = db.relationship('Producto', foreign_keys=[producto_id])
    usuario      = db.relationship('User', foreign_keys=[usuario_id])

class HistorialCotizacion(db.Model):
    """Registra cada cambio realizado en una cotización."""
    __tablename__ = 'historial_cotizaciones'
    id             = db.Column(db.Integer, primary_key=True)
    cotizacion_id  = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=False)
    cambios        = db.Column(db.Text)  # descripción de los cambios
    usuario_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    cotizacion     = db.relationship('Cotizacion', foreign_keys=[cotizacion_id])
    usuario        = db.relationship('User', foreign_keys=[usuario_id])

class MarcaProducto(db.Model):
    __tablename__ = 'marcas_producto'
    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    nombre_marca = db.Column(db.String(200), nullable=False)  # Brand name
    nso = db.Column(db.String(50))  # NSO specific to this brand
    registro_sanitario = db.Column(db.String(100))  # INVIMA number
    documento_legal_id = db.Column(db.Integer, db.ForeignKey('documentos_legales.id'), nullable=True)
    activo = db.Column(db.Boolean, default=True)
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo = db.Column(db.Boolean, default=False)
    producto = db.relationship('Producto', foreign_keys=[producto_id])
    documento = db.relationship('DocumentoLegal', foreign_keys=[documento_legal_id])

class CompraMateria(db.Model):
    __tablename__ = 'compras_materia'
    id              = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    producto_id     = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    materia_id      = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=True)
    nombre_item     = db.Column(db.String(200), nullable=False)
    tipo_compra     = db.Column(db.String(50), default='insumo')  # materia_prima, producto_terminado, insumo, otro
    unidad          = db.Column(db.String(30), default='unidades')
    proveedor       = db.Column(db.String(200))
    proveedor_id    = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    fecha           = db.Column(db.Date, nullable=False)
    nro_factura     = db.Column(db.String(100))
    cantidad        = db.Column(db.Float, default=1)
    costo_producto  = db.Column(db.Float, default=0)
    impuestos       = db.Column(db.Float, default=0)
    transporte      = db.Column(db.Float, default=0)
    costo_total     = db.Column(db.Float, default=0)
    precio_unitario = db.Column(db.Float, default=0)
    tiene_caducidad = db.Column(db.Boolean, default=False)
    fecha_caducidad = db.Column(db.Date, nullable=True)
    notas           = db.Column(db.Text)
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo         = db.Column(db.Boolean, default=False)
    # v36 — vincular a OC y recepcion
    orden_compra_id      = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    orden_compra_item_id = db.Column(db.Integer, db.ForeignKey('ordenes_compra_items.id'), nullable=True)
    estado_recepcion     = db.Column(db.String(30), default='solicitado')  # solicitado, recibido, parcial, devuelto
    cantidad_recibida    = db.Column(db.Float, default=0)
    producto        = db.relationship('Producto', foreign_keys=[producto_id])
    materia         = db.relationship('MateriaPrima', foreign_keys=[materia_id])
    proveedor_rel   = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    orden_compra    = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])

class CotizacionProveedor(db.Model):
    __tablename__ = 'cotizaciones_proveedor'
    id                    = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero                = db.Column(db.String(20))               # CP-YYYY-NNN
    proveedor_id          = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    tipo_cotizacion       = db.Column(db.String(20), default='general')  # maquila, general
    tipo_producto_servicio= db.Column(db.String(100))  # ej: materia prima, servicio logístico, empaque
    nombre_producto       = db.Column(db.String(200), nullable=False)
    descripcion           = db.Column(db.Text)
    sku                   = db.Column(db.String(50))
    precio_unitario       = db.Column(db.Float, default=0)
    unidades_minimas      = db.Column(db.Integer, default=1)
    unidad                = db.Column(db.String(30), default='unidades')
    plazo_entrega         = db.Column(db.String(100))   # texto descriptivo legacy
    plazo_entrega_dias    = db.Column(db.Integer, default=0)   # días hábiles (structured)
    condiciones_pago      = db.Column(db.String(200))   # texto legacy
    condicion_pago_tipo   = db.Column(db.String(30), default='contado')  # contado, credito, anticipo_saldo, consignacion
    condicion_pago_dias   = db.Column(db.Integer, default=0)  # días de crédito
    anticipo_porcentaje   = db.Column(db.Float, default=0)    # % anticipo si aplica
    fecha_cotizacion      = db.Column(db.Date)
    vigencia              = db.Column(db.Date)
    estado                = db.Column(db.String(20), default='vigente')  # vigente, vencida, en_revision
    notas                 = db.Column(db.Text)
    calendario_integrado  = db.Column(db.Boolean, default=False)  # ya se agendó entrega al calendario
    creado_por            = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en             = db.Column(db.DateTime, default=datetime.utcnow)
    materia_prima_id      = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=True)
    es_demo               = db.Column(db.Boolean, default=False)
    proveedor             = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    materia               = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])

class CotizacionGranel(db.Model):
    """Cotizaciones de maquila/tercerizacion (tabla legacy: cotizaciones_granel)."""
    __tablename__ = 'cotizaciones_granel'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    nombre_producto  = db.Column(db.String(200), nullable=False)
    sku              = db.Column(db.String(50))
    nso              = db.Column(db.String(50))
    proveedor        = db.Column(db.String(200))
    precio_unitario  = db.Column(db.Float, default=0)
    unidades_minimas = db.Column(db.Integer, default=1)
    fecha_cotizacion = db.Column(db.Date)
    vigencia         = db.Column(db.Date)
    estado           = db.Column(db.String(20), default='vigente')
    notas            = db.Column(db.Text)
    creado_por       = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    producto         = db.relationship('Producto', foreign_keys=[producto_id])

class DocumentoLegal(db.Model):
    __tablename__ = 'documentos_legales'
    id                = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    tipo              = db.Column(db.String(50), nullable=False)
    # tipos: permiso_sanitario, registro_invima, nso, contrato, licencia, certificado, otro
    titulo            = db.Column(db.String(200), nullable=False)
    numero            = db.Column(db.String(100))   # número del documento
    entidad           = db.Column(db.String(200))   # entidad emisora (INVIMA, cámara de comercio, etc.)
    descripcion       = db.Column(db.Text)
    estado            = db.Column(db.String(20), default='vigente')  # vigente, vencido, en_tramite, suspendido
    fecha_emision     = db.Column(db.Date)
    fecha_vencimiento = db.Column(db.Date)
    recordatorio_dias = db.Column(db.Integer, default=30)  # días antes de vencer para alertar
    archivo_url       = db.Column(db.String(500))
    notas             = db.Column(db.Text)
    activo            = db.Column(db.Boolean, default=True)
    cliente_id        = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True, index=True)
    proveedor_id      = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True, index=True)
    producto_id       = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    tipo_entidad      = db.Column(db.String(30), nullable=True)  # cliente, proveedor, producto, empresa
    es_demo           = db.Column(db.Boolean, default=False)
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)
    # v40 — firma digital portal
    firma_empresa_data = db.Column(db.Text, nullable=True)  # firma base64 de la empresa
    firma_empresa_por  = db.Column(db.String(200), nullable=True)
    firma_empresa_en   = db.Column(db.DateTime, nullable=True)
    firma_portal_data  = db.Column(db.Text, nullable=True)  # firma base64 del cliente/proveedor
    firma_portal_por   = db.Column(db.String(200), nullable=True)
    firma_portal_en    = db.Column(db.DateTime, nullable=True)
    selfie_empresa_data = db.Column(db.Text, nullable=True)  # selfie base64 del firmante empresa
    selfie_portal_data = db.Column(db.Text, nullable=True)  # selfie base64 del firmante portal
    requiere_firma_portal = db.Column(db.Boolean, default=False)
    contenido_html     = db.Column(db.Text, nullable=True)  # HTML del contrato generado
    producto          = db.relationship('Producto', foreign_keys=[producto_id])

class CuentaPUC(db.Model):
    """Plan Único de Cuentas — catálogo contable colombiano (Decreto 2650/1993)."""
    __tablename__ = 'cuentas_puc'
    id          = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    codigo      = db.Column(db.String(10), unique=True, index=True, nullable=False)
    nombre      = db.Column(db.String(200), nullable=False)
    nivel       = db.Column(db.Integer, default=1)  # 1=clase,2=grupo,3=cuenta,4=subcuenta,5=auxiliar
    naturaleza  = db.Column(db.String(7), default='debito')  # debito | credito
    tipo        = db.Column(db.String(20))  # activo,pasivo,patrimonio,ingreso,gasto,costo_venta,costo_produccion
    padre_codigo= db.Column(db.String(10), nullable=True)
    acepta_mov  = db.Column(db.Boolean, default=True)
    activo      = db.Column(db.Boolean, default=True)
    descripcion = db.Column(db.Text, nullable=True)

class AsientoContable(db.Model):
    __tablename__ = 'asientos_contables'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero           = db.Column(db.String(20))     # AC-YYYY-NNN
    fecha            = db.Column(db.Date, nullable=False)
    descripcion      = db.Column(db.String(300), nullable=False)
    tipo             = db.Column(db.String(30), default='manual')
    # tipo: manual | venta | compra | gasto | nomina | ingreso_externo | inversion_socio | gasto_caja_chica
    subtipo          = db.Column(db.String(50), nullable=True)
    referencia       = db.Column(db.String(100))
    # Legacy single-line (kept for backward compat)
    debe             = db.Column(db.Float, default=0)
    haber            = db.Column(db.Float, default=0)
    cuenta_debe      = db.Column(db.String(100))
    cuenta_haber     = db.Column(db.String(100))
    # v34 PUC fields
    tipo_documento   = db.Column(db.String(20), default='comprobante')  # comprobante_egreso,comprobante_ingreso,nota_contable,factura_venta,factura_compra
    estado_asiento   = db.Column(db.String(20), default='borrador')     # borrador,aprobado,anulado
    tercero_nit      = db.Column(db.String(30), nullable=True)
    tercero_nombre   = db.Column(db.String(200), nullable=True)
    periodo          = db.Column(db.String(7), nullable=True)  # "2026-04" para cierre mensual
    notas            = db.Column(db.Text)
    venta_id         = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True, index=True)
    orden_compra_id  = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True, index=True)
    proveedor_id     = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True, index=True)
    gasto_id         = db.Column(db.Integer, db.ForeignKey('gastos_operativos.id'), nullable=True)
    clasificacion    = db.Column(db.String(10), default='egreso')    # ingreso | egreso
    nro_transaccion  = db.Column(db.String(100), nullable=True)
    banco_nombre     = db.Column(db.String(120), nullable=True)
    banco_cuenta     = db.Column(db.String(80), nullable=True)
    beneficiario     = db.Column(db.String(200), nullable=True)
    metodo_pago      = db.Column(db.String(30), nullable=True)
    fecha_pago       = db.Column(db.Date, nullable=True)
    creado_por       = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    # v36 — estado de pago para flujo OC/ventas
    estado_pago      = db.Column(db.String(20), default='pendiente')  # pendiente, parcial, completo
    monto_pagado     = db.Column(db.Float, default=0)  # para pagos parciales
    venta            = db.relationship('Venta', foreign_keys=[venta_id])
    orden_compra     = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])
    proveedor        = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    gasto            = db.relationship('GastoOperativo', foreign_keys=[gasto_id])
    lineas           = db.relationship('LineaAsiento', backref='asiento', lazy=True, cascade='all, delete-orphan')

class MovimientoBancario(db.Model):
    """Movimiento importado de extracto bancario para conciliación."""
    __tablename__ = 'movimientos_bancarios'
    id          = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    fecha       = db.Column(db.Date, nullable=False)
    descripcion = db.Column(db.String(300))
    referencia  = db.Column(db.String(100))
    monto       = db.Column(db.Float, nullable=False)
    tipo        = db.Column(db.String(10), default='debito')   # debito, credito
    saldo       = db.Column(db.Float, nullable=True)
    banco       = db.Column(db.String(100))
    conciliado  = db.Column(db.Boolean, default=False)
    asiento_id  = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=True)
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    asiento     = db.relationship('AsientoContable', foreign_keys=[asiento_id])

class NotaContable(db.Model):
    """Nota credito o debito — correccion parcial/total de una factura."""
    __tablename__ = 'notas_contables'
    id              = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero          = db.Column(db.String(20))  # NC-YYYY-NNN o ND-YYYY-NNN
    tipo            = db.Column(db.String(10), nullable=False)  # credito, debito
    fecha           = db.Column(db.Date, nullable=False)
    venta_id        = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    asiento_original_id = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=True)
    asiento_nota_id = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=True)
    monto           = db.Column(db.Float, nullable=False)
    motivo          = db.Column(db.String(300), nullable=False)
    descripcion     = db.Column(db.Text)
    estado          = db.Column(db.String(20), default='emitida')  # emitida, anulada
    tercero_nit     = db.Column(db.String(30))
    tercero_nombre  = db.Column(db.String(200))
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    venta           = db.relationship('Venta', foreign_keys=[venta_id])
    asiento_original = db.relationship('AsientoContable', foreign_keys=[asiento_original_id])
    asiento_nota    = db.relationship('AsientoContable', foreign_keys=[asiento_nota_id])

class LineaAsiento(db.Model):
    """Línea de un asiento contable — partida doble con cuenta PUC."""
    __tablename__ = 'lineas_asiento'
    id              = db.Column(db.Integer, primary_key=True)
    asiento_id      = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=False)
    cuenta_puc_id   = db.Column(db.Integer, db.ForeignKey('cuentas_puc.id'), nullable=False)
    descripcion     = db.Column(db.String(300))
    debe            = db.Column(db.Float, default=0)
    haber           = db.Column(db.Float, default=0)
    tercero_nit     = db.Column(db.String(30), nullable=True)
    tercero_nombre  = db.Column(db.String(200), nullable=True)
    centro_costo    = db.Column(db.String(50), nullable=True)
    orden           = db.Column(db.Integer, default=0)
    cuenta          = db.relationship('CuentaPUC', foreign_keys=[cuenta_puc_id])

class ReglaTributaria(db.Model):
    __tablename__ = 'reglas_tributarias'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre           = db.Column(db.String(100), nullable=False)
    descripcion      = db.Column(db.Text)
    porcentaje       = db.Column(db.Float, default=0)
    aplica_a         = db.Column(db.String(30), default='ventas')  # ventas, ingresos, profit, proveedor_producto, proveedor_maquila
    proveedor_nombre = db.Column(db.String(200))
    activo           = db.Column(db.Boolean, default=True)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)

class MovimientoInventario(db.Model):
    """Audit trail de todos los movimientos de stock."""
    __tablename__ = 'movimientos_inventario'
    id              = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    producto_id     = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    materia_prima_id= db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=True)
    tipo            = db.Column(db.String(30), nullable=False)  # ingreso, egreso, reserva, liberacion, ajuste
    cantidad        = db.Column(db.Float, default=0)
    stock_anterior  = db.Column(db.Float, default=0)
    stock_posterior = db.Column(db.Float, default=0)
    referencia      = db.Column(db.String(200))  # "Venta VNT-2026-001", "OC OC-2026-003"
    usuario_id      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)


class GastoOperativo(db.Model):
    __tablename__ = 'gastos_operativos'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    fecha        = db.Column(db.Date, nullable=False)
    tipo         = db.Column(db.String(50), nullable=False)
    tipo_custom  = db.Column(db.String(100))
    descripcion  = db.Column(db.String(200))
    monto        = db.Column(db.Float, default=0, nullable=False)
    recurrencia  = db.Column(db.String(10), default='unico')  # unico, mensual
    es_plantilla = db.Column(db.Boolean, default=False)
    notas        = db.Column(db.Text)
    creado_por   = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo      = db.Column(db.Boolean, default=False)
    estado_pago  = db.Column(db.String(20), default='pendiente')  # pendiente, pagado

class Nota(db.Model):
    __tablename__ = 'notas'
    id             = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    titulo         = db.Column(db.String(200))
    contenido      = db.Column(db.Text, nullable=False)
    cliente_id     = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    producto_id    = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    modulo         = db.Column(db.String(50))   # ventas, produccion, inventario, gastos, tareas, otro
    fecha_revision = db.Column(db.Date, nullable=True)
    creado_por     = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo        = db.Column(db.Boolean, default=False)
    # v36 — notas vinculadas a entidades + tipos
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    venta_id        = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    proveedor_id    = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    tipo_nota       = db.Column(db.String(30), default='nota')   # nota, alerta, seguimiento, resolucion
    estado_nota     = db.Column(db.String(20), default='abierta')  # abierta, resuelta
    prioridad       = db.Column(db.String(10), default='normal')   # baja, normal, alta
    cliente        = db.relationship('Cliente', foreign_keys=[cliente_id])
    producto       = db.relationship('Producto', foreign_keys=[producto_id])
    autor          = db.relationship('User', foreign_keys=[creado_por])
    orden_compra   = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])
    venta_ref      = db.relationship('Venta', foreign_keys=[venta_id])
    proveedor_rel  = db.relationship('Proveedor', foreign_keys=[proveedor_id])

class Actividad(db.Model):
    __tablename__ = 'actividades'
    id          = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    tipo        = db.Column(db.String(20))   # crear, editar, eliminar, completar
    entidad     = db.Column(db.String(50))   # cliente, venta, tarea, nota...
    entidad_id  = db.Column(db.Integer)
    descripcion = db.Column(db.String(300))
    usuario_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    usuario     = db.relationship('User', foreign_keys=[usuario_id])

class ConfigEmpresa(db.Model):
    __tablename__ = 'config_empresa'
    id         = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre     = db.Column(db.String(200), default='Evore')
    nit        = db.Column(db.String(30))
    direccion  = db.Column(db.Text)
    telefono   = db.Column(db.String(30))
    email      = db.Column(db.String(120))
    ciudad     = db.Column(db.String(100))
    sitio_web  = db.Column(db.String(200))
    firma_path = db.Column(db.String(300), nullable=True)
    # Datos bancarios (para mostrar a clientes que pagan suscripcion)
    banco_nombre    = db.Column(db.String(120))
    banco_tipo      = db.Column(db.String(40))     # Ahorros, Corriente
    banco_cuenta    = db.Column(db.String(80))
    banco_titular   = db.Column(db.String(120))
    banco_nit       = db.Column(db.String(30))      # NIT del titular de la cuenta
    # v39 — Info legal completa (ley colombiana)
    representante_legal = db.Column(db.String(200), nullable=True)
    representante_cedula = db.Column(db.String(30), nullable=True)
    representante_cargo = db.Column(db.String(100), nullable=True)
    tipo_sociedad = db.Column(db.String(100), nullable=True)  # SAS, LTDA, SA, etc.
    matricula_mercantil = db.Column(db.String(50), nullable=True)
    camara_comercio = db.Column(db.String(100), nullable=True)
    regimen_tributario = db.Column(db.String(50), nullable=True)  # comun, simplificado
    actividad_economica = db.Column(db.String(200), nullable=True)  # CIIU
    contador_nombre = db.Column(db.String(200), nullable=True)
    contador_tarjeta = db.Column(db.String(50), nullable=True)  # tarjeta profesional
    revisor_fiscal = db.Column(db.String(200), nullable=True)
    revisor_tarjeta = db.Column(db.String(50), nullable=True)
    # v40 — Parametros nomina editables (JSON override sobre company_config defaults)
    nomina_params = db.Column(db.Text, nullable=True)  # JSON: {"min_wage": 1423500, ...}
    # DIAN — facturación electrónica (schema prep)
    resolucion_facturacion = db.Column(db.String(50))                       # DIAN resolution number
    prefijo_factura      = db.Column(db.String(10))                         # Invoice prefix (e.g., "FE")
    rango_desde          = db.Column(db.Integer)                            # Authorized range start
    rango_hasta          = db.Column(db.Integer)                            # Authorized range end
    consecutivo_actual   = db.Column(db.Integer, default=0)
    ambiente_dian        = db.Column(db.String(20), default='habilitacion') # habilitacion, produccion
    software_id_dian     = db.Column(db.String(100))
    pin_dian             = db.Column(db.String(10))

class Evento(db.Model):
    __tablename__ = 'eventos'
    id          = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    titulo      = db.Column(db.String(200), nullable=False)
    tipo        = db.Column(db.String(20), default='recordatorio')  # cita, reunion, recordatorio
    fecha       = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.String(5))
    hora_fin    = db.Column(db.String(5))
    descripcion = db.Column(db.Text)
    usuario_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo     = db.Column(db.Boolean, default=False)
    usuario     = db.relationship('User', foreign_keys=[usuario_id])

class CotizacionItem(db.Model):
    __tablename__ = 'cotizacion_items'
    id            = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=False)
    producto_id   = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    servicio_id   = db.Column(db.Integer, db.ForeignKey('servicios.id'), nullable=True)    # v30
    nombre_prod   = db.Column(db.String(200))
    cantidad      = db.Column(db.Float, default=1)
    precio_unit   = db.Column(db.Float, default=0)
    subtotal      = db.Column(db.Float, default=0)
    unidad        = db.Column(db.String(30), default='unidades')   # v30
    aplica_iva    = db.Column(db.Boolean, default=True)            # v30 — IVA por ítem
    iva_pct       = db.Column(db.Float, default=0)                 # v30 — % IVA este ítem
    iva_monto     = db.Column(db.Float, default=0)                 # v30 — monto IVA calculado
    tipo_item     = db.Column(db.String(20), default='producto')   # v30 — 'producto' | 'servicio'
    servicio      = db.relationship('Servicio', foreign_keys=[servicio_id])  # v30

class Cotizacion(db.Model):
    __tablename__ = 'cotizaciones'
    id                  = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero              = db.Column(db.String(20))
    titulo              = db.Column(db.String(200), nullable=False)
    cliente_id          = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    subtotal            = db.Column(db.Float, default=0)
    iva                 = db.Column(db.Float, default=0)
    total               = db.Column(db.Float, default=0)
    porcentaje_anticipo = db.Column(db.Float, default=50)
    monto_anticipo      = db.Column(db.Float, default=0)
    saldo               = db.Column(db.Float, default=0)
    estado              = db.Column(db.String(30), default='borrador')  # borrador, enviada, aprobada, confirmacion_orden
    fecha_emision       = db.Column(db.Date, default=date_type.today)
    fecha_validez       = db.Column(db.Date)
    dias_entrega        = db.Column(db.Integer, default=30)
    fecha_entrega_est   = db.Column(db.Date)
    condiciones_pago    = db.Column(db.Text)
    notas               = db.Column(db.Text)
    dias_tipo           = db.Column(db.String(20), default='calendario')  # v30: 'calendario' | 'habiles'
    tiempo_desde        = db.Column(db.String(20), default='anticipo')    # v30: 'anticipo' | 'firma'
    iva_incluido        = db.Column(db.Boolean, default=True)  # precios incluyen IVA (BOM ya incluye IVA)
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    es_demo             = db.Column(db.Boolean, default=False)
    items               = db.relationship('CotizacionItem', backref='cotizacion', lazy=True, cascade='all, delete-orphan')
    cliente             = db.relationship('Cliente', foreign_keys=[cliente_id])

    @property
    def esta_vencida(self):
        """True si fecha_validez ya pasó y el estado es borrador o enviada."""
        if not self.fecha_validez:
            return False
        return (self.fecha_validez < date_type.today() and
                self.estado in ('borrador', 'enviada'))

class LoteProducto(db.Model):
    __tablename__ = 'lotes_producto'
    id                  = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    producto_id         = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    numero_lote         = db.Column(db.String(80), nullable=False)
    nso                 = db.Column(db.String(80))
    fecha_produccion    = db.Column(db.Date)
    fecha_vencimiento   = db.Column(db.Date)
    unidades_producidas = db.Column(db.Float, default=0)
    unidades_restantes  = db.Column(db.Float, default=0)
    notas               = db.Column(db.Text)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    producto            = db.relationship('Producto', foreign_keys=[producto_id], backref='lotes')

# Tabla asociativa MateriaPrima ↔ Producto (M2M)
class MateriaPrimaProducto(db.Model):
    __tablename__ = 'materia_prima_productos'
    id               = db.Column(db.Integer, primary_key=True)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False)
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)

class MateriaPrima(db.Model):
    __tablename__ = 'materias_primas'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre           = db.Column(db.String(200), nullable=False)
    descripcion      = db.Column(db.Text)
    unidad           = db.Column(db.String(30), default='unidades')  # kg, g, litros, ml, unidades
    stock_disponible = db.Column(db.Float, default=0)
    stock_reservado  = db.Column(db.Float, default=0)
    stock_minimo     = db.Column(db.Float, default=0)
    costo_unitario   = db.Column(db.Float, default=0)
    categoria        = db.Column(db.String(100))
    proveedor        = db.Column(db.String(200))
    proveedor_id     = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)  # legacy compat (primer producto)
    activo           = db.Column(db.Boolean, default=True)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo          = db.Column(db.Boolean, default=False)
    producto         = db.relationship('Producto', foreign_keys=[producto_id])
    proveedor_rel    = db.relationship('Proveedor', foreign_keys=[proveedor_id])
    productos_rel    = db.relationship(
        'Producto',
        secondary='materia_prima_productos',
        primaryjoin='MateriaPrima.id == MateriaPrimaProducto.materia_prima_id',
        secondaryjoin='MateriaPrimaProducto.producto_id == Producto.id',
        viewonly=True
    )

class LoteMateriaPrima(db.Model):
    """Lote de stock de materia prima ingresado mediante compra."""
    __tablename__ = 'lotes_materia_prima'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False)
    compra_id        = db.Column(db.Integer, db.ForeignKey('compras_materia.id'), nullable=True)
    numero_lote      = db.Column(db.String(80))
    nro_factura      = db.Column(db.String(100))
    proveedor        = db.Column(db.String(200))
    fecha_compra     = db.Column(db.Date)
    fecha_vencimiento= db.Column(db.Date, nullable=True)
    cantidad_inicial = db.Column(db.Float, default=0)
    cantidad_disponible = db.Column(db.Float, default=0)
    cantidad_reservada  = db.Column(db.Float, default=0)
    costo_unitario   = db.Column(db.Float, default=0)
    notas            = db.Column(db.Text)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    materia          = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id],
                                       backref=db.backref('lotes_materia', lazy=True,
                                                          order_by='LoteMateriaPrima.fecha_vencimiento'))
    compra           = db.relationship('CompraMateria', foreign_keys=[compra_id])

    @property
    def proxima_caducidad(self):
        """True si vence en los próximos 90 días."""
        if not self.fecha_vencimiento:
            return False
        from datetime import date, timedelta
        return self.fecha_vencimiento <= (date.today() + timedelta(days=90))

    @property
    def ya_vencido(self):
        if not self.fecha_vencimiento:
            return False
        from datetime import date
        return self.fecha_vencimiento < date.today()


class RecetaProducto(db.Model):
    __tablename__ = 'recetas_producto'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    unidades_produce = db.Column(db.Integer, default=1)    # cuántas unidades produce esta receta
    descripcion      = db.Column(db.Text)
    activo           = db.Column(db.Boolean, default=True)
    margen_pct       = db.Column(db.Float, default=30)  # % ganancia definido por director financiero
    precio_venta_sugerido = db.Column(db.Float, default=0)  # precio calculado: costo + margen + IVA
    costo_calculado  = db.Column(db.Float, default=0)  # costo unitario calculado desde ingredientes
    es_demo          = db.Column(db.Boolean, default=False)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    producto         = db.relationship('Producto', foreign_keys=[producto_id], backref='receta')
    items            = db.relationship('RecetaItem', backref='receta', lazy=True,
                                       cascade='all, delete-orphan')

class RecetaItem(db.Model):
    __tablename__ = 'receta_items'
    id               = db.Column(db.Integer, primary_key=True)
    receta_id        = db.Column(db.Integer, db.ForeignKey('recetas_producto.id'), nullable=False)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False)
    cantidad_por_unidad = db.Column(db.Float, default=0)
    es_empaque       = db.Column(db.Boolean, default=False)
    rendimiento      = db.Column(db.Float, default=1)  # v41: unidades de producto que cubre 1 unidad de este insumo
    # Ejemplo: caja de 250 uds → rendimiento=250, cinta para 100 cajas de 250 → rendimiento=25000
    clasificacion    = db.Column(db.String(30), default='materia_prima')
    # clasificacion: materia_prima | maquila | empaque_primario | empaque_secundario
    materia          = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])

class ReservaProduccion(db.Model):
    __tablename__ = 'reservas_produccion'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False)
    cantidad         = db.Column(db.Float, default=0)
    estado           = db.Column(db.String(20), default='reservado')  # reservado, usado, cancelado
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    lote_id          = db.Column(db.Integer, db.ForeignKey('lotes_producto.id'), nullable=True)
    lote_materia_prima_id = db.Column(db.Integer, db.ForeignKey('lotes_materia_prima.id'), nullable=True)
    orden_produccion_id   = db.Column(db.Integer, db.ForeignKey('ordenes_produccion.id'), nullable=True)
    notas            = db.Column(db.Text)
    creado_por       = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    venta_id         = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    materia          = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])
    producto         = db.relationship('Producto', foreign_keys=[producto_id])
    venta            = db.relationship('Venta', foreign_keys=[venta_id])
    lote_mp          = db.relationship('LoteMateriaPrima', foreign_keys=[lote_materia_prima_id])
    orden_produccion = db.relationship('OrdenProduccion', foreign_keys=[orden_produccion_id])

class OrdenProduccion(db.Model):
    __tablename__ = 'ordenes_produccion'
    id                = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    cotizacion_id     = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)
    venta_id          = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    producto_id       = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    operario_id       = db.Column(db.Integer, db.ForeignKey('empleados.id'), nullable=True)  # v41
    cantidad_total    = db.Column(db.Float, default=0)
    cantidad_stock    = db.Column(db.Float, default=0)
    cantidad_producir = db.Column(db.Float, default=0)
    merma             = db.Column(db.Float, default=0)  # v41 — desperdicio/scrap
    merma_motivo      = db.Column(db.String(200), nullable=True)
    numero_lote       = db.Column(db.String(80))
    estado            = db.Column(db.String(30), default='en_produccion')
    notas             = db.Column(db.Text)
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)
    completado_en     = db.Column(db.DateTime, nullable=True)
    fecha_inicio_real = db.Column(db.Date, nullable=True)
    fecha_fin_estimada= db.Column(db.Date, nullable=True)
    producto          = db.relationship('Producto', foreign_keys=[producto_id])
    operario          = db.relationship('Empleado', foreign_keys=[operario_id])
    cotizacion        = db.relationship('Cotizacion', foreign_keys=[cotizacion_id])
    venta             = db.relationship('Venta', foreign_keys=[venta_id], back_populates='ordenes_produccion')

class Comision(db.Model):
    """Comision por venta para vendedor."""
    __tablename__ = 'comisiones'
    id          = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    venta_id    = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    vendedor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    porcentaje  = db.Column(db.Float, default=5.0)
    monto       = db.Column(db.Float, default=0)
    estado      = db.Column(db.String(20), default='pendiente')  # pendiente, pagada
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    venta       = db.relationship('Venta', foreign_keys=[venta_id])
    vendedor    = db.relationship('User', foreign_keys=[vendedor_id])

class Incapacidad(db.Model):
    """Incapacidad medica de un empleado."""
    __tablename__ = 'incapacidades'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    empleado_id  = db.Column(db.Integer, db.ForeignKey('empleados.id'), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin    = db.Column(db.Date, nullable=False)
    tipo         = db.Column(db.String(30), default='general')  # general, laboral, maternidad
    entidad      = db.Column(db.String(30), default='EPS')  # EPS, ARL
    dias         = db.Column(db.Integer, default=0)
    diagnostico  = db.Column(db.String(300))
    notas        = db.Column(db.Text)
    creado_por   = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    empleado     = db.relationship('Empleado', foreign_keys=[empleado_id])

class VacacionTomada(db.Model):
    """Registro de vacaciones tomadas por empleado."""
    __tablename__ = 'vacaciones_tomadas'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    empleado_id  = db.Column(db.Integer, db.ForeignKey('empleados.id'), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin    = db.Column(db.Date, nullable=False)
    dias         = db.Column(db.Integer, default=0)
    tipo         = db.Column(db.String(20), default='remuneradas')  # remuneradas, compensadas_dinero
    notas        = db.Column(db.Text)
    creado_por   = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    empleado     = db.relationship('Empleado', foreign_keys=[empleado_id])

class Requisicion(db.Model):
    """Requisicion de compra — solicitud pre-OC."""
    __tablename__ = 'requisiciones'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero       = db.Column(db.String(20))
    solicitante_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    descripcion  = db.Column(db.Text, nullable=False)
    motivo       = db.Column(db.String(200))
    estado       = db.Column(db.String(20), default='pendiente')  # pendiente, aprobada, rechazada, convertida
    prioridad    = db.Column(db.String(10), default='media')
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    solicitante  = db.relationship('User', foreign_keys=[solicitante_id])
    orden_compra = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])

class Notificacion(db.Model):
    __tablename__ = 'notificaciones'
    id         = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    tipo       = db.Column(db.String(40), default='info')  # tarea_asignada, alerta_stock, info
    titulo     = db.Column(db.String(200), nullable=False)
    mensaje    = db.Column(db.Text)
    url        = db.Column(db.String(300))
    leida      = db.Column(db.Boolean, default=False, index=True)
    creado_en  = db.Column(db.DateTime, default=datetime.utcnow)
    usuario    = db.relationship('User', foreign_keys=[usuario_id])

class Empleado(db.Model):
    __tablename__ = 'empleados'
    id                  = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre              = db.Column(db.String(100), nullable=False)
    apellido            = db.Column(db.String(100), nullable=False)
    cedula              = db.Column(db.String(30))
    email               = db.Column(db.String(120))
    telefono            = db.Column(db.String(30))
    cargo               = db.Column(db.String(100))
    departamento        = db.Column(db.String(100))
    tipo_contrato       = db.Column(db.String(40), default='indefinido')  # indefinido, fijo, obra_labor, prestacion_servicios
    salario_base        = db.Column(db.Float, default=0)
    auxilio_transporte  = db.Column(db.Boolean, default=True)  # aplica si salario <= 2 SMLMV
    nivel_riesgo_arl    = db.Column(db.Integer, default=1)  # 1-5
    estado              = db.Column(db.String(20), default='activo', index=True)  # activo, inactivo, retirado
    fecha_ingreso       = db.Column(db.Date)
    fecha_retiro        = db.Column(db.Date, nullable=True)
    motivo_retiro       = db.Column(db.String(30), nullable=True)  # renuncia, despido_justa, despido_sin_justa, mutuo_acuerdo
    notas               = db.Column(db.Text)
    tipo_sangre         = db.Column(db.String(10))
    contacto_emergencia_nombre   = db.Column(db.String(120))
    contacto_emergencia_telefono = db.Column(db.String(30))
    contacto_emergencia_parentesco = db.Column(db.String(50))
    eps                 = db.Column(db.String(100))
    caja_compensacion   = db.Column(db.String(100))
    fondo_pensiones     = db.Column(db.String(100))
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo             = db.Column(db.Boolean, default=False)

class HoraExtra(db.Model):
    """Registro de horas extra por empleado — Art. 168-170 CST."""
    __tablename__ = 'horas_extra'
    id           = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    empleado_id  = db.Column(db.Integer, db.ForeignKey('empleados.id'), nullable=False)
    fecha        = db.Column(db.Date, nullable=False)
    tipo         = db.Column(db.String(30), nullable=False)
    # tipos: diurna (25%), nocturna (75%), dominical_diurna (100%), dominical_nocturna (150%)
    horas        = db.Column(db.Float, nullable=False, default=1)
    recargo_pct  = db.Column(db.Float, default=0.25)  # porcentaje de recargo
    valor        = db.Column(db.Float, default=0)  # valor calculado
    periodo      = db.Column(db.String(7))  # "2026-04" para vincular a cierre de nomina
    notas        = db.Column(db.String(200))
    creado_por   = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    empleado     = db.relationship('Empleado', foreign_keys=[empleado_id])

class UserSesion(db.Model):
    __tablename__ = 'user_sesiones'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    login_at   = db.Column(db.DateTime, default=datetime.utcnow)
    logout_at  = db.Column(db.DateTime, nullable=True)
    duracion_min = db.Column(db.Float, default=0)

class PreCotizacionItem(db.Model):
    __tablename__ = 'pre_cotizacion_items'
    id              = db.Column(db.Integer, primary_key=True)
    precot_id       = db.Column(db.Integer, db.ForeignKey('pre_cotizaciones.id'), nullable=False)
    nombre_prod     = db.Column(db.String(200))
    cantidad        = db.Column(db.Float, default=0)
    precio_unit     = db.Column(db.Float, default=0)
    subtotal        = db.Column(db.Float, default=0)
    notas           = db.Column(db.String(300))

class PreCotizacion(db.Model):
    __tablename__ = 'pre_cotizaciones'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    numero           = db.Column(db.String(30))
    cliente_id       = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    cliente_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    sales_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    estado           = db.Column(db.String(30), default='pendiente')
    notas_cliente    = db.Column(db.Text)
    notas_manager    = db.Column(db.Text)
    subtotal         = db.Column(db.Float, default=0)
    iva              = db.Column(db.Float, default=0)
    total            = db.Column(db.Float, default=0)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    cliente          = db.relationship('Cliente', foreign_keys=[cliente_id])
    cliente_user     = db.relationship('User', foreign_keys=[cliente_user_id])
    sales_manager    = db.relationship('User', foreign_keys=[sales_manager_id])
    items            = db.relationship('PreCotizacionItem', backref='precot', lazy=True, cascade='all, delete-orphan')


# ── v30: Servicio — entidad sin inventario ────────────────────────────────────
class Servicio(db.Model):
    """Servicio que puede incluirse en cotizaciones y ventas sin afectar inventario."""
    __tablename__ = 'servicios'
    id            = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre        = db.Column(db.String(200), nullable=False)
    descripcion   = db.Column(db.Text)
    costo_interno = db.Column(db.Float, default=0)   # costo para la empresa
    precio_venta  = db.Column(db.Float, default=0)   # precio al cliente
    unidad        = db.Column(db.String(30), default='servicio')  # servicio, hora, día, proyecto
    categoria     = db.Column(db.String(100))
    activo        = db.Column(db.Boolean, default=True)
    creado_por    = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en     = db.Column(db.DateTime, default=datetime.utcnow)
    es_demo       = db.Column(db.Boolean, default=False)

    @property
    def margen(self):
        if not self.precio_venta or self.precio_venta == 0:
            return 0
        return round((self.precio_venta - self.costo_interno) / self.precio_venta * 100, 1)


# ── v30: EmpaqueSecundario — calculadora de empaques para producto ────────────
class EmpaqueSecundario(db.Model):
    """Configuración de empaque secundario (caja) para un producto terminado."""
    __tablename__ = 'empaques_secundarios'
    id               = db.Column(db.Integer, primary_key=True)
    company_id       = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    nombre           = db.Column(db.String(100), default='Caja')  # v41: nombre del empaque (Caja, Bolsa, etc.)
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    alto             = db.Column(db.Float, default=0)   # cm
    ancho            = db.Column(db.Float, default=0)   # cm
    largo            = db.Column(db.Float, default=0)   # cm
    peso_unitario    = db.Column(db.Float, default=0)   # kg por unidad de producto
    peso_max_caja    = db.Column(db.Float, default=0)   # kg máximo por caja
    unidades_por_caja= db.Column(db.Integer, default=1) # calculado o aprobado
    ancho_caja       = db.Column(db.Float, default=0)   # cm — dimensiones finales de la caja
    largo_caja       = db.Column(db.Float, default=0)
    alto_caja        = db.Column(db.Float, default=0)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=True)
    # FK a la materia prima "caja" que se crea automáticamente al aprobar
    aprobado         = db.Column(db.Boolean, default=False)
    notas            = db.Column(db.Text)
    creado_por       = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    producto         = db.relationship('Producto', foreign_keys=[producto_id])
    materia_prima    = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])

    def cajas_para_pedido(self, cantidad_pedido):
        """Calcula cuántas cajas se necesitan para una cantidad dada."""
        if not self.unidades_por_caja or self.unidades_por_caja == 0:
            return 0
        import math
        return math.ceil(cantidad_pedido / self.unidades_por_caja)


class ForoPublicacion(db.Model):
    """Publicacion en el foro Somos Evore."""
    __tablename__ = 'foro_publicaciones'
    id              = db.Column(db.Integer, primary_key=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo            = db.Column(db.String(20), default='producto')  # producto, servicio
    modalidad       = db.Column(db.String(10), default='vendo')     # vendo, compro
    titulo          = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text, nullable=False)
    industria       = db.Column(db.String(100))
    imagen_url      = db.Column(db.String(500))
    precio_referencia = db.Column(db.Float, nullable=True)
    unidad          = db.Column(db.String(50))  # unidad, kg, litro, servicio, etc.
    activo          = db.Column(db.Boolean, default=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en  = db.Column(db.DateTime, default=datetime.utcnow)
    company         = db.relationship('Company', backref=db.backref('publicaciones_foro', lazy=True))
    user            = db.relationship('User', foreign_keys=[user_id])

class ForoValoracion(db.Model):
    """Valoracion de 1-5 estrellas tras una venta confirmada."""
    __tablename__ = 'foro_valoraciones'
    id              = db.Column(db.Integer, primary_key=True)
    proveedor_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    cliente_company_id   = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    cliente_user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    publicacion_id       = db.Column(db.Integer, db.ForeignKey('foro_publicaciones.id'), nullable=True)
    estrellas       = db.Column(db.Integer, nullable=False)  # 1-5
    comentario      = db.Column(db.Text)
    estado          = db.Column(db.String(20), default='activa', index=True)  # activa, apelada, eliminada
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    proveedor       = db.relationship('Company', foreign_keys=[proveedor_company_id])
    cliente         = db.relationship('Company', foreign_keys=[cliente_company_id])
    cliente_user    = db.relationship('User', foreign_keys=[cliente_user_id])
    publicacion     = db.relationship('ForoPublicacion', backref=db.backref('valoraciones', lazy=True))

class ForoApelacion(db.Model):
    """Apelacion de una valoracion — mediada por admin Evore."""
    __tablename__ = 'foro_apelaciones'
    id              = db.Column(db.Integer, primary_key=True)
    valoracion_id   = db.Column(db.Integer, db.ForeignKey('foro_valoraciones.id'), nullable=False)
    solicitado_por  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    motivo          = db.Column(db.Text, nullable=False)
    estado          = db.Column(db.String(30), default='pendiente')  # pendiente, favor_cliente, favor_proveedor
    notas_admin     = db.Column(db.Text)
    resuelto_por    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    resuelto_en     = db.Column(db.DateTime, nullable=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    valoracion      = db.relationship('ForoValoracion', backref=db.backref('apelacion', uselist=False))
    solicitante     = db.relationship('User', foreign_keys=[solicitado_por])
    admin_resolver  = db.relationship('User', foreign_keys=[resuelto_por])


class ForoBanner(db.Model):
    """Banner publicitario en el marketplace."""
    __tablename__ = 'foro_banners'
    id              = db.Column(db.Integer, primary_key=True)
    titulo          = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text)
    imagen_url      = db.Column(db.String(500))
    link_url        = db.Column(db.String(500))
    industria       = db.Column(db.String(100))  # NULL = all industries
    tipo            = db.Column(db.String(20), default='evore')  # evore, tercero
    activo          = db.Column(db.Boolean, default=True)
    orden           = db.Column(db.Integer, default=0)
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)


class Suscripcion(db.Model):
    """Suscripcion mensual/anual a un plan de Evore."""
    __tablename__ = 'suscripciones'
    id              = db.Column(db.Integer, primary_key=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    plan            = db.Column(db.String(20), nullable=False)          # starter, pro
    periodo         = db.Column(db.String(10), default='mensual')       # mensual, anual
    usuarios_extra  = db.Column(db.Integer, default=0)                  # solo pro: extras sobre 3
    monto_mensual   = db.Column(db.Float, default=0)                    # valor mensual real
    monto_cobrado   = db.Column(db.Float, default=0)                    # monto del ultimo cobro
    estado          = db.Column(db.String(20), default='pendiente', index=True)  # pendiente, activa, vencida, cancelada
    fecha_inicio    = db.Column(db.Date, nullable=True)
    fecha_proximo_pago = db.Column(db.Date, nullable=True)
    fecha_vencimiento  = db.Column(db.Date, nullable=True)
    asiento_id      = db.Column(db.Integer, db.ForeignKey('asientos_contables.id'), nullable=True)
    recordatorio_enviado = db.Column(db.Boolean, default=False)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por      = db.Column(db.Integer, nullable=True)
    company         = db.relationship('Company', backref=db.backref('suscripciones', lazy=True))


# ══════════════════════════════════════════════════════════════════
# PROYECTOS (Project Management — Jira/Notion style)
# ══════════════════════════════════════════════════════════════════

class Proyecto(db.Model):
    __tablename__ = 'proyectos'
    id              = db.Column(db.Integer, primary_key=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    codigo          = db.Column(db.String(20))  # PRY-001
    nombre          = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text)
    estado          = db.Column(db.String(20), default='planificacion', index=True)
    # planificacion, en_progreso, pausado, completado, cancelado
    prioridad       = db.Column(db.String(10), default='media')
    color           = db.Column(db.String(7), default='#0176D3')  # hex for kanban
    fecha_inicio    = db.Column(db.Date)
    fecha_fin       = db.Column(db.Date)
    presupuesto     = db.Column(db.Float, default=0)
    responsable_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Vinculacion con entidades del CRM
    cliente_id      = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    etiquetas       = db.Column(db.Text, default='[]')  # JSON: ["lanzamiento","urgente"]
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    responsable     = db.relationship('User', foreign_keys=[responsable_id])
    creador         = db.relationship('User', foreign_keys=[creado_por])
    cliente         = db.relationship('Cliente', foreign_keys=[cliente_id])
    fases           = db.relationship('ProyectoFase', backref='proyecto', lazy=True,
                                       order_by='ProyectoFase.orden', cascade='all, delete-orphan')
    gastos          = db.relationship('ProyectoGasto', backref='proyecto', lazy=True,
                                       cascade='all, delete-orphan')

class ProyectoFase(db.Model):
    __tablename__ = 'proyecto_fases'
    id              = db.Column(db.Integer, primary_key=True)
    proyecto_id     = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False, index=True)
    nombre          = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text)
    orden           = db.Column(db.Integer, default=0)
    estado          = db.Column(db.String(20), default='pendiente')
    # pendiente, en_progreso, completada
    fecha_inicio    = db.Column(db.Date)
    fecha_fin       = db.Column(db.Date)
    color           = db.Column(db.String(7), default='#6B7280')
    tareas          = db.relationship('ProyectoTarea', backref='fase', lazy=True,
                                       order_by='ProyectoTarea.orden', cascade='all, delete-orphan')

class ProyectoTarea(db.Model):
    __tablename__ = 'proyecto_tareas'
    id              = db.Column(db.Integer, primary_key=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True, index=True)
    proyecto_id     = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False, index=True)
    fase_id         = db.Column(db.Integer, db.ForeignKey('proyecto_fases.id'), nullable=True, index=True)
    titulo          = db.Column(db.String(300), nullable=False)
    descripcion     = db.Column(db.Text)
    estado          = db.Column(db.String(20), default='por_hacer', index=True)
    # por_hacer, en_progreso, en_revision, completada
    prioridad       = db.Column(db.String(10), default='media')
    tipo            = db.Column(db.String(30), default='tarea')
    # tarea, compra, legal, finanzas, produccion, logistica
    orden           = db.Column(db.Integer, default=0)
    responsable_id  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    fecha_inicio    = db.Column(db.Date)
    fecha_limite    = db.Column(db.Date)
    estimacion_hrs  = db.Column(db.Float, default=0)
    progreso        = db.Column(db.Integer, default=0)  # 0-100
    # ── Vinculos a entidades del CRM ──
    venta_id        = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    orden_compra_id = db.Column(db.Integer, db.ForeignKey('ordenes_compra.id'), nullable=True)
    orden_produccion_id = db.Column(db.Integer, db.ForeignKey('ordenes_produccion.id'), nullable=True)
    gasto_id        = db.Column(db.Integer, db.ForeignKey('gastos_operativos.id'), nullable=True)
    documento_legal_id = db.Column(db.Integer, db.ForeignKey('documentos_legales.id'), nullable=True)
    tarea_id        = db.Column(db.Integer, db.ForeignKey('tareas.id'), nullable=True)  # ticket generado
    etiquetas       = db.Column(db.Text, default='[]')
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    completado_en   = db.Column(db.DateTime, nullable=True)
    # Relationships
    responsable     = db.relationship('User', foreign_keys=[responsable_id])
    creador         = db.relationship('User', foreign_keys=[creado_por])
    venta           = db.relationship('Venta', foreign_keys=[venta_id])
    orden_compra    = db.relationship('OrdenCompra', foreign_keys=[orden_compra_id])
    orden_produccion = db.relationship('OrdenProduccion', foreign_keys=[orden_produccion_id])
    gasto           = db.relationship('GastoOperativo', foreign_keys=[gasto_id])
    documento_legal = db.relationship('DocumentoLegal', foreign_keys=[documento_legal_id])
    ticket          = db.relationship('Tarea', foreign_keys=[tarea_id])
    comentarios     = db.relationship('ProyectoComentario', backref='tarea_proy', lazy=True,
                                       order_by='ProyectoComentario.creado_en', cascade='all, delete-orphan')

class ProyectoComentario(db.Model):
    __tablename__ = 'proyecto_comentarios'
    id              = db.Column(db.Integer, primary_key=True)
    tarea_id        = db.Column(db.Integer, db.ForeignKey('proyecto_tareas.id'), nullable=False, index=True)
    autor_id        = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    mensaje         = db.Column(db.Text, nullable=False)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    autor           = db.relationship('User', foreign_keys=[autor_id])

class ProyectoGasto(db.Model):
    """Gasto vinculado a un proyecto — referencia a GastoOperativo."""
    __tablename__ = 'proyecto_gastos'
    id              = db.Column(db.Integer, primary_key=True)
    proyecto_id     = db.Column(db.Integer, db.ForeignKey('proyectos.id'), nullable=False, index=True)
    gasto_id        = db.Column(db.Integer, db.ForeignKey('gastos_operativos.id'), nullable=False)
    descripcion     = db.Column(db.String(200))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    gasto           = db.relationship('GastoOperativo', foreign_keys=[gasto_id])


# ══════════════════════════════════════════════════════════════════
# CAPACITACIÓN (Training module)
# ══════════════════════════════════════════════════════════════════

class CapCurso(db.Model):
    """Curso de capacitación — contenido global de plataforma."""
    __tablename__ = 'cap_cursos'
    id              = db.Column(db.Integer, primary_key=True)
    titulo          = db.Column(db.String(200), nullable=False)
    descripcion     = db.Column(db.Text)
    modulo_crm      = db.Column(db.String(50))  # ventas, compras, produccion, contable, nomina, inventario, tareas, empaques
    icono           = db.Column(db.String(50), default='bi-mortarboard')
    orden           = db.Column(db.Integer, default=0)
    nivel           = db.Column(db.String(20), default='basico')  # basico, intermedio, avanzado
    activo          = db.Column(db.Boolean, default=True)
    roles_objetivo  = db.Column(db.Text, default='[]')  # JSON list of roles
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    lecciones       = db.relationship('CapLeccion', backref='curso', lazy=True, order_by='CapLeccion.orden')
    preguntas       = db.relationship('CapPregunta', backref='curso', lazy=True, order_by='CapPregunta.orden')

class CapLeccion(db.Model):
    """Lección dentro de un curso — paso a paso."""
    __tablename__ = 'cap_lecciones'
    id              = db.Column(db.Integer, primary_key=True)
    curso_id        = db.Column(db.Integer, db.ForeignKey('cap_cursos.id'), nullable=False, index=True)
    titulo          = db.Column(db.String(200), nullable=False)
    contenido       = db.Column(db.Text, nullable=False)
    orden           = db.Column(db.Integer, default=0)
    duracion_min    = db.Column(db.Integer, default=5)
    activo          = db.Column(db.Boolean, default=True)
    pasos           = db.Column(db.Text, default='[]')  # JSON: [{"codigo":"crear_cliente","label":"Crear un cliente","entidad":"cliente"}]
    ruta_practica   = db.Column(db.String(100))  # endpoint name for redirect, e.g. "cliente_nuevo"

class CapPregunta(db.Model):
    """Pregunta de evaluación de un curso."""
    __tablename__ = 'cap_preguntas'
    id                  = db.Column(db.Integer, primary_key=True)
    curso_id            = db.Column(db.Integer, db.ForeignKey('cap_cursos.id'), nullable=False, index=True)
    texto               = db.Column(db.Text, nullable=False)
    opciones            = db.Column(db.Text, nullable=False)  # JSON: ["opcion A", "opcion B", ...]
    respuesta_correcta  = db.Column(db.Integer, nullable=False)  # 0-based index
    orden               = db.Column(db.Integer, default=0)

class CapProgreso(db.Model):
    """Progreso de un usuario en una lección."""
    __tablename__ = 'cap_progresos'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    leccion_id      = db.Column(db.Integer, db.ForeignKey('cap_lecciones.id'), nullable=False)
    completado      = db.Column(db.Boolean, default=False)
    completado_en   = db.Column(db.DateTime, nullable=True)
    __table_args__  = (db.UniqueConstraint('user_id', 'company_id', 'leccion_id', name='uq_cap_progreso'),)
    user            = db.relationship('User', foreign_keys=[user_id])
    leccion         = db.relationship('CapLeccion', foreign_keys=[leccion_id])

class CapEvaluacion(db.Model):
    """Resultado de evaluación de un curso por un usuario."""
    __tablename__ = 'cap_evaluaciones'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    company_id      = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    curso_id        = db.Column(db.Integer, db.ForeignKey('cap_cursos.id'), nullable=False)
    puntaje         = db.Column(db.Integer, nullable=False)
    total_preguntas = db.Column(db.Integer, nullable=False)
    porcentaje      = db.Column(db.Float, nullable=False)
    respuestas      = db.Column(db.Text)  # JSON detailed answers
    aprobado        = db.Column(db.Boolean, default=False)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    user            = db.relationship('User', foreign_keys=[user_id])
    curso           = db.relationship('CapCurso', foreign_keys=[curso_id])


@login_manager.user_loader
def load_user(uid): return db.session.get(User, int(uid))

def _migrate(conn):
    """Agrega columnas nuevas a tablas existentes sin romper datos actuales."""
    migrations = [
        # GastoOperativo — campos v11
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS tipo_custom VARCHAR(100)"),
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS recurrencia VARCHAR(20) DEFAULT 'unico'"),
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS es_plantilla BOOLEAN DEFAULT FALSE"),
        # Producto — fecha de caducidad
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS fecha_caducidad DATE"),
        # Nota — campos v11
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS producto_id INTEGER REFERENCES productos(id)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS modulo VARCHAR(50)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS fecha_revision DATE"),
        # ReglaTributaria — proveedor
        ("ALTER TABLE reglas_tributarias ADD COLUMN IF NOT EXISTS proveedor_nombre VARCHAR(200)"),
        # User — módulos personalizados v12
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS modulos_permitidos TEXT DEFAULT '[]'"),
        # CompraMateria — campos v12
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS materia_id INTEGER REFERENCES materias_primas(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS tipo_compra VARCHAR(50) DEFAULT 'insumo'"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS unidad VARCHAR(30) DEFAULT 'unidades'"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS tiene_caducidad BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS fecha_caducidad DATE"),
        # Tarea — campos v12.1 (parejas de tareas + cotizacion)
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS cotizacion_id INTEGER REFERENCES cotizaciones(id)"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS tarea_tipo VARCHAR(50)"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS tarea_pareja_id INTEGER REFERENCES tareas(id)"),
        # OrdenProduccion — v12.2 venta_id para vincular con ventas
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        # MateriaPrima — v12.2 producto principal al que pertenece
        ("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS producto_id INTEGER REFERENCES productos(id)"),
        # Venta — v12.2 seguimiento de entrega
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS cliente_informado_en TIMESTAMP"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS entregado_en TIMESTAMP"),
        # v12.3 — numero único de venta
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS numero VARCHAR(20)"),
        # v12.3 — venta_id en reservas
        ("ALTER TABLE reservas_produccion ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        # v12.3 — proveedor_id en materias y compras
        ("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        # v12.4 — órdenes de compra
        ("CREATE TABLE IF NOT EXISTS ordenes_compra (id SERIAL PRIMARY KEY, numero VARCHAR(20), proveedor_id INTEGER REFERENCES proveedores(id), estado VARCHAR(30) DEFAULT 'borrador', fecha_emision DATE, fecha_esperada DATE, subtotal FLOAT DEFAULT 0, iva FLOAT DEFAULT 0, total FLOAT DEFAULT 0, notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS ordenes_compra_items (id SERIAL PRIMARY KEY, orden_id INTEGER REFERENCES ordenes_compra(id) ON DELETE CASCADE, nombre_item VARCHAR(200) NOT NULL, descripcion TEXT, cantidad FLOAT DEFAULT 1, unidad VARCHAR(30) DEFAULT 'unidades', precio_unit FLOAT DEFAULT 0, subtotal FLOAT DEFAULT 0)"),
        # v13 — cotizaciones proveedor
        ("CREATE TABLE IF NOT EXISTS cotizaciones_proveedor (id SERIAL PRIMARY KEY, numero VARCHAR(20), proveedor_id INTEGER REFERENCES proveedores(id), nombre_producto VARCHAR(200) NOT NULL, descripcion TEXT, sku VARCHAR(50), precio_unitario FLOAT DEFAULT 0, unidades_minimas INTEGER DEFAULT 1, unidad VARCHAR(30) DEFAULT 'unidades', plazo_entrega VARCHAR(100), condiciones_pago VARCHAR(200), fecha_cotizacion DATE, vigencia DATE, estado VARCHAR(20) DEFAULT 'vigente', notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v13 — documentos legales
        ("CREATE TABLE IF NOT EXISTS documentos_legales (id SERIAL PRIMARY KEY, tipo VARCHAR(50) NOT NULL, titulo VARCHAR(200) NOT NULL, numero VARCHAR(100), entidad VARCHAR(200), descripcion TEXT, estado VARCHAR(20) DEFAULT 'vigente', fecha_emision DATE, fecha_vencimiento DATE, recordatorio_dias INTEGER DEFAULT 30, archivo_url VARCHAR(500), notas TEXT, activo BOOLEAN DEFAULT TRUE, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v13 — asientos contables
        ("CREATE TABLE IF NOT EXISTS asientos_contables (id SERIAL PRIMARY KEY, numero VARCHAR(20), fecha DATE NOT NULL, descripcion VARCHAR(300) NOT NULL, tipo VARCHAR(30) DEFAULT 'manual', referencia VARCHAR(100), debe FLOAT DEFAULT 0, haber FLOAT DEFAULT 0, cuenta_debe VARCHAR(100), cuenta_haber VARCHAR(100), notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v14 — Proveedor tipo (proveedor/transportista/ambos)
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS tipo VARCHAR(20) DEFAULT 'proveedor'"),
        # v14 — CotizacionProveedor campos estructurados
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS tipo_cotizacion VARCHAR(20) DEFAULT 'general'"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS tipo_producto_servicio VARCHAR(100)"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS plazo_entrega_dias INTEGER DEFAULT 0"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS condicion_pago_tipo VARCHAR(30) DEFAULT 'contado'"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS condicion_pago_dias INTEGER DEFAULT 0"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS anticipo_porcentaje FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS calendario_integrado BOOLEAN DEFAULT FALSE"),
        # v14 — OrdenCompra campos nuevos
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS cotizacion_id INTEGER REFERENCES cotizaciones_proveedor(id)"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS fecha_estimada_pago DATE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS transportista_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS fecha_estimada_recogida DATE"),
        # v14 — OrdenCompraItem link a cotizacion
        ("ALTER TABLE ordenes_compra_items ADD COLUMN IF NOT EXISTS cotizacion_id INTEGER REFERENCES cotizaciones_proveedor(id)"),
        # v14 — OrdenProduccion fechas para Gantt
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS fecha_inicio_real DATE"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS fecha_fin_estimada DATE"),
        # v18 — Cliente información bancaria y legal
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS banco_nombre VARCHAR(120)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS banco_cuenta VARCHAR(80)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS banco_tipo VARCHAR(40)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS banco_titular VARCHAR(120)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS info_legal TEXT"),
        # v18 — User onboarding y cliente link
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_dismissed BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS cliente_id INTEGER REFERENCES clientes(id)"),
        # v18 — Cliente sales manager y parámetros
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS sales_manager_id INTEGER REFERENCES users(id)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS anticipo_pct FLOAT DEFAULT 50"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS minimo_pedido INTEGER DEFAULT 1"),
        # v18 — User Sessions
        ("CREATE TABLE IF NOT EXISTS user_sesiones (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), login_at TIMESTAMP DEFAULT NOW(), logout_at TIMESTAMP, duracion_min FLOAT DEFAULT 0)"),
        # v18 — Pre-cotizaciones
        ("CREATE TABLE IF NOT EXISTS pre_cotizaciones (id SERIAL PRIMARY KEY, numero VARCHAR(30), cliente_id INTEGER NOT NULL REFERENCES clientes(id), cliente_user_id INTEGER REFERENCES users(id), sales_manager_id INTEGER REFERENCES users(id), estado VARCHAR(30) DEFAULT 'pendiente', notas_cliente TEXT, notas_manager TEXT, subtotal FLOAT DEFAULT 0, iva FLOAT DEFAULT 0, total FLOAT DEFAULT 0, creado_en TIMESTAMP DEFAULT NOW(), actualizado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS pre_cotizacion_items (id SERIAL PRIMARY KEY, precot_id INTEGER NOT NULL REFERENCES pre_cotizaciones(id), nombre_prod VARCHAR(200), cantidad FLOAT DEFAULT 0, precio_unit FLOAT DEFAULT 0, subtotal FLOAT DEFAULT 0, notas VARCHAR(300))"),
        # v19 — User proveedor link
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        # v19 — OrdenCompra confirmación por proveedor
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS confirmado_en TIMESTAMP"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS confirmado_por INTEGER REFERENCES users(id)"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS estado_proveedor VARCHAR(30) DEFAULT 'pendiente'"),
        # v19 — Cotizaciones columnas faltantes (anticipo, saldo, numero, fecha_entrega_est)
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS numero VARCHAR(20)"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS porcentaje_anticipo FLOAT DEFAULT 50"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS monto_anticipo FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS saldo FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS fecha_entrega_est DATE"),
        # v21 — Lotes de materia prima (stock por lote/factura con fecha vencimiento)
        ("CREATE TABLE IF NOT EXISTS lotes_materia_prima (id SERIAL PRIMARY KEY, materia_prima_id INTEGER NOT NULL REFERENCES materias_primas(id), compra_id INTEGER REFERENCES compras_materia(id), numero_lote VARCHAR(80), nro_factura VARCHAR(100), proveedor VARCHAR(200), fecha_compra DATE, fecha_vencimiento DATE, cantidad_inicial FLOAT DEFAULT 0, cantidad_disponible FLOAT DEFAULT 0, cantidad_reservada FLOAT DEFAULT 0, costo_unitario FLOAT DEFAULT 0, notas TEXT, creado_en TIMESTAMP DEFAULT NOW())"),
        # v21 — ReservaProduccion link a lote de materia prima
        ("ALTER TABLE reservas_produccion ADD COLUMN IF NOT EXISTS lote_materia_prima_id INTEGER REFERENCES lotes_materia_prima(id)"),
        # v21 — MateriaPrima ↔ Producto (M2M) — una materia puede usarse en varios productos
        ("CREATE TABLE IF NOT EXISTS materia_prima_productos (id SERIAL PRIMARY KEY, materia_prima_id INTEGER NOT NULL REFERENCES materias_primas(id), producto_id INTEGER NOT NULL REFERENCES productos(id))"),
        # v19 — Proveedor contacto
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS contacto_nombre VARCHAR(100)"),
        # v20 — Nómina colombiana
        ("CREATE TABLE IF NOT EXISTS empleados (id SERIAL PRIMARY KEY, nombre VARCHAR(100) NOT NULL, apellido VARCHAR(100) NOT NULL, cedula VARCHAR(30), email VARCHAR(120), telefono VARCHAR(30), cargo VARCHAR(100), departamento VARCHAR(100), tipo_contrato VARCHAR(40) DEFAULT 'indefinido', salario_base FLOAT DEFAULT 0, auxilio_transporte BOOLEAN DEFAULT TRUE, nivel_riesgo_arl INTEGER DEFAULT 1, estado VARCHAR(20) DEFAULT 'activo', fecha_ingreso DATE, fecha_retiro DATE, motivo_retiro VARCHAR(30), notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v30 — Servicios (entidad sin inventario)
        ("CREATE TABLE IF NOT EXISTS servicios (id SERIAL PRIMARY KEY, nombre VARCHAR(200) NOT NULL, descripcion TEXT, costo_interno FLOAT DEFAULT 0, precio_venta FLOAT DEFAULT 0, unidad VARCHAR(30) DEFAULT 'servicio', categoria VARCHAR(100), activo BOOLEAN DEFAULT TRUE, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v30 — Empaques secundarios
        ("CREATE TABLE IF NOT EXISTS empaques_secundarios (id SERIAL PRIMARY KEY, producto_id INTEGER NOT NULL REFERENCES productos(id), alto FLOAT DEFAULT 0, ancho FLOAT DEFAULT 0, largo FLOAT DEFAULT 0, peso_unitario FLOAT DEFAULT 0, peso_max_caja FLOAT DEFAULT 0, unidades_por_caja INTEGER DEFAULT 1, materia_prima_id INTEGER REFERENCES materias_primas(id), aprobado BOOLEAN DEFAULT FALSE, notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # v30 — CotizacionItem: unidad + IVA por ítem + servicio
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS unidad VARCHAR(30) DEFAULT 'unidades'"),
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS aplica_iva BOOLEAN DEFAULT TRUE"),
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS iva_pct FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS iva_monto FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS tipo_item VARCHAR(20) DEFAULT 'producto'"),
        ("ALTER TABLE cotizacion_items ADD COLUMN IF NOT EXISTS servicio_id INTEGER REFERENCES servicios(id)"),
        # v30 — Cotizacion: tipo de días + base de tiempo
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS dias_tipo VARCHAR(20) DEFAULT 'calendario'"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS tiempo_desde VARCHAR(20) DEFAULT 'anticipo'"),
        # v30 — OrdenCompra: fecha real de anticipo recibido
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS fecha_anticipo_real DATE"),
        # v30 — ConfigEmpresa: firma digital
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS firma_path VARCHAR(300)"),
        # v30 — AsientoContable: subtipo + FK ventas/OC
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS subtipo VARCHAR(50)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        # v31 — AsientoContable: campos de pago detallados + clasificacion + proveedor
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS clasificacion VARCHAR(10) DEFAULT 'egreso'"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS nro_transaccion VARCHAR(100)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS banco_nombre VARCHAR(120)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS banco_cuenta VARCHAR(80)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS beneficiario VARCHAR(200)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR(30)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS fecha_pago DATE"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        # v30 — VentaProducto: servicio + unidad
        ("ALTER TABLE venta_productos ADD COLUMN IF NOT EXISTS es_servicio BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE venta_productos ADD COLUMN IF NOT EXISTS servicio_id INTEGER REFERENCES servicios(id)"),
        ("ALTER TABLE venta_productos ADD COLUMN IF NOT EXISTS unidad VARCHAR(30) DEFAULT 'unidades'"),
        # v32 — Venta: vincular cotización origen
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS cotizacion_id INTEGER REFERENCES cotizaciones(id)"),
        # v33 — Producto: stock reservado para ATP (Available to Promise)
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS stock_reservado INTEGER DEFAULT 0"),
        ("ALTER TABLE productos ADD COLUMN stock_reservado INTEGER DEFAULT 0"),
        # v33 — ReservaProduccion: FK directa a OrdenProduccion para trazabilidad
        ("ALTER TABLE reservas_produccion ADD COLUMN IF NOT EXISTS orden_produccion_id INTEGER REFERENCES ordenes_produccion(id)"),
        ("ALTER TABLE reservas_produccion ADD COLUMN orden_produccion_id INTEGER REFERENCES ordenes_produccion(id)"),
        # v33 — AsientoContable: FK a GastoOperativo para partida doble automática
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS gasto_id INTEGER REFERENCES gastos_operativos(id)"),
        ("ALTER TABLE asientos_contables ADD COLUMN gasto_id INTEGER REFERENCES gastos_operativos(id)"),
        # v33 — Venta: monto_pagado_total para reconciliación de pagos
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS monto_pagado_total FLOAT DEFAULT 0"),
        ("ALTER TABLE ventas ADD COLUMN monto_pagado_total FLOAT DEFAULT 0"),
        # v33 — PagoVenta: tabla de pagos parciales
        ("CREATE TABLE IF NOT EXISTS pagos_venta (id SERIAL PRIMARY KEY, venta_id INTEGER NOT NULL REFERENCES ventas(id), monto FLOAT NOT NULL, tipo VARCHAR(30) DEFAULT 'anticipo', metodo_pago VARCHAR(30) DEFAULT 'transferencia', referencia VARCHAR(100), fecha DATE NOT NULL, notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS pagos_venta (id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER NOT NULL REFERENCES ventas(id), monto FLOAT NOT NULL, tipo VARCHAR(30) DEFAULT 'anticipo', metodo_pago VARCHAR(30) DEFAULT 'transferencia', referencia VARCHAR(100), fecha DATE NOT NULL, notas TEXT, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        # v34 — Aprobaciones: sistema de confirmación para acciones financieras
        ("CREATE TABLE IF NOT EXISTS aprobaciones (id SERIAL PRIMARY KEY, tipo_accion VARCHAR(50) NOT NULL, descripcion VARCHAR(300), monto FLOAT DEFAULT 0, datos_json TEXT, estado VARCHAR(20) DEFAULT 'pendiente', solicitado_por INTEGER NOT NULL REFERENCES users(id), aprobado_por INTEGER REFERENCES users(id), notas_aprobador TEXT, creado_en TIMESTAMP DEFAULT NOW(), resuelto_en TIMESTAMP)"),
        ("CREATE TABLE IF NOT EXISTS aprobaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, tipo_accion VARCHAR(50) NOT NULL, descripcion VARCHAR(300), monto FLOAT DEFAULT 0, datos_json TEXT, estado VARCHAR(20) DEFAULT 'pendiente', solicitado_por INTEGER NOT NULL REFERENCES users(id), aprobado_por INTEGER REFERENCES users(id), notas_aprobador TEXT, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP, resuelto_en TIMESTAMP)"),
        # v34 — PUC: Plan Único de Cuentas colombiano
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20) DEFAULT 'comprobante'"),
        ("ALTER TABLE asientos_contables ADD COLUMN tipo_documento VARCHAR(20) DEFAULT 'comprobante'"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS estado_asiento VARCHAR(20) DEFAULT 'borrador'"),
        ("ALTER TABLE asientos_contables ADD COLUMN estado_asiento VARCHAR(20) DEFAULT 'borrador'"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS tercero_nit VARCHAR(30)"),
        ("ALTER TABLE asientos_contables ADD COLUMN tercero_nit VARCHAR(30)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS tercero_nombre VARCHAR(200)"),
        ("ALTER TABLE asientos_contables ADD COLUMN tercero_nombre VARCHAR(200)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS periodo VARCHAR(7)"),
        ("ALTER TABLE asientos_contables ADD COLUMN periodo VARCHAR(7)"),
        # v34 — Onboarding por rol
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_step INTEGER DEFAULT 0"),
        ("ALTER TABLE users ADD COLUMN onboarding_step INTEGER DEFAULT 0"),
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarding_role_config TEXT DEFAULT '{}'"),
        ("ALTER TABLE users ADD COLUMN onboarding_role_config TEXT DEFAULT '{}'"),
        # v35 — Producto: costo_receta auto-calculado desde receta + costos MP
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS costo_receta FLOAT DEFAULT 0"),
        ("ALTER TABLE productos ADD COLUMN costo_receta FLOAT DEFAULT 0"),
        # v35 — MarcaProducto: un producto puede tener varias marcas (mismo recipe, diferente NSO/nombre)
        ("CREATE TABLE IF NOT EXISTS marcas_producto (id SERIAL PRIMARY KEY, producto_id INTEGER NOT NULL REFERENCES productos(id), nombre_marca VARCHAR(200) NOT NULL, nso VARCHAR(50), registro_sanitario VARCHAR(100), documento_legal_id INTEGER REFERENCES documentos_legales(id), activo BOOLEAN DEFAULT TRUE, creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS marcas_producto (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER NOT NULL REFERENCES productos(id), nombre_marca VARCHAR(200) NOT NULL, nso VARCHAR(50), registro_sanitario VARCHAR(100), documento_legal_id INTEGER REFERENCES documentos_legales(id), activo BOOLEAN DEFAULT TRUE, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        # v35 — Cliente: envío, transportista preferido, contrato
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS envio_responsable VARCHAR(20) DEFAULT 'cliente'"),
        ("ALTER TABLE clientes ADD COLUMN envio_responsable VARCHAR(20) DEFAULT 'cliente'"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS transportista_preferido_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE clientes ADD COLUMN transportista_preferido_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS contrato_id INTEGER REFERENCES documentos_legales(id)"),
        ("ALTER TABLE clientes ADD COLUMN contrato_id INTEGER REFERENCES documentos_legales(id)"),
        # v35 — DocumentoLegal: vincular a cliente/proveedor/producto
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS cliente_id INTEGER REFERENCES clientes(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN cliente_id INTEGER REFERENCES clientes(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN proveedor_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS producto_id INTEGER REFERENCES productos(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN producto_id INTEGER REFERENCES productos(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS tipo_entidad VARCHAR(30)"),
        ("ALTER TABLE documentos_legales ADD COLUMN tipo_entidad VARCHAR(30)"),
        # v35 — CotizacionProveedor: FK a materia prima
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS materia_prima_id INTEGER REFERENCES materias_primas(id)"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN materia_prima_id INTEGER REFERENCES materias_primas(id)"),
        # v35 — Proveedor: capacidad vehículo y tipo
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS capacidad_vehiculo_kg FLOAT DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN capacidad_vehiculo_kg FLOAT DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS capacidad_vehiculo_m3 FLOAT DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN capacidad_vehiculo_m3 FLOAT DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS tipo_vehiculo VARCHAR(50)"),
        ("ALTER TABLE proveedores ADD COLUMN tipo_vehiculo VARCHAR(50)"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS envia_material BOOLEAN DEFAULT TRUE"),
        ("ALTER TABLE proveedores ADD COLUMN envia_material BOOLEAN DEFAULT TRUE"),
        # v35 — VentaProducto: marca y costo unitario
        ("ALTER TABLE venta_productos ADD COLUMN IF NOT EXISTS marca_id INTEGER REFERENCES marcas_producto(id)"),
        ("ALTER TABLE venta_productos ADD COLUMN marca_id INTEGER REFERENCES marcas_producto(id)"),
        ("ALTER TABLE venta_productos ADD COLUMN IF NOT EXISTS costo_unitario FLOAT DEFAULT 0"),
        ("ALTER TABLE venta_productos ADD COLUMN costo_unitario FLOAT DEFAULT 0"),
        # v35 — RecetaItem: flag empaque
        ("ALTER TABLE receta_items ADD COLUMN IF NOT EXISTS es_empaque BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE receta_items ADD COLUMN es_empaque BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE receta_items ADD COLUMN IF NOT EXISTS clasificacion VARCHAR(30) DEFAULT 'materia_prima'"),
        ("ALTER TABLE receta_items ADD COLUMN clasificacion VARCHAR(30) DEFAULT 'materia_prima'"),
        ("ALTER TABLE recetas_producto ADD COLUMN IF NOT EXISTS margen_pct FLOAT DEFAULT 30"),
        ("ALTER TABLE recetas_producto ADD COLUMN margen_pct FLOAT DEFAULT 30"),
        ("ALTER TABLE recetas_producto ADD COLUMN IF NOT EXISTS precio_venta_sugerido FLOAT DEFAULT 0"),
        ("ALTER TABLE recetas_producto ADD COLUMN precio_venta_sugerido FLOAT DEFAULT 0"),
        ("ALTER TABLE recetas_producto ADD COLUMN IF NOT EXISTS costo_calculado FLOAT DEFAULT 0"),
        ("ALTER TABLE recetas_producto ADD COLUMN costo_calculado FLOAT DEFAULT 0"),
        # es_demo — flag para datos de demostración
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE clientes ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE productos ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE materias_primas ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE proveedores ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE recetas_producto ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE recetas_producto ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE cotizaciones ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ventas ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE gastos_operativos ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE tareas ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE notas ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE eventos ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE eventos ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE empleados ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE servicios ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE servicios ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        # Historial de precios y cotizaciones
        ("CREATE TABLE IF NOT EXISTS historial_precios (id SERIAL PRIMARY KEY, producto_id INTEGER NOT NULL REFERENCES productos(id), precio_anterior FLOAT DEFAULT 0, precio_nuevo FLOAT DEFAULT 0, origen VARCHAR(100), usuario_id INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS historial_cotizaciones (id SERIAL PRIMARY KEY, cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id), cambios TEXT, usuario_id INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        # Dimensiones de la caja final en empaques
        ("ALTER TABLE empaques_secundarios ADD COLUMN IF NOT EXISTS ancho_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN ancho_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN IF NOT EXISTS largo_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN largo_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN IF NOT EXISTS alto_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN alto_caja FLOAT DEFAULT 0"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE marcas_producto ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE marcas_producto ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE documentos_legales ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE compras_materia ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE contactos_cliente ADD COLUMN IF NOT EXISTS es_demo BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE contactos_cliente ADD COLUMN es_demo BOOLEAN DEFAULT FALSE"),
        # v36 — OrdenCompra: campos flujo OC ↔ contable
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS monto_pagado FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_compra ADD COLUMN monto_pagado FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS estado_recepcion VARCHAR(30) DEFAULT 'pendiente'"),
        ("ALTER TABLE ordenes_compra ADD COLUMN estado_recepcion VARCHAR(30) DEFAULT 'pendiente'"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS cantidad_recibida FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_compra ADD COLUMN cantidad_recibida FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS tiene_problema_calidad BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN tiene_problema_calidad BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS venta_origen_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE ordenes_compra ADD COLUMN venta_origen_id INTEGER REFERENCES ventas(id)"),
        # v36 — CompraMateria: vincular a OC y recepcion
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS orden_compra_item_id INTEGER REFERENCES ordenes_compra_items(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN orden_compra_item_id INTEGER REFERENCES ordenes_compra_items(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS estado_recepcion VARCHAR(30) DEFAULT 'solicitado'"),
        ("ALTER TABLE compras_materia ADD COLUMN estado_recepcion VARCHAR(30) DEFAULT 'solicitado'"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS cantidad_recibida FLOAT DEFAULT 0"),
        ("ALTER TABLE compras_materia ADD COLUMN cantidad_recibida FLOAT DEFAULT 0"),
        # v36 — AsientoContable: estado de pago
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS estado_pago VARCHAR(20) DEFAULT 'pendiente'"),
        ("ALTER TABLE asientos_contables ADD COLUMN estado_pago VARCHAR(20) DEFAULT 'pendiente'"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS monto_pagado FLOAT DEFAULT 0"),
        ("ALTER TABLE asientos_contables ADD COLUMN monto_pagado FLOAT DEFAULT 0"),
        # v36 — Venta: monto anticipo recibido real
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS monto_anticipo_recibido FLOAT DEFAULT 0"),
        ("ALTER TABLE ventas ADD COLUMN monto_anticipo_recibido FLOAT DEFAULT 0"),
        # v36 — Tarea: vincular a OC/venta + categoria
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE tareas ADD COLUMN orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE tareas ADD COLUMN venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS categoria VARCHAR(50)"),
        ("ALTER TABLE tareas ADD COLUMN categoria VARCHAR(50)"),
        # v36 — Nota: vincular a entidades + tipos
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE notas ADD COLUMN orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE notas ADD COLUMN venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS proveedor_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE notas ADD COLUMN proveedor_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS tipo_nota VARCHAR(30) DEFAULT 'nota'"),
        ("ALTER TABLE notas ADD COLUMN tipo_nota VARCHAR(30) DEFAULT 'nota'"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS estado_nota VARCHAR(20) DEFAULT 'abierta'"),
        ("ALTER TABLE notas ADD COLUMN estado_nota VARCHAR(20) DEFAULT 'abierta'"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS prioridad VARCHAR(10) DEFAULT 'normal'"),
        ("ALTER TABLE notas ADD COLUMN prioridad VARCHAR(10) DEFAULT 'normal'"),
        # v36 — User: workspace tabs
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace_tabs TEXT DEFAULT '[]'"),
        ("ALTER TABLE users ADD COLUMN workspace_tabs TEXT DEFAULT '[]'"),
        # v37 — Aprobaciones vinculadas a entidades
        ("ALTER TABLE aprobaciones ADD COLUMN IF NOT EXISTS orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN orden_compra_id INTEGER REFERENCES ordenes_compra(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN IF NOT EXISTS venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN venta_id INTEGER REFERENCES ventas(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN IF NOT EXISTS cotizacion_id INTEGER REFERENCES cotizaciones(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN cotizacion_id INTEGER REFERENCES cotizaciones(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN IF NOT EXISTS asiento_id INTEGER REFERENCES asientos_contables(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN asiento_id INTEGER REFERENCES asientos_contables(id)"),
        # v39 — ConfigEmpresa info legal completa
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS representante_legal VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN representante_legal VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS representante_cedula VARCHAR(30)"),
        ("ALTER TABLE config_empresa ADD COLUMN representante_cedula VARCHAR(30)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS representante_cargo VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN representante_cargo VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS tipo_sociedad VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN tipo_sociedad VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS matricula_mercantil VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN matricula_mercantil VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS camara_comercio VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN camara_comercio VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS regimen_tributario VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN regimen_tributario VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS actividad_economica VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN actividad_economica VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS contador_nombre VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN contador_nombre VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS contador_tarjeta VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN contador_tarjeta VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS revisor_fiscal VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN revisor_fiscal VARCHAR(200)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS revisor_tarjeta VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN revisor_tarjeta VARCHAR(50)"),
        # v39 — MovimientoInventario table
        ("CREATE TABLE IF NOT EXISTS movimientos_inventario (id SERIAL PRIMARY KEY, producto_id INTEGER REFERENCES productos(id), materia_prima_id INTEGER REFERENCES materias_primas(id), tipo VARCHAR(30) NOT NULL, cantidad FLOAT DEFAULT 0, stock_anterior FLOAT DEFAULT 0, stock_posterior FLOAT DEFAULT 0, referencia VARCHAR(200), usuario_id INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS movimientos_inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, producto_id INTEGER REFERENCES productos(id), materia_prima_id INTEGER REFERENCES materias_primas(id), tipo VARCHAR(30) NOT NULL, cantidad FLOAT DEFAULT 0, stock_anterior FLOAT DEFAULT 0, stock_posterior FLOAT DEFAULT 0, referencia VARCHAR(200), usuario_id INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        # v39 — Proveedor evaluacion + soft delete
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS score_calidad FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN score_calidad FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS score_entrega FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN score_entrega FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS score_precio FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN score_precio FLOAT DEFAULT 5.0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS total_oc INTEGER DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN total_oc INTEGER DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS total_rechazos INTEGER DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN total_rechazos INTEGER DEFAULT 0"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP"),
        ("ALTER TABLE proveedores ADD COLUMN deleted_at TIMESTAMP"),
        # v38 — Venta: transportista y enviado
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS transportista_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE ventas ADD COLUMN transportista_id INTEGER REFERENCES proveedores(id)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS enviado_en TIMESTAMP"),
        ("ALTER TABLE ventas ADD COLUMN enviado_en TIMESTAMP"),
        # v37 — GastoOperativo: estado de pago
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS estado_pago VARCHAR(20) DEFAULT 'pendiente'"),
        ("ALTER TABLE gastos_operativos ADD COLUMN estado_pago VARCHAR(20) DEFAULT 'pendiente'"),
        # v37 — Bloqueo por aprobacion en OC y Ventas
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS pendiente_aprobacion BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ordenes_compra ADD COLUMN pendiente_aprobacion BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS pendiente_aprobacion BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE ventas ADD COLUMN pendiente_aprobacion BOOLEAN DEFAULT FALSE"),
        # v40 — Bidirectional payment tracking
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS estado_cliente_pago VARCHAR(30) DEFAULT 'pendiente'"),
        ("ALTER TABLE ventas ADD COLUMN estado_cliente_pago VARCHAR(30) DEFAULT 'pendiente'"),
        # v40 — DocumentoLegal: firma digital portal
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_empresa_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_empresa_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_empresa_por VARCHAR(200)"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_empresa_por VARCHAR(200)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_empresa_en TIMESTAMP"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_empresa_en TIMESTAMP"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_portal_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_portal_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_portal_por VARCHAR(200)"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_portal_por VARCHAR(200)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS firma_portal_en TIMESTAMP"),
        ("ALTER TABLE documentos_legales ADD COLUMN firma_portal_en TIMESTAMP"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS requiere_firma_portal BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE documentos_legales ADD COLUMN requiere_firma_portal BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS nomina_params TEXT"),
        ("ALTER TABLE config_empresa ADD COLUMN nomina_params TEXT"),
        # v41 — EmpaqueSecundario: nombre del empaque
        ("ALTER TABLE empaques_secundarios ADD COLUMN IF NOT EXISTS nombre VARCHAR(100) DEFAULT 'Caja'"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN nombre VARCHAR(100) DEFAULT 'Caja'"),
        # v41 — RecetaItem: rendimiento para empaques
        ("ALTER TABLE receta_items ADD COLUMN IF NOT EXISTS rendimiento FLOAT DEFAULT 1"),
        ("ALTER TABLE receta_items ADD COLUMN rendimiento FLOAT DEFAULT 1"),
        # v41 — OrdenProduccion: operario y merma
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS operario_id INTEGER REFERENCES empleados(id)"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN operario_id INTEGER REFERENCES empleados(id)"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS merma FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN merma FLOAT DEFAULT 0"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS merma_motivo VARCHAR(200)"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN merma_motivo VARCHAR(200)"),
        # v41 — Tracking envio
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS guia_transporte VARCHAR(100)"),
        ("ALTER TABLE ventas ADD COLUMN guia_transporte VARCHAR(100)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS estado_envio VARCHAR(30) DEFAULT 'pendiente'"),
        ("ALTER TABLE ventas ADD COLUMN estado_envio VARCHAR(30) DEFAULT 'pendiente'"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS selfie_empresa_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN selfie_empresa_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS selfie_portal_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN selfie_portal_data TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS contenido_html TEXT"),
        ("ALTER TABLE documentos_legales ADD COLUMN contenido_html TEXT"),
        # v42 — Empleado: tipo de sangre y contacto de emergencia
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS tipo_sangre VARCHAR(10)"),
        ("ALTER TABLE empleados ADD COLUMN tipo_sangre VARCHAR(10)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS contacto_emergencia_nombre VARCHAR(120)"),
        ("ALTER TABLE empleados ADD COLUMN contacto_emergencia_nombre VARCHAR(120)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS contacto_emergencia_telefono VARCHAR(30)"),
        ("ALTER TABLE empleados ADD COLUMN contacto_emergencia_telefono VARCHAR(30)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS contacto_emergencia_parentesco VARCHAR(50)"),
        ("ALTER TABLE empleados ADD COLUMN contacto_emergencia_parentesco VARCHAR(50)"),
        # v42b — User: roles multiples asignados
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS roles_asignados TEXT DEFAULT '[]'"),
        ("ALTER TABLE users ADD COLUMN roles_asignados TEXT DEFAULT '[]'"),
        # v42c — Empleado: EPS, caja de compensacion, fondo de pensiones
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS eps VARCHAR(100)"),
        ("ALTER TABLE empleados ADD COLUMN eps VARCHAR(100)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS caja_compensacion VARCHAR(100)"),
        ("ALTER TABLE empleados ADD COLUMN caja_compensacion VARCHAR(100)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS fondo_pensiones VARCHAR(100)"),
        ("ALTER TABLE empleados ADD COLUMN fondo_pensiones VARCHAR(100)"),
        # Client tier segmentation
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS tier VARCHAR(20) DEFAULT 'standard'"),
        ("ALTER TABLE clientes ADD COLUMN tier VARCHAR(20) DEFAULT 'standard'"),
        # DIAN — facturación electrónica (schema prep)
        # Venta: campos factura electrónica
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS numero_factura VARCHAR(30)"),
        ("ALTER TABLE ventas ADD COLUMN numero_factura VARCHAR(30)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS cufe VARCHAR(200)"),
        ("ALTER TABLE ventas ADD COLUMN cufe VARCHAR(200)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS estado_dian VARCHAR(20)"),
        ("ALTER TABLE ventas ADD COLUMN estado_dian VARCHAR(20)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS xml_factura TEXT"),
        ("ALTER TABLE ventas ADD COLUMN xml_factura TEXT"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS medio_pago VARCHAR(10) DEFAULT '10'"),
        ("ALTER TABLE ventas ADD COLUMN medio_pago VARCHAR(10) DEFAULT '10'"),
        # Cliente: datos tributarios DIAN
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(10) DEFAULT 'NIT'"),
        ("ALTER TABLE clientes ADD COLUMN tipo_documento VARCHAR(10) DEFAULT 'NIT'"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS digito_verificacion VARCHAR(1)"),
        ("ALTER TABLE clientes ADD COLUMN digito_verificacion VARCHAR(1)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS regimen_fiscal VARCHAR(50)"),
        ("ALTER TABLE clientes ADD COLUMN regimen_fiscal VARCHAR(50)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS municipio_dane VARCHAR(10)"),
        ("ALTER TABLE clientes ADD COLUMN municipio_dane VARCHAR(10)"),
        # ConfigEmpresa: resolución de facturación DIAN
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS resolucion_facturacion VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN resolucion_facturacion VARCHAR(50)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS prefijo_factura VARCHAR(10)"),
        ("ALTER TABLE config_empresa ADD COLUMN prefijo_factura VARCHAR(10)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS rango_desde INTEGER"),
        ("ALTER TABLE config_empresa ADD COLUMN rango_desde INTEGER"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS rango_hasta INTEGER"),
        ("ALTER TABLE config_empresa ADD COLUMN rango_hasta INTEGER"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS consecutivo_actual INTEGER DEFAULT 0"),
        ("ALTER TABLE config_empresa ADD COLUMN consecutivo_actual INTEGER DEFAULT 0"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS ambiente_dian VARCHAR(20) DEFAULT 'habilitacion'"),
        ("ALTER TABLE config_empresa ADD COLUMN ambiente_dian VARCHAR(20) DEFAULT 'habilitacion'"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS software_id_dian VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN software_id_dian VARCHAR(100)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS pin_dian VARCHAR(10)"),
        ("ALTER TABLE config_empresa ADD COLUMN pin_dian VARCHAR(10)"),
        # Producto: código UNSPSC para DIAN
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS codigo_unspsc VARCHAR(20)"),
        ("ALTER TABLE productos ADD COLUMN codigo_unspsc VARCHAR(20)"),
        # v43 — Performance indices for frequently queried columns
        ("CREATE INDEX IF NOT EXISTS idx_ventas_estado ON ventas(estado)"),
        ("CREATE INDEX IF NOT EXISTS idx_ventas_creado_en ON ventas(creado_en)"),
        ("CREATE INDEX IF NOT EXISTS idx_ordenes_compra_estado ON ordenes_compra(estado)"),
        ("CREATE INDEX IF NOT EXISTS idx_tareas_estado ON tareas(estado)"),
        ("CREATE INDEX IF NOT EXISTS idx_tareas_asignado_a ON tareas(asignado_a)"),
        ("CREATE INDEX IF NOT EXISTS idx_empleados_estado ON empleados(estado)"),
        ("CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario_id ON notificaciones(usuario_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_notificaciones_leida ON notificaciones(leida)"),
        ("CREATE INDEX IF NOT EXISTS idx_actividades_creado_en ON actividades(creado_en)"),
        # ══════════════════════════════════════════════════
        # MULTI-TENANCY — Phase 1
        # ══════════════════════════════════════════════════
        # User: company_id default
        ("ALTER TABLE users ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE users ADD COLUMN company_id INTEGER REFERENCES companies(id)"),
        # ConfigEmpresa: company_id
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE config_empresa ADD COLUMN company_id INTEGER REFERENCES companies(id)"),
        # Indices
        ("CREATE INDEX IF NOT EXISTS idx_user_companies_user ON user_companies(user_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_user_companies_company ON user_companies(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_users_company ON users(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_config_empresa_company ON config_empresa(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_company_rel_from ON company_relationships(company_from_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_company_rel_to ON company_relationships(company_to_id)"),
        # Multi-tenancy Phase 2b: Company max_users + es_principal
        ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS max_users INTEGER DEFAULT 3"),
        ("ALTER TABLE companies ADD COLUMN max_users INTEGER DEFAULT 3"),
        ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS es_principal BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE companies ADD COLUMN es_principal BOOLEAN DEFAULT FALSE"),
        ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(10) DEFAULT 'NIT'"),
        ("ALTER TABLE companies ADD COLUMN tipo_documento VARCHAR(10) DEFAULT 'NIT'"),
        # ══════════════════════════════════════════════════
        # MULTI-TENANCY — Phase 2: company_id on all tables
        # ══════════════════════════════════════════════════
        ("ALTER TABLE contactos_cliente ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE ordenes_compra ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE proveedores ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE aprobaciones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE tareas ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE productos ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE compras_materia ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE cotizaciones_proveedor ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE cotizaciones_granel ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE documentos_legales ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE cuentas_puc ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE asientos_contables ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE movimientos_bancarios ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE notas_contables ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE reglas_tributarias ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE movimientos_inventario ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE gastos_operativos ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE notas ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE actividades ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE eventos ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE lotes_producto ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE materias_primas ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE lotes_materia_prima ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE recetas_producto ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE reservas_produccion ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE ordenes_produccion ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE comisiones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE incapacidades ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE vacaciones_tomadas ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE requisiciones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE notificaciones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE empleados ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE horas_extra ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE pre_cotizaciones ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE servicios ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        ("ALTER TABLE empaques_secundarios ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id)"),
        # Indices for company_id
        ("CREATE INDEX IF NOT EXISTS idx_clientes_company ON clientes(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_ventas_company ON ventas(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_ordenes_compra_company ON ordenes_compra(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_proveedores_company ON proveedores(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_productos_company ON productos(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_tareas_company ON tareas(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_asientos_contables_company ON asientos_contables(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_gastos_operativos_company ON gastos_operativos(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_empleados_company ON empleados(company_id)"),
        ("CREATE INDEX IF NOT EXISTS idx_cotizaciones_company ON cotizaciones(company_id)"),
        # ── Suscripciones y datos bancarios empresa ──
        ("CREATE TABLE IF NOT EXISTS suscripciones (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id), plan VARCHAR(20) NOT NULL, periodo VARCHAR(10) DEFAULT 'mensual', usuarios_extra INTEGER DEFAULT 0, monto_mensual FLOAT DEFAULT 0, monto_cobrado FLOAT DEFAULT 0, estado VARCHAR(20) DEFAULT 'pendiente', fecha_inicio DATE, fecha_proximo_pago DATE, fecha_vencimiento DATE, asiento_id INTEGER REFERENCES asientos_contables(id), recordatorio_enviado BOOLEAN DEFAULT FALSE, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP, creado_por INTEGER)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS banco_nombre VARCHAR(120)"),
        ("ALTER TABLE config_empresa ADD COLUMN banco_nombre VARCHAR(120)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS banco_tipo VARCHAR(40)"),
        ("ALTER TABLE config_empresa ADD COLUMN banco_tipo VARCHAR(40)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS banco_cuenta VARCHAR(80)"),
        ("ALTER TABLE config_empresa ADD COLUMN banco_cuenta VARCHAR(80)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS banco_titular VARCHAR(120)"),
        ("ALTER TABLE config_empresa ADD COLUMN banco_titular VARCHAR(120)"),
        ("ALTER TABLE config_empresa ADD COLUMN IF NOT EXISTS banco_nit VARCHAR(30)"),
        ("ALTER TABLE config_empresa ADD COLUMN banco_nit VARCHAR(30)"),
        # ── Foro Somos Evore ──
        ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS industria VARCHAR(100)"),
        ("ALTER TABLE companies ADD COLUMN industria VARCHAR(100)"),
        ("CREATE TABLE IF NOT EXISTS foro_publicaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id), user_id INTEGER NOT NULL REFERENCES users(id), tipo VARCHAR(20) DEFAULT 'producto', titulo VARCHAR(200) NOT NULL, descripcion TEXT NOT NULL, industria VARCHAR(100), imagen_url VARCHAR(500), precio_referencia FLOAT, unidad VARCHAR(50), activo BOOLEAN DEFAULT TRUE, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        ("CREATE TABLE IF NOT EXISTS foro_valoraciones (id INTEGER PRIMARY KEY AUTOINCREMENT, proveedor_company_id INTEGER NOT NULL REFERENCES companies(id), cliente_company_id INTEGER NOT NULL REFERENCES companies(id), cliente_user_id INTEGER NOT NULL REFERENCES users(id), publicacion_id INTEGER REFERENCES foro_publicaciones(id), estrellas INTEGER NOT NULL, comentario TEXT, estado VARCHAR(20) DEFAULT 'activa', creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        ("CREATE TABLE IF NOT EXISTS foro_apelaciones (id INTEGER PRIMARY KEY AUTOINCREMENT, valoracion_id INTEGER NOT NULL REFERENCES foro_valoraciones(id), solicitado_por INTEGER NOT NULL REFERENCES users(id), motivo TEXT NOT NULL, estado VARCHAR(30) DEFAULT 'pendiente', notas_admin TEXT, resuelto_por INTEGER REFERENCES users(id), resuelto_en TIMESTAMP, creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        ("ALTER TABLE foro_publicaciones ADD COLUMN IF NOT EXISTS modalidad VARCHAR(10) DEFAULT 'vendo'"),
        ("ALTER TABLE foro_publicaciones ADD COLUMN modalidad VARCHAR(10) DEFAULT 'vendo'"),
        # ── Foro Banners (marketplace ads) ──
        ("CREATE TABLE IF NOT EXISTS foro_banners (id SERIAL PRIMARY KEY, titulo VARCHAR(200) NOT NULL, descripcion TEXT, imagen_url VARCHAR(500), link_url VARCHAR(500), industria VARCHAR(100), tipo VARCHAR(20) DEFAULT 'evore', activo BOOLEAN DEFAULT TRUE, orden INTEGER DEFAULT 0, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT NOW())"),
        ("CREATE TABLE IF NOT EXISTS foro_banners (id INTEGER PRIMARY KEY AUTOINCREMENT, titulo VARCHAR(200) NOT NULL, descripcion TEXT, imagen_url VARCHAR(500), link_url VARCHAR(500), industria VARCHAR(100), tipo VARCHAR(20) DEFAULT 'evore', activo BOOLEAN DEFAULT TRUE, orden INTEGER DEFAULT 0, creado_por INTEGER REFERENCES users(id), creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"),
        # ── Cotizacion: iva_incluido ──
        ("ALTER TABLE cotizaciones ADD COLUMN IF NOT EXISTS iva_incluido BOOLEAN DEFAULT TRUE"),
        ("ALTER TABLE cotizaciones ADD COLUMN iva_incluido BOOLEAN DEFAULT TRUE"),
        # ── Capacitacion: practice fields ──
        ("ALTER TABLE cap_lecciones ADD COLUMN IF NOT EXISTS pasos TEXT DEFAULT '[]'"),
        ("ALTER TABLE cap_lecciones ADD COLUMN pasos TEXT DEFAULT '[]'"),
        ("ALTER TABLE cap_lecciones ADD COLUMN IF NOT EXISTS ruta_practica VARCHAR(100)"),
        ("ALTER TABLE cap_lecciones ADD COLUMN ruta_practica VARCHAR(100)"),
    ]
    # Execute ALL migrations individually with rollback on each failure
    # This prevents one failed migration from aborting the entire transaction
    for sql in migrations:
        try:
            conn.execute(db.text(sql))
            conn.commit()
        except Exception:
            try: conn.rollback()
            except Exception: pass
    # ── Multi-tenancy: assign existing data to default company ──
    try:
        result = conn.execute(db.text("SELECT id FROM companies ORDER BY id LIMIT 1"))
        row = result.fetchone()
        if row:
            default_cid = row[0]
            tables_with_company = [
                'clientes','proveedores','ventas','ordenes_compra','productos',
                'tareas','cotizaciones','asientos_contables','gastos_operativos',
                'empleados','notas','actividades','eventos','documentos_legales',
                'compras_materia','cotizaciones_proveedor','cotizaciones_granel',
                'reglas_tributarias','materias_primas','recetas_producto',
                'ordenes_produccion','reservas_produccion','lotes_producto',
                'lotes_materia_prima','notificaciones','comisiones','requisiciones',
                'aprobaciones','horas_extra','incapacidades','vacaciones_tomadas',
                'pre_cotizaciones','servicios','empaques_secundarios','contactos_cliente',
                'cuentas_puc','movimientos_bancarios','notas_contables','movimientos_inventario',
            ]
            for t in tables_with_company:
                try:
                    conn.execute(db.text(f"UPDATE {t} SET company_id = :cid WHERE company_id IS NULL"), {'cid': default_cid})
                except Exception:
                    pass
            conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass

def init_db():
    """Create tables and run migrations. Call inside app context."""
    db.create_all()
    try:
        with db.engine.connect() as conn:
            _migrate(conn)
    except Exception as em:
        import logging
        logging.warning(f'Migrate error (non-critical): {em}')
    import os, secrets, logging
    from company_config import COMPANY
    _admin_email = os.environ.get('ADMIN_EMAIL', COMPANY['admin_email'])
    # ── Multi-tenancy: ensure default company exists ──
    default_company = Company.query.first()
    if not default_company:
        default_company = Company(
            nombre=COMPANY['name'],
            slug=COMPANY['name'].lower().replace(' ', '-'),
            nit='',
            plan='pro',
            max_users=999,
            activo=True,
            es_principal=True,
            creado_por=None
        )
        db.session.add(default_company)
        db.session.commit()
        logging.info(f'Default company created: {default_company.nombre} (id={default_company.id})')
    # Ensure first company is always marked as principal
    if default_company and not default_company.es_principal:
        default_company.es_principal = True
        default_company.max_users = 999
        db.session.commit()
        logging.info(f'Company {default_company.nombre} marked as es_principal=True')
    # ── Assign existing users to default company if not assigned ──
    unassigned = User.query.filter(User.company_id.is_(None)).all()
    if unassigned:
        for u in unassigned:
            u.company_id = default_company.id
            # Also create UserCompany record if missing
            existing_uc = UserCompany.query.filter_by(user_id=u.id, company_id=default_company.id).first()
            if not existing_uc:
                db.session.add(UserCompany(
                    user_id=u.id, company_id=default_company.id,
                    rol=u.rol, roles_asignados=u.roles_asignados or '[]',
                    modulos_permitidos=u.modulos_permitidos or '[]'
                ))
        db.session.commit()
        logging.info(f'Assigned {len(unassigned)} users to default company')
    # ── Fix orphan records: set company_id on rows that have NULL ──
    _tables_with_company_id = [
        'clientes', 'proveedores', 'ventas', 'productos', 'materias_primas',
        'empleados', 'ordenes_compra', 'cotizaciones', 'gastos_operativos',
        'servicios', 'asientos_contables', 'ordenes_produccion', 'recetas_producto',
        'reglas_tributarias', 'tareas', 'eventos', 'notas', 'notificaciones',
        'actividades', 'movimientos_inventario', 'movimientos_bancarios',
        'lotes_materia_prima', 'lotes_producto', 'comisiones', 'documentos_legales',
        'compras_materia', 'cotizaciones_proveedor', 'requisiciones', 'aprobaciones',
        'empaques_secundarios', 'pre_cotizaciones',
    ]
    try:
        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        existing = set(inspector.get_table_names())
        fixed = 0
        for tbl in _tables_with_company_id:
            if tbl not in existing:
                continue
            cols = [c['name'] for c in inspector.get_columns(tbl)]
            if 'company_id' not in cols:
                continue
            r = db.session.execute(db.text(
                f"UPDATE {tbl} SET company_id = :cid WHERE company_id IS NULL"
            ), {'cid': default_company.id})
            if r.rowcount:
                fixed += r.rowcount
        if fixed:
            db.session.commit()
            logging.info(f'Fixed {fixed} orphan rows (set company_id={default_company.id})')
    except Exception as e:
        db.session.rollback()
        logging.warning(f'Fix orphan company_id: {e}')

    # ── Create admin user if not exists ──
    if not User.query.filter_by(email=_admin_email).first():
        _admin_pass = os.environ.get('ADMIN_PASSWORD')
        if not _admin_pass:
            _admin_pass = secrets.token_urlsafe(14)
            logging.warning('ADMIN AUTO-GENERATED PASSWORD (save this!): %s', _admin_pass)
        admin = User(nombre='Administrador', email=_admin_email, rol='admin', company_id=default_company.id)
        admin.set_password(_admin_pass)
        db.session.add(admin)
        db.session.flush()
        db.session.add(UserCompany(user_id=admin.id, company_id=default_company.id, rol='admin'))
        db.session.commit()
    # ── Link ConfigEmpresa to default company ──
    config = ConfigEmpresa.query.first()
    if not config:
        config = ConfigEmpresa(
            nombre=COMPANY['name'],
            email=COMPANY['default_email'],
            sitio_web=COMPANY['default_website'],
            company_id=default_company.id
        )
        db.session.add(config)
        db.session.commit()
    elif not config.company_id:
        config.company_id = default_company.id
        db.session.commit()
    # Sembrar catálogo contable según país
    if COMPANY['chart_of_accounts'] == 'co_puc':
        _seed_puc()
    elif COMPANY['chart_of_accounts'] == 'mx_cuc':
        _seed_cuc_mx()
    # Auto-generar SKU para productos que no tengan
    _fix_missing_skus()
    # Sembrar cursos de capacitacion
    _seed_capacitacion()
    logging.info(f'App iniciada para: {COMPANY["name"]} ({COMPANY["country"]})')


def _fix_missing_skus():
    """Genera SKU para productos que tengan None o vacío."""
    try:
        # Use raw SQL to bypass auto-filter during init
        result = db.session.execute(db.text(
            "SELECT id, nombre FROM productos WHERE sku IS NULL OR sku = 'None' OR sku = ''"
        )).fetchall()
        if not result:
            return
        for row in result:
            sku = _generar_sku(row[1])
            db.session.execute(db.text("UPDATE productos SET sku = :sku WHERE id = :id"), {'sku': sku, 'id': row[0]})
        db.session.commit()
    except Exception as e:
        logging.warning(f'_fix_missing_skus: {e}')
        try: db.session.rollback()
        except Exception: pass




def _seed_puc():
    """Siembra el Plan Único de Cuentas mínimo para empresa manufacturera colombiana."""
    import logging
    try:
        count = db.session.execute(db.text("SELECT COUNT(*) FROM cuentas_puc")).scalar()
        if count and count > 0:
            return
    except Exception:
        return

    logging.info('Sembrando PUC colombiano...')
    # (codigo, nombre, nivel, naturaleza, tipo, padre, acepta_mov)
    cuentas = [
        # ═══ CLASE 1: ACTIVOS ═══
        ('1',     'Activo',                          1, 'debito', 'activo',      None, False),
        ('11',    'Disponible',                      2, 'debito', 'activo',      '1',  False),
        ('1105',  'Caja',                            3, 'debito', 'activo',      '11', False),
        ('110505','Caja general',                    5, 'debito', 'activo',      '1105', True),
        ('110510','Cajas menores',                   5, 'debito', 'activo',      '1105', True),
        ('1110',  'Bancos',                          3, 'debito', 'activo',      '11', False),
        ('111005','Moneda nacional',                 5, 'debito', 'activo',      '1110', True),
        ('13',    'Deudores',                        2, 'debito', 'activo',      '1',  False),
        ('1305',  'Clientes',                        3, 'debito', 'activo',      '13', False),
        ('130505','Nacionales',                      5, 'debito', 'activo',      '1305', True),
        ('1355',  'Anticipos y avances',             3, 'debito', 'activo',      '13', True),
        ('1365',  'Cuentas por cobrar a trabajadores',3,'debito', 'activo',      '13', True),
        ('1380',  'Deudores varios',                 3, 'debito', 'activo',      '13', True),
        ('14',    'Inventarios',                     2, 'debito', 'activo',      '1',  False),
        ('1405',  'Materias primas',                 3, 'debito', 'activo',      '14', True),
        ('1410',  'Productos en proceso',            3, 'debito', 'activo',      '14', True),
        ('1430',  'Productos terminados',            3, 'debito', 'activo',      '14', True),
        ('1435',  'Mercancias no fabricadas',        3, 'debito', 'activo',      '14', True),
        ('1465',  'Envases y empaques',              3, 'debito', 'activo',      '14', True),
        ('15',    'Propiedad planta y equipo',       2, 'debito', 'activo',      '1',  False),
        ('1520',  'Maquinaria y equipo',             3, 'debito', 'activo',      '15', True),
        ('1524',  'Equipo de oficina',               3, 'debito', 'activo',      '15', True),
        ('1528',  'Equipo de computacion',           3, 'debito', 'activo',      '15', True),
        ('1540',  'Equipo de transporte',            3, 'debito', 'activo',      '15', True),
        ('1592',  'Depreciacion acumulada',          3, 'credito','activo',      '15', True),
        # ═══ CLASE 2: PASIVOS ═══
        ('2',     'Pasivo',                          1, 'credito','pasivo',      None, False),
        ('22',    'Proveedores',                     2, 'credito','pasivo',      '2',  False),
        ('2205',  'Proveedores nacionales',          3, 'credito','pasivo',      '22', False),
        ('220505','Nacionales',                      5, 'credito','pasivo',      '2205', True),
        ('23',    'Cuentas por pagar',               2, 'credito','pasivo',      '2',  False),
        ('2335',  'Costos y gastos por pagar',       3, 'credito','pasivo',      '23', True),
        ('2365',  'Retencion en la fuente',          3, 'credito','pasivo',      '23', False),
        ('236505','Salarios y pagos laborales',      5, 'credito','pasivo',      '2365', True),
        ('236540','Compras',                         5, 'credito','pasivo',      '2365', True),
        ('2367',  'Impuesto a las ventas retenido',  3, 'credito','pasivo',      '23', True),
        ('2368',  'Impuesto industria y comercio ret',3,'credito','pasivo',      '23', True),
        ('2370',  'Retenciones y aportes de nomina', 3, 'credito','pasivo',      '23', True),
        ('2380',  'Acreedores varios',               3, 'credito','pasivo',      '23', True),
        ('24',    'Impuestos gravamenes y tasas',    2, 'credito','pasivo',      '2',  False),
        ('2404',  'De renta y complementarios',      3, 'credito','pasivo',      '24', True),
        ('2408',  'IVA por pagar',                   3, 'credito','pasivo',      '24', False),
        ('240801','IVA generado en ventas',          5, 'credito','pasivo',      '2408', True),
        ('240802','IVA descontable en compras',      5, 'debito', 'pasivo',      '2408', True),
        ('25',    'Obligaciones laborales',          2, 'credito','pasivo',      '2',  False),
        ('2505',  'Salarios por pagar',              3, 'credito','pasivo',      '25', True),
        ('2510',  'Cesantias consolidadas',          3, 'credito','pasivo',      '25', True),
        ('2515',  'Intereses sobre cesantias',       3, 'credito','pasivo',      '25', True),
        ('2520',  'Prima de servicios',              3, 'credito','pasivo',      '25', True),
        ('2525',  'Vacaciones consolidadas',         3, 'credito','pasivo',      '25', True),
        # ═══ CLASE 3: PATRIMONIO ═══
        ('3',     'Patrimonio',                      1, 'credito','patrimonio',  None, False),
        ('31',    'Capital social',                  2, 'credito','patrimonio',  '3',  False),
        ('3105',  'Capital suscrito y pagado',       3, 'credito','patrimonio',  '31', True),
        ('3115',  'Aportes sociales',                3, 'credito','patrimonio',  '31', True),
        ('32',    'Superavit de capital',            2, 'credito','patrimonio',  '3',  False),
        ('3205',  'Reserva legal',                   3, 'credito','patrimonio',  '32', True),
        ('36',    'Resultados del ejercicio',        2, 'credito','patrimonio',  '3',  False),
        ('3605',  'Utilidad del ejercicio',          3, 'credito','patrimonio',  '36', True),
        ('3610',  'Perdida del ejercicio',           3, 'debito', 'patrimonio',  '36', True),
        # ═══ CLASE 4: INGRESOS ═══
        ('4',     'Ingresos',                        1, 'credito','ingreso',     None, False),
        ('41',    'Operacionales',                   2, 'credito','ingreso',     '4',  False),
        ('4135',  'Comercio al por mayor y menor',   3, 'credito','ingreso',     '41', True),
        ('4140',  'Servicios prestados',             3, 'credito','ingreso',     '41', True),
        ('4170',  'Devoluciones en ventas (DB)',      3, 'debito', 'ingreso',     '41', True),
        ('42',    'No operacionales',                2, 'credito','ingreso',     '4',  False),
        ('4210',  'Financieros',                     3, 'credito','ingreso',     '42', True),
        ('4295',  'Diversos',                        3, 'credito','ingreso',     '42', True),
        # ═══ CLASE 5: GASTOS ═══
        ('5',     'Gastos',                          1, 'debito', 'gasto',       None, False),
        ('51',    'Operacionales de administracion', 2, 'debito', 'gasto',       '5',  False),
        ('5105',  'Gastos de personal',              3, 'debito', 'gasto',       '51', False),
        ('510506','Sueldos',                         5, 'debito', 'gasto',       '5105', True),
        ('510527','Auxilio de transporte',           5, 'debito', 'gasto',       '5105', True),
        ('510530','Cesantias',                       5, 'debito', 'gasto',       '5105', True),
        ('510533','Intereses sobre cesantias',       5, 'debito', 'gasto',       '5105', True),
        ('510536','Prima de servicios',              5, 'debito', 'gasto',       '5105', True),
        ('510539','Vacaciones',                      5, 'debito', 'gasto',       '5105', True),
        ('510568','Aportes a ARL',                   5, 'debito', 'gasto',       '5105', True),
        ('510569','Aportes EPS empleador',           5, 'debito', 'gasto',       '5105', True),
        ('510570','Aportes pension empleador',       5, 'debito', 'gasto',       '5105', True),
        ('510572','Aportes caja compensacion',       5, 'debito', 'gasto',       '5105', True),
        ('5110',  'Honorarios',                      3, 'debito', 'gasto',       '51', True),
        ('5115',  'Impuestos',                       3, 'debito', 'gasto',       '51', True),
        ('5120',  'Arrendamientos',                  3, 'debito', 'gasto',       '51', True),
        ('5130',  'Seguros',                         3, 'debito', 'gasto',       '51', True),
        ('5135',  'Servicios',                       3, 'debito', 'gasto',       '51', False),
        ('513525','Acueducto y alcantarillado',      5, 'debito', 'gasto',       '5135', True),
        ('513530','Energia electrica',               5, 'debito', 'gasto',       '5135', True),
        ('513535','Telefono e internet',             5, 'debito', 'gasto',       '5135', True),
        ('5145',  'Mantenimiento y reparaciones',    3, 'debito', 'gasto',       '51', True),
        ('5155',  'Gastos de viaje',                 3, 'debito', 'gasto',       '51', True),
        ('5195',  'Diversos',                        3, 'debito', 'gasto',       '51', True),
        ('53',    'No operacionales',                2, 'debito', 'gasto',       '5',  False),
        ('5305',  'Financieros',                     3, 'debito', 'gasto',       '53', True),
        # ═══ CLASE 6: COSTOS DE VENTA ═══
        ('6',     'Costos de venta',                 1, 'debito', 'costo_venta', None, False),
        ('61',    'Costo de ventas y prestacion de servicios',2,'debito','costo_venta','6', False),
        ('6135',  'Comercio al por mayor y menor',   3, 'debito', 'costo_venta', '61', True),
        # ═══ CLASE 7: COSTOS DE PRODUCCION ═══
        ('7',     'Costos de produccion',            1, 'debito', 'costo_produccion', None, False),
        ('71',    'Materia prima',                   2, 'debito', 'costo_produccion', '7',  False),
        ('7105',  'Materia prima directa',           3, 'debito', 'costo_produccion', '71', True),
        ('72',    'Mano de obra directa',            2, 'debito', 'costo_produccion', '7',  False),
        ('7205',  'Mano de obra directa',            3, 'debito', 'costo_produccion', '72', True),
        ('73',    'Costos indirectos',               2, 'debito', 'costo_produccion', '7',  False),
        ('7305',  'Costos indirectos de fabricacion', 3,'debito', 'costo_produccion', '73', True),
    ]

    for codigo, nombre, nivel, naturaleza, tipo, padre, acepta in cuentas:
        db.session.add(CuentaPUC(
            codigo=codigo, nombre=nombre, nivel=nivel, naturaleza=naturaleza,
            tipo=tipo, padre_codigo=padre, acepta_mov=acepta, activo=True))

    try:
        db.session.commit()
        logging.info(f'PUC colombiano sembrado: {len(cuentas)} cuentas.')
    except Exception as e:
        db.session.rollback()
        logging.warning(f'Error sembrando PUC: {e}')


def _seed_cuc_mx():
    """Siembra el Catalogo de Cuentas minimo para empresa manufacturera mexicana."""
    import logging
    try:
        count = db.session.execute(db.text("SELECT COUNT(*) FROM cuentas_puc")).scalar()
        if count and count > 0:
            return
    except Exception:
        return
    logging.info('Sembrando CUC mexicano...')
    cuentas = [
        # Clase 1: Activos
        ('1',     'Activo',                      1, 'debito', 'activo', None, False),
        ('11',    'Efectivo y equivalentes',      2, 'debito', 'activo', '1', False),
        ('1101',  'Caja',                         3, 'debito', 'activo', '11', True),
        ('1102',  'Bancos',                       3, 'debito', 'activo', '11', True),
        ('12',    'Cuentas por cobrar',           2, 'debito', 'activo', '1', False),
        ('1201',  'Clientes',                     3, 'debito', 'activo', '12', True),
        ('1202',  'Anticipos a proveedores',      3, 'debito', 'activo', '12', True),
        ('1205',  'IVA acreditable',              3, 'debito', 'activo', '12', True),
        ('1206',  'ISR a favor',                  3, 'debito', 'activo', '12', True),
        ('13',    'Inventarios',                  2, 'debito', 'activo', '1', False),
        ('1301',  'Materia prima',                3, 'debito', 'activo', '13', True),
        ('1302',  'Produccion en proceso',        3, 'debito', 'activo', '13', True),
        ('1303',  'Producto terminado',           3, 'debito', 'activo', '13', True),
        ('1304',  'Envases y empaques',           3, 'debito', 'activo', '13', True),
        ('15',    'Activo fijo',                  2, 'debito', 'activo', '1', False),
        ('1501',  'Maquinaria y equipo',          3, 'debito', 'activo', '15', True),
        ('1502',  'Equipo de transporte',         3, 'debito', 'activo', '15', True),
        ('1503',  'Equipo de computo',            3, 'debito', 'activo', '15', True),
        ('1504',  'Mobiliario y equipo oficina',  3, 'debito', 'activo', '15', True),
        ('1590',  'Depreciacion acumulada',       3, 'credito','activo', '15', True),
        # Clase 2: Pasivos
        ('2',     'Pasivo',                       1, 'credito','pasivo', None, False),
        ('21',    'Proveedores',                  2, 'credito','pasivo', '2', False),
        ('2101',  'Proveedores nacionales',       3, 'credito','pasivo', '21', True),
        ('22',    'Impuestos por pagar',          2, 'credito','pasivo', '2', False),
        ('2201',  'IVA trasladado',               3, 'credito','pasivo', '22', True),
        ('2202',  'ISR retenido sueldos',         3, 'credito','pasivo', '22', True),
        ('2203',  'ISR por pagar',                3, 'credito','pasivo', '22', True),
        ('2204',  'IMSS por pagar',               3, 'credito','pasivo', '22', True),
        ('2205',  'INFONAVIT por pagar',          3, 'credito','pasivo', '22', True),
        ('2206',  'SAR/RCV por pagar',            3, 'credito','pasivo', '22', True),
        ('23',    'Acreedores diversos',          2, 'credito','pasivo', '2', False),
        ('2301',  'Acreedores diversos',          3, 'credito','pasivo', '23', True),
        ('24',    'Obligaciones laborales',       2, 'credito','pasivo', '2', False),
        ('2401',  'Sueldos por pagar',            3, 'credito','pasivo', '24', True),
        ('2402',  'Aguinaldo por pagar',          3, 'credito','pasivo', '24', True),
        ('2403',  'Vacaciones por pagar',         3, 'credito','pasivo', '24', True),
        ('2404',  'Prima vacacional por pagar',   3, 'credito','pasivo', '24', True),
        ('2405',  'PTU por pagar',                3, 'credito','pasivo', '24', True),
        # Clase 3: Capital contable
        ('3',     'Capital contable',             1, 'credito','patrimonio', None, False),
        ('31',    'Capital social',               2, 'credito','patrimonio', '3', False),
        ('3101',  'Capital social',               3, 'credito','patrimonio', '31', True),
        ('32',    'Resultados',                   2, 'credito','patrimonio', '3', False),
        ('3201',  'Utilidad del ejercicio',       3, 'credito','patrimonio', '32', True),
        ('3202',  'Perdida del ejercicio',        3, 'debito', 'patrimonio', '32', True),
        ('3203',  'Resultados acumulados',        3, 'credito','patrimonio', '32', True),
        # Clase 4: Ingresos
        ('4',     'Ingresos',                     1, 'credito','ingreso', None, False),
        ('41',    'Ingresos por ventas',          2, 'credito','ingreso', '4', False),
        ('4101',  'Ventas nacionales',            3, 'credito','ingreso', '41', True),
        ('4102',  'Servicios prestados',          3, 'credito','ingreso', '41', True),
        ('4103',  'Devoluciones sobre ventas',    3, 'debito', 'ingreso', '41', True),
        ('42',    'Otros ingresos',               2, 'credito','ingreso', '4', False),
        ('4201',  'Ingresos financieros',         3, 'credito','ingreso', '42', True),
        # Clase 5: Gastos
        ('5',     'Gastos de operacion',          1, 'debito', 'gasto', None, False),
        ('51',    'Gastos de administracion',     2, 'debito', 'gasto', '5', False),
        ('5101',  'Sueldos y salarios',           3, 'debito', 'gasto', '51', True),
        ('5102',  'Aguinaldo',                    3, 'debito', 'gasto', '51', True),
        ('5103',  'Prima vacacional',             3, 'debito', 'gasto', '51', True),
        ('5104',  'IMSS patron',                  3, 'debito', 'gasto', '51', True),
        ('5105',  'INFONAVIT',                    3, 'debito', 'gasto', '51', True),
        ('5106',  'SAR/RCV',                      3, 'debito', 'gasto', '51', True),
        ('5110',  'Honorarios',                   3, 'debito', 'gasto', '51', True),
        ('5115',  'Arrendamiento',                3, 'debito', 'gasto', '51', True),
        ('5120',  'Servicios (agua, luz, tel)',    3, 'debito', 'gasto', '51', True),
        ('5125',  'Mantenimiento',                3, 'debito', 'gasto', '51', True),
        ('5130',  'Seguros',                      3, 'debito', 'gasto', '51', True),
        ('5135',  'Fletes y transportes',         3, 'debito', 'gasto', '51', True),
        ('5190',  'Otros gastos',                 3, 'debito', 'gasto', '51', True),
        ('52',    'Gastos financieros',           2, 'debito', 'gasto', '5', False),
        ('5201',  'Intereses bancarios',          3, 'debito', 'gasto', '52', True),
        ('5202',  'Comisiones bancarias',         3, 'debito', 'gasto', '52', True),
        # Clase 6: Costos
        ('6',     'Costo de ventas',              1, 'debito', 'costo_venta', None, False),
        ('61',    'Costo de lo vendido',          2, 'debito', 'costo_venta', '6', False),
        ('6101',  'Costo de ventas',              3, 'debito', 'costo_venta', '61', True),
        # Clase 7: Costos de produccion
        ('7',     'Costos de produccion',         1, 'debito', 'costo_produccion', None, False),
        ('71',    'Materia prima consumida',      2, 'debito', 'costo_produccion', '7', False),
        ('7101',  'Materia prima directa',        3, 'debito', 'costo_produccion', '71', True),
        ('72',    'Mano de obra directa',         2, 'debito', 'costo_produccion', '7', False),
        ('7201',  'Sueldos produccion',           3, 'debito', 'costo_produccion', '72', True),
        ('73',    'Gastos indirectos fabricacion', 2,'debito', 'costo_produccion', '7', False),
        ('7301',  'CIF',                          3, 'debito', 'costo_produccion', '73', True),
    ]
    for codigo, nombre, nivel, naturaleza, tipo, padre, acepta in cuentas:
        db.session.add(CuentaPUC(
            codigo=codigo, nombre=nombre, nivel=nivel, naturaleza=naturaleza,
            tipo=tipo, padre_codigo=padre, acepta_mov=acepta, activo=True))
    try:
        db.session.commit()
        logging.info(f'CUC mexicano sembrado: {len(cuentas)} cuentas.')
    except Exception as e:
        db.session.rollback()
        logging.warning(f'Error sembrando CUC: {e}')


def _generar_sku(nombre_producto):
    """Genera SKU automático: 3 letras + 2 números (máx 5 chars)."""
    import re, random
    # Take first 3 consonants or letters from name
    clean = re.sub(r'[^A-Za-z]', '', nombre_producto.upper())
    # Remove vowels to get consonants, fallback to all letters
    consonants = re.sub(r'[AEIOU]', '', clean)
    if len(consonants) < 3:
        consonants = clean
    letters = consonants[:3].ljust(3, 'X')
    # Random 2 digits
    nums = f'{random.randint(10, 99)}'
    sku = letters + nums
    # Ensure uniqueness
    from models import Producto
    existing = Producto.query.filter_by(sku=sku).first()
    attempts = 0
    while existing and attempts < 50:
        nums = f'{random.randint(10, 99)}'
        sku = letters + nums
        existing = Producto.query.filter_by(sku=sku).first()
        attempts += 1
    return sku


def _seed_demo_data():
    """Crea datos demo completos con flujo integrado de manufactura."""
    import logging
    from datetime import date, timedelta

    try:
        from company_config import COMPANY
        _domain = COMPANY['default_email'].split('@')[1]
        tester_email = f'tester@{_domain}'
        tester = User.query.filter_by(email=tester_email).first()
        if not tester:
            tester = User(nombre='Tester Demo', email=tester_email, rol='tester')
            tester.set_password('tester123')
            db.session.add(tester); db.session.commit()
            logging.info(f'Usuario tester creado: {tester_email} / tester123')

        # Si ya hay datos demo, no sembrar de nuevo
        if Cliente.query.filter_by(es_demo=True).count() > 0:
            return
    except Exception as e:
        logging.warning(f'Seed check error: {e}')
        return

    uid = tester.id
    hoy = date.today()
    logging.info('Sembrando datos demo para tester...')

    # ── Director financiero demo ──
    df = User(nombre='Carlos Mendez', email=f'director@{_domain}', rol='director_financiero')
    df.set_password('director123')
    db.session.add(df)

    do = User(nombre='Laura Rios', email=f'operativo@{_domain}', rol='director_operativo')
    do.set_password('operativo123')
    db.session.add(do)

    vendedor = User(nombre='Andres Vargas', email=f'vendedor@{_domain}', rol='vendedor')
    vendedor.set_password('vendedor123')
    db.session.add(vendedor)

    produccion_user = User(nombre='Maria Torres', email=f'produccion@{_domain}', rol='produccion')
    produccion_user.set_password('produccion123')
    db.session.add(produccion_user)

    contador = User(nombre='Sofia Perez', email=f'contador@{_domain}', rol='contador')
    contador.set_password('contador123')
    db.session.add(contador)
    db.session.flush()

    # ── Proveedores ──
    prov1 = Proveedor(es_demo=True, nombre='Juan Ramirez', empresa='QuimiCol SAS', nit='900123456-1',
                      email='ventas@quimicol.co', telefono='3101234567', tipo='proveedor',
                      categoria='Quimicos', direccion='Cra 45 #26-85, Medellin', activo=True)
    prov2 = Proveedor(es_demo=True, nombre='Pedro Gomez', empresa='Envases del Valle', nit='900654321-2',
                      email='pedidos@envases.co', telefono='3209876543', tipo='proveedor',
                      categoria='Empaques', direccion='Cl 10 #4-20, Cali', activo=True)
    prov3 = Proveedor(es_demo=True, nombre='TransCarga Ltda', empresa='TransCarga Ltda', nit='800111222-3',
                      email='despachos@transcarga.co', telefono='3157778899', tipo='transportista',
                      categoria='Transporte', direccion='Zona Industrial, Bogota', activo=True)
    db.session.add_all([prov1, prov2, prov3]); db.session.flush()

    # ── Clientes ──
    c1 = Cliente(es_demo=True, nombre='Ana Lopez', empresa='Distribuidora Nacional SAS', nit='901234567-8',
                 estado_relacion='cliente_activo', dir_comercial='Cra 7 #32-16 Of. 401, Bogota',
                 dir_entrega='Bodega 5, Zona Franca Bogota', anticipo_pct=50, sales_manager_id=uid)
    c2 = Cliente(es_demo=True, nombre='Roberto Silva', empresa='Cadena FreshMart', nit='800987654-3',
                 estado_relacion='cliente_activo', dir_comercial='Av 68 #13-51, Bogota',
                 dir_entrega='CEDI FreshMart, Funza', anticipo_pct=60, sales_manager_id=uid)
    c3 = Cliente(es_demo=True, nombre='Patricia Herrera', empresa='NaturVida Ltda', nit='900555444-1',
                 estado_relacion='prospecto', dir_comercial='Cl 80 #11-23, Medellin',
                 anticipo_pct=50, sales_manager_id=uid)
    c4 = Cliente(es_demo=True, nombre='Diego Castillo', empresa='HotelGroup Colombia', nit='800333222-5',
                 estado_relacion='negociacion', dir_comercial='Cra 1 #5-60, Cartagena',
                 dir_entrega='Hotel Caribe, Cartagena', anticipo_pct=40, sales_manager_id=uid)
    c5 = Cliente(es_demo=True, nombre='Camila Ortiz', empresa='Tiendas del Barrio SAS', nit='901777888-9',
                 estado_relacion='cliente_activo', dir_comercial='Cl 50 #20-10, Bucaramanga',
                 anticipo_pct=50, sales_manager_id=uid)
    db.session.add_all([c1, c2, c3, c4, c5]); db.session.flush()

    # Contactos
    db.session.add_all([
        ContactoCliente(es_demo=True, cliente_id=c1.id, nombre='Ana Lopez', cargo='Gerente Compras', email='ana@distnacional.co', telefono='3104561234'),
        ContactoCliente(es_demo=True, cliente_id=c1.id, nombre='Mario Diaz', cargo='Bodeguero', email='bodega@distnacional.co', telefono='3114567890'),
        ContactoCliente(es_demo=True, cliente_id=c2.id, nombre='Roberto Silva', cargo='Director Comercial', email='roberto@freshmart.co', telefono='3201234567'),
        ContactoCliente(es_demo=True, cliente_id=c3.id, nombre='Patricia Herrera', cargo='Gerente General', email='patricia@naturvida.co', telefono='3156789012'),
        ContactoCliente(es_demo=True, cliente_id=c4.id, nombre='Diego Castillo', cargo='Jefe Compras', email='compras@hotelgroup.co', telefono='3187654321'),
        ContactoCliente(es_demo=True, cliente_id=c5.id, nombre='Camila Ortiz', cargo='Propietaria', email='camila@tiendasbarrio.co', telefono='3171112233'),
    ])

    # ── Productos terminados ──
    p1 = Producto(es_demo=True, nombre='Detergente Industrial 5L', sku='DET-5L', precio=45000, costo=22000,
                  stock=120, stock_minimo=20, categoria='Limpieza')
    p2 = Producto(es_demo=True, nombre='Desengrasante Concentrado 1L', sku='DES-1L', precio=28000, costo=12000,
                  stock=85, stock_minimo=15, categoria='Limpieza')
    p3 = Producto(es_demo=True, nombre='Jabon Liquido Antibacterial 500ml', sku='JAB-500', precio=15000, costo=6500,
                  stock=200, stock_minimo=30, categoria='Higiene')
    p4 = Producto(es_demo=True, nombre='Limpiador Multiusos 1L', sku='LIM-1L', precio=18000, costo=8000,
                  stock=150, stock_minimo=25, categoria='Limpieza')
    p5 = Producto(es_demo=True, nombre='Ambientador Premium 400ml', sku='AMB-400', precio=22000, costo=9500,
                  stock=60, stock_minimo=10, categoria='Ambientacion')
    p6 = Producto(es_demo=True, nombre='Suavizante Textil 2L', sku='SUA-2L', precio=32000, costo=14000,
                  stock=40, stock_minimo=15, categoria='Textil')
    db.session.add_all([p1, p2, p3, p4, p5, p6]); db.session.flush()

    # ── Materias primas ──
    mp1 = MateriaPrima(es_demo=True, nombre='Tensoactivo anionico', unidad='kg', stock_disponible=250, stock_minimo=50,
                       costo_unitario=8500, categoria='Quimicos', activo=True)
    mp2 = MateriaPrima(es_demo=True, nombre='Soda caustica', unidad='kg', stock_disponible=100, stock_minimo=20,
                       costo_unitario=4200, categoria='Quimicos', activo=True)
    mp3 = MateriaPrima(es_demo=True, nombre='Fragancia lavanda', unidad='litros', stock_disponible=30, stock_minimo=5,
                       costo_unitario=45000, categoria='Fragancias', activo=True)
    mp4 = MateriaPrima(es_demo=True, nombre='Agua desionizada', unidad='litros', stock_disponible=500, stock_minimo=100,
                       costo_unitario=800, categoria='Base', activo=True)
    mp5 = MateriaPrima(es_demo=True, nombre='Colorante azul', unidad='kg', stock_disponible=15, stock_minimo=3,
                       costo_unitario=32000, categoria='Colorantes', activo=True)
    mp6 = MateriaPrima(es_demo=True, nombre='Envase PET 5L', unidad='unidades', stock_disponible=300, stock_minimo=50,
                       costo_unitario=2800, categoria='Empaques', proveedor_id=prov2.id, activo=True)
    mp7 = MateriaPrima(es_demo=True, nombre='Envase PET 1L', unidad='unidades', stock_disponible=500, stock_minimo=80,
                       costo_unitario=1500, categoria='Empaques', proveedor_id=prov2.id, activo=True)
    mp8 = MateriaPrima(es_demo=True, nombre='Tapa rosca 38mm', unidad='unidades', stock_disponible=800, stock_minimo=100,
                       costo_unitario=450, categoria='Empaques', activo=True)
    mp9 = MateriaPrima(es_demo=True, nombre='Etiqueta autoadhesiva', unidad='unidades', stock_disponible=600, stock_minimo=100,
                       costo_unitario=350, categoria='Empaques', activo=True)
    mp10 = MateriaPrima(es_demo=True, nombre='Triclosan', unidad='kg', stock_disponible=8, stock_minimo=2,
                        costo_unitario=120000, categoria='Antibacterial', activo=True)
    db.session.add_all([mp1, mp2, mp3, mp4, mp5, mp6, mp7, mp8, mp9, mp10]); db.session.flush()

    # ── Recetas (BOM) ──
    # Detergente 5L: tensoactivo + soda + fragancia + agua + envase + tapa + etiqueta
    r1 = RecetaProducto(es_demo=True, producto_id=p1.id, unidades_produce=10, descripcion='Lote de 10 detergentes 5L', activo=True)
    db.session.add(r1); db.session.flush()
    db.session.add_all([
        RecetaItem(receta_id=r1.id, materia_prima_id=mp1.id, cantidad_por_unidad=2.5),   # 2.5kg tensoactivo x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp2.id, cantidad_por_unidad=0.8),   # 0.8kg soda x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp3.id, cantidad_por_unidad=0.15),  # 0.15L fragancia x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp4.id, cantidad_por_unidad=4.0),   # 4L agua x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp6.id, cantidad_por_unidad=1.0),   # 1 envase 5L x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp8.id, cantidad_por_unidad=1.0),   # 1 tapa x 10
        RecetaItem(receta_id=r1.id, materia_prima_id=mp9.id, cantidad_por_unidad=1.0),   # 1 etiqueta x 10
    ])

    # Jabon 500ml: tensoactivo + triclosan + fragancia + agua + envase 1L(se usa) + tapa + etiqueta
    r2 = RecetaProducto(es_demo=True, producto_id=p3.id, unidades_produce=20, descripcion='Lote de 20 jabones 500ml', activo=True)
    db.session.add(r2); db.session.flush()
    db.session.add_all([
        RecetaItem(receta_id=r2.id, materia_prima_id=mp1.id, cantidad_por_unidad=0.5),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp10.id, cantidad_por_unidad=0.05),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp3.id, cantidad_por_unidad=0.03),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp4.id, cantidad_por_unidad=0.45),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp7.id, cantidad_por_unidad=1.0),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp8.id, cantidad_por_unidad=1.0),
        RecetaItem(receta_id=r2.id, materia_prima_id=mp9.id, cantidad_por_unidad=1.0),
    ])

    # ── Servicios ──
    s1 = Servicio(es_demo=True, nombre='Fumigacion industrial', costo_interno=80000, precio_venta=180000,
                  unidad='servicio', categoria='Especializados', activo=True, creado_por=uid)
    s2 = Servicio(es_demo=True, nombre='Capacitacion manejo quimicos', costo_interno=50000, precio_venta=120000,
                  unidad='hora', categoria='Formacion', activo=True, creado_por=uid)
    db.session.add_all([s1, s2]); db.session.flush()

    # ── Empleados ──
    db.session.add_all([
        Empleado(es_demo=True, nombre='Carlos', apellido='Gutierrez', cedula='1020304050', cargo='Operario planta',
                 departamento='Produccion', salario_base=1423500, tipo_contrato='indefinido',
                 fecha_ingreso=hoy - timedelta(days=365), estado='activo', creado_por=uid),
        Empleado(es_demo=True, nombre='Lucia', apellido='Fernandez', cedula='1060708090', cargo='Auxiliar logistica',
                 departamento='Logistica', salario_base=1600000, tipo_contrato='indefinido',
                 fecha_ingreso=hoy - timedelta(days=200), estado='activo', creado_por=uid),
        Empleado(es_demo=True, nombre='Jorge', apellido='Martinez', cedula='1030507090', cargo='Quimico formulador',
                 departamento='Produccion', salario_base=3200000, tipo_contrato='indefinido',
                 auxilio_transporte=False, fecha_ingreso=hoy - timedelta(days=500), estado='activo', creado_por=uid),
    ])

    # ── Cotizaciones ──
    cot1 = Cotizacion(es_demo=True, numero='COT-2026-001', titulo='Dotacion limpieza Q2 - Dist Nacional',
                      cliente_id=c1.id, subtotal=2700000, iva=513000, total=3213000,
                      porcentaje_anticipo=50, monto_anticipo=1606500, saldo=1606500,
                      estado='enviada', fecha_emision=hoy - timedelta(days=5),
                      fecha_validez=hoy + timedelta(days=25), dias_entrega=15,
                      fecha_entrega_est=hoy + timedelta(days=20),
                      condiciones_pago='50% anticipo, saldo contra entrega',
                      notas='Cliente solicita entrega en bodega Zona Franca',
                      creado_por=uid)
    db.session.add(cot1); db.session.flush()
    db.session.add_all([
        CotizacionItem(cotizacion_id=cot1.id, producto_id=p1.id, nombre_prod='Detergente Industrial 5L',
                       cantidad=30, precio_unit=45000, subtotal=1350000, aplica_iva=True, iva_pct=19, iva_monto=256500),
        CotizacionItem(cotizacion_id=cot1.id, producto_id=p2.id, nombre_prod='Desengrasante Concentrado 1L',
                       cantidad=20, precio_unit=28000, subtotal=560000, aplica_iva=True, iva_pct=19, iva_monto=106400),
        CotizacionItem(cotizacion_id=cot1.id, producto_id=p3.id, nombre_prod='Jabon Liquido Antibacterial 500ml',
                       cantidad=40, precio_unit=15000, subtotal=600000, aplica_iva=True, iva_pct=19, iva_monto=114000),
        CotizacionItem(cotizacion_id=cot1.id, servicio_id=s2.id, nombre_prod='Capacitacion manejo quimicos (2h)',
                       cantidad=2, precio_unit=120000, subtotal=240000, tipo_item='servicio',
                       aplica_iva=True, iva_pct=19, iva_monto=45600),
    ])

    cot2 = Cotizacion(es_demo=True, numero='COT-2026-002', titulo='Amenities hotel - HotelGroup',
                      cliente_id=c4.id, subtotal=1540000, iva=292600, total=1832600,
                      porcentaje_anticipo=40, monto_anticipo=733040, saldo=1099560,
                      estado='aprobada', fecha_emision=hoy - timedelta(days=10),
                      fecha_validez=hoy + timedelta(days=20), dias_entrega=20,
                      fecha_entrega_est=hoy + timedelta(days=15),
                      notas='Incluye personalizacion de etiquetas con logo hotel',
                      creado_por=uid)
    db.session.add(cot2); db.session.flush()
    db.session.add_all([
        CotizacionItem(cotizacion_id=cot2.id, producto_id=p3.id, nombre_prod='Jabon Liquido Antibacterial 500ml',
                       cantidad=60, precio_unit=15000, subtotal=900000, aplica_iva=True, iva_pct=19, iva_monto=171000),
        CotizacionItem(cotizacion_id=cot2.id, producto_id=p5.id, nombre_prod='Ambientador Premium 400ml',
                       cantidad=20, precio_unit=22000, subtotal=440000, aplica_iva=True, iva_pct=19, iva_monto=83600),
        CotizacionItem(cotizacion_id=cot2.id, servicio_id=s1.id, nombre_prod='Fumigacion areas comunes',
                       cantidad=1, precio_unit=180000, subtotal=180000, tipo_item='servicio',
                       aplica_iva=True, iva_pct=19, iva_monto=34200),
    ])

    # ── Ventas en distintos estados ──
    v1 = Venta(es_demo=True, numero='VNT-2026-001', titulo='Pedido mensual FreshMart marzo',
               cliente_id=c2.id, subtotal=1890000, iva=359100, total=2249100,
               porcentaje_anticipo=60, monto_anticipo=1349460, saldo=899640,
               monto_pagado_total=1349460, estado='anticipo_pagado',
               fecha_anticipo=hoy - timedelta(days=3), dias_entrega=10,
               fecha_entrega_est=hoy + timedelta(days=7),
               notas='Entrega en CEDI Funza, horario 6am-2pm', creado_por=uid)
    db.session.add(v1); db.session.flush()
    db.session.add_all([
        VentaProducto(venta_id=v1.id, producto_id=p1.id, nombre_prod='Detergente Industrial 5L',
                      cantidad=20, precio_unit=45000, subtotal=900000),
        VentaProducto(venta_id=v1.id, producto_id=p4.id, nombre_prod='Limpiador Multiusos 1L',
                      cantidad=30, precio_unit=18000, subtotal=540000),
        VentaProducto(venta_id=v1.id, producto_id=p3.id, nombre_prod='Jabon Liquido Antibacterial 500ml',
                      cantidad=30, precio_unit=15000, subtotal=450000),
    ])
    # Pago del anticipo
    db.session.add(PagoVenta(venta_id=v1.id, monto=1349460, tipo='anticipo',
                             metodo_pago='transferencia', referencia='TRF-2026-0301',
                             fecha=hoy - timedelta(days=3), creado_por=uid))

    v2 = Venta(es_demo=True, numero='VNT-2026-002', titulo='Suministro trimestral Tiendas del Barrio',
               cliente_id=c5.id, subtotal=960000, iva=182400, total=1142400,
               porcentaje_anticipo=50, monto_anticipo=571200, saldo=1142400,
               estado='negociacion', dias_entrega=20,
               fecha_entrega_est=hoy + timedelta(days=25),
               notas='Pendiente confirmar cantidades finales', creado_por=uid)
    db.session.add(v2); db.session.flush()
    db.session.add_all([
        VentaProducto(venta_id=v2.id, producto_id=p4.id, nombre_prod='Limpiador Multiusos 1L',
                      cantidad=20, precio_unit=18000, subtotal=360000),
        VentaProducto(venta_id=v2.id, producto_id=p5.id, nombre_prod='Ambientador Premium 400ml',
                      cantidad=15, precio_unit=22000, subtotal=330000),
        VentaProducto(venta_id=v2.id, producto_id=p6.id, nombre_prod='Suavizante Textil 2L',
                      cantidad=10, precio_unit=32000, subtotal=320000),
    ])

    v3 = Venta(es_demo=True, numero='VNT-2026-003', titulo='Pedido urgente NaturVida',
               cliente_id=c3.id, subtotal=675000, iva=128250, total=803250,
               porcentaje_anticipo=50, monto_anticipo=401625, saldo=0,
               monto_pagado_total=803250, estado='pagado',
               fecha_anticipo=hoy - timedelta(days=15), dias_entrega=5,
               fecha_entrega_est=hoy - timedelta(days=8),
               entregado_en=datetime.utcnow() - timedelta(days=7),
               notas='Entregado y pagado en su totalidad', creado_por=uid)
    db.session.add(v3); db.session.flush()
    db.session.add_all([
        VentaProducto(venta_id=v3.id, producto_id=p1.id, nombre_prod='Detergente Industrial 5L',
                      cantidad=15, precio_unit=45000, subtotal=675000),
    ])
    db.session.add_all([
        PagoVenta(venta_id=v3.id, monto=401625, tipo='anticipo', metodo_pago='transferencia',
                  referencia='TRF-NV-001', fecha=hoy - timedelta(days=15), creado_por=uid),
        PagoVenta(venta_id=v3.id, monto=401625, tipo='saldo', metodo_pago='transferencia',
                  referencia='TRF-NV-002', fecha=hoy - timedelta(days=7), creado_por=uid),
    ])

    # ── Gastos operativos ──
    db.session.add_all([
        GastoOperativo(es_demo=True, fecha=hoy - timedelta(days=30), tipo='Arriendo', descripcion='Arriendo bodega planta',
                       monto=3500000, recurrencia='mensual', es_plantilla=True, creado_por=uid),
        GastoOperativo(es_demo=True, fecha=hoy - timedelta(days=15), tipo='Servicios', descripcion='Energia electrica marzo',
                       monto=850000, creado_por=uid),
        GastoOperativo(es_demo=True, fecha=hoy - timedelta(days=10), tipo='Transporte', descripcion='Flete despacho Medellin',
                       monto=420000, creado_por=uid),
        GastoOperativo(es_demo=True, fecha=hoy - timedelta(days=5), tipo='Mantenimiento', descripcion='Reparacion mezcladora industrial',
                       monto=780000, creado_por=uid),
    ])

    # ── Notas ──
    db.session.add_all([
        Nota(es_demo=True, titulo='Reunion con FreshMart', contenido='Roberto confirmo interes en contrato anual. Preparar propuesta.',
             cliente_id=c2.id, fecha_revision=hoy + timedelta(days=3), creado_por=uid),
        Nota(es_demo=True, titulo='Formula nueva ambientador', contenido='Probar version con aceite esencial de eucalipto. Muestra lista para viernes.',
             fecha_revision=hoy + timedelta(days=5), creado_por=uid),
    ])

    # ── Tareas ──
    t1 = Tarea(es_demo=True, titulo='Preparar muestras para HotelGroup', descripcion='Enviar 3 muestras de jabon + ambientador con logo personalizado',
               estado='pendiente', prioridad='alta', fecha_vencimiento=hoy + timedelta(days=2),
               asignado_a=uid, creado_por=uid)
    t2 = Tarea(es_demo=True, titulo='Revisar inventario quimicos', descripcion='Verificar stock de tensoactivo y soda caustica antes de produccion',
               estado='en_progreso', prioridad='media', fecha_vencimiento=hoy + timedelta(days=1),
               asignado_a=uid, creado_por=uid)
    t3 = Tarea(es_demo=True, titulo='Facturar pedido NaturVida', descripcion='Generar factura electronica VNT-2026-003',
               estado='completada', prioridad='baja', creado_por=uid)
    db.session.add_all([t1, t2, t3]); db.session.flush()
    db.session.add_all([
        TareaAsignado(tarea_id=t1.id, user_id=uid),
        TareaAsignado(tarea_id=t2.id, user_id=uid),
    ])

    # ── Eventos ──
    db.session.add_all([
        Evento(es_demo=True, titulo='Visita planta FreshMart', fecha=hoy + timedelta(days=5), tipo='reunion',
               descripcion='Roberto Silva visita planta para auditar procesos', usuario_id=uid),
        Evento(es_demo=True, titulo='Vencimiento cotizacion HotelGroup', fecha=hoy + timedelta(days=20), tipo='recordatorio',
               descripcion='COT-2026-002 vence, hacer seguimiento', usuario_id=uid),
    ])

    # ── Regla tributaria ──
    if not ReglaTributaria.query.first():
        db.session.add(ReglaTributaria(nombre='IVA General', descripcion='IVA 19% sobre ventas',
                                       porcentaje=19.0, aplica_a='ventas', activo=True))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error al sembrar datos demo fase 1: {e}')
        return

    # ── Fase 2: datos que dependen de los anteriores (IDs ya asignados) ──
    try:
        # Marcas para productos
        det5l = Producto.query.filter_by(nombre='Detergente Industrial 5L').first()
        jab500 = Producto.query.filter_by(nombre='Jabon Liquido Antibacterial 500ml').first()
        if det5l:
            db.session.add(MarcaProducto(es_demo=True, producto_id=det5l.id, nombre_marca='EvoreClean Industrial',
                                          nso='NSO-2024-0451', registro_sanitario='INVIMA-2024-DI-001'))
            db.session.add(MarcaProducto(es_demo=True, producto_id=det5l.id, nombre_marca='LimpioMax Pro',
                                          nso='NSO-2024-0452', registro_sanitario='INVIMA-2024-DI-002'))
        if jab500:
            db.session.add(MarcaProducto(es_demo=True, producto_id=jab500.id, nombre_marca='EvoreHand Antibacterial',
                                          nso='NSO-2024-0460', registro_sanitario='INVIMA-2024-JA-001'))

        # Actualizar clasificación de ingredientes en recetas existentes
        for ri in RecetaItem.query.all():
            mp = db.session.get(MateriaPrima, ri.materia_prima_id)
            if mp and mp.categoria == 'Empaques':
                ri.clasificacion = 'empaque_primario'
                ri.es_empaque = True
            else:
                ri.clasificacion = 'materia_prima'

        # Auto-generar SKU para productos sin SKU
        for p in Producto.query.filter(Producto.sku == None).all():
            p.sku = _generar_sku(p.nombre)

        # Calcular costos de recetas
        for r in RecetaProducto.query.filter_by(activo=True).all():
            try:
                from utils import _calcular_costo_receta
                costo = _calcular_costo_receta(r.producto_id)
                r.costo_calculado = costo['costo_unitario']
                r.margen_pct = 30
                precio_sin_iva = costo['costo_unitario'] * 1.30  # 30% margen
                r.precio_venta_sugerido = round(precio_sin_iva * 1.19, 2)  # + 19% IVA
                if r.producto:
                    r.producto.precio = r.precio_venta_sugerido
                    r.producto.costo = round(costo['costo_unitario'], 2)
                    r.producto.costo_receta = round(costo['costo_unitario'], 2)
            except Exception:
                pass

        # Configurar envío en clientes
        c1 = Cliente.query.filter_by(empresa='Distribuidora Nacional SAS').first()
        c2 = Cliente.query.filter_by(empresa='Cadena FreshMart').first()
        c4 = Cliente.query.filter_by(empresa='HotelGroup Colombia').first()
        trans = Proveedor.query.filter_by(empresa='TransCarga Ltda').first()
        if c1:
            c1.envio_responsable = 'empresa'  # Nosotros enviamos
            if trans: c1.transportista_preferido_id = trans.id
        if c2:
            c2.envio_responsable = 'cliente'  # Ellos recogen
        if c4:
            c4.envio_responsable = 'empresa'
            if trans: c4.transportista_preferido_id = trans.id

        # Capacidad del transportista
        if trans:
            trans.capacidad_vehiculo_kg = 5000
            trans.capacidad_vehiculo_m3 = 20
            trans.tipo_vehiculo = 'furgon'
            trans.envia_material = True

        # Cotizaciones de proveedor vinculadas a materias primas
        prov1 = Proveedor.query.filter_by(empresa='QuimiCol SAS').first()
        prov2 = Proveedor.query.filter_by(empresa='Envases del Valle').first()
        hoy = date.today()
        if prov1:
            mp_tenso = MateriaPrima.query.filter_by(nombre='Tensoactivo anionico').first()
            mp_soda = MateriaPrima.query.filter_by(nombre='Soda caustica').first()
            mp_frag = MateriaPrima.query.filter_by(nombre='Fragancia lavanda').first()
            if mp_tenso:
                db.session.add(CotizacionProveedor(es_demo=True, 
                    numero='CP-2026-001', proveedor_id=prov1.id, materia_prima_id=mp_tenso.id,
                    nombre_producto='Tensoactivo anionico industrial', precio_unitario=8200,
                    unidad='kg', plazo_entrega_dias=10, estado='vigente',
                    fecha_cotizacion=hoy - timedelta(days=15), vigencia=hoy + timedelta(days=60),
                    creado_por=uid))
            if mp_soda:
                db.session.add(CotizacionProveedor(es_demo=True, 
                    numero='CP-2026-002', proveedor_id=prov1.id, materia_prima_id=mp_soda.id,
                    nombre_producto='Soda caustica perlas', precio_unitario=4000,
                    unidad='kg', plazo_entrega_dias=7, estado='vigente',
                    fecha_cotizacion=hoy - timedelta(days=10), vigencia=hoy + timedelta(days=45),
                    creado_por=uid))
            if mp_frag:
                db.session.add(CotizacionProveedor(es_demo=True, 
                    numero='CP-2026-003', proveedor_id=prov1.id, materia_prima_id=mp_frag.id,
                    nombre_producto='Fragancia lavanda concentrada', precio_unitario=43000,
                    unidad='litros', plazo_entrega_dias=15, estado='vigente',
                    fecha_cotizacion=hoy - timedelta(days=20), vigencia=hoy + timedelta(days=30),
                    creado_por=uid))
        if prov2:
            mp_env5 = MateriaPrima.query.filter_by(nombre='Envase PET 5L').first()
            mp_env1 = MateriaPrima.query.filter_by(nombre='Envase PET 1L').first()
            if mp_env5:
                db.session.add(CotizacionProveedor(es_demo=True, 
                    numero='CP-2026-004', proveedor_id=prov2.id, materia_prima_id=mp_env5.id,
                    nombre_producto='Envase PET 5 litros cristal', precio_unitario=2600,
                    unidad='unidades', plazo_entrega_dias=12, estado='vigente',
                    fecha_cotizacion=hoy - timedelta(days=10), vigencia=hoy + timedelta(days=50),
                    creado_por=uid))
            if mp_env1:
                db.session.add(CotizacionProveedor(es_demo=True, 
                    numero='CP-2026-005', proveedor_id=prov2.id, materia_prima_id=mp_env1.id,
                    nombre_producto='Envase PET 1 litro cristal', precio_unitario=1400,
                    unidad='unidades', plazo_entrega_dias=12, estado='vigente',
                    fecha_cotizacion=hoy - timedelta(days=10), vigencia=hoy + timedelta(days=50),
                    creado_por=uid))

        # Documentos legales
        db.session.add(DocumentoLegal(es_demo=True, 
            tipo='registro_invima', titulo='Registro INVIMA Detergentes',
            numero='INVIMA-2024-DI-001', entidad='INVIMA',
            estado='vigente', fecha_emision=hoy - timedelta(days=200),
            fecha_vencimiento=hoy + timedelta(days=165), recordatorio_dias=30,
            producto_id=det5l.id if det5l else None, tipo_entidad='producto',
            creado_por=uid))
        db.session.add(DocumentoLegal(es_demo=True, 
            tipo='contrato', titulo='Contrato suministro - Distribuidora Nacional',
            numero='CTR-2026-001', entidad='Evore',
            estado='vigente', fecha_emision=hoy - timedelta(days=90),
            fecha_vencimiento=hoy + timedelta(days=275),
            cliente_id=c1.id if c1 else None, tipo_entidad='cliente',
            creado_por=uid))

        db.session.commit()

        # Recalcular costos con cotizaciones vigentes
        for r in RecetaProducto.query.filter_by(activo=True).all():
            try:
                costo = _calcular_costo_receta(r.producto_id)
                r.costo_calculado = costo['costo_unitario']
                precio_sin_iva = costo['costo_unitario'] * (1 + r.margen_pct / 100)
                r.precio_venta_sugerido = round(precio_sin_iva * 1.19, 2)
                if r.producto:
                    r.producto.precio = r.precio_venta_sugerido
                    r.producto.costo = round(costo['costo_unitario'], 2)
                    r.producto.costo_receta = round(costo['costo_unitario'], 2)
            except Exception:
                pass

        db.session.commit()
        logging.info('Datos demo v35 sembrados: clientes, productos, recetas con costos, marcas, cotizaciones proveedor, documentos legales, SKUs.')
    except Exception as e:
        db.session.rollback()
        logging.error(f'Error al sembrar datos demo fase 2: {e}')

def _seed_capacitacion():
    """Seed training courses, lessons and quiz questions."""
    import json, logging
    already_seeded = CapCurso.query.first() is not None
    if already_seeded:
        # Still run practice step updates
        try:
            _update_cap_practice_steps()
        except Exception as e:
            logging.warning(f'Cap practice steps update: {e}')
        return
    try:
        CURSOS = [
            {
                'titulo': 'Gestion de Ventas y Cotizaciones',
                'descripcion': 'Aprende a registrar clientes, crear cotizaciones, convertirlas en ventas y gestionar pagos.',
                'modulo_crm': 'ventas', 'icono': 'bi-bag-fill', 'orden': 1, 'nivel': 'basico',
                'roles_objetivo': json.dumps(['vendedor','sales_manager','admin']),
                'lecciones': [
                    {'titulo': 'Crear un cliente nuevo', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Registrar un nuevo cliente con sus contactos y datos comerciales.</p><div class="paso"><span class="paso-num">1</span>Ve al modulo <strong>Clientes</strong> en el sidebar.</div><div class="paso"><span class="paso-num">2</span>Haz clic en <strong>+ Nuevo</strong> en la barra superior.</div><div class="paso"><span class="paso-num">3</span>Completa: empresa, NIT, tipo de documento, direccion comercial y direccion de entrega.</div><div class="paso"><span class="paso-num">4</span>En la seccion <strong>Contactos</strong>, agrega nombre, cargo, email y telefono del contacto principal.</div><div class="paso"><span class="paso-num">5</span>Haz clic en <strong>Crear Cliente</strong>.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Si el NIT ya existe como empresa en Evore, se creara automaticamente una relacion comercial bidireccional.</div>'},
                    {'titulo': 'Elaborar una cotizacion', 'orden': 2, 'duracion_min': 8,
                     'contenido': '<h6>Objetivo</h6><p>Crear una cotizacion formal con productos, cantidades, precios e IVA.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Cotizaciones</strong> desde el dock Comercial.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nueva</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona el cliente. Si no existe, puedes crearlo desde aqui.</div><div class="paso"><span class="paso-num">4</span>Agrega productos o servicios con cantidad y precio unitario.</div><div class="paso"><span class="paso-num">5</span>El sistema calcula automaticamente subtotal, IVA y total.</div><div class="paso"><span class="paso-num">6</span>Guarda y descarga el PDF para enviar al cliente.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Las cotizaciones tienen vigencia. Cuando el cliente aprueba, puedes convertirla en venta con un clic.</div>'},
                    {'titulo': 'Convertir cotizacion en venta', 'orden': 3, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Convertir una cotizacion aprobada en una venta activa en el pipeline.</p><div class="paso"><span class="paso-num">1</span>Abre la cotizacion aprobada.</div><div class="paso"><span class="paso-num">2</span>Haz clic en <strong>Convertir en Venta</strong>.</div><div class="paso"><span class="paso-num">3</span>Se crea automaticamente: la venta en estado <strong>prospecto</strong>, un asiento contable de ingreso y el contrato del cliente en el portal.</div><div class="paso"><span class="paso-num">4</span>La venta aparece en el modulo Ventas lista para avanzar en el pipeline.</div><div class="alerta"><i class="bi bi-exclamation-triangle me-1"></i>Solo el contable puede confirmar el anticipo desde Asientos Contables. Esto cambia la venta a estado anticipo_pagado.</div>'},
                    {'titulo': 'Pipeline de ventas y estados', 'orden': 4, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Entender el flujo de estados de una venta y como avanzarla.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Ventas</strong> para ver todas en vista de tarjetas.</div><div class="paso"><span class="paso-num">2</span>Los estados son: <strong>prospecto → negociacion → anticipo_pagado → pagado → entregado → completado</strong>.</div><div class="paso"><span class="paso-num">3</span>Para cambiar estado, abre la venta y usa el boton de cambio de estado.</div><div class="paso"><span class="paso-num">4</span>Al pasar a <strong>anticipo_pagado</strong> se reserva stock automaticamente y se generan OC para materias faltantes.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Usa los filtros y el buscador para encontrar ventas rapidamente. Puedes filtrar por estado, cliente o fecha.</div>'},
                    {'titulo': 'Registrar pagos', 'orden': 5, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Confirmar pagos parciales o totales desde Asientos Contables.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Operaciones → Asientos contables</strong>.</div><div class="paso"><span class="paso-num">2</span>Busca el asiento de ingreso vinculado a la venta.</div><div class="paso"><span class="paso-num">3</span>Haz clic en <strong>Cobro</strong> y selecciona pago total o parcial.</div><div class="paso"><span class="paso-num">4</span>Indica el metodo de pago (transferencia, efectivo, Nequi).</div><div class="paso"><span class="paso-num">5</span>Al confirmar, el estado de la venta cambia automaticamente.</div><div class="alerta"><i class="bi bi-exclamation-triangle me-1"></i>Los pagos solo los puede confirmar un usuario con rol contable o admin.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Cual es el primer paso para crear una venta en el CRM?', 'opciones': json.dumps(['Ir directamente a Ventas y crear','Registrar un cliente primero','Crear un asiento contable','Enviar un correo al cliente']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que sucede automaticamente al convertir una cotizacion en venta?', 'opciones': json.dumps(['Se envia un correo al cliente','Se crea asiento contable, contrato y la venta en pipeline','Se descuenta inventario','Se genera la factura DIAN']), 'respuesta_correcta': 1, 'orden': 2},
                    {'texto': 'Quien puede confirmar el pago de anticipo de una venta?', 'opciones': json.dumps(['El vendedor','El cliente desde el portal','El contable o admin desde Asientos Contables','Cualquier usuario']), 'respuesta_correcta': 2, 'orden': 3},
                    {'texto': 'Cual es el flujo correcto de estados de una venta?', 'opciones': json.dumps(['prospecto → pagado → entregado','prospecto → negociacion → anticipo_pagado → pagado → entregado → completado','negociacion → produccion → entregado','borrador → enviada → recibida']), 'respuesta_correcta': 1, 'orden': 4},
                    {'texto': 'Que pasa al cambiar una venta a estado anticipo_pagado?', 'opciones': json.dumps(['Se elimina la cotizacion','Se reserva stock y se generan OC para materias faltantes','Se envia notificacion al cliente','No pasa nada especial']), 'respuesta_correcta': 1, 'orden': 5},
                ]
            },
            {
                'titulo': 'Compras y Proveedores',
                'descripcion': 'Registra proveedores, crea cotizaciones, genera ordenes de compra y recibe materiales.',
                'modulo_crm': 'compras', 'icono': 'bi-cart-check', 'orden': 2, 'nivel': 'basico',
                'roles_objetivo': json.dumps(['produccion','director_operativo','admin']),
                'lecciones': [
                    {'titulo': 'Registrar un proveedor', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Crear un proveedor con datos de contacto y tipo.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Proveedores</strong> desde el dock de Compras.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nuevo</strong>.</div><div class="paso"><span class="paso-num">3</span>Completa: nombre, empresa, NIT, email, telefono.</div><div class="paso"><span class="paso-num">4</span>Selecciona el tipo: <strong>proveedor</strong>, <strong>transportista</strong> o <strong>ambos</strong>.</div><div class="paso"><span class="paso-num">5</span>Guarda el proveedor.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Los transportistas tambien se registran aqui. Al crear una OC podras asignar transportista y se creara un ticket automatico.</div>'},
                    {'titulo': 'Crear cotizacion de proveedor', 'orden': 2, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Solicitar y registrar cotizaciones de proveedores para materias primas.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Cotizaciones de proveedor</strong>.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nueva</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona proveedor, producto, precio unitario, unidades minimas y plazo de entrega.</div><div class="paso"><span class="paso-num">4</span>El estado inicia como <strong>en revision</strong>. Cambialo a <strong>vigente</strong> cuando el proveedor confirme.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Al crear materias primas desde BOM se generan cotizaciones automaticamente en estado "en revision".</div>'},
                    {'titulo': 'Generar orden de compra', 'orden': 3, 'duracion_min': 8,
                     'contenido': '<h6>Objetivo</h6><p>Crear una OC seleccionando cotizaciones vigentes del proveedor.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Ordenes de compra → Nueva</strong>.</div><div class="paso"><span class="paso-num">2</span>Selecciona el proveedor. Se cargan automaticamente sus cotizaciones.</div><div class="paso"><span class="paso-num">3</span>Marca las cotizaciones que quieres incluir y haz clic en <strong>Agregar seleccionadas</strong>.</div><div class="paso"><span class="paso-num">4</span>Ajusta cantidades y agrega items manuales si es necesario.</div><div class="paso"><span class="paso-num">5</span>Opcionalmente asigna transportista y fecha de recogida.</div><div class="paso"><span class="paso-num">6</span>Guarda. Se genera automaticamente un asiento contable de egreso.</div>'},
                    {'titulo': 'Confirmar pago y recibir material', 'orden': 4, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Pagar la OC y registrar la recepcion de materias primas.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Operaciones → Asientos contables</strong>.</div><div class="paso"><span class="paso-num">2</span>Busca el asiento de egreso de la OC y confirma el pago.</div><div class="paso"><span class="paso-num">3</span>El proveedor recibe notificacion en su portal y puede confirmar la recepcion del anticipo.</div><div class="paso"><span class="paso-num">4</span>Cuando llegue el material, ve a <strong>Produccion → Recepcion MP</strong> y registra las cantidades recibidas.</div><div class="paso"><span class="paso-num">5</span>El stock de materias primas se actualiza automaticamente.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Donde se registran los transportistas en el CRM?', 'opciones': json.dumps(['En un modulo aparte de Logistica','En el modulo de Proveedores, con tipo "transportista"','En Configuracion','No se pueden registrar']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que se genera automaticamente al crear una orden de compra?', 'opciones': json.dumps(['Una factura de venta','Un asiento contable de egreso y contrato proveedor','Un ticket para el cliente','Nada automatico']), 'respuesta_correcta': 1, 'orden': 2},
                    {'texto': 'Desde donde se confirma el pago de una OC?', 'opciones': json.dumps(['Desde la OC directamente','Desde el modulo de Proveedores','Desde Asientos Contables en Finanzas','Desde el portal del proveedor']), 'respuesta_correcta': 2, 'orden': 3},
                    {'texto': 'Que pasa cuando un proveedor no tiene cotizaciones vigentes?', 'opciones': json.dumps(['No se puede crear OC','Se pueden agregar items manuales a la OC','El sistema crea cotizaciones automaticamente','Se bloquea el proveedor']), 'respuesta_correcta': 1, 'orden': 4},
                    {'texto': 'Donde se registra la recepcion de materias primas?', 'opciones': json.dumps(['En el modulo de Compras','En Produccion → Recepcion MP','En Inventario','En Asientos Contables']), 'respuesta_correcta': 1, 'orden': 5},
                ]
            },
            {
                'titulo': 'Produccion y Recetas (BOM)',
                'descripcion': 'Crea recetas de producto, gestiona ordenes de produccion y controla el proceso de manufactura.',
                'modulo_crm': 'produccion', 'icono': 'bi-gear-fill', 'orden': 3, 'nivel': 'intermedio',
                'roles_objetivo': json.dumps(['produccion','director_operativo','admin']),
                'lecciones': [
                    {'titulo': 'Crear una receta de producto (BOM)', 'orden': 1, 'duracion_min': 8,
                     'contenido': '<h6>Objetivo</h6><p>Definir los ingredientes y cantidades necesarias para producir un producto.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Produccion → Recetas</strong>.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nueva</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona el producto terminado o crea uno nuevo.</div><div class="paso"><span class="paso-num">4</span>Agrega ingredientes: materia prima, cantidad por unidad y clasificacion (MP/Maquila, empaque primario o secundario).</div><div class="paso"><span class="paso-num">5</span>Si necesitas una materia prima nueva, usa el boton <strong>Nueva materia prima</strong> sin salir del formulario.</div><div class="paso"><span class="paso-num">6</span>Define el margen de ganancia (%) y guarda.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Al crear materias primas desde aqui se genera automaticamente una cotizacion pendiente en Compras.</div>'},
                    {'titulo': 'Crear orden de produccion', 'orden': 2, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Iniciar la produccion de un lote de productos.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Produccion → Ordenes</strong>.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nueva</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona la receta y la cantidad a producir.</div><div class="paso"><span class="paso-num">4</span>El sistema verifica si hay stock suficiente de materias primas.</div><div class="paso"><span class="paso-num">5</span>Si falta stock, se crean alertas automaticas.</div><div class="paso"><span class="paso-num">6</span>Avanza la orden por los estados: pendiente → en_produccion → completada.</div>'},
                    {'titulo': 'Gestionar reservas de materia prima', 'orden': 3, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Entender como el sistema reserva materias primas para produccion.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Produccion → Reservas</strong>.</div><div class="paso"><span class="paso-num">2</span>Aqui ves todas las reservas activas de materias primas.</div><div class="paso"><span class="paso-num">3</span>Las reservas se crean automaticamente al confirmar anticipo de una venta.</div><div class="paso"><span class="paso-num">4</span>El stock reservado se descuenta del stock disponible.</div><div class="paso"><span class="paso-num">5</span>Usa el sistema FIFO con trazabilidad de lotes para asegurar que se use primero el material mas antiguo.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Que es un BOM en el contexto del CRM?', 'opciones': json.dumps(['Un tipo de factura','La lista de materiales (receta) para producir un producto','Un reporte contable','Un tipo de orden de compra']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que sucede al crear una materia prima desde el formulario de receta?', 'opciones': json.dumps(['Solo se crea la materia prima','Se crea la materia prima y una cotizacion pendiente en Compras','Se descuenta del inventario','Se envia correo al proveedor']), 'respuesta_correcta': 1, 'orden': 2},
                    {'texto': 'Como se reservan materias primas para produccion?', 'opciones': json.dumps(['Manualmente en cada orden','Automaticamente al confirmar anticipo de venta','No hay sistema de reservas','El proveedor las reserva']), 'respuesta_correcta': 1, 'orden': 3},
                    {'texto': 'Que sistema usa el CRM para despachar materia prima?', 'opciones': json.dumps(['LIFO (ultimo en entrar, primero en salir)','Aleatorio','FIFO con trazabilidad de lotes y vencimiento','No hay control de lotes']), 'respuesta_correcta': 2, 'orden': 4},
                ]
            },
            {
                'titulo': 'Contabilidad y Finanzas',
                'descripcion': 'Navega el PUC, gestiona asientos contables, gastos y genera reportes financieros.',
                'modulo_crm': 'contable', 'icono': 'bi-currency-dollar', 'orden': 4, 'nivel': 'intermedio',
                'roles_objetivo': json.dumps(['contador','director_financiero','admin']),
                'lecciones': [
                    {'titulo': 'Navegar el Plan Unico de Cuentas (PUC)', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Entender la estructura del PUC colombiano en el CRM.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Operaciones → Plan de Cuentas</strong>.</div><div class="paso"><span class="paso-num">2</span>El PUC tiene 102 cuentas del Decreto 2650/1993.</div><div class="paso"><span class="paso-num">3</span>La estructura es: clase (1 digito) → grupo (2) → cuenta (4) → subcuenta (6).</div><div class="paso"><span class="paso-num">4</span>Puedes buscar por codigo o nombre.</div><div class="paso"><span class="paso-num">5</span>Cada asiento contable referencia cuentas del PUC.</div>'},
                    {'titulo': 'Asientos contables generados y manuales', 'orden': 2, 'duracion_min': 7,
                     'contenido': '<h6>Objetivo</h6><p>Entender los dos tipos de asientos y como gestionarlos.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Operaciones → Asientos contables</strong>.</div><div class="paso"><span class="paso-num">2</span>Pestana <strong>Generados</strong>: asientos creados automaticamente por ventas, OC, nomina y gastos.</div><div class="paso"><span class="paso-num">3</span>Pestana <strong>Manuales</strong>: asientos que creas tu directamente.</div><div class="paso"><span class="paso-num">4</span>Para crear uno manual, clic en <strong>Nuevo ingreso</strong> o <strong>Nuevo egreso</strong>.</div><div class="paso"><span class="paso-num">5</span>Completa: fecha, descripcion, cuenta debe/haber, monto.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Los asientos generados son la forma principal de confirmar pagos. Al confirmar un pago, el estado de la OC o venta cambia automaticamente.</div>'},
                    {'titulo': 'Gastos operativos', 'orden': 3, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Registrar gastos del negocio (arriendo, servicios, etc.).</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Operaciones → Gastos</strong>.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nuevo</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona categoria, proveedor (opcional), monto y fecha.</div><div class="paso"><span class="paso-num">4</span>Se genera automaticamente un asiento contable de egreso.</div>'},
                    {'titulo': 'Generar reportes financieros', 'orden': 4, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Generar Balance General, Estado de Resultados y otros reportes.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Finanzas → Reportes</strong>.</div><div class="paso"><span class="paso-num">2</span><strong>Balance de Prueba</strong>: verifica que debitos = creditos.</div><div class="paso"><span class="paso-num">3</span><strong>Balance General</strong>: Activos = Pasivos + Patrimonio.</div><div class="paso"><span class="paso-num">4</span><strong>Estado de Resultados</strong>: Ingresos - Gastos = Utilidad.</div><div class="paso"><span class="paso-num">5</span><strong>Flujo de caja</strong>: movimientos de efectivo por periodo.</div><div class="paso"><span class="paso-num">6</span>Todos los reportes son exportables.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Cuantas cuentas tiene el PUC colombiano en el CRM?', 'opciones': json.dumps(['50','75','102','200']), 'respuesta_correcta': 2, 'orden': 1},
                    {'texto': 'Cual es la diferencia entre asientos generados y manuales?', 'opciones': json.dumps(['No hay diferencia','Los generados se crean automaticamente por ventas/OC/nomina; los manuales los crea el usuario','Los manuales son provisionales','Los generados no se pueden editar']), 'respuesta_correcta': 1, 'orden': 2},
                    {'texto': 'Que reporte verifica que debitos sean iguales a creditos?', 'opciones': json.dumps(['Estado de Resultados','Flujo de Caja','Balance de Prueba','Balance General']), 'respuesta_correcta': 2, 'orden': 3},
                    {'texto': 'Que pasa al registrar un gasto operativo?', 'opciones': json.dumps(['Solo queda registrado','Se genera automaticamente un asiento contable de egreso','Se envia al proveedor','Se descuenta de inventario']), 'respuesta_correcta': 1, 'orden': 4},
                ]
            },
            {
                'titulo': 'Nomina Colombiana',
                'descripcion': 'Liquida nomina mensual con parafiscales, horas extra, incapacidades y retencion en la fuente.',
                'modulo_crm': 'nomina', 'icono': 'bi-people-fill', 'orden': 5, 'nivel': 'avanzado',
                'roles_objetivo': json.dumps(['contador','director_financiero','admin']),
                'lecciones': [
                    {'titulo': 'Registrar empleados', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Crear un empleado con salario, tipo de contrato y afiliaciones.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Nomina</strong> y clic en <strong>+ Nuevo empleado</strong>.</div><div class="paso"><span class="paso-num">2</span>Completa: nombre, cedula, cargo, departamento, tipo de contrato.</div><div class="paso"><span class="paso-num">3</span>Define el salario base mensual.</div><div class="paso"><span class="paso-num">4</span>Indica si aplica auxilio de transporte (obligatorio para salarios < 2 SMLMV).</div><div class="paso"><span class="paso-num">5</span>Selecciona nivel de riesgo ARL (1 a 5).</div><div class="paso"><span class="paso-num">6</span>Completa EPS, fondo de pensiones y caja de compensacion.</div>'},
                    {'titulo': 'Liquidar nomina mensual', 'orden': 2, 'duracion_min': 8,
                     'contenido': '<h6>Objetivo</h6><p>Cerrar la nomina del mes con todos los calculos legales.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Nomina</strong> y clic en <strong>Cerrar nomina</strong>.</div><div class="paso"><span class="paso-num">2</span>El sistema calcula automaticamente: salud (4% empleado), pension (4% empleado), parafiscales patronales.</div><div class="paso"><span class="paso-num">3</span>Se aplica retencion en la fuente segun Art. 383 ET con tabla de UVT.</div><div class="paso"><span class="paso-num">4</span>Se prorratea por dias trabajados si el empleado no trabajo el mes completo.</div><div class="paso"><span class="paso-num">5</span>Al cerrar se genera automaticamente un gasto operativo por el total de nomina.</div><div class="alerta"><i class="bi bi-exclamation-triangle me-1"></i>Si no cierras nomina antes del dia 5 del mes siguiente, se genera un ticket automatico al admin.</div>'},
                    {'titulo': 'Horas extra e incapacidades', 'orden': 3, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Registrar horas extra, incapacidades y vacaciones.</p><div class="paso"><span class="paso-num">1</span><strong>Horas extra</strong>: desde la ficha del empleado, registra tipo (diurna, nocturna, dominical), fecha y cantidad.</div><div class="paso"><span class="paso-num">2</span>Los recargos se calculan segun Art. 168-170 del CST.</div><div class="paso"><span class="paso-num">3</span><strong>Incapacidades</strong>: registra fecha inicio, fin y tipo (general, laboral).</div><div class="paso"><span class="paso-num">4</span><strong>Vacaciones</strong>: registra periodos tomados.</div><div class="paso"><span class="paso-num">5</span>Todos se reflejan automaticamente en la liquidacion del mes.</div>'},
                ],
                'preguntas': [
                    {'texto': 'A partir de que monto de salario NO aplica auxilio de transporte?', 'opciones': json.dumps(['1 SMLMV','2 SMLMV','3 SMLMV','Siempre aplica']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que porcentaje de salud aporta el empleado?', 'opciones': json.dumps(['8%','4%','12.5%','2%']), 'respuesta_correcta': 1, 'orden': 2},
                    {'texto': 'Que pasa si no se cierra la nomina antes del 5 del mes siguiente?', 'opciones': json.dumps(['Nada','Se bloquea el sistema','Se genera un ticket automatico al admin','Se pierde la informacion']), 'respuesta_correcta': 2, 'orden': 3},
                    {'texto': 'Que articulo del ET regula la retencion en la fuente por salarios?', 'opciones': json.dumps(['Art. 168','Art. 240','Art. 383','Art. 500']), 'respuesta_correcta': 2, 'orden': 4},
                ]
            },
            {
                'titulo': 'Inventario y Lotes',
                'descripcion': 'Gestiona productos terminados, materias primas, lotes con trazabilidad FIFO y alertas de stock.',
                'modulo_crm': 'inventario', 'icono': 'bi-box-seam-fill', 'orden': 6, 'nivel': 'basico',
                'roles_objetivo': json.dumps(['produccion','director_operativo','admin']),
                'lecciones': [
                    {'titulo': 'Registrar productos terminados', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Crear un producto con precio, SKU y stock minimo.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Inventario → Productos</strong>.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nuevo</strong>.</div><div class="paso"><span class="paso-num">3</span>Completa: nombre, precio de venta, stock minimo.</div><div class="paso"><span class="paso-num">4</span>El SKU se genera automaticamente si no lo defines.</div><div class="paso"><span class="paso-num">5</span>El stock solo se incrementa mediante produccion completada o ingresos manuales.</div>'},
                    {'titulo': 'Gestionar materias primas', 'orden': 2, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Registrar y controlar materias primas con alertas de stock minimo.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Produccion → Materias primas</strong>.</div><div class="paso"><span class="paso-num">2</span>Crea materias primas con nombre, unidad de medida, stock minimo y proveedor.</div><div class="paso"><span class="paso-num">3</span>El stock se actualiza automaticamente al registrar compras.</div><div class="paso"><span class="paso-num">4</span>Cuando el stock baja del minimo, aparece alerta en el dashboard.</div>'},
                    {'titulo': 'Lotes y trazabilidad', 'orden': 3, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Entender el sistema de lotes con FIFO y vencimiento.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Inventario → Lotes</strong>.</div><div class="paso"><span class="paso-num">2</span>Cada lote tiene: numero, fecha de ingreso, fecha de vencimiento y cantidad.</div><div class="paso"><span class="paso-num">3</span>El sistema usa <strong>FIFO</strong>: primero sale el lote mas antiguo.</div><div class="paso"><span class="paso-num">4</span>Los lotes proximos a vencer generan alertas automaticas.</div><div class="paso"><span class="paso-num">5</span>Toda salida queda trazada al lote de origen.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Como se incrementa el stock de productos terminados?', 'opciones': json.dumps(['Editando el producto manualmente','Mediante produccion completada o ingresos','Desde Asientos Contables','Desde el portal del cliente']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que significa FIFO en el contexto de inventario?', 'opciones': json.dumps(['First In, First Out — primero entra, primero sale','Fast Inventory, Fast Output','Final Inventory Financial Order','No tiene significado especial']), 'respuesta_correcta': 0, 'orden': 2},
                    {'texto': 'Que pasa cuando el stock de una materia prima baja del minimo?', 'opciones': json.dumps(['Se bloquea la produccion','Aparece una alerta en el dashboard','Se hace pedido automatico','Nada']), 'respuesta_correcta': 1, 'orden': 3},
                ]
            },
            {
                'titulo': 'Tickets y Gestion de Tareas',
                'descripcion': 'Crea y gestiona tickets de trabajo, asigna responsables y da seguimiento.',
                'modulo_crm': 'tareas', 'icono': 'bi-check2-square', 'orden': 7, 'nivel': 'basico',
                'roles_objetivo': json.dumps([]),
                'lecciones': [
                    {'titulo': 'Crear y asignar tickets', 'orden': 1, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Crear un ticket con prioridad, tipo y asignarlo a un equipo.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Tickets</strong> en el sidebar.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nueva</strong>.</div><div class="paso"><span class="paso-num">3</span>Define titulo, descripcion, prioridad (baja/media/alta) y categoria.</div><div class="paso"><span class="paso-num">4</span>Asigna a uno o varios usuarios responsables.</div><div class="paso"><span class="paso-num">5</span>Define fecha de vencimiento si aplica.</div>'},
                    {'titulo': 'Tickets automaticos del sistema', 'orden': 2, 'duracion_min': 4,
                     'contenido': '<h6>Objetivo</h6><p>Entender los tickets que el CRM crea automaticamente.</p><div class="paso"><span class="paso-num">1</span><strong>Nomina pendiente</strong>: si no cierras nomina a tiempo, se crea ticket al admin.</div><div class="paso"><span class="paso-num">2</span><strong>Transporte OC</strong>: al asignar transportista a una OC, se crea ticket 2 dias antes de la recogida.</div><div class="paso"><span class="paso-num">3</span><strong>Calidad</strong>: reportar problemas en produccion crea tickets automaticos.</div><div class="paso"><span class="paso-num">4</span><strong>Stock bajo</strong>: alertas de inventario generan tickets.</div><div class="tip"><i class="bi bi-lightbulb me-1"></i>Los tickets automaticos tienen tipo y categoria especificos para filtrarlos facilmente.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Que tipos de tickets crea el sistema automaticamente?', 'opciones': json.dumps(['Solo de ventas','Nomina pendiente, transporte OC, calidad y stock bajo','Solo de produccion','El sistema no crea tickets automaticos']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Cuantos dias antes de la recogida se crea el ticket de transporte?', 'opciones': json.dumps(['1 dia','2 dias','5 dias','El mismo dia']), 'respuesta_correcta': 1, 'orden': 2},
                ]
            },
            {
                'titulo': 'Empaques y Logistica',
                'descripcion': 'Configura empaques secundarios, calcula distribuciones y gestiona despachos.',
                'modulo_crm': 'empaques', 'icono': 'bi-truck', 'orden': 8, 'nivel': 'intermedio',
                'roles_objetivo': json.dumps(['produccion','director_operativo','admin']),
                'lecciones': [
                    {'titulo': 'Configurar empaques secundarios', 'orden': 1, 'duracion_min': 6,
                     'contenido': '<h6>Objetivo</h6><p>Definir como se empaca un producto en cajas para envio.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Empaques</strong> desde el dock de Logistica.</div><div class="paso"><span class="paso-num">2</span>Clic en <strong>+ Nuevo</strong>.</div><div class="paso"><span class="paso-num">3</span>Selecciona el producto y define: dimensiones unitarias (alto, ancho, largo en cm) y peso por unidad (kg).</div><div class="paso"><span class="paso-num">4</span>Define el peso maximo por caja.</div><div class="paso"><span class="paso-num">5</span>El sistema calcula automaticamente las unidades por caja y las dimensiones optimas.</div><div class="paso"><span class="paso-num">6</span>Al <strong>aprobar</strong> el empaque, se crea una materia prima tipo "caja" y cotizaciones para caja y cinta.</div>'},
                    {'titulo': 'Calculadora de envio', 'orden': 2, 'duracion_min': 5,
                     'contenido': '<h6>Objetivo</h6><p>Calcular el costo de envio con transportistas y comparar opciones.</p><div class="paso"><span class="paso-num">1</span>Ve a <strong>Logistica → Calculadora de envio</strong>.</div><div class="paso"><span class="paso-num">2</span>Ingresa: origen, destino, peso total y volumen.</div><div class="paso"><span class="paso-num">3</span>El sistema compara tarifas FTL vs paqueteria.</div><div class="paso"><span class="paso-num">4</span>Selecciona transportistas compatibles registrados en el sistema.</div><div class="paso"><span class="paso-num">5</span>Calcula costo con margen incluido.</div>'},
                ],
                'preguntas': [
                    {'texto': 'Que se crea automaticamente al aprobar un empaque secundario?', 'opciones': json.dumps(['Un producto nuevo','Una materia prima tipo "caja" y cotizaciones para caja y cinta','Un asiento contable','Una orden de produccion']), 'respuesta_correcta': 1, 'orden': 1},
                    {'texto': 'Que calcula el sistema al definir las dimensiones y peso de un empaque?', 'opciones': json.dumps(['Solo el precio','Las unidades por caja y dimensiones optimas de la caja','La ruta de envio','El tiempo de entrega']), 'respuesta_correcta': 1, 'orden': 2},
                ]
            },
        ]

        for cd in CURSOS:
            curso = CapCurso(
                titulo=cd['titulo'], descripcion=cd['descripcion'],
                modulo_crm=cd['modulo_crm'], icono=cd['icono'],
                orden=cd['orden'], nivel=cd['nivel'],
                roles_objetivo=cd['roles_objetivo']
            )
            db.session.add(curso)
            db.session.flush()
            for ld in cd.get('lecciones', []):
                db.session.add(CapLeccion(
                    curso_id=curso.id, titulo=ld['titulo'],
                    contenido=ld['contenido'], orden=ld['orden'],
                    duracion_min=ld['duracion_min']
                ))
            for pd in cd.get('preguntas', []):
                db.session.add(CapPregunta(
                    curso_id=curso.id, texto=pd['texto'],
                    opciones=pd['opciones'],
                    respuesta_correcta=pd['respuesta_correcta'],
                    orden=pd['orden']
                ))
        db.session.commit()
        logging.info(f'Capacitacion: {len(CURSOS)} cursos sembrados con lecciones y preguntas')
    except Exception as e:
        db.session.rollback()
        logging.warning(f'Seed capacitacion: {e}')

    # Update lessons with practice steps (runs every time, idempotent)
    try:
        _update_cap_practice_steps()
    except Exception as e:
        logging.warning(f'Cap practice steps update: {e}')


def _update_cap_practice_steps():
    """Add practice step definitions and route targets to lessons."""
    import json
    STEPS = {
        'Crear un cliente nuevo': {
            'ruta_practica': 'cliente_nuevo',
            'pasos': [{'codigo': 'crear_cliente', 'label': 'Crear un cliente con empresa y NIT', 'entidad': 'cliente'}]
        },
        'Elaborar una cotizacion': {
            'ruta_practica': 'cotizacion_nueva',
            'pasos': [{'codigo': 'crear_cotizacion', 'label': 'Crear una cotizacion con items', 'entidad': 'cotizacion'}]
        },
        'Convertir cotizacion en venta': {
            'ruta_practica': 'ventas_index',
            'pasos': [{'codigo': 'crear_venta', 'label': 'Crear o convertir una venta', 'entidad': 'venta'}]
        },
        'Registrar un proveedor': {
            'ruta_practica': 'proveedor_nuevo',
            'pasos': [{'codigo': 'crear_proveedor', 'label': 'Registrar un proveedor', 'entidad': 'proveedor'}]
        },
        'Crear cotizacion de proveedor': {
            'ruta_practica': 'cotizacion_proveedor_nueva',
            'pasos': [{'codigo': 'crear_cot_prov', 'label': 'Crear cotizacion de proveedor', 'entidad': 'cotizacion_proveedor'}]
        },
        'Generar orden de compra': {
            'ruta_practica': 'orden_compra_nueva',
            'pasos': [{'codigo': 'crear_oc', 'label': 'Crear una orden de compra', 'entidad': 'orden_compra'}]
        },
        'Crear una receta de producto (BOM)': {
            'ruta_practica': 'receta_nueva',
            'pasos': [
                {'codigo': 'crear_receta', 'label': 'Crear una receta con ingredientes', 'entidad': 'receta'},
            ]
        },
        'Registrar productos terminados': {
            'ruta_practica': 'producto_nuevo',
            'pasos': [{'codigo': 'crear_producto', 'label': 'Crear un producto terminado', 'entidad': 'producto'}]
        },
        'Registrar empleados': {
            'ruta_practica': 'empleado_nuevo',
            'pasos': [{'codigo': 'crear_empleado', 'label': 'Registrar un empleado', 'entidad': 'empleado'}]
        },
        'Crear y asignar tickets': {
            'ruta_practica': 'tarea_nueva',
            'pasos': [{'codigo': 'crear_tarea', 'label': 'Crear un ticket', 'entidad': 'tarea'}]
        },
        'Configurar empaques secundarios': {
            'ruta_practica': 'empaques_nuevo',
            'pasos': [{'codigo': 'crear_empaque', 'label': 'Crear un empaque secundario', 'entidad': 'empaque'}]
        },
    }
    updated = 0
    for titulo, data in STEPS.items():
        leccion = CapLeccion.query.filter_by(titulo=titulo).first()
        if not leccion:
            continue
        changed = False
        if data.get('ruta_practica') and leccion.ruta_practica != data['ruta_practica']:
            leccion.ruta_practica = data['ruta_practica']
            changed = True
        if data.get('pasos'):
            new_pasos = json.dumps(data['pasos'])
            if leccion.pasos != new_pasos:
                leccion.pasos = new_pasos
                changed = True
        if changed:
            updated += 1
    if updated:
        db.session.commit()
