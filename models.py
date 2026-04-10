# models.py — All SQLAlchemy models + DB init
from extensions import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date as date_type
import json, secrets, os, logging

__all__ = ['User', 'ContactoCliente', 'Cliente', 'OrdenCompra', 'OrdenCompraItem', 'Proveedor', 'VentaProducto', 'Venta', 'TareaAsignado', 'TareaComentario', 'Tarea', 'Producto', 'CompraMateria', 'CotizacionProveedor', 'CotizacionGranel', 'DocumentoLegal', 'AsientoContable', 'ReglaTributaria', 'GastoOperativo', 'Nota', 'Actividad', 'ConfigEmpresa', 'Evento', 'CotizacionItem', 'Cotizacion', 'LoteProducto', 'MateriaPrima', 'MateriaPrimaProducto', 'LoteMateriaPrima', 'RecetaProducto', 'RecetaItem', 'ReservaProduccion', 'OrdenProduccion', 'Notificacion', 'Empleado', 'UserSesion', 'PreCotizacionItem', 'PreCotizacion', 'load_user', '_migrate', 'init_db']


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id                  = db.Column(db.Integer, primary_key=True)
    nombre              = db.Column(db.String(100), nullable=False)
    email               = db.Column(db.String(120), unique=True, nullable=False)
    password_hash       = db.Column(db.String(256), nullable=False)
    rol                 = db.Column(db.String(20), default='usuario')
    activo              = db.Column(db.Boolean, default=True)
    modulos_permitidos  = db.Column(db.Text, default='[]')   # JSON list
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    onboarding_dismissed = db.Column(db.Boolean, default=False)
    cliente_id           = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    proveedor_id        = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    def set_password(self, p):   self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)

class ContactoCliente(db.Model):
    __tablename__ = 'contactos_cliente'
    id         = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=False)
    nombre     = db.Column(db.String(100), nullable=False)
    cargo      = db.Column(db.String(100))
    email      = db.Column(db.String(120))
    telefono   = db.Column(db.String(20))

class Cliente(db.Model):
    __tablename__ = 'clientes'
    id              = db.Column(db.Integer, primary_key=True)
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
    contactos       = db.relationship('ContactoCliente', backref='cliente_rel', lazy=True, cascade='all, delete-orphan')
    ventas          = db.relationship('Venta', backref='cliente', lazy=True)
    sales_manager    = db.relationship('User', foreign_keys=[sales_manager_id])

class OrdenCompra(db.Model):
    __tablename__ = 'ordenes_compra'
    id                      = db.Column(db.Integer, primary_key=True)
    numero                  = db.Column(db.String(20))               # OC-YYYY-NNN
    proveedor_id            = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    cotizacion_id           = db.Column(db.Integer, db.ForeignKey('cotizaciones_proveedor.id'), nullable=True)
    transportista_id        = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    estado                  = db.Column(db.String(30), default='borrador')  # borrador, enviada, recibida, cancelada
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
    estado_proveedor        = db.Column(db.String(30), default='pendiente')  # pendiente, confirmada
    confirmado_en           = db.Column(db.DateTime, nullable=True)
    confirmado_por          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
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
    creado_en  = db.Column(db.DateTime, default=datetime.utcnow)

class VentaProducto(db.Model):
    __tablename__ = 'venta_productos'
    id          = db.Column(db.Integer, primary_key=True)
    venta_id    = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    nombre_prod = db.Column(db.String(200))
    cantidad    = db.Column(db.Float, default=1)
    precio_unit = db.Column(db.Float, default=0)
    subtotal    = db.Column(db.Float, default=0)

class Venta(db.Model):
    __tablename__ = 'ventas'
    id                  = db.Column(db.Integer, primary_key=True)
    titulo              = db.Column(db.String(200), nullable=False)
    cliente_id          = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    subtotal            = db.Column(db.Float, default=0)
    iva                 = db.Column(db.Float, default=0)
    total               = db.Column(db.Float, default=0)
    porcentaje_anticipo = db.Column(db.Float, default=0)
    monto_anticipo      = db.Column(db.Float, default=0)
    saldo               = db.Column(db.Float, default=0)
    estado              = db.Column(db.String(30), default='prospecto')
    fecha_anticipo      = db.Column(db.Date)
    dias_entrega        = db.Column(db.Integer, default=30)
    fecha_entrega_est   = db.Column(db.Date)
    notas               = db.Column(db.Text)
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    numero              = db.Column(db.String(20))               # v12.3 VNT-YYYY-NNN
    cliente_informado_en= db.Column(db.DateTime, nullable=True)  # v12.2
    entregado_en        = db.Column(db.DateTime, nullable=True)   # v12.2
    items               = db.relationship('VentaProducto', backref='venta', lazy=True, cascade='all, delete-orphan')
    ordenes_produccion  = db.relationship('OrdenProduccion', foreign_keys='OrdenProduccion.venta_id', lazy=True, back_populates='venta')

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
    titulo            = db.Column(db.String(200), nullable=False)
    descripcion       = db.Column(db.Text)
    estado            = db.Column(db.String(20), default='pendiente')
    prioridad         = db.Column(db.String(10), default='media')
    fecha_vencimiento = db.Column(db.Date)
    asignado_a        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)
    cotizacion_id     = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)
    tarea_tipo        = db.Column(db.String(50), nullable=True)   # comprar_materias, verificar_abono
    tarea_pareja_id   = db.Column(db.Integer, db.ForeignKey('tareas.id'), nullable=True)
    asignado_user     = db.relationship('User', foreign_keys=[asignado_a], backref='tareas_asignadas')
    creador           = db.relationship('User', foreign_keys=[creado_por])
    asignados         = db.relationship('TareaAsignado', backref='tarea', lazy=True, cascade='all, delete-orphan')
    comentarios       = db.relationship('TareaComentario', backref='tarea', lazy=True, cascade='all, delete-orphan', order_by='TareaComentario.creado_en')

class Producto(db.Model):
    __tablename__ = 'productos'
    id           = db.Column(db.Integer, primary_key=True)
    nombre       = db.Column(db.String(200), nullable=False)
    descripcion  = db.Column(db.Text)
    sku          = db.Column(db.String(50))
    nso          = db.Column(db.String(50))
    precio       = db.Column(db.Float, default=0)
    costo        = db.Column(db.Float, default=0)
    stock        = db.Column(db.Integer, default=0)
    stock_minimo    = db.Column(db.Integer, default=5)
    categoria       = db.Column(db.String(100))
    activo          = db.Column(db.Boolean, default=True)
    fecha_caducidad = db.Column(db.Date, nullable=True)
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    venta_items     = db.relationship('VentaProducto', backref='producto', lazy=True)

class CompraMateria(db.Model):
    __tablename__ = 'compras_materia'
    id              = db.Column(db.Integer, primary_key=True)
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
    producto        = db.relationship('Producto', foreign_keys=[producto_id])
    materia         = db.relationship('MateriaPrima', foreign_keys=[materia_id])
    proveedor_rel   = db.relationship('Proveedor', foreign_keys=[proveedor_id])

class CotizacionProveedor(db.Model):
    __tablename__ = 'cotizaciones_proveedor'
    id                    = db.Column(db.Integer, primary_key=True)
    numero                = db.Column(db.String(20))               # CP-YYYY-NNN
    proveedor_id          = db.Column(db.Integer, db.ForeignKey('proveedores.id'), nullable=True)
    tipo_cotizacion       = db.Column(db.String(20), default='general')  # granel, general
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
    proveedor             = db.relationship('Proveedor', foreign_keys=[proveedor_id])

class CotizacionGranel(db.Model):
    __tablename__ = 'cotizaciones_granel'
    id               = db.Column(db.Integer, primary_key=True)
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
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)

class AsientoContable(db.Model):
    __tablename__ = 'asientos_contables'
    id          = db.Column(db.Integer, primary_key=True)
    numero      = db.Column(db.String(20))     # AC-YYYY-NNN
    fecha       = db.Column(db.Date, nullable=False)
    descripcion = db.Column(db.String(300), nullable=False)
    tipo        = db.Column(db.String(30), default='manual')  # manual, venta, compra, gasto
    referencia  = db.Column(db.String(100))
    debe        = db.Column(db.Float, default=0)
    haber       = db.Column(db.Float, default=0)
    cuenta_debe = db.Column(db.String(100))
    cuenta_haber= db.Column(db.String(100))
    notas       = db.Column(db.Text)
    creado_por  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)

class ReglaTributaria(db.Model):
    __tablename__ = 'reglas_tributarias'
    id               = db.Column(db.Integer, primary_key=True)
    nombre           = db.Column(db.String(100), nullable=False)
    descripcion      = db.Column(db.Text)
    porcentaje       = db.Column(db.Float, default=0)
    aplica_a         = db.Column(db.String(30), default='ventas')  # ventas, ingresos, profit, proveedor_producto, proveedor_granel
    proveedor_nombre = db.Column(db.String(200))
    activo           = db.Column(db.Boolean, default=True)
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)

class GastoOperativo(db.Model):
    __tablename__ = 'gastos_operativos'
    id           = db.Column(db.Integer, primary_key=True)
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

class Nota(db.Model):
    __tablename__ = 'notas'
    id             = db.Column(db.Integer, primary_key=True)
    titulo         = db.Column(db.String(200))
    contenido      = db.Column(db.Text, nullable=False)
    cliente_id     = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    producto_id    = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    modulo         = db.Column(db.String(50))   # ventas, produccion, inventario, gastos, tareas, otro
    fecha_revision = db.Column(db.Date, nullable=True)
    creado_por     = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow)
    cliente        = db.relationship('Cliente', foreign_keys=[cliente_id])
    producto       = db.relationship('Producto', foreign_keys=[producto_id])
    autor          = db.relationship('User', foreign_keys=[creado_por])

class Actividad(db.Model):
    __tablename__ = 'actividades'
    id          = db.Column(db.Integer, primary_key=True)
    tipo        = db.Column(db.String(20))   # crear, editar, eliminar, completar
    entidad     = db.Column(db.String(50))   # cliente, venta, tarea, nota...
    entidad_id  = db.Column(db.Integer)
    descripcion = db.Column(db.String(300))
    usuario_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    usuario     = db.relationship('User', foreign_keys=[usuario_id])

class ConfigEmpresa(db.Model):
    __tablename__ = 'config_empresa'
    id        = db.Column(db.Integer, primary_key=True)
    nombre    = db.Column(db.String(200), default='Evore')
    nit       = db.Column(db.String(30))
    direccion = db.Column(db.Text)
    telefono  = db.Column(db.String(30))
    email     = db.Column(db.String(120))
    ciudad    = db.Column(db.String(100))
    sitio_web = db.Column(db.String(200))

class Evento(db.Model):
    __tablename__ = 'eventos'
    id          = db.Column(db.Integer, primary_key=True)
    titulo      = db.Column(db.String(200), nullable=False)
    tipo        = db.Column(db.String(20), default='recordatorio')  # cita, reunion, recordatorio
    fecha       = db.Column(db.Date, nullable=False)
    hora_inicio = db.Column(db.String(5))
    hora_fin    = db.Column(db.String(5))
    descripcion = db.Column(db.Text)
    usuario_id  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)
    usuario     = db.relationship('User', foreign_keys=[usuario_id])

class CotizacionItem(db.Model):
    __tablename__ = 'cotizacion_items'
    id            = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=False)
    producto_id   = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    nombre_prod   = db.Column(db.String(200))
    cantidad      = db.Column(db.Float, default=1)
    precio_unit   = db.Column(db.Float, default=0)
    subtotal      = db.Column(db.Float, default=0)

class Cotizacion(db.Model):
    __tablename__ = 'cotizaciones'
    id                  = db.Column(db.Integer, primary_key=True)
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
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    items               = db.relationship('CotizacionItem', backref='cotizacion', lazy=True, cascade='all, delete-orphan')
    cliente             = db.relationship('Cliente', foreign_keys=[cliente_id])

class LoteProducto(db.Model):
    __tablename__ = 'lotes_producto'
    id                  = db.Column(db.Integer, primary_key=True)
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
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    unidades_produce = db.Column(db.Integer, default=1)    # cuántas unidades produce esta receta
    descripcion      = db.Column(db.Text)
    activo           = db.Column(db.Boolean, default=True)
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
    materia          = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])

class ReservaProduccion(db.Model):
    __tablename__ = 'reservas_produccion'
    id               = db.Column(db.Integer, primary_key=True)
    materia_prima_id = db.Column(db.Integer, db.ForeignKey('materias_primas.id'), nullable=False)
    cantidad         = db.Column(db.Float, default=0)
    estado           = db.Column(db.String(20), default='reservado')  # reservado, usado, cancelado
    producto_id      = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    lote_id          = db.Column(db.Integer, db.ForeignKey('lotes_producto.id'), nullable=True)
    lote_materia_prima_id = db.Column(db.Integer, db.ForeignKey('lotes_materia_prima.id'), nullable=True)
    notas            = db.Column(db.Text)
    creado_por       = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en        = db.Column(db.DateTime, default=datetime.utcnow)
    venta_id         = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    materia          = db.relationship('MateriaPrima', foreign_keys=[materia_prima_id])
    producto         = db.relationship('Producto', foreign_keys=[producto_id])
    venta            = db.relationship('Venta', foreign_keys=[venta_id])
    lote_mp          = db.relationship('LoteMateriaPrima', foreign_keys=[lote_materia_prima_id])

class OrdenProduccion(db.Model):
    __tablename__ = 'ordenes_produccion'
    id                = db.Column(db.Integer, primary_key=True)
    cotizacion_id     = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=True)
    venta_id          = db.Column(db.Integer, db.ForeignKey('ventas.id'), nullable=True)
    producto_id       = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    cantidad_total    = db.Column(db.Float, default=0)   # total requerido
    cantidad_stock    = db.Column(db.Float, default=0)   # ya en stock al crear
    cantidad_producir = db.Column(db.Float, default=0)   # diferencia a producir
    numero_lote       = db.Column(db.String(80))
    estado            = db.Column(db.String(30), default='en_produccion')
    # pendiente_materiales | en_produccion | completado
    notas             = db.Column(db.Text)
    creado_por        = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en         = db.Column(db.DateTime, default=datetime.utcnow)
    completado_en     = db.Column(db.DateTime, nullable=True)
    fecha_inicio_real = db.Column(db.Date, nullable=True)      # v14 Gantt
    fecha_fin_estimada= db.Column(db.Date, nullable=True)      # v14 Gantt
    producto          = db.relationship('Producto', foreign_keys=[producto_id])
    cotizacion        = db.relationship('Cotizacion', foreign_keys=[cotizacion_id])
    venta             = db.relationship('Venta', foreign_keys=[venta_id], back_populates='ordenes_produccion')

class Notificacion(db.Model):
    __tablename__ = 'notificaciones'
    id         = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo       = db.Column(db.String(40), default='info')  # tarea_asignada, alerta_stock, info
    titulo     = db.Column(db.String(200), nullable=False)
    mensaje    = db.Column(db.Text)
    url        = db.Column(db.String(300))
    leida      = db.Column(db.Boolean, default=False)
    creado_en  = db.Column(db.DateTime, default=datetime.utcnow)
    usuario    = db.relationship('User', foreign_keys=[usuario_id])

class Empleado(db.Model):
    __tablename__ = 'empleados'
    id                  = db.Column(db.Integer, primary_key=True)
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
    estado              = db.Column(db.String(20), default='activo')  # activo, inactivo, retirado
    fecha_ingreso       = db.Column(db.Date)
    fecha_retiro        = db.Column(db.Date, nullable=True)
    motivo_retiro       = db.Column(db.String(30), nullable=True)  # renuncia, despido_justa, despido_sin_justa, mutuo_acuerdo
    notas               = db.Column(db.Text)
    creado_por          = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en           = db.Column(db.DateTime, default=datetime.utcnow)

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
    ]
    for sql in migrations:
        try:
            conn.execute(db.text(sql))
            conn.commit()
        except Exception as em:
            try: conn.rollback()
            except: pass
            print(f'Migración omitida (puede ser SQLite o ya existe): {em}')

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
    _admin_email = os.environ.get('ADMIN_EMAIL', 'admin@evore.us')
    if not User.query.filter_by(email=_admin_email).first():
        _admin_pass = os.environ.get('ADMIN_PASSWORD')
        if not _admin_pass:
            _admin_pass = secrets.token_urlsafe(14)
            logging.warning('ADMIN AUTO-GENERATED PASSWORD (save this!): %s', _admin_pass)
        admin = User(nombre='Administrador', email=_admin_email, rol='admin')
        admin.set_password(_admin_pass)
        db.session.add(admin); db.session.commit()
    if not ConfigEmpresa.query.first():
        db.session.add(ConfigEmpresa(nombre='Evore', email='contacto@evore.us', sitio_web='evore.us'))
        db.session.commit()