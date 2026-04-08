# =============================================================
# EVORE CRM — v8 (Tareas+Chat, Producción, Compras, Granel, Impuestos, NSO)
# =============================================================

from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os, json
from jinja2 import DictLoader

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'evore-crm-2024-key')
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///crm.db')
if _db_url.startswith('postgres://'): _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Inicia sesión para continuar.'
login_manager.login_message_category = 'warning'

@app.context_processor
def inject_globals(): return {'now': datetime.utcnow()}

@app.template_filter('cop')
def cop(value):
    try: return '$ {:,.0f}'.format(float(value or 0)).replace(',','.')
    except: return '$ 0'

@app.template_filter('moneda')
def moneda(value):
    try: return '${:,.2f}'.format(float(value or 0))
    except: return '$0.00'

@app.template_filter('moneda0')
def moneda0(value):
    try: return '${:,.0f}'.format(float(value or 0))
    except: return '$0'

# =============================================================
# MODELOS
# =============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    nombre        = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    rol           = db.Column(db.String(20), default='usuario')
    activo        = db.Column(db.Boolean, default=True)
    creado_en     = db.Column(db.DateTime, default=datetime.utcnow)
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
    contactos       = db.relationship('ContactoCliente', backref='cliente_rel', lazy=True, cascade='all, delete-orphan')
    ventas          = db.relationship('Venta', backref='cliente', lazy=True)

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
    items               = db.relationship('VentaProducto', backref='venta', lazy=True, cascade='all, delete-orphan')

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
    stock_minimo = db.Column(db.Integer, default=5)
    categoria    = db.Column(db.String(100))
    activo       = db.Column(db.Boolean, default=True)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    venta_items  = db.relationship('VentaProducto', backref='producto', lazy=True)

class CompraMateria(db.Model):
    __tablename__ = 'compras_materia'
    id              = db.Column(db.Integer, primary_key=True)
    producto_id     = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    nombre_item     = db.Column(db.String(200), nullable=False)
    proveedor       = db.Column(db.String(200))
    fecha           = db.Column(db.Date, nullable=False)
    nro_factura     = db.Column(db.String(100))
    cantidad        = db.Column(db.Float, default=1)
    costo_producto  = db.Column(db.Float, default=0)
    impuestos       = db.Column(db.Float, default=0)
    transporte      = db.Column(db.Float, default=0)
    costo_total     = db.Column(db.Float, default=0)
    precio_unitario = db.Column(db.Float, default=0)
    notas           = db.Column(db.Text)
    creado_por      = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en       = db.Column(db.DateTime, default=datetime.utcnow)
    producto        = db.relationship('Producto', foreign_keys=[producto_id])

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

class ReglaTributaria(db.Model):
    __tablename__ = 'reglas_tributarias'
    id          = db.Column(db.Integer, primary_key=True)
    nombre      = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    porcentaje  = db.Column(db.Float, default=0)
    aplica_a    = db.Column(db.String(100))
    activo      = db.Column(db.Boolean, default=True)
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)

class GastoOperativo(db.Model):
    __tablename__ = 'gastos_operativos'
    id          = db.Column(db.Integer, primary_key=True)
    fecha       = db.Column(db.Date, nullable=False)
    tipo        = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(200))
    monto       = db.Column(db.Float, default=0, nullable=False)
    notas       = db.Column(db.Text)
    creado_por  = db.Column(db.Integer, db.ForeignKey('users.id'))
    creado_en   = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

# =============================================================
# TEMPLATES
# =============================================================

_CSS = """{% raw %}<style>
:root{--sb:#1a1f36;--ac:#5e72e4;--bg:#f4f6fb}
body{background:var(--bg);font-family:'Segoe UI',sans-serif}
#sb{position:fixed;top:0;left:0;height:100vh;width:252px;background:var(--sb);display:flex;flex-direction:column;z-index:1000}
.sb-brand{padding:1.3rem 1.2rem .85rem;color:#fff;font-size:1.3rem;font-weight:700;border-bottom:1px solid rgba(255,255,255,.08);letter-spacing:1px}
.sb-brand span{color:var(--ac)}
.sb-sec{font-size:.67rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,.3);padding:.65rem 1.2rem .2rem}
.sb-nav .nav-link{color:#a8b0d3;padding:.48rem 1.2rem;border-radius:8px;margin:.05rem .65rem;display:flex;align-items:center;gap:.65rem;font-size:.87rem;transition:all .2s}
.sb-nav .nav-link:hover{background:rgba(255,255,255,.07);color:#fff}
.sb-nav .nav-link.active{background:var(--ac);color:#fff}
.sb-nav .nav-link i{font-size:1rem;width:19px}
.sb-foot{padding:.85rem 1.2rem;border-top:1px solid rgba(255,255,255,.08);color:#a8b0d3;font-size:.82rem;margin-top:auto}
.u-name{color:#fff;font-weight:600}
.u-rol{font-size:.67rem;padding:2px 8px;border-radius:20px;background:rgba(94,114,228,.3);color:var(--ac)}
#main{margin-left:252px;min-height:100vh}
.topbar{background:#fff;padding:.68rem 1.4rem;border-bottom:1px solid #e8ecf0;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.pg-title{font-size:1.1rem;font-weight:600;color:#1a1f36;margin:0}
.content{padding:1.4rem}
.sc{background:#fff;border-radius:12px;padding:1.2rem 1.4rem;box-shadow:0 2px 8px rgba(0,0,0,.06);transition:transform .2s}
.sc:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}
.si{width:46px;height:46px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:1.3rem}
.sv{font-size:1.7rem;font-weight:700;color:#1a1f36}
.sl{color:#8898aa;font-size:.82rem}
.tc{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden}
.ch{background:#fff;border-bottom:1px solid #f0f0f0;padding:.85rem 1.4rem;font-weight:600;color:#1a1f36}
.table{margin:0}
.table th{font-size:.71rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#8898aa;border-bottom:1px solid #f0f0f0;padding:.65rem 1rem}
.table td{padding:.65rem 1rem;vertical-align:middle;border-bottom:1px solid #f8f9fa;color:#525f7f}
.table tbody tr:last-child td{border-bottom:none}
.table tbody tr:hover{background:#f8f9fe}
.b{padding:3px 10px;border-radius:20px;font-size:.72rem;font-weight:600}
.b-activo,.b-ganado,.b-completada,.b-baja,.b-vip,.b-vigente{background:#d4edda;color:#155724}
.b-inactivo,.b-perdido,.b-alta,.b-vencida{background:#f8d7da;color:#721c24}
.b-prospecto,.b-pendiente,.b-media,.b-anticipo_pagado,.b-en_revision{background:#fff3cd;color:#856404}
.b-negociacion,.b-en_progreso,.b-cliente_activo{background:#cce5ff;color:#004085}
.fc{background:#fff;border-radius:12px;padding:1.8rem;box-shadow:0 2px 8px rgba(0,0,0,.06);max-width:820px}
.form-label{font-weight:600;font-size:.875rem;color:#525f7f}
.form-control,.form-select{border:1.5px solid #e9ecef;border-radius:8px;padding:.5rem .75rem;font-size:.9rem;transition:border-color .2s}
.form-control:focus,.form-select:focus{border-color:var(--ac);box-shadow:0 0 0 3px rgba(94,114,228,.15)}
.btn-primary{background:var(--ac);border-color:var(--ac)}
.btn-primary:hover{background:#4a5bd4;border-color:#4a5bd4}
.alert{border-radius:10px;border:none}
.prod-row{background:#f8f9fe;border-radius:8px;padding:.75rem;margin-bottom:.5rem;border:1px solid #e8ecf0}
.totales-box{background:#f8f9fe;border-radius:10px;padding:1rem 1.4rem;border:1px solid #e8ecf0}
.chat-bubble{background:#f0f2ff;border-radius:12px 12px 12px 2px;padding:.65rem 1rem;margin-bottom:.5rem;max-width:80%}
.chat-bubble.mine{background:#5e72e4;color:#fff;border-radius:12px 12px 2px 12px;margin-left:auto}
.chat-bubble.mine .chat-meta{color:rgba(255,255,255,.7)}
.chat-meta{font-size:.72rem;color:#8898aa;margin-top:.25rem}
@media(max-width:768px){#sb{width:54px}#sb .nav-link span,.sb-brand .bt,.sb-sec,.ui{display:none}#main{margin-left:54px}}
</style>{% endraw %}"""

_CDN = """<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">"""
_BSJ = '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>'

T = {}

T['base.html'] = """<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{% block title %}Evore CRM{% endblock %}</title>
""" + _CDN + _CSS + """
</head><body>
<nav id="sb">
  <div class="sb-brand" style="padding:.85rem 1rem .7rem"><a href="/" style="text-decoration:none;color:inherit"><div class="d-flex align-items-center gap-2"><svg width="31" height="28" viewBox="0 0 100 90" fill="none" stroke="rgba(255,255,255,.88)" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M50,67 C44,63 41,35 50,5 C59,35 56,63 50,67Z"/><path d="M50,67 C41,64 23,43 27,20 C33,32 46,57 50,67Z"/><path d="M50,67 C59,64 77,43 73,20 C67,32 54,57 50,67Z"/><path d="M50,67 C37,65 11,53 13,35 C17,43 36,60 50,67Z"/><path d="M50,67 C63,65 89,53 87,35 C83,43 64,60 50,67Z"/><path d="M50,69 C39,74 19,76 4,69 C6,62 28,65 50,69Z"/><path d="M50,69 C61,74 81,76 96,69 C94,62 72,65 50,69Z"/><path d="M50,69 C46,73 46,81 50,83 C54,81 54,73 50,69Z"/></svg><span style="letter-spacing:4px;font-size:1.05rem;font-weight:700">EVORE<span class="bt" style="font-weight:300;font-size:.72rem;letter-spacing:1px;opacity:.65"> CRM</span></span></div></a></div>
  <div class="sb-nav py-2" style="overflow-y:auto;flex:1">
    <div class="sb-sec">Principal</div>
    <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint=='dashboard' %}active{% endif %}">
      <i class="bi bi-grid-1x2-fill"></i><span>Dashboard</span></a>
    <div class="sb-sec">Comercial</div>
    <a href="{{ url_for('clientes') }}" class="nav-link {% if 'cliente' in request.endpoint %}active{% endif %}">
      <i class="bi bi-people-fill"></i><span>Clientes</span></a>
    <a href="{{ url_for('ventas') }}" class="nav-link {% if 'venta' in request.endpoint %}active{% endif %}">
      <i class="bi bi-graph-up-arrow"></i><span>Ventas</span></a>
    <a href="{{ url_for('tareas') }}" class="nav-link {% if 'tarea' in request.endpoint %}active{% endif %}">
      <i class="bi bi-check2-square"></i><span>Tareas</span></a>
    <div class="sb-sec">Operaciones</div>
    <a href="{{ url_for('inventario') }}" class="nav-link {% if 'inventario' in request.endpoint or 'producto' in request.endpoint %}active{% endif %}">
      <i class="bi bi-box-seam-fill"></i><span>Inventario</span></a>
    <a href="{{ url_for('produccion_index') }}" class="nav-link {% if 'produccion' in request.endpoint or 'compra' in request.endpoint or 'granel' in request.endpoint or 'impuesto' in request.endpoint %}active{% endif %}">
      <i class="bi bi-gear-fill"></i><span>Producción</span></a>
    <a href="{{ url_for('gastos') }}" class="nav-link {% if 'gasto' in request.endpoint %}active{% endif %}">
      <i class="bi bi-receipt"></i><span>Gastos</span></a>
    <a href="{{ url_for('reportes') }}" class="nav-link {% if 'reporte' in request.endpoint %}active{% endif %}">
      <i class="bi bi-bar-chart-fill"></i><span>Reportes</span></a>
    {% if current_user.rol == 'admin' %}
    <div class="sb-sec">Admin</div>
    <a href="{{ url_for('admin_usuarios') }}" class="nav-link {% if 'admin' in request.endpoint %}active{% endif %}">
      <i class="bi bi-shield-person-fill"></i><span>Usuarios</span></a>
    {% endif %}
  </div>
  <div class="sb-foot">
    <div class="d-flex align-items-center gap-2">
      <div class="rounded-circle bg-primary d-flex align-items-center justify-content-center text-white fw-bold"
           style="width:31px;height:31px;font-size:.8rem;flex-shrink:0">{{ current_user.nombre[0].upper() }}</div>
      <div class="ui"><div class="u-name">{{ current_user.nombre }}</div>
        <span class="u-rol">{{ current_user.rol }}</span></div>
    </div>
    <a href="{{ url_for('perfil') }}" class="nav-link mt-1">
      <i class="bi bi-person-gear"></i><span>Mi perfil</span></a>
    <a href="{{ url_for('logout') }}" class="nav-link mt-1 text-danger">
      <i class="bi bi-box-arrow-right"></i><span>Salir</span></a>
  </div>
</nav>
<div id="main">
  <div class="topbar">
    <h1 class="pg-title">{% block page_title %}{% endblock %}</h1>
    <div class="d-flex align-items-center gap-3">
      {% block topbar_actions %}{% endblock %}
      <span class="text-muted" style="font-size:.82rem"><i class="bi bi-calendar3"></i> {{ now.strftime('%d %b %Y') }}</span>
    </div>
  </div>
  <div class="content">
    {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}{% for cat, msg in messages %}
    <div class="alert alert-{{ cat }} alert-dismissible fade show">{{ msg }}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button></div>
    {% endfor %}{% endif %}{% endwith %}
    {% block content %}{% endblock %}
  </div>
</div>
""" + _BSJ + """{% block scripts %}{% endblock %}
</body></html>"""

T['login.html'] = """<!DOCTYPE html>
<html lang="es"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evore CRM — Login</title>""" + _CDN + """
<style>
body{background:linear-gradient(135deg,#1a1f36,#2d3561);min-height:100vh;display:flex;align-items:center;justify-content:center;font-family:'Segoe UI',sans-serif}
.card{border-radius:20px;padding:2.3rem;width:100%;max-width:420px;box-shadow:0 20px 60px rgba(0,0,0,.3);border:none}
.brand{font-size:2rem;font-weight:800;color:#1a1f36}.brand span{color:#5e72e4}
.form-control{border:1.5px solid #e9ecef;border-radius:10px;padding:.62rem 1rem}
.form-control:focus{border-color:#5e72e4;box-shadow:0 0 0 3px rgba(94,114,228,.15)}
.igt{background:#f8f9fe;border:1.5px solid #e9ecef;border-right:none;color:#8898aa;border-radius:10px 0 0 10px}
.input-group .form-control{border-left:none;border-radius:0 10px 10px 0}
.btn-lg{background:linear-gradient(135deg,#5e72e4,#4a5bd4);border:none;color:#fff;padding:.75rem;border-radius:10px;font-weight:600;transition:all .3s;width:100%}
.btn-lg:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(94,114,228,.4);color:#fff}
</style></head><body>
<div class="card bg-white">
  <div class="text-center mb-4">
    <svg width="68" height="61" viewBox="0 0 100 90" fill="none" stroke="#d3af37" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M50,67 C44,63 41,35 50,5 C59,35 56,63 50,67Z"/><path d="M50,67 C41,64 23,43 27,20 C33,32 46,57 50,67Z"/><path d="M50,67 C59,64 77,43 73,20 C67,32 54,57 50,67Z"/><path d="M50,67 C37,65 11,53 13,35 C17,43 36,60 50,67Z"/><path d="M50,67 C63,65 89,53 87,35 C83,43 64,60 50,67Z"/><path d="M50,69 C39,74 19,76 4,69 C6,62 28,65 50,69Z"/><path d="M50,69 C61,74 81,76 96,69 C94,62 72,65 50,69Z"/><path d="M50,69 C46,73 46,81 50,83 C54,81 54,73 50,69Z"/></svg>
    <div style="font-size:1.85rem;font-weight:700;letter-spacing:10px;color:#1d1d1b;font-family:Georgia,'Times New Roman',serif;line-height:1.1;margin-top:.15rem">EVORE</div>
    <p class="text-muted mb-0" style="font-size:.78rem;letter-spacing:3px;margin-top:.25rem">SISTEMA DE GESTIÓN</p>
  </div>
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}{% for cat, msg in messages %}
  <div class="alert alert-{{ cat }} py-2 mb-3" style="border-radius:10px;border:none;font-size:.875rem">{{ msg }}</div>
  {% endfor %}{% endif %}{% endwith %}
  <form method="POST">
    <div class="mb-3"><label class="form-label fw-semibold" style="font-size:.875rem;color:#525f7f">Correo</label>
      <div class="input-group"><span class="input-group-text igt"><i class="bi bi-envelope"></i></span>
        <input type="email" name="email" class="form-control" required autofocus></div></div>
    <div class="mb-4"><label class="form-label fw-semibold" style="font-size:.875rem;color:#525f7f">Contraseña</label>
      <div class="input-group"><span class="input-group-text igt"><i class="bi bi-lock"></i></span>
        <input type="password" name="password" class="form-control" required></div></div>
    <button type="submit" class="btn btn-lg"><i class="bi bi-box-arrow-in-right me-2"></i>Iniciar Sesión</button>
  </form>
</div>""" + _BSJ + """</body></html>"""

T['dashboard.html'] = """{% extends 'base.html' %}
{% block title %}Dashboard{% endblock %}{% block page_title %}Dashboard{% endblock %}
{% block topbar_actions %}
<button id="btnM" class="btn btn-sm btn-outline-secondary" onclick="toggleMoneda()">
  <i class="bi bi-currency-exchange me-1"></i><span id="lblM">Ver en USD</span></button>
<small class="text-muted" id="tasaInfo"></small>
{% endblock %}
{% block content %}
<div class="row g-3 mb-3">
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv">{{ total_clientes }}</div><div class="sl">Clientes activos</div></div>
    <div class="si" style="background:#e8eeff"><i class="bi bi-people-fill" style="color:#5e72e4"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv">{{ ventas_ganadas }}</div><div class="sl">Ventas ganadas</div></div>
    <div class="si" style="background:#e3f9ee"><i class="bi bi-graph-up-arrow" style="color:#2dce89"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv">{{ tareas_pendientes }}</div><div class="sl">Tareas pendientes</div></div>
    <div class="si" style="background:#fff4e5"><i class="bi bi-check2-square" style="color:#fb6340"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv valor-cop" data-cop="{{ ingresos_totales }}">$ {{ '{:,.0f}'.format(ingresos_totales).replace(',','.') }}</div>
      <div class="sl">Ingresos COP</div></div>
    <div class="si" style="background:#fce8ff"><i class="bi bi-currency-dollar" style="color:#c300ff"></i></div>
  </div></div></div>
</div>
<div class="row g-3 mb-4">
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv valor-cop" data-cop="{{ gastos_totales }}">$ {{ '{:,.0f}'.format(gastos_totales).replace(',','.') }}</div>
      <div class="sl">Gastos operativos</div></div>
    <div class="si" style="background:#ffeaea"><i class="bi bi-receipt" style="color:#e74c3c"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv valor-cop" data-cop="{{ balance }}">$ {{ '{:,.0f}'.format(balance).replace(',','.') }}</div>
      <div class="sl">Balance neto</div></div>
    <div class="si" style="background:#e8fff3"><i class="bi bi-bar-chart-fill" style="color:#27ae60"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv valor-cop" data-cop="{{ saldo_pendiente }}">$ {{ '{:,.0f}'.format(saldo_pendiente).replace(',','.') }}</div>
      <div class="sl">Saldo por cobrar</div></div>
    <div class="si" style="background:#fff8e1"><i class="bi bi-hourglass-split" style="color:#f39c12"></i></div>
  </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc"><div class="d-flex justify-content-between align-items-start">
    <div><div class="sv">{{ productos_bajo_stock }}</div><div class="sl">Stock bajo</div></div>
    <div class="si" style="background:#ffeaea"><i class="bi bi-exclamation-triangle" style="color:#e74c3c"></i></div>
  </div></div></div>
</div>
<div class="row g-4">
  <div class="col-lg-6"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-check2-square me-2 text-warning"></i>Tareas pendientes</span>
      <a href="{{ url_for('tarea_nueva') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i></a></div>
    {% if tareas_recientes %}<table class="table"><tbody>
    {% for t in tareas_recientes %}<tr>
      <td><a href="{{ url_for('tarea_ver', id=t.id) }}" class="fw-semibold text-decoration-none" style="color:#1a1f36">{{ t.titulo }}</a>
        <div><small class="text-muted">{{ t.asignado_user.nombre if t.asignado_user else '' }}</small></div></td>
      <td><span class="b b-{{ t.prioridad }}">{{ t.prioridad.title() }}</span></td>
    </tr>{% endfor %}</tbody></table>
    {% else %}<div class="text-center text-muted py-4"><i class="bi bi-check2-all" style="font-size:2rem"></i>
      <p class="mt-2 mb-0">Sin pendientes</p></div>{% endif %}
  </div></div>
  <div class="col-lg-6"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-graph-up me-2 text-success"></i>Ventas recientes</span>
      <a href="{{ url_for('venta_nueva') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i></a></div>
    {% if ventas_recientes %}<table class="table"><tbody>
    {% for v in ventas_recientes %}<tr>
      <td><div class="fw-semibold" style="color:#1a1f36">{{ v.titulo }}</div>
        <small class="text-muted">{{ v.cliente.empresa or v.cliente.nombre if v.cliente else '—' }}</small></td>
      <td class="fw-semibold valor-cop" data-cop="{{ v.total }}">$ {{ '{:,.0f}'.format(v.total).replace(',','.') }}</td>
      <td><span class="b b-{{ v.estado }}">{{ v.estado.replace('_',' ').title() }}</span></td>
    </tr>{% endfor %}</tbody></table>
    {% else %}<div class="text-center text-muted py-4"><i class="bi bi-graph-up" style="font-size:2rem"></i>
      <p class="mt-2 mb-0">Sin ventas</p></div>{% endif %}
  </div></div>
</div>{% endblock %}
{% block scripts %}<script>
let tasaCOP=null,enUSD=false;
async function cargarTasa(){
  try{const r=await fetch('https://open.er-api.com/v6/latest/USD');
    const d=await r.json();tasaCOP=d.rates.COP;
    document.getElementById('tasaInfo').textContent='1 USD = $'+tasaCOP.toFixed(0).replace(/\B(?=(\d{3})+(?!\d))/g,'.')+ ' COP';
  }catch(e){}
}
function toggleMoneda(){
  if(!tasaCOP)return;enUSD=!enUSD;
  document.getElementById('lblM').textContent=enUSD?'Ver en COP':'Ver en USD';
  document.querySelectorAll('.valor-cop').forEach(el=>{
    const c=parseFloat(el.dataset.cop)||0;
    el.textContent=enUSD?'USD '+(c/tasaCOP).toLocaleString('en-US',{maximumFractionDigits:0}):'$ '+c.toLocaleString('es-CO',{maximumFractionDigits:0});
  });
}
cargarTasa();
</script>{% endblock %}"""

T['clientes/index.html'] = """{% extends 'base.html' %}
{% block title %}Clientes{% endblock %}{% block page_title %}Clientes{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('cliente_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nuevo</a>{% endblock %}
{% block content %}
<div class="tc mb-3"><div class="p-3"><form method="GET" class="row g-2 align-items-end">
  <div class="col-sm-4"><input type="text" name="buscar" class="form-control form-control-sm" placeholder="Nombre, empresa, NIT..." value="{{ busqueda }}"></div>
  <div class="col-sm-3"><select name="estado_rel" class="form-select form-select-sm">
    <option value="">Todas las relaciones</option>
    {% for er in ['prospecto','negociacion','cliente_activo','vip','inactivo','perdido'] %}
    <option value="{{ er }}" {% if estado_rel_f==er %}selected{% endif %}>{{ er.replace('_',' ').title() }}</option>{% endfor %}
  </select></div>
  <div class="col-auto">
    <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-search"></i></button>
    <a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm">Limpiar</a>
  </div>
</form></div></div>
<div class="tc"><div class="ch"><i class="bi bi-people-fill me-2"></i>{{ items|length }} cliente(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Empresa</th><th>NIT</th><th>Relación</th><th>Contacto principal</th><th>Alta</th><th></th></tr></thead>
  <tbody>{% for c in items %}<tr>
    <td><a href="{{ url_for('cliente_ver', id=c.id) }}" class="fw-semibold text-decoration-none" style="color:#1a1f36">{{ c.empresa or c.nombre }}</a>
      {% if c.empresa %}<div><small class="text-muted">{{ c.nombre }}</small></div>{% endif %}</td>
    <td><small class="text-muted">{{ c.nit or '—' }}</small></td>
    <td><span class="b b-{{ c.estado_relacion }}">{{ c.estado_relacion.replace('_',' ').title() }}</span></td>
    <td>{% if c.contactos %}<small>{{ c.contactos[0].nombre }}{% if c.contactos[0].cargo %} · {{ c.contactos[0].cargo }}{% endif %}</small>{% else %}—{% endif %}</td>
    <td><small class="text-muted">{{ c.creado_en.strftime('%d/%m/%Y') }}</small></td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('cliente_ver', id=c.id) }}" class="btn btn-sm btn-outline-primary"><i class="bi bi-eye"></i></a>
      <a href="{{ url_for('cliente_editar', id=c.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('cliente_eliminar', id=c.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-people" style="font-size:3rem"></i>
  <p class="mt-3">Sin clientes.</p><a href="{{ url_for('cliente_nuevo') }}" class="btn btn-primary">Agregar</a></div>
{% endif %}</div>{% endblock %}"""

T['clientes/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc" style="max-width:900px"><form method="POST">
<h6 class="text-muted mb-3 text-uppercase" style="letter-spacing:1px;font-size:.75rem">Información de la empresa</h6>
<div class="row g-3 mb-4">
  <div class="col-md-6"><label class="form-label">Empresa *</label>
    <input type="text" name="empresa" class="form-control" value="{{ obj.empresa if obj else '' }}" required></div>
  <div class="col-md-3"><label class="form-label">NIT</label>
    <input type="text" name="nit" class="form-control" placeholder="900.123.456-7" value="{{ obj.nit if obj else '' }}"></div>
  <div class="col-md-3"><label class="form-label">Estado relación</label>
    <select name="estado_relacion" class="form-select">
      {% for er,lbl in [('prospecto','Prospecto'),('negociacion','Negociación'),('cliente_activo','Cliente Activo'),('vip','VIP'),('inactivo','Inactivo'),('perdido','Perdido')] %}
      <option value="{{ er }}" {% if obj and obj.estado_relacion==er %}selected{% elif not obj and er=='prospecto' %}selected{% endif %}>{{ lbl }}</option>{% endfor %}
    </select></div>
  <div class="col-md-6"><label class="form-label">Dirección Cámara de Comercio</label>
    <input type="text" name="dir_comercial" class="form-control" value="{{ obj.dir_comercial if obj else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Dirección de entrega</label>
    <input type="text" name="dir_entrega" class="form-control" value="{{ obj.dir_entrega if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="2">{{ obj.notas if obj else '' }}</textarea></div>
</div><hr class="my-3">
<div class="d-flex justify-content-between align-items-center mb-3">
  <h6 class="text-muted mb-0 text-uppercase" style="letter-spacing:1px;font-size:.75rem">Contactos</h6>
  <button type="button" class="btn btn-sm btn-outline-primary" onclick="addContacto()"><i class="bi bi-plus-lg me-1"></i>Agregar</button>
</div>
<div id="contactosContainer">
  {% if obj and obj.contactos %}{% for c in obj.contactos %}
  <div class="prod-row mb-2"><div class="row g-2 align-items-end">
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Nombre *</label>
      <input type="text" name="c_nombre[]" class="form-control form-control-sm" value="{{ c.nombre }}" required></div>
    <div class="col-md-2"><label class="form-label mb-1" style="font-size:.8rem">Cargo</label>
      <input type="text" name="c_cargo[]" class="form-control form-control-sm" value="{{ c.cargo or '' }}"></div>
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Email</label>
      <input type="email" name="c_email[]" class="form-control form-control-sm" value="{{ c.email or '' }}"></div>
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Teléfono</label>
      <input type="text" name="c_telefono[]" class="form-control form-control-sm" value="{{ c.telefono or '' }}"></div>
    <div class="col-md-1"><button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="this.closest('.prod-row').remove()"><i class="bi bi-trash"></i></button></div>
  </div></div>{% endfor %}{% endif %}
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Cliente' }}</button>
  <a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}
{% block scripts %}<script>
function addContacto(){
  document.getElementById('contactosContainer').insertAdjacentHTML('beforeend',`<div class="prod-row mb-2"><div class="row g-2 align-items-end">
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Nombre *</label><input type="text" name="c_nombre[]" class="form-control form-control-sm" required></div>
    <div class="col-md-2"><label class="form-label mb-1" style="font-size:.8rem">Cargo</label><input type="text" name="c_cargo[]" class="form-control form-control-sm"></div>
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Email</label><input type="email" name="c_email[]" class="form-control form-control-sm"></div>
    <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Teléfono</label><input type="text" name="c_telefono[]" class="form-control form-control-sm"></div>
    <div class="col-md-1"><button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="this.closest('.prod-row').remove()"><i class="bi bi-trash"></i></button></div>
  </div></div>`);
}
</script>{% endblock %}"""

T['clientes/ver.html'] = """{% extends 'base.html' %}
{% block title %}{{ obj.empresa or obj.nombre }}{% endblock %}
{% block page_title %}{{ obj.empresa or obj.nombre }}{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('cliente_editar', id=obj.id) }}" class="btn btn-primary btn-sm"><i class="bi bi-pencil me-1"></i>Editar</a>
<a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>
{% endblock %}
{% block content %}<div class="row g-4">
  <div class="col-lg-4">
    <div class="fc mb-3">
      <div class="d-flex align-items-center gap-3 mb-3">
        <div class="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
             style="width:50px;height:50px;background:#5e72e4;font-size:1.2rem;flex-shrink:0">{{ (obj.empresa or obj.nombre)[0].upper() }}</div>
        <div><h5 class="mb-1">{{ obj.empresa or obj.nombre }}</h5>
          <span class="b b-{{ obj.estado_relacion }}">{{ obj.estado_relacion.replace('_',' ').title() }}</span></div>
      </div><hr>
      <dl class="row mb-0" style="font-size:.88rem">
        {% if obj.empresa %}<dt class="col-5 text-muted">Rep. Legal</dt><dd class="col-7">{{ obj.nombre }}</dd>{% endif %}
        <dt class="col-5 text-muted">NIT</dt><dd class="col-7">{{ obj.nit or '—' }}</dd>
        <dt class="col-5 text-muted">Dir. Comercial</dt><dd class="col-7">{{ obj.dir_comercial or '—' }}</dd>
        <dt class="col-5 text-muted">Dir. Entrega</dt><dd class="col-7">{{ obj.dir_entrega or '—' }}</dd>
      </dl>
      {% if obj.notas %}<hr><p style="font-size:.88rem">{{ obj.notas }}</p>{% endif %}
    </div>
    {% if obj.contactos %}<div class="fc">
      <h6 class="text-muted text-uppercase mb-3" style="font-size:.72rem;letter-spacing:1px">Contactos</h6>
      {% for c in obj.contactos %}
      <div class="d-flex gap-2 mb-3">
        <div class="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
             style="width:34px;height:34px;background:#8898aa;font-size:.8rem;flex-shrink:0">{{ c.nombre[0].upper() }}</div>
        <div style="font-size:.88rem">
          <div class="fw-semibold">{{ c.nombre }}{% if c.cargo %} <span class="text-muted fw-normal">· {{ c.cargo }}</span>{% endif %}</div>
          {% if c.email %}<div><a href="mailto:{{ c.email }}" class="text-decoration-none">{{ c.email }}</a></div>{% endif %}
          {% if c.telefono %}<div class="text-muted">{{ c.telefono }}</div>{% endif %}
        </div>
      </div>{% endfor %}
    </div>{% endif %}
  </div>
  <div class="col-lg-8"><div class="tc">
    <div class="ch d-flex justify-content-between">
      <span><i class="bi bi-graph-up me-2"></i>Ventas</span>
      <a href="{{ url_for('venta_nueva') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i></a></div>
    {% if obj.ventas %}<table class="table">
      <thead><tr><th>Título</th><th>Total COP</th><th>Saldo</th><th>Estado</th></tr></thead>
      <tbody>{% for v in obj.ventas %}<tr>
        <td class="fw-semibold">{{ v.titulo }}</td>
        <td>$ {{ '{:,.0f}'.format(v.total).replace(',','.') }}</td>
        <td>$ {{ '{:,.0f}'.format(v.saldo).replace(',','.') }}</td>
        <td><span class="b b-{{ v.estado }}">{{ v.estado.replace('_',' ').title() }}</span></td>
      </tr>{% endfor %}</tbody>
    </table>
    {% else %}<div class="text-center text-muted py-4"><i class="bi bi-graph-up" style="font-size:2rem"></i>
      <p class="mt-2 mb-0">Sin ventas</p></div>{% endif %}
  </div></div>
</div>{% endblock %}"""

T['ventas/index.html'] = """{% extends 'base.html' %}
{% block title %}Ventas{% endblock %}{% block page_title %}Ventas{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('venta_nueva') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva</a>{% endblock %}
{% block content %}
<div class="mb-3 d-flex gap-2 flex-wrap">
  {% for est,lbl in [('','Todas'),('prospecto','Prospecto'),('negociacion','Negociación'),('anticipo_pagado','Anticipo'),('ganado','Ganado'),('perdido','Perdido')] %}
  <a href="{{ url_for('ventas', estado=est) }}" class="btn btn-sm {{ 'btn-primary' if estado_f==est else 'btn-outline-secondary' }}">{{ lbl }}</a>{% endfor %}
</div>
<div class="tc"><div class="ch"><i class="bi bi-graph-up-arrow me-2"></i>{{ items|length }} venta(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Título</th><th>Cliente</th><th>Total</th><th>Anticipo</th><th>Saldo</th><th>Estado</th><th>Entrega est.</th><th></th></tr></thead>
  <tbody>{% for v in items %}<tr>
    <td class="fw-semibold" style="color:#1a1f36">{{ v.titulo }}</td>
    <td>{% if v.cliente %}<a href="{{ url_for('cliente_ver', id=v.cliente.id) }}" class="text-decoration-none">{{ v.cliente.empresa or v.cliente.nombre }}</a>{% else %}—{% endif %}</td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(v.total).replace(',','.') }}</td>
    <td>$ {{ '{:,.0f}'.format(v.monto_anticipo).replace(',','.') }}</td>
    <td class="{{ 'text-danger fw-semibold' if v.saldo > 0 else '' }}">$ {{ '{:,.0f}'.format(v.saldo).replace(',','.') }}</td>
    <td><span class="b b-{{ v.estado }}">{{ v.estado.replace('_',' ').title() }}</span></td>
    <td>{% if v.fecha_entrega_est %}<small>{{ v.fecha_entrega_est.strftime('%d/%m/%Y') }}</small>{% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('venta_editar', id=v.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('venta_eliminar', id=v.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-graph-up-arrow" style="font-size:3rem"></i>
  <p class="mt-3">Sin ventas.</p><a href="{{ url_for('venta_nueva') }}" class="btn btn-primary">Crear primera</a></div>
{% endif %}</div>{% endblock %}"""

T['ventas/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('ventas') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc" style="max-width:960px"><form method="POST">
<div class="row g-3 mb-3">
  <div class="col-md-8"><label class="form-label">Título *</label>
    <input type="text" name="titulo" class="form-control" value="{{ obj.titulo if obj else '' }}" required></div>
  <div class="col-md-4"><label class="form-label">Cliente</label>
    <select name="cliente_id" class="form-select"><option value="">Sin cliente</option>
      {% for c in clientes_list %}<option value="{{ c.id }}" {% if obj and obj.cliente_id==c.id %}selected{% endif %}>{{ c.empresa or c.nombre }}</option>{% endfor %}
    </select></div>
</div><hr class="my-3">
<div class="d-flex justify-content-between align-items-center mb-2">
  <h6 class="text-muted mb-0 text-uppercase" style="letter-spacing:1px;font-size:.75rem">Productos</h6>
  <button type="button" class="btn btn-sm btn-outline-primary" onclick="addProd()"><i class="bi bi-plus-lg me-1"></i>Agregar</button>
</div>
<div id="prodsContainer"></div>
<div class="totales-box mt-3 mb-4"><div class="row g-2 justify-content-end"><div class="col-md-4">
  <div class="d-flex justify-content-between py-1 border-bottom"><span class="text-muted">Subtotal:</span><strong id="lblSub">$ 0</strong></div>
  <div class="d-flex justify-content-between py-1 border-bottom"><span class="text-muted">IVA 19%:</span><strong id="lblIva">$ 0</strong></div>
  <div class="d-flex justify-content-between py-1"><span class="fw-bold">Total:</span><strong id="lblTot" style="color:#5e72e4;font-size:1.1rem">$ 0</strong></div>
</div></div></div>
<hr class="my-3">
<div class="row g-3 mb-3">
  <div class="col-md-3"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      {% for est,lbl in [('prospecto','Prospecto'),('negociacion','Negociación'),('anticipo_pagado','Anticipo Pagado'),('ganado','Ganado'),('perdido','Perdido')] %}
      <option value="{{ est }}" {% if obj and obj.estado==est %}selected{% elif not obj and est=='prospecto' %}selected{% endif %}>{{ lbl }}</option>{% endfor %}
    </select></div>
  <div class="col-md-3"><label class="form-label">% Anticipo</label>
    <div class="input-group"><input type="number" name="porcentaje_anticipo" id="pctA" class="form-control" min="0" max="100" step="1"
      value="{{ obj.porcentaje_anticipo|int if obj else '0' }}" oninput="calcA()"><span class="input-group-text">%</span></div></div>
  <div class="col-md-3"><label class="form-label">Monto anticipo COP</label>
    <input type="text" id="montoAVis" class="form-control" readonly style="background:#f8f9fe">
    <input type="hidden" name="monto_anticipo" id="montoAHid"></div>
  <div class="col-md-3"><label class="form-label">Saldo a pagar</label>
    <input type="text" id="saldoVis" class="form-control" readonly style="background:#f8f9fe">
    <input type="hidden" name="saldo" id="saldoHid"></div>
  <div class="col-md-4"><label class="form-label">Fecha pago anticipo</label>
    <input type="date" name="fecha_anticipo" id="fAnticipo" class="form-control"
      value="{{ obj.fecha_anticipo.strftime('%Y-%m-%d') if obj and obj.fecha_anticipo else '' }}" onchange="calcEnt()"></div>
  <div class="col-md-4"><label class="form-label">Días de producción</label>
    <select name="dias_entrega" id="diasEnt" class="form-select" onchange="calcEnt()">
      <option value="30" {% if not obj or obj.dias_entrega==30 %}selected{% endif %}>30 días</option>
      <option value="45" {% if obj and obj.dias_entrega==45 %}selected{% endif %}>45 días</option>
    </select></div>
  <div class="col-md-4"><label class="form-label">Entrega estimada</label>
    <input type="text" id="entVis" class="form-control" readonly style="background:#f8f9fe">
    <input type="hidden" name="fecha_entrega_est" id="entHid" value="{{ obj.fecha_entrega_est.strftime('%Y-%m-%d') if obj and obj.fecha_entrega_est else '' }}"></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="2">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<input type="hidden" name="subtotal_calc" id="subHid">
<input type="hidden" name="iva_calc" id="ivaHid">
<input type="hidden" name="total_calc" id="totHid">
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Venta' }}</button>
  <a href="{{ url_for('ventas') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}
{% block scripts %}<script>
const PRODS={{ productos_json|safe }};const ITEMS={{ items_json|safe }};let totG=0;
function fCOP(n){return '$ '+Math.round(n).toLocaleString('es-CO');}
function addProd(pid='',cant=1,precio=0){
  const opts=PRODS.map(p=>`<option value="${p.id}" data-p="${p.precio}" ${p.id==pid?'selected':''}>${p.nombre}${p.sku?' ('+p.sku+')':''}</option>`).join('');
  const idx=Date.now();
  document.getElementById('prodsContainer').insertAdjacentHTML('beforeend',`<div class="prod-row mb-2" id="pr${idx}">
    <div class="row g-2 align-items-end">
      <div class="col-md-5"><label class="form-label mb-1" style="font-size:.8rem">Producto</label>
        <select name="prod_id[]" class="form-select form-select-sm" onchange="onPC(this,${idx})">${opts}</select></div>
      <div class="col-md-2"><label class="form-label mb-1" style="font-size:.8rem">Cantidad</label>
        <input type="number" name="prod_cant[]" class="form-control form-control-sm" min="0.01" step="0.01" value="${cant}" oninput="calcRow(${idx})"></div>
      <div class="col-md-3"><label class="form-label mb-1" style="font-size:.8rem">Precio unit. COP sin IVA</label>
        <input type="number" name="prod_precio[]" id="pp${idx}" class="form-control form-control-sm" min="0" step="1" value="${precio}" oninput="calcRow(${idx})"></div>
      <div class="col-md-1"><label class="form-label mb-1" style="font-size:.8rem">Subtotal</label>
        <input type="text" id="ps${idx}" class="form-control form-control-sm" readonly style="background:#f8f9fe"></div>
      <div class="col-md-1"><label class="form-label mb-1" style="font-size:.8rem"> </label>
        <button type="button" class="btn btn-sm btn-outline-danger w-100" onclick="document.getElementById('pr${idx}').remove();calcTot()"><i class="bi bi-trash"></i></button></div>
    </div></div>`);
  calcRow(idx);
}
function onPC(sel,idx){const o=sel.options[sel.selectedIndex];document.getElementById('pp'+idx).value=Math.round(o.dataset.p||0);calcRow(idx);}
function calcRow(idx){
  const pr=document.getElementById('pr'+idx);if(!pr)return;
  const c=parseFloat(pr.querySelector('[name="prod_cant[]"]').value)||0;
  const p=parseFloat(document.getElementById('pp'+idx).value)||0;
  document.getElementById('ps'+idx).value=fCOP(c*p);calcTot();
}
function calcTot(){
  let sub=0;
  document.querySelectorAll('[name="prod_cant[]"]').forEach((el,i)=>{
    sub+=(parseFloat(el.value)||0)*(parseFloat(document.querySelectorAll('[name="prod_precio[]"]')[i].value)||0);
  });
  const iva=sub*.19,tot=sub+iva;totG=tot;
  document.getElementById('lblSub').textContent=fCOP(sub);
  document.getElementById('lblIva').textContent=fCOP(iva);
  document.getElementById('lblTot').textContent=fCOP(tot);
  document.getElementById('subHid').value=Math.round(sub);
  document.getElementById('ivaHid').value=Math.round(iva);
  document.getElementById('totHid').value=Math.round(tot);calcA();
}
function calcA(){
  const pct=parseFloat(document.getElementById('pctA').value)||0;
  const ant=totG*pct/100,sal=totG-ant;
  document.getElementById('montoAVis').value=fCOP(ant);document.getElementById('montoAHid').value=Math.round(ant);
  document.getElementById('saldoVis').value=fCOP(sal);document.getElementById('saldoHid').value=Math.round(sal);
}
function calcEnt(){
  const fa=document.getElementById('fAnticipo').value;const d=parseInt(document.getElementById('diasEnt').value)||30;
  if(fa){const dt=new Date(fa);dt.setDate(dt.getDate()+d);const iso=dt.toISOString().split('T')[0];
    const p=iso.split('-');document.getElementById('entVis').value=p[2]+'/'+p[1]+'/'+p[0];document.getElementById('entHid').value=iso;}
}
if(ITEMS.length>0){ITEMS.forEach(it=>addProd(it.pid,it.cant,it.precio));}else{addProd();}
calcEnt();
const feh=document.getElementById('entHid').value;if(feh){const p=feh.split('-');document.getElementById('entVis').value=p[2]+'/'+p[1]+'/'+p[0];}
</script>{% endblock %}"""

T['tareas/index.html'] = """{% extends 'base.html' %}
{% block title %}Tareas{% endblock %}{% block page_title %}Tareas{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('tarea_nueva') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva</a>{% endblock %}
{% block content %}
<div class="mb-3 d-flex gap-2 flex-wrap">
  {% for est,lbl in [('','Todas'),('pendiente','Pendiente'),('en_progreso','En progreso'),('completada','Completada')] %}
  <a href="{{ url_for('tareas', estado=est) }}" class="btn btn-sm {{ 'btn-primary' if estado_f==est else 'btn-outline-secondary' }}">{{ lbl }}</a>{% endfor %}
  <span class="text-muted mx-1">|</span>
  <a href="{{ url_for('tareas', prioridad='alta') }}" class="btn btn-sm {{ 'btn-danger' if prioridad_f=='alta' else 'btn-outline-secondary' }}">Alta prioridad</a>
</div>
<div class="tc"><div class="ch"><i class="bi bi-check2-square me-2"></i>{{ items|length }} tarea(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Tarea</th><th>Prioridad</th><th>Estado</th><th>Asignada a</th><th>Vence</th><th></th></tr></thead>
  <tbody>{% for t in items %}<tr {% if t.estado=='completada' %}style="opacity:.6"{% endif %}>
    <td><a href="{{ url_for('tarea_ver', id=t.id) }}" class="fw-semibold text-decoration-none {% if t.estado=='completada' %}text-decoration-line-through{% endif %}" style="color:#1a1f36">{{ t.titulo }}</a>
      {% if t.comentarios %}<span class="badge bg-light text-secondary ms-1" style="font-size:.65rem"><i class="bi bi-chat-dots"></i> {{ t.comentarios|length }}</span>{% endif %}</td>
    <td><span class="b b-{{ t.prioridad }}">{{ t.prioridad.title() }}</span></td>
    <td><span class="b b-{{ t.estado }}">{{ t.estado.replace('_',' ').title() }}</span></td>
    <td>{{ t.asignado_user.nombre if t.asignado_user else '—' }}</td>
    <td>{% if t.fecha_vencimiento %}
      <small class="{{ 'text-danger fw-bold' if t.estado!='completada' and t.fecha_vencimiento < now.date() else 'text-muted' }}">{{ t.fecha_vencimiento.strftime('%d/%m/%Y') }}</small>
      {% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('tarea_ver', id=t.id) }}" class="btn btn-sm btn-outline-primary" title="Ver y chatear"><i class="bi bi-chat-dots"></i></a>
      {% if t.estado!='completada' %}<form method="POST" action="{{ url_for('tarea_completar', id=t.id) }}">
        <button class="btn btn-sm btn-outline-success"><i class="bi bi-check2"></i></button></form>{% endif %}
      <a href="{{ url_for('tarea_editar', id=t.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('tarea_eliminar', id=t.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-check2-all" style="font-size:3rem"></i>
  <p class="mt-3">Sin tareas.</p><a href="{{ url_for('tarea_nueva') }}" class="btn btn-primary">Crear primera</a></div>
{% endif %}</div>{% endblock %}"""

T['tareas/ver.html'] = """{% extends 'base.html' %}
{% block title %}{{ tarea.titulo }}{% endblock %}{% block page_title %}{{ tarea.titulo }}{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('tarea_editar', id=tarea.id) }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-pencil me-1"></i>Editar</a>
{% if tarea.estado != 'completada' %}
<form method="POST" action="{{ url_for('tarea_completar', id=tarea.id) }}" class="d-inline">
  <button class="btn btn-success btn-sm"><i class="bi bi-check2 me-1"></i>Completar</button></form>{% endif %}
<a href="{{ url_for('tareas') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>
{% endblock %}
{% block content %}<div class="row g-4">
  <div class="col-lg-4">
    <div class="fc">
      <div class="mb-3">
        <span class="b b-{{ tarea.estado }} me-2">{{ tarea.estado.replace('_',' ').title() }}</span>
        <span class="b b-{{ tarea.prioridad }}">{{ tarea.prioridad.title() }} prioridad</span>
      </div>
      {% if tarea.descripcion %}<p style="font-size:.9rem">{{ tarea.descripcion }}</p><hr>{% endif %}
      <dl class="row mb-0" style="font-size:.88rem">
        <dt class="col-5 text-muted">Creada por</dt><dd class="col-7">{{ tarea.creador.nombre if tarea.creador else '—' }}</dd>
        <dt class="col-5 text-muted">Asignada a</dt><dd class="col-7">{{ tarea.asignado_user.nombre if tarea.asignado_user else '—' }}</dd>
        {% if tarea.asignados %}
        <dt class="col-5 text-muted">También</dt>
        <dd class="col-7">{% for a in tarea.asignados %}{{ a.user.nombre }}{% if not loop.last %}, {% endif %}{% endfor %}</dd>{% endif %}
        {% if tarea.fecha_vencimiento %}
        <dt class="col-5 text-muted">Vence</dt>
        <dd class="col-7 {{ 'text-danger fw-bold' if tarea.estado!='completada' and tarea.fecha_vencimiento < now.date() else '' }}">{{ tarea.fecha_vencimiento.strftime('%d/%m/%Y') }}</dd>{% endif %}
        <dt class="col-5 text-muted">Creada</dt><dd class="col-7">{{ tarea.creado_en.strftime('%d/%m/%Y') }}</dd>
      </dl>
    </div>
  </div>
  <div class="col-lg-8">
    <div class="tc">
      <div class="ch"><i class="bi bi-chat-dots me-2"></i>Conversación ({{ tarea.comentarios|length }} mensajes)</div>
      <div style="max-height:420px;overflow-y:auto;padding:1rem" id="chatBox">
        {% if tarea.comentarios %}
          {% for c in tarea.comentarios %}
          <div class="d-flex {% if c.autor_id == current_user.id %}justify-content-end{% endif %} mb-2">
            <div class="chat-bubble {{ 'mine' if c.autor_id == current_user.id else '' }}">
              <div>{{ c.mensaje }}</div>
              <div class="chat-meta">{{ c.autor.nombre }} · {{ c.creado_en.strftime('%d/%m %H:%M') }}</div>
            </div>
          </div>{% endfor %}
        {% else %}
        <div class="text-center text-muted py-4"><i class="bi bi-chat" style="font-size:2rem"></i>
          <p class="mt-2 mb-0">Sin mensajes aún. ¡Sé el primero!</p></div>{% endif %}
      </div>
      <div class="p-3 border-top">
        <form method="POST" action="{{ url_for('tarea_comentar', id=tarea.id) }}">
          <div class="d-flex gap-2">
            <input type="text" name="mensaje" class="form-control" placeholder="Escribe un mensaje..." required autofocus>
            <button type="submit" class="btn btn-primary"><i class="bi bi-send"></i></button>
          </div>
        </form>
      </div>
    </div>
  </div>
</div>{% endblock %}
{% block scripts %}<script>
const cb=document.getElementById('chatBox');if(cb)cb.scrollTop=cb.scrollHeight;
</script>{% endblock %}"""

T['tareas/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('tareas') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-12"><label class="form-label">Título *</label>
    <input type="text" name="titulo" class="form-control" value="{{ obj.titulo if obj else '' }}" required></div>
  <div class="col-md-4"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      <option value="pendiente" {% if not obj or obj.estado=='pendiente' %}selected{% endif %}>Pendiente</option>
      <option value="en_progreso" {% if obj and obj.estado=='en_progreso' %}selected{% endif %}>En progreso</option>
      <option value="completada" {% if obj and obj.estado=='completada' %}selected{% endif %}>Completada</option>
    </select></div>
  <div class="col-md-4"><label class="form-label">Prioridad</label>
    <select name="prioridad" class="form-select">
      <option value="baja" {% if obj and obj.prioridad=='baja' %}selected{% endif %}>Baja</option>
      <option value="media" {% if not obj or obj.prioridad=='media' %}selected{% endif %}>Media</option>
      <option value="alta" {% if obj and obj.prioridad=='alta' %}selected{% endif %}>Alta</option>
    </select></div>
  <div class="col-md-4"><label class="form-label">Fecha vencimiento</label>
    <input type="date" name="fecha_vencimiento" class="form-control"
      value="{{ obj.fecha_vencimiento.strftime('%Y-%m-%d') if obj and obj.fecha_vencimiento else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Asignado principal</label>
    <select name="asignado_a" class="form-select">
      {% for u in usuarios %}<option value="{{ u.id }}" {% if (obj and obj.asignado_a==u.id) or (not obj and u.id==current_user.id) %}selected{% endif %}>
        {{ u.nombre }}{% if u.id==current_user.id %} (yo){% endif %}</option>{% endfor %}
    </select></div>
  <div class="col-md-6"><label class="form-label">También asignar a</label>
    <select name="otros_asignados[]" class="form-select" multiple style="height:90px">
      {% for u in usuarios %}{% if u.id != current_user.id %}
      <option value="{{ u.id }}" {% if obj and u.id in asignados_ids %}selected{% endif %}>{{ u.nombre }}</option>
      {% endif %}{% endfor %}
    </select>
    <div class="form-text">Ctrl+clic para seleccionar varios</div></div>
  <div class="col-12"><label class="form-label">Descripción</label>
    <textarea name="descripcion" class="form-control" rows="4">{{ obj.descripcion if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Tarea' }}</button>
  <a href="{{ url_for('tareas') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['inventario/index.html'] = """{% extends 'base.html' %}
{% block title %}Inventario{% endblock %}{% block page_title %}Inventario{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('producto_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nuevo</a>{% endblock %}
{% block content %}
<div class="tc mb-3"><div class="p-3"><form method="GET" class="row g-2 align-items-end">
  <div class="col-sm-5"><input type="text" name="buscar" class="form-control form-control-sm" placeholder="Nombre, SKU, NSO..." value="{{ busqueda }}"></div>
  <div class="col-sm-3"><select name="categoria" class="form-select form-select-sm">
    <option value="">Todas las categorías</option>
    {% for cat in categorias %}<option value="{{ cat }}" {% if categoria_f==cat %}selected{% endif %}>{{ cat }}</option>{% endfor %}
  </select></div>
  <div class="col-auto">
    <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-search"></i></button>
    <a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary btn-sm">Limpiar</a>
  </div>
</form></div></div>
<div class="tc"><div class="ch"><i class="bi bi-box-seam-fill me-2"></i>{{ items|length }} producto(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Producto</th><th>SKU</th><th>NSO (INVIMA)</th><th>Precio venta</th><th>Costo</th><th>Stock</th><th></th></tr></thead>
  <tbody>{% for p in items %}<tr>
    <td><div class="fw-semibold" style="color:#1a1f36">{{ p.nombre }}</div>
      {% if p.categoria %}<small class="text-muted">{{ p.categoria }}</small>{% endif %}</td>
    <td><small class="text-muted">{{ p.sku or '—' }}</small></td>
    <td><small class="text-muted">{{ p.nso or '—' }}</small></td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(p.precio).replace(',','.') }}</td>
    <td>$ {{ '{:,.0f}'.format(p.costo).replace(',','.') }}</td>
    <td><span class="fw-semibold {{ 'text-danger' if p.stock <= p.stock_minimo else 'text-success' }}">{{ p.stock }}</span>
      <small class="text-muted"> / mín {{ p.stock_minimo }}</small>
      {% if p.stock <= p.stock_minimo %}<span class="badge bg-danger ms-1" style="font-size:.65rem">BAJO</span>{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('producto_editar', id=p.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('producto_eliminar', id=p.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-box-seam" style="font-size:3rem"></i>
  <p class="mt-3">Sin productos.</p><a href="{{ url_for('producto_nuevo') }}" class="btn btn-primary">Agregar</a></div>
{% endif %}</div>{% endblock %}"""

T['inventario/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre *</label>
    <input type="text" name="nombre" class="form-control" value="{{ obj.nombre if obj else '' }}" required></div>
  <div class="col-md-3"><label class="form-label">SKU</label>
    <input type="text" name="sku" class="form-control" value="{{ obj.sku if obj else '' }}"></div>
  <div class="col-md-3"><label class="form-label">NSO (INVIMA)</label>
    <input type="text" name="nso" class="form-control" placeholder="NSO-XXXX-XXXX" value="{{ obj.nso if obj else '' }}"></div>
  <div class="col-md-3"><label class="form-label">Precio venta COP</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="precio" class="form-control" step="1" min="0" value="{{ obj.precio|int if obj else '0' }}"></div></div>
  <div class="col-md-3"><label class="form-label">Costo COP <small class="text-muted">(auto desde Producción)</small></label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="costo" class="form-control" step="1" min="0" value="{{ obj.costo|int if obj else '0' }}"></div></div>
  <div class="col-md-3"><label class="form-label">Stock actual</label>
    <input type="number" name="stock" class="form-control" min="0" value="{{ obj.stock if obj else '0' }}"></div>
  <div class="col-md-3"><label class="form-label">Stock mínimo</label>
    <input type="number" name="stock_minimo" class="form-control" min="0" value="{{ obj.stock_minimo if obj else '5' }}"></div>
  <div class="col-md-6"><label class="form-label">Categoría</label>
    <input type="text" name="categoria" class="form-control" value="{{ obj.categoria if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Descripción</label>
    <textarea name="descripcion" class="form-control" rows="3">{{ obj.descripcion if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Producto' }}</button>
  <a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['produccion/index.html'] = """{% extends 'base.html' %}
{% block title %}Producción{% endblock %}{% block page_title %}Producción{% endblock %}
{% block content %}
<div class="row g-3 mb-4">
  <div class="col-md-3"><div class="sc"><div class="sv valor-cop" data-cop="{{ total_compras }}">$ {{ '{:,.0f}'.format(total_compras).replace(',','.') }}</div>
    <div class="sl">Total en compras</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv valor-cop" data-cop="{{ compras_mes }}">$ {{ '{:,.0f}'.format(compras_mes).replace(',','.') }}</div>
    <div class="sl">Compras este mes</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv">{{ cotizaciones_vigentes }}</div>
    <div class="sl">Cotizaciones granel vigentes</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv">{{ reglas_activas }}</div>
    <div class="sl">Reglas tributarias activas</div></div></div>
</div>
<div class="row g-4">
  <div class="col-md-4"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-cart3 me-2 text-primary"></i>Compras recientes</span>
      <a href="{{ url_for('compras') }}" class="btn btn-sm btn-outline-primary">Ver todas</a></div>
    {% if compras_recientes %}<table class="table"><tbody>
    {% for c in compras_recientes %}<tr>
      <td><div class="fw-semibold" style="font-size:.88rem;color:#1a1f36">{{ c.nombre_item }}</div>
        <small class="text-muted">{{ c.proveedor or '—' }} · {{ c.fecha.strftime('%d/%m/%Y') }}</small></td>
      <td class="fw-semibold" style="white-space:nowrap">$ {{ '{:,.0f}'.format(c.costo_total).replace(',','.') }}</td>
    </tr>{% endfor %}</tbody></table>
    {% else %}<div class="text-center text-muted py-3"><p class="mb-2">Sin compras</p>
      <a href="{{ url_for('compra_nueva') }}" class="btn btn-sm btn-primary">Registrar</a></div>{% endif %}
  </div></div>
  <div class="col-md-4"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-building me-2 text-success"></i>Cotizaciones Granel</span>
      <a href="{{ url_for('granel') }}" class="btn btn-sm btn-outline-success">Ver todas</a></div>
    {% if granel_recientes %}<table class="table"><tbody>
    {% for g in granel_recientes %}<tr>
      <td><div class="fw-semibold" style="font-size:.88rem;color:#1a1f36">{{ g.nombre_producto }}</div>
        <small class="text-muted">SKU: {{ g.sku or '—' }} · NSO: {{ g.nso or '—' }}</small></td>
      <td><span class="b b-{{ g.estado }}">{{ g.estado.title() }}</span></td>
    </tr>{% endfor %}</tbody></table>
    {% else %}<div class="text-center text-muted py-3"><p class="mb-2">Sin cotizaciones</p>
      <a href="{{ url_for('granel_nuevo') }}" class="btn btn-sm btn-success">Agregar</a></div>{% endif %}
  </div></div>
  <div class="col-md-4"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-percent me-2 text-warning"></i>Reglas tributarias</span>
      <a href="{{ url_for('impuestos') }}" class="btn btn-sm btn-outline-warning">Ver todas</a></div>
    {% if reglas %}<table class="table"><tbody>
    {% for r in reglas %}<tr>
      <td><div class="fw-semibold" style="font-size:.88rem;color:#1a1f36">{{ r.nombre }}</div>
        <small class="text-muted">{{ r.aplica_a or '' }}</small></td>
      <td class="fw-semibold">{{ r.porcentaje }}%</td>
    </tr>{% endfor %}</tbody></table>
    {% else %}<div class="text-center text-muted py-3"><p class="mb-2">Sin reglas</p>
      <a href="{{ url_for('impuesto_nuevo') }}" class="btn btn-sm btn-warning">Agregar</a></div>{% endif %}
  </div></div>
</div>{% endblock %}"""

T['produccion/compras.html'] = """{% extends 'base.html' %}
{% block title %}Compras{% endblock %}{% block page_title %}Compras de Materia Prima{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('compra_nueva') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva compra</a>
<a href="{{ url_for('produccion_index') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Producción</a>
{% endblock %}
{% block content %}
<div class="row g-3 mb-3">
  <div class="col-md-3"><div class="sc"><div class="sv">$ {{ '{:,.0f}'.format(total_general).replace(',','.') }}</div><div class="sl">Total acumulado</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv">$ {{ '{:,.0f}'.format(total_mes).replace(',','.') }}</div><div class="sl">Este mes</div></div></div>
</div>
<div class="tc"><div class="ch"><i class="bi bi-cart3 me-2"></i>{{ items|length }} compra(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Ítem</th><th>Proveedor</th><th>Fecha</th><th># Factura</th><th>Cto. Producto</th><th>Impuestos</th><th>Transporte</th><th>Total</th><th>Cant.</th><th>P. Unitario</th><th>Producto vinculado</th><th></th></tr></thead>
  <tbody>{% for c in items %}<tr>
    <td class="fw-semibold" style="color:#1a1f36">{{ c.nombre_item }}</td>
    <td>{{ c.proveedor or '—' }}</td>
    <td><small>{{ c.fecha.strftime('%d/%m/%Y') }}</small></td>
    <td><small class="text-muted">{{ c.nro_factura or '—' }}</small></td>
    <td>$ {{ '{:,.0f}'.format(c.costo_producto).replace(',','.') }}</td>
    <td>$ {{ '{:,.0f}'.format(c.impuestos).replace(',','.') }}</td>
    <td>$ {{ '{:,.0f}'.format(c.transporte).replace(',','.') }}</td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(c.costo_total).replace(',','.') }}</td>
    <td>{{ c.cantidad }}</td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(c.precio_unitario).replace(',','.') }}</td>
    <td>{% if c.producto %}<span class="badge bg-light text-dark">{{ c.producto.nombre }}</span>{% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('compra_editar', id=c.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('compra_eliminar', id=c.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-cart3" style="font-size:3rem"></i>
  <p class="mt-3">Sin compras.</p><a href="{{ url_for('compra_nueva') }}" class="btn btn-primary">Registrar primera</a></div>
{% endif %}</div>{% endblock %}"""

T['produccion/compra_form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('compras') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc" style="max-width:900px"><form method="POST" id="frmC">
<div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre del ítem *</label>
    <input type="text" name="nombre_item" class="form-control" value="{{ obj.nombre_item if obj else '' }}" required></div>
  <div class="col-md-6"><label class="form-label">Proveedor</label>
    <input type="text" name="proveedor" class="form-control" value="{{ obj.proveedor if obj else '' }}"></div>
  <div class="col-md-4"><label class="form-label">Fecha *</label>
    <input type="date" name="fecha" class="form-control" value="{{ obj.fecha.strftime('%Y-%m-%d') if obj else today }}" required></div>
  <div class="col-md-4"><label class="form-label"># Factura</label>
    <input type="text" name="nro_factura" class="form-control" value="{{ obj.nro_factura if obj else '' }}"></div>
  <div class="col-md-4"><label class="form-label">Cantidad</label>
    <input type="number" name="cantidad" id="cant" class="form-control" step="0.01" min="0.01" value="{{ obj.cantidad if obj else '1' }}" oninput="calc()"></div>
  <div class="col-md-4"><label class="form-label">Costo del producto COP</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="costo_producto" id="cP" class="form-control" step="1" min="0" value="{{ obj.costo_producto|int if obj else '0' }}" oninput="calc()"></div></div>
  <div class="col-md-4"><label class="form-label">Impuestos COP</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="impuestos" id="imp" class="form-control" step="1" min="0" value="{{ obj.impuestos|int if obj else '0' }}" oninput="calc()"></div></div>
  <div class="col-md-4"><label class="form-label">Transporte COP</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="transporte" id="tsp" class="form-control" step="1" min="0" value="{{ obj.transporte|int if obj else '0' }}" oninput="calc()"></div></div>
  <div class="col-md-6"><label class="form-label fw-bold">Costo total COP</label>
    <input type="text" id="totVis" class="form-control fw-bold" readonly style="background:#f0f2ff;font-size:1.05rem">
    <input type="hidden" name="costo_total" id="totHid"></div>
  <div class="col-md-6"><label class="form-label fw-bold">Precio unitario COP</label>
    <input type="text" id="pUVis" class="form-control fw-bold" readonly style="background:#f0f2ff;font-size:1.05rem">
    <input type="hidden" name="precio_unitario" id="pUHid"></div>
  <div class="col-12"><label class="form-label">Vincular a producto en inventario</label>
    <select name="producto_id" class="form-select">
      <option value="">— No vincular —</option>
      {% for p in productos %}<option value="{{ p.id }}" {% if obj and obj.producto_id==p.id %}selected{% endif %}>{{ p.nombre }}{% if p.sku %} ({{ p.sku }}){% endif %}</option>{% endfor %}
    </select>
    <div class="form-text">Al guardar, actualizará el costo del producto seleccionado.</div></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="2">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Guardar Compra' }}</button>
  <a href="{{ url_for('compras') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}
{% block scripts %}<script>
function fCOP(n){return '$ '+Math.round(n).toLocaleString('es-CO');}
function calc(){
  const cp=parseFloat(document.getElementById('cP').value)||0;
  const imp=parseFloat(document.getElementById('imp').value)||0;
  const tsp=parseFloat(document.getElementById('tsp').value)||0;
  const cant=parseFloat(document.getElementById('cant').value)||1;
  const tot=cp+imp+tsp;const pu=cant>0?tot/cant:0;
  document.getElementById('totVis').value=fCOP(tot);document.getElementById('totHid').value=Math.round(tot);
  document.getElementById('pUVis').value=fCOP(pu);document.getElementById('pUHid').value=Math.round(pu);
}
calc();
</script>{% endblock %}"""

T['produccion/granel.html'] = """{% extends 'base.html' %}
{% block title %}Granel{% endblock %}{% block page_title %}Cotizaciones Granel{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('granel_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva cotización</a>
<a href="{{ url_for('produccion_index') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Producción</a>
{% endblock %}
{% block content %}
<div class="mb-3 d-flex gap-2">
  {% for est,lbl in [('','Todas'),('vigente','Vigentes'),('vencida','Vencidas'),('en_revision','En revisión')] %}
  <a href="{{ url_for('granel', estado=est) }}" class="btn btn-sm {{ 'btn-primary' if estado_f==est else 'btn-outline-secondary' }}">{{ lbl }}</a>{% endfor %}
</div>
<div class="tc"><div class="ch"><i class="bi bi-building me-2"></i>{{ items|length }} cotización(es)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Producto</th><th>SKU</th><th>NSO (INVIMA)</th><th>Proveedor</th><th>P. Unitario</th><th>Mín. unidades</th><th>Vigencia</th><th>Estado</th><th>Producto inv.</th><th></th></tr></thead>
  <tbody>{% for g in items %}<tr>
    <td class="fw-semibold" style="color:#1a1f36">{{ g.nombre_producto }}</td>
    <td><small class="text-muted">{{ g.sku or '—' }}</small></td>
    <td><small class="text-muted">{{ g.nso or '—' }}</small></td>
    <td>{{ g.proveedor or '—' }}</td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(g.precio_unitario).replace(',','.') }}</td>
    <td>{{ g.unidades_minimas }}</td>
    <td>{% if g.vigencia %}<small class="{{ 'text-danger' if g.vigencia < now.date() else 'text-muted' }}">{{ g.vigencia.strftime('%d/%m/%Y') }}</small>{% else %}—{% endif %}</td>
    <td><span class="b b-{{ g.estado }}">{{ g.estado.replace('_',' ').title() }}</span></td>
    <td>{% if g.producto %}<small>{{ g.producto.nombre }}</small>{% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('granel_editar', id=g.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('granel_eliminar', id=g.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-building" style="font-size:3rem"></i>
  <p class="mt-3">Sin cotizaciones.</p><a href="{{ url_for('granel_nuevo') }}" class="btn btn-primary">Agregar primera</a></div>
{% endif %}</div>{% endblock %}"""

T['produccion/granel_form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('granel') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc" style="max-width:900px"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre del producto *</label>
    <input type="text" name="nombre_producto" class="form-control" value="{{ obj.nombre_producto if obj else '' }}" required></div>
  <div class="col-md-3"><label class="form-label">SKU</label>
    <input type="text" name="sku" class="form-control" value="{{ obj.sku if obj else '' }}"></div>
  <div class="col-md-3"><label class="form-label">NSO (INVIMA)</label>
    <input type="text" name="nso" class="form-control" placeholder="NSO-XXXX" value="{{ obj.nso if obj else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Proveedor / Fabricante</label>
    <input type="text" name="proveedor" class="form-control" value="{{ obj.proveedor if obj else '' }}"></div>
  <div class="col-md-3"><label class="form-label">Precio unitario COP</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="precio_unitario" class="form-control" step="1" min="0" value="{{ obj.precio_unitario|int if obj else '0' }}"></div></div>
  <div class="col-md-3"><label class="form-label">Mínimo de unidades</label>
    <input type="number" name="unidades_minimas" class="form-control" min="1" value="{{ obj.unidades_minimas if obj else '1' }}"></div>
  <div class="col-md-4"><label class="form-label">Fecha cotización</label>
    <input type="date" name="fecha_cotizacion" class="form-control"
      value="{{ obj.fecha_cotizacion.strftime('%Y-%m-%d') if obj and obj.fecha_cotizacion else today }}"></div>
  <div class="col-md-4"><label class="form-label">Vigencia hasta</label>
    <input type="date" name="vigencia" class="form-control"
      value="{{ obj.vigencia.strftime('%Y-%m-%d') if obj and obj.vigencia else '' }}"></div>
  <div class="col-md-4"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      {% for est,lbl in [('vigente','Vigente'),('vencida','Vencida'),('en_revision','En revisión')] %}
      <option value="{{ est }}" {% if obj and obj.estado==est %}selected{% elif not obj and est=='vigente' %}selected{% endif %}>{{ lbl }}</option>{% endfor %}
    </select></div>
  <div class="col-12"><label class="form-label">Vincular a producto en inventario</label>
    <select name="producto_id" class="form-select">
      <option value="">— No vincular —</option>
      {% for p in productos %}<option value="{{ p.id }}" {% if obj and obj.producto_id==p.id %}selected{% endif %}>{{ p.nombre }}{% if p.sku %} ({{ p.sku }}){% endif %}</option>{% endfor %}
    </select>
    <div class="form-text">Si estado es "Vigente", actualizará el costo del producto en inventario.</div></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="2">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Guardar Cotización' }}</button>
  <a href="{{ url_for('granel') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['produccion/impuestos.html'] = """{% extends 'base.html' %}
{% block title %}Impuestos{% endblock %}{% block page_title %}Reglas Tributarias{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('impuesto_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva regla</a>
<a href="{{ url_for('produccion_index') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Producción</a>
{% endblock %}
{% block content %}
<div class="alert alert-info" style="border-radius:10px;border:none">
  <i class="bi bi-info-circle me-2"></i>Esta sección es para que el contador configure las reglas tributarias que aplican a las compras y operaciones de la empresa.
</div>
<div class="tc"><div class="ch"><i class="bi bi-percent me-2"></i>{{ items|length }} regla(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Nombre</th><th>Descripción</th><th>%</th><th>Aplica a</th><th>Estado</th><th></th></tr></thead>
  <tbody>{% for r in items %}<tr>
    <td class="fw-semibold" style="color:#1a1f36">{{ r.nombre }}</td>
    <td><small class="text-muted">{{ r.descripcion or '—' }}</small></td>
    <td class="fw-semibold">{{ r.porcentaje }}%</td>
    <td>{{ r.aplica_a or '—' }}</td>
    <td><span class="b b-{{ 'activo' if r.activo else 'inactivo' }}">{{ 'Activa' if r.activo else 'Inactiva' }}</span></td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('impuesto_editar', id=r.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('impuesto_eliminar', id=r.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-percent" style="font-size:3rem"></i>
  <p class="mt-3">Sin reglas configuradas.</p><a href="{{ url_for('impuesto_nuevo') }}" class="btn btn-primary">Agregar primera</a></div>
{% endif %}</div>{% endblock %}"""

T['produccion/impuesto_form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('impuestos') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre *</label>
    <input type="text" name="nombre" class="form-control" placeholder="Ej: IVA compras insumos" value="{{ obj.nombre if obj else '' }}" required></div>
  <div class="col-md-3"><label class="form-label">Porcentaje %</label>
    <div class="input-group"><input type="number" name="porcentaje" class="form-control" step="0.01" min="0" max="100"
      value="{{ obj.porcentaje if obj else '0' }}"><span class="input-group-text">%</span></div></div>
  <div class="col-md-3"><label class="form-label">Estado</label>
    <select name="activo" class="form-select">
      <option value="1" {% if not obj or obj.activo %}selected{% endif %}>Activa</option>
      <option value="0" {% if obj and not obj.activo %}selected{% endif %}>Inactiva</option>
    </select></div>
  <div class="col-12"><label class="form-label">Aplica a</label>
    <input type="text" name="aplica_a" class="form-control" placeholder="Ej: Materias primas importadas, servicios de maquila..."
      value="{{ obj.aplica_a if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Descripción / Instrucciones para el equipo</label>
    <textarea name="descripcion" class="form-control" rows="4" placeholder="Explicar cuándo y cómo aplicar esta regla...">{{ obj.descripcion if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Guardar Regla' }}</button>
  <a href="{{ url_for('impuestos') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['gastos/index.html'] = """{% extends 'base.html' %}
{% block title %}Gastos Operativos{% endblock %}{% block page_title %}Gastos Operativos{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('gasto_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Agregar gasto</a>{% endblock %}
{% block content %}
<div class="row g-3 mb-4">
  <div class="col-md-3"><div class="sc"><div class="sv">$ {{ '{:,.0f}'.format(total_general).replace(',','.') }}</div><div class="sl">Total acumulado COP</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv">$ {{ '{:,.0f}'.format(total_mes).replace(',','.') }}</div><div class="sl">Este mes</div></div></div>
  <div class="col-md-3"><div class="sc"><div class="sv">{{ total_registros }}</div><div class="sl">Registros totales</div></div></div>
</div>
<div class="tc mb-3"><div class="p-3"><form method="GET" class="row g-2 align-items-end">
  <div class="col-sm-3"><select name="tipo" class="form-select form-select-sm">
    <option value="">Todos los tipos</option>
    {% for t in tipos %}<option value="{{ t }}" {% if tipo_f==t %}selected{% endif %}>{{ t }}</option>{% endfor %}
  </select></div>
  <div class="col-sm-2"><input type="date" name="desde" class="form-control form-control-sm" value="{{ desde_f }}"></div>
  <div class="col-sm-2"><input type="date" name="hasta" class="form-control form-control-sm" value="{{ hasta_f }}"></div>
  <div class="col-auto">
    <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-search"></i></button>
    <a href="{{ url_for('gastos') }}" class="btn btn-outline-secondary btn-sm">Limpiar</a>
  </div>
</form></div></div>
<div class="tc"><div class="ch"><i class="bi bi-receipt me-2"></i>{{ items|length }} gasto(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Fecha</th><th>Tipo</th><th>Descripción</th><th>Monto COP</th><th></th></tr></thead>
  <tbody>{% for g in items %}<tr>
    <td><small>{{ g.fecha.strftime('%d/%m/%Y') }}</small></td>
    <td><span class="badge bg-secondary">{{ g.tipo }}</span></td>
    <td>{{ g.descripcion or '—' }}</td>
    <td class="fw-semibold">$ {{ '{:,.0f}'.format(g.monto).replace(',','.') }}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('gasto_editar', id=g.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('gasto_eliminar', id=g.id) }}" onsubmit="return confirm('¿Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5"><i class="bi bi-receipt" style="font-size:3rem"></i>
  <p class="mt-3">Sin gastos.</p><a href="{{ url_for('gasto_nuevo') }}" class="btn btn-primary">Agregar primero</a></div>
{% endif %}</div>{% endblock %}"""

T['gastos/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('gastos') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-4"><label class="form-label">Fecha *</label>
    <input type="date" name="fecha" class="form-control" value="{{ obj.fecha.strftime('%Y-%m-%d') if obj else today }}" required></div>
  <div class="col-md-4"><label class="form-label">Tipo *</label>
    <select name="tipo" class="form-select" required>
      {% for t in ['Arriendo','Servicios públicos','Nómina','Transporte','Mercadeo','Materia prima','Maquinaria','Impuestos','Logística','Mantenimiento','Otros'] %}
      <option value="{{ t }}" {% if obj and obj.tipo==t %}selected{% endif %}>{{ t }}</option>{% endfor %}
    </select></div>
  <div class="col-md-4"><label class="form-label">Monto COP *</label>
    <div class="input-group"><span class="input-group-text">$</span>
      <input type="number" name="monto" class="form-control" step="1" min="0" value="{{ obj.monto|int if obj else '0' }}" required></div></div>
  <div class="col-12"><label class="form-label">Descripción</label>
    <input type="text" name="descripcion" class="form-control" value="{{ obj.descripcion if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="2">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Guardar Gasto' }}</button>
  <a href="{{ url_for('gastos') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['admin/usuarios.html'] = """{% extends 'base.html' %}
{% block title %}Usuarios{% endblock %}{% block page_title %}Gestión de Usuarios{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('admin_usuario_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nuevo Usuario</a>{% endblock %}
{% block content %}<div class="tc"><div class="ch"><i class="bi bi-shield-person-fill me-2"></i>{{ items|length }} usuario(s)</div>
<table class="table"><thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th>Alta</th><th></th></tr></thead>
<tbody>{% for u in items %}<tr>
  <td><div class="d-flex align-items-center gap-2">
    <div class="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
         style="width:30px;height:30px;background:#5e72e4;font-size:.8rem;flex-shrink:0">{{ u.nombre[0].upper() }}</div>
    <div class="fw-semibold" style="color:#1a1f36">{{ u.nombre }}</div></div></td>
  <td>{{ u.email }}</td>
  <td><span class="badge {{ 'bg-primary' if u.rol=='admin' else 'bg-secondary' }}">{{ u.rol.title() }}</span></td>
  <td><span class="b b-{{ 'activo' if u.activo else 'inactivo' }}">{{ 'Activo' if u.activo else 'Inactivo' }}</span></td>
  <td><small class="text-muted">{{ u.creado_en.strftime('%d/%m/%Y') }}</small></td>
  <td>{% if u.id != current_user.id %}
    <form method="POST" action="{{ url_for('admin_usuario_toggle', id=u.id) }}">
      <button class="btn btn-sm {{ 'btn-outline-warning' if u.activo else 'btn-outline-success' }}">
        {{ 'Desactivar' if u.activo else 'Activar' }}</button></form>
    {% else %}<small class="text-muted">(tú)</small>{% endif %}</td>
</tr>{% endfor %}</tbody></table></div>{% endblock %}"""

T['admin/usuario_form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('admin_usuarios') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre *</label><input type="text" name="nombre" class="form-control" required></div>
  <div class="col-md-6"><label class="form-label">Email *</label><input type="email" name="email" class="form-control" required></div>
  <div class="col-md-6"><label class="form-label">Contraseña *</label><input type="password" name="password" class="form-control" required></div>
  <div class="col-md-6"><label class="form-label">Rol</label>
    <select name="rol" class="form-select"><option value="usuario">Usuario</option><option value="admin">Administrador</option></select></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>Crear Usuario</button>
  <a href="{{ url_for('admin_usuarios') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['perfil.html'] = """{% extends 'base.html' %}
{% block title %}Mi Perfil{% endblock %}{% block page_title %}Mi Perfil{% endblock %}
{% block content %}
<div class="row g-4">
  <div class="col-md-6">
    <div class="fc">
      <h5 class="mb-3"><i class="bi bi-person-circle me-2 text-primary"></i>Datos personales</h5>
      <form method="POST" action="{{ url_for('perfil') }}">
        <input type="hidden" name="accion" value="datos">
        <div class="row g-3">
          <div class="col-12"><label class="form-label">Nombre *</label>
            <input type="text" name="nombre" class="form-control" value="{{ current_user.nombre }}" required></div>
          <div class="col-12"><label class="form-label">Email *</label>
            <input type="email" name="email" class="form-control" value="{{ current_user.email }}" required></div>
        </div>
        <div class="mt-3">
          <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>Guardar cambios</button>
        </div>
      </form>
    </div>
  </div>
  <div class="col-md-6">
    <div class="fc">
      <h5 class="mb-3"><i class="bi bi-lock-fill me-2 text-warning"></i>Cambiar contraseña</h5>
      <form method="POST" action="{{ url_for('perfil') }}">
        <input type="hidden" name="accion" value="password">
        <div class="row g-3">
          <div class="col-12"><label class="form-label">Contraseña actual *</label>
            <input type="password" name="password_actual" class="form-control" required></div>
          <div class="col-12"><label class="form-label">Nueva contraseña *</label>
            <input type="password" name="password_nueva" class="form-control" minlength="6" required></div>
          <div class="col-12"><label class="form-label">Confirmar nueva contraseña *</label>
            <input type="password" name="password_confirmar" class="form-control" minlength="6" required></div>
        </div>
        <div class="mt-3">
          <button type="submit" class="btn btn-warning"><i class="bi bi-key me-1"></i>Cambiar contraseña</button>
        </div>
      </form>
    </div>
  </div>
</div>{% endblock %}"""

T['reportes.html'] = """{% extends 'base.html' %}
{% block title %}Reportes{% endblock %}{% block page_title %}Reportes{% endblock %}
{% block topbar_actions %}
<div class="dropdown">
  <button class="btn btn-success btn-sm dropdown-toggle" data-bs-toggle="dropdown"><i class="bi bi-file-earmark-excel me-1"></i>Exportar Excel</button>
  <ul class="dropdown-menu">
    <li><a class="dropdown-item" href="{{ url_for('exportar_ventas') }}"><i class="bi bi-graph-up-arrow me-2 text-primary"></i>Ventas</a></li>
    <li><a class="dropdown-item" href="{{ url_for('exportar_gastos') }}"><i class="bi bi-receipt me-2 text-danger"></i>Gastos Operativos</a></li>
    <li><a class="dropdown-item" href="{{ url_for('exportar_inventario') }}"><i class="bi bi-box-seam me-2 text-success"></i>Inventario</a></li>
    <li><a class="dropdown-item" href="{{ url_for('exportar_clientes') }}"><i class="bi bi-people me-2 text-info"></i>Clientes</a></li>
  </ul>
</div>{% endblock %}
{% block content %}
<div class="row g-3 mb-4">
  <div class="col-md-3"><div class="sc">
    <div class="sv" style="color:#5e72e4">{{ total_clientes }}</div>
    <div class="sl">Clientes activos</div></div></div>
  <div class="col-md-3"><div class="sc">
    <div class="sv valor-cop" data-cop="{{ ingresos_totales }}">$ {{ '{:,.0f}'.format(ingresos_totales).replace(',','.') }}</div>
    <div class="sl">Ingresos totales (ventas ganadas)</div></div></div>
  <div class="col-md-3"><div class="sc">
    <div class="sv valor-cop" data-cop="{{ gastos_totales }}">$ {{ '{:,.0f}'.format(gastos_totales).replace(',','.') }}</div>
    <div class="sl">Gastos operativos totales</div></div></div>
  <div class="col-md-3"><div class="sc">
    <div class="sv valor-cop" data-cop="{{ balance }}" style="color:{{ '#2dce89' if balance>=0 else '#f5365c' }}">$ {{ '{:,.0f}'.format(balance).replace(',','.') }}</div>
    <div class="sl">Balance</div></div></div>
</div>
<div class="row g-4 mb-4">
  <div class="col-lg-7">
    <div class="tc"><div class="ch"><i class="bi bi-bar-chart me-2"></i>Ventas por mes (últimos 6 meses)</div>
      <canvas id="chartVentas" height="100"></canvas>
    </div>
  </div>
  <div class="col-lg-5">
    <div class="tc"><div class="ch"><i class="bi bi-pie-chart me-2"></i>Gastos por tipo</div>
      <canvas id="chartGastos" height="160"></canvas>
    </div>
  </div>
</div>
<div class="row g-4">
  <div class="col-md-6">
    <div class="tc"><div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-trophy me-2 text-warning"></i>Top 5 clientes por ventas</span></div>
      <table class="table"><tbody>
      {% for c in top_clientes %}
      <tr><td><a href="{{ url_for('cliente_ver', id=c.id) }}" class="fw-semibold text-decoration-none" style="color:#1a1f36">{{ c.empresa or c.nombre }}</a></td>
        <td class="text-end fw-semibold">$ {{ '{:,.0f}'.format(c.total_ventas or 0).replace(',','.') }}</td></tr>
      {% else %}<tr><td colspan="2" class="text-muted text-center">Sin datos</td></tr>{% endfor %}
      </tbody></table>
    </div>
  </div>
  <div class="col-md-6">
    <div class="tc"><div class="ch"><i class="bi bi-exclamation-triangle me-2 text-warning"></i>Stock bajo</div>
      {% if bajo_stock %}
      <table class="table"><thead><tr><th>Producto</th><th>Stock</th><th>Mínimo</th></tr></thead><tbody>
      {% for p in bajo_stock %}
      <tr><td>{{ p.nombre }}</td>
        <td class="fw-bold text-danger">{{ p.stock }}</td>
        <td class="text-muted">{{ p.stock_minimo }}</td></tr>
      {% endfor %}</tbody></table>
      {% else %}<div class="text-center text-muted py-3"><i class="bi bi-check-circle text-success" style="font-size:2rem"></i>
        <p class="mt-2">Todo el inventario está OK</p></div>{% endif %}
    </div>
  </div>
</div>{% endblock %}
{% block scripts %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>
const meses = {{ meses_labels|tojson }};
const ventasMes = {{ ventas_por_mes|tojson }};
const gastosTipos = {{ gastos_tipos_labels|tojson }};
const gastosTotales = {{ gastos_tipos_values|tojson }};
new Chart(document.getElementById('chartVentas'),{type:'bar',data:{labels:meses,datasets:[{
  label:'Ventas COP',data:ventasMes,backgroundColor:'rgba(94,114,228,0.7)',borderRadius:6}]},
  options:{responsive:true,plugins:{legend:{display:false}},scales:{y:{ticks:{callback:v=>'$'+v.toLocaleString('es-CO')}}}}});
const colores=['#5e72e4','#2dce89','#fb6340','#11cdef','#f4f5f7','#adb5bd'];
new Chart(document.getElementById('chartGastos'),{type:'doughnut',data:{labels:gastosTipos,
  datasets:[{data:gastosTotales,backgroundColor:colores.slice(0,gastosTipos.length),borderWidth:2}]},
  options:{responsive:true,plugins:{legend:{position:'bottom'}}}});
</script>{% endblock %}"""

app.jinja_loader = DictLoader(T)

# =============================================================
# RUTAS — AUTENTICACIÓN
# =============================================================

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email','').strip()).first()
        if user and user.check_password(request.form.get('password','')) and user.activo:
            login_user(user, remember=bool(request.form.get('remember')))
            flash(f'¡Bienvenido, {user.nombre}!', 'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Email o contraseña incorrectos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); flash('Sesión cerrada.', 'info'); return redirect(url_for('login'))

# =============================================================
# DASHBOARD
# =============================================================

@app.route('/')
@login_required
def dashboard():
    from datetime import date
    hoy = date.today()
    mes_inicio = hoy.replace(day=1)
    ingresos = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['ganado','anticipo_pagado'])).scalar() or 0
    gastos_tot = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
    gastos_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha >= mes_inicio).scalar() or 0
    saldo_pend = db.session.query(db.func.sum(Venta.saldo)).filter(Venta.estado.in_(['anticipo_pagado','negociacion'])).scalar() or 0
    return render_template('dashboard.html',
        total_clientes       = Cliente.query.filter_by(estado='activo').count(),
        ventas_ganadas       = Venta.query.filter_by(estado='ganado').count(),
        tareas_pendientes    = Tarea.query.filter(Tarea.estado != 'completada').count(),
        ingresos_totales     = ingresos,
        gastos_totales       = gastos_tot,
        balance              = ingresos - gastos_tot,
        saldo_pendiente      = saldo_pend,
        productos_bajo_stock = Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).count(),
        tareas_recientes     = Tarea.query.filter(Tarea.estado!='completada').order_by(Tarea.creado_en.desc()).limit(5).all(),
        ventas_recientes     = Venta.query.order_by(Venta.creado_en.desc()).limit(6).all(),
    )

# =============================================================
# CLIENTES
# =============================================================

@app.route('/clientes')
@login_required
def clientes():
    busqueda = request.args.get('buscar','')
    estado_rel_f = request.args.get('estado_rel','')
    q = Cliente.query
    if busqueda:
        q = q.filter(db.or_(Cliente.nombre.ilike(f'%{busqueda}%'),
                             Cliente.empresa.ilike(f'%{busqueda}%'),
                             Cliente.nit.ilike(f'%{busqueda}%')))
    if estado_rel_f: q = q.filter_by(estado_relacion=estado_rel_f)
    return render_template('clientes/index.html', items=q.order_by(Cliente.empresa, Cliente.nombre).all(),
                           busqueda=busqueda, estado_rel_f=estado_rel_f)

def _save_contactos(cliente_obj):
    ContactoCliente.query.filter_by(cliente_id=cliente_obj.id).delete()
    nombres   = request.form.getlist('c_nombre[]')
    cargos    = request.form.getlist('c_cargo[]')
    emails    = request.form.getlist('c_email[]')
    telefonos = request.form.getlist('c_telefono[]')
    for i, n in enumerate(nombres):
        if n.strip():
            db.session.add(ContactoCliente(
                cliente_id=cliente_obj.id,
                nombre=n.strip(),
                cargo=cargos[i] if i < len(cargos) else '',
                email=emails[i] if i < len(emails) else '',
                telefono=telefonos[i] if i < len(telefonos) else ''))

@app.route('/clientes/nuevo', methods=['GET','POST'])
@login_required
def cliente_nuevo():
    if request.method == 'POST':
        c = Cliente(nombre=request.form.get('empresa','') or request.form.get('nombre',''),
            empresa=request.form.get('empresa',''), nit=request.form.get('nit',''),
            estado_relacion=request.form.get('estado_relacion','prospecto'),
            dir_comercial=request.form.get('dir_comercial',''),
            dir_entrega=request.form.get('dir_entrega',''),
            notas=request.form.get('notas',''), estado='activo')
        db.session.add(c); db.session.flush()
        _save_contactos(c); db.session.commit()
        flash('Cliente creado.','success'); return redirect(url_for('clientes'))
    return render_template('clientes/form.html', obj=None, titulo='Nuevo Cliente')

@app.route('/clientes/<int:id>')
@login_required
def cliente_ver(id):
    return render_template('clientes/ver.html', obj=Cliente.query.get_or_404(id))

@app.route('/clientes/<int:id>/editar', methods=['GET','POST'])
@login_required
def cliente_editar(id):
    obj = Cliente.query.get_or_404(id)
    if request.method == 'POST':
        obj.empresa=request.form.get('empresa',''); obj.nit=request.form.get('nit','')
        obj.nombre=request.form.get('empresa','') or obj.nombre
        obj.estado_relacion=request.form.get('estado_relacion','prospecto')
        obj.dir_comercial=request.form.get('dir_comercial','')
        obj.dir_entrega=request.form.get('dir_entrega','')
        obj.notas=request.form.get('notas',''); obj.actualizado_en=datetime.utcnow()
        db.session.flush(); _save_contactos(obj); db.session.commit()
        flash('Cliente actualizado.','success'); return redirect(url_for('cliente_ver', id=obj.id))
    return render_template('clientes/form.html', obj=obj, titulo='Editar Cliente')

@app.route('/clientes/<int:id>/eliminar', methods=['POST'])
@login_required
def cliente_eliminar(id):
    obj=Cliente.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Cliente eliminado.','info'); return redirect(url_for('clientes'))

# =============================================================
# VENTAS
# =============================================================

@app.route('/ventas')
@login_required
def ventas():
    estado_f=request.args.get('estado','')
    q=Venta.query
    if estado_f: q=q.filter_by(estado=estado_f)
    return render_template('ventas/index.html', items=q.order_by(Venta.creado_en.desc()).all(), estado_f=estado_f)

def _prods_json():
    prods = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return json.dumps([{'id':p.id,'nombre':p.nombre,'sku':p.sku or '','precio':p.precio} for p in prods])

def _save_items(venta_obj):
    VentaProducto.query.filter_by(venta_id=venta_obj.id).delete()
    pids    = request.form.getlist('prod_id[]')
    cants   = request.form.getlist('prod_cant[]')
    precios = request.form.getlist('prod_precio[]')
    for i, pid in enumerate(pids):
        cant  = float(cants[i]) if i < len(cants) else 1
        precio= float(precios[i]) if i < len(precios) else 0
        prod  = Producto.query.get(int(pid)) if pid else None
        db.session.add(VentaProducto(
            venta_id=venta_obj.id,
            producto_id=int(pid) if pid else None,
            nombre_prod=prod.nombre if prod else '',
            cantidad=cant, precio_unit=precio, subtotal=cant*precio))

@app.route('/ventas/nueva', methods=['GET','POST'])
@login_required
def venta_nueva():
    cl = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
    if request.method == 'POST':
        fa = request.form.get('fecha_anticipo')
        fe = request.form.get('fecha_entrega_est')
        v = Venta(titulo=request.form['titulo'],
            cliente_id=request.form.get('cliente_id') or None,
            subtotal=float(request.form.get('subtotal_calc') or 0),
            iva=float(request.form.get('iva_calc') or 0),
            total=float(request.form.get('total_calc') or 0),
            porcentaje_anticipo=float(request.form.get('porcentaje_anticipo') or 0),
            monto_anticipo=float(request.form.get('monto_anticipo') or 0),
            saldo=float(request.form.get('saldo') or 0),
            estado=request.form.get('estado','prospecto'),
            fecha_anticipo=datetime.strptime(fa,'%Y-%m-%d').date() if fa else None,
            dias_entrega=int(request.form.get('dias_entrega') or 30),
            fecha_entrega_est=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None,
            notas=request.form.get('notas',''), creado_por=current_user.id)
        db.session.add(v); db.session.flush()
        _save_items(v); db.session.commit()
        flash('Venta creada.','success'); return redirect(url_for('ventas'))
    return render_template('ventas/form.html', obj=None, clientes_list=cl,
                           titulo='Nueva Venta', productos_json=_prods_json(), items_json='[]')

@app.route('/ventas/<int:id>/editar', methods=['GET','POST'])
@login_required
def venta_editar(id):
    obj = Venta.query.get_or_404(id)
    cl  = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
    if request.method == 'POST':
        fa = request.form.get('fecha_anticipo')
        fe = request.form.get('fecha_entrega_est')
        obj.titulo=request.form['titulo']; obj.cliente_id=request.form.get('cliente_id') or None
        obj.subtotal=float(request.form.get('subtotal_calc') or 0)
        obj.iva=float(request.form.get('iva_calc') or 0)
        obj.total=float(request.form.get('total_calc') or 0)
        obj.porcentaje_anticipo=float(request.form.get('porcentaje_anticipo') or 0)
        obj.monto_anticipo=float(request.form.get('monto_anticipo') or 0)
        obj.saldo=float(request.form.get('saldo') or 0)
        obj.estado=request.form.get('estado','prospecto')
        obj.fecha_anticipo=datetime.strptime(fa,'%Y-%m-%d').date() if fa else None
        obj.dias_entrega=int(request.form.get('dias_entrega') or 30)
        obj.fecha_entrega_est=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None
        obj.notas=request.form.get('notas','')
        db.session.flush(); _save_items(obj); db.session.commit()
        flash('Venta actualizada.','success'); return redirect(url_for('ventas'))
    items_j = json.dumps([{'pid':it.producto_id or '','nombre':it.nombre_prod,
                            'cant':it.cantidad,'precio':it.precio_unit} for it in obj.items])
    return render_template('ventas/form.html', obj=obj, clientes_list=cl,
                           titulo='Editar Venta', productos_json=_prods_json(), items_json=items_j)

@app.route('/ventas/<int:id>/eliminar', methods=['POST'])
@login_required
def venta_eliminar(id):
    obj=Venta.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Venta eliminada.','info'); return redirect(url_for('ventas'))

# =============================================================
# TAREAS (v8: múltiples asignados + chat)
# =============================================================

def _save_asignados(tarea_obj):
    TareaAsignado.query.filter_by(tarea_id=tarea_obj.id).delete()
    # asignado principal
    principal = request.form.get('asignado_a')
    # otros asignados (multi-select)
    otros = request.form.getlist('otros_asignados[]')
    seen = set()
    for uid_str in ([principal] if principal else []) + otros:
        try:
            uid = int(uid_str)
            if uid not in seen:
                seen.add(uid)
                db.session.add(TareaAsignado(tarea_id=tarea_obj.id, user_id=uid))
        except (ValueError, TypeError):
            pass
    if not seen:
        db.session.add(TareaAsignado(tarea_id=tarea_obj.id, user_id=current_user.id))

@app.route('/tareas')
@login_required
def tareas():
    estado_f=request.args.get('estado',''); prioridad_f=request.args.get('prioridad','')
    q=Tarea.query
    if estado_f: q=q.filter_by(estado=estado_f)
    if prioridad_f: q=q.filter_by(prioridad=prioridad_f)
    return render_template('tareas/index.html', items=q.order_by(Tarea.creado_en.desc()).all(),
        estado_f=estado_f, prioridad_f=prioridad_f)

@app.route('/tareas/nueva', methods=['GET','POST'])
@login_required
def tarea_nueva():
    us=User.query.filter_by(activo=True).all()
    if request.method == 'POST':
        fs=request.form.get('fecha_vencimiento')
        t=Tarea(titulo=request.form['titulo'], descripcion=request.form.get('descripcion',''),
            estado=request.form.get('estado','pendiente'), prioridad=request.form.get('prioridad','media'),
            fecha_vencimiento=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None,
            asignado_a=int(request.form.get('asignado_a') or current_user.id),
            creado_por=current_user.id)
        db.session.add(t); db.session.flush()
        _save_asignados(t); db.session.commit()
        flash('Tarea creada.','success'); return redirect(url_for('tareas'))
    return render_template('tareas/form.html', obj=None, usuarios=us, titulo='Nueva Tarea', asignados_ids=[])

@app.route('/tareas/<int:id>')
@login_required
def tarea_ver(id):
    obj=Tarea.query.get_or_404(id)
    return render_template('tareas/ver.html', obj=obj, tarea=obj)

@app.route('/tareas/<int:id>/comentar', methods=['POST'])
@login_required
def tarea_comentar(id):
    obj=Tarea.query.get_or_404(id)
    msg=request.form.get('mensaje','').strip()
    if msg:
        db.session.add(TareaComentario(tarea_id=obj.id, autor_id=current_user.id, mensaje=msg))
        db.session.commit()
        flash('Comentario agregado.','success')
    return redirect(url_for('tarea_ver', id=id))

@app.route('/tareas/<int:id>/editar', methods=['GET','POST'])
@login_required
def tarea_editar(id):
    obj=Tarea.query.get_or_404(id); us=User.query.filter_by(activo=True).all()
    if request.method == 'POST':
        fs=request.form.get('fecha_vencimiento')
        obj.titulo=request.form['titulo']; obj.descripcion=request.form.get('descripcion','')
        obj.estado=request.form.get('estado','pendiente'); obj.prioridad=request.form.get('prioridad','media')
        obj.fecha_vencimiento=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None
        obj.asignado_a=int(request.form.get('asignado_a') or current_user.id)
        db.session.flush(); _save_asignados(obj); db.session.commit()
        flash('Tarea actualizada.','success'); return redirect(url_for('tarea_ver', id=obj.id))
    asignados_ids=[a.user_id for a in obj.asignados]
    return render_template('tareas/form.html', obj=obj, usuarios=us, titulo='Editar Tarea', asignados_ids=asignados_ids)

@app.route('/tareas/<int:id>/completar', methods=['POST'])
@login_required
def tarea_completar(id):
    obj=Tarea.query.get_or_404(id); obj.estado='completada'; db.session.commit()
    flash('¡Tarea completada!','success'); return redirect(url_for('tareas'))

@app.route('/tareas/<int:id>/eliminar', methods=['POST'])
@login_required
def tarea_eliminar(id):
    obj=Tarea.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Tarea eliminada.','info'); return redirect(url_for('tareas'))

# =============================================================
# INVENTARIO (v8: NSO + costo)
# =============================================================

@app.route('/inventario')
@login_required
def inventario():
    busqueda=request.args.get('buscar',''); categoria_f=request.args.get('categoria','')
    q=Producto.query.filter_by(activo=True)
    if busqueda:
        q=q.filter(db.or_(Producto.nombre.ilike(f'%{busqueda}%'),
                           Producto.sku.ilike(f'%{busqueda}%'),
                           Producto.nso.ilike(f'%{busqueda}%')))
    if categoria_f: q=q.filter_by(categoria=categoria_f)
    cats=[c[0] for c in db.session.query(Producto.categoria).filter(
        Producto.activo==True,Producto.categoria!=None,Producto.categoria!='').distinct().all()]
    return render_template('inventario/index.html', items=q.order_by(Producto.nombre).all(),
                           busqueda=busqueda, categoria_f=categoria_f, categorias=cats)

@app.route('/inventario/nuevo', methods=['GET','POST'])
@login_required
def producto_nuevo():
    if request.method == 'POST':
        db.session.add(Producto(
            nombre=request.form['nombre'], descripcion=request.form.get('descripcion',''),
            sku=request.form.get('sku') or None, nso=request.form.get('nso') or None,
            precio=float(request.form.get('precio',0) or 0),
            costo=float(request.form.get('costo',0) or 0),
            stock=int(request.form.get('stock',0) or 0),
            stock_minimo=int(request.form.get('stock_minimo',5) or 5),
            categoria=request.form.get('categoria','')))
        db.session.commit(); flash('Producto creado.','success'); return redirect(url_for('inventario'))
    return render_template('inventario/form.html', obj=None, titulo='Nuevo Producto')

@app.route('/inventario/<int:id>/editar', methods=['GET','POST'])
@login_required
def producto_editar(id):
    obj=Producto.query.get_or_404(id)
    if request.method == 'POST':
        obj.nombre=request.form['nombre']; obj.descripcion=request.form.get('descripcion','')
        obj.sku=request.form.get('sku') or None; obj.nso=request.form.get('nso') or None
        obj.precio=float(request.form.get('precio',0) or 0)
        obj.costo=float(request.form.get('costo',0) or 0)
        obj.stock=int(request.form.get('stock',0) or 0)
        obj.stock_minimo=int(request.form.get('stock_minimo',5) or 5)
        obj.categoria=request.form.get('categoria','')
        db.session.commit(); flash('Producto actualizado.','success'); return redirect(url_for('inventario'))
    return render_template('inventario/form.html', obj=obj, titulo='Editar Producto')

@app.route('/inventario/<int:id>/eliminar', methods=['POST'])
@login_required
def producto_eliminar(id):
    obj=Producto.query.get_or_404(id); obj.activo=False; db.session.commit()
    flash('Producto eliminado.','info'); return redirect(url_for('inventario'))

# =============================================================
# PRODUCCIÓN
# =============================================================

@app.route('/produccion')
@login_required
def produccion_index():
    from datetime import date
    mes_ini = date.today().replace(day=1)
    total_compras  = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
    compras_mes    = db.session.query(db.func.sum(CompraMateria.costo_total)).filter(CompraMateria.fecha >= mes_ini).scalar() or 0
    cotizaciones_vigentes = CotizacionGranel.query.filter_by(estado='vigente').count()
    reglas_activas = ReglaTributaria.query.filter_by(activo=True).count()
    compras_recientes = CompraMateria.query.order_by(CompraMateria.fecha.desc()).limit(5).all()
    granel_recientes  = CotizacionGranel.query.order_by(CotizacionGranel.creado_en.desc()).limit(5).all()
    reglas = ReglaTributaria.query.filter_by(activo=True).order_by(ReglaTributaria.nombre).limit(5).all()
    return render_template('produccion/index.html',
        total_compras=total_compras, compras_mes=compras_mes,
        cotizaciones_vigentes=cotizaciones_vigentes, reglas_activas=reglas_activas,
        compras_recientes=compras_recientes, granel_recientes=granel_recientes,
        reglas=reglas)

# --- Compras de Materia Prima ---

@app.route('/produccion/compras')
@login_required
def compras():
    busqueda=request.args.get('buscar','')
    q=CompraMateria.query
    if busqueda:
        q=q.filter(db.or_(CompraMateria.nombre_item.ilike(f'%{busqueda}%'),
                           CompraMateria.proveedor.ilike(f'%{busqueda}%'),
                           CompraMateria.nro_factura.ilike(f'%{busqueda}%')))
    from datetime import date
    mes_ini = date.today().replace(day=1)
    total_general = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
    total_mes = db.session.query(db.func.sum(CompraMateria.costo_total)).filter(CompraMateria.fecha >= mes_ini).scalar() or 0
    return render_template('produccion/compras.html', items=q.order_by(CompraMateria.fecha.desc()).all(),
                           busqueda=busqueda, total_general=total_general, total_mes=total_mes)

@app.route('/produccion/compras/nueva', methods=['GET','POST'])
@login_required
def compra_nueva():
    if request.method == 'POST':
        fd = request.form.get('fecha')
        cant  = float(request.form.get('cantidad',1) or 1)
        costo_p = float(request.form.get('costo_producto',0) or 0)
        imp   = float(request.form.get('impuestos',0) or 0)
        trans = float(request.form.get('transporte',0) or 0)
        costo_total = costo_p + imp + trans
        precio_unit = (costo_total / cant) if cant > 0 else 0
        pid   = request.form.get('producto_id') or None
        c = CompraMateria(
            producto_id=int(pid) if pid else None,
            nombre_item=request.form['nombre_item'],
            proveedor=request.form.get('proveedor',''),
            fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
            nro_factura=request.form.get('nro_factura',''),
            cantidad=cant, costo_producto=costo_p, impuestos=imp, transporte=trans,
            costo_total=costo_total, precio_unitario=precio_unit,
            notas=request.form.get('notas',''), creado_por=current_user.id)
        db.session.add(c)
        if pid:
            prod = Producto.query.get(int(pid))
            if prod: prod.costo = precio_unit
        db.session.commit()
        flash('Compra registrada y costo actualizado.','success')
        return redirect(url_for('compras'))
    return render_template('produccion/compra_form.html', obj=None, titulo='Nueva Compra',
                           productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/produccion/compras/<int:id>/editar', methods=['GET','POST'])
@login_required
def compra_editar(id):
    obj=CompraMateria.query.get_or_404(id)
    if request.method == 'POST':
        fd = request.form.get('fecha')
        cant  = float(request.form.get('cantidad',1) or 1)
        costo_p = float(request.form.get('costo_producto',0) or 0)
        imp   = float(request.form.get('impuestos',0) or 0)
        trans = float(request.form.get('transporte',0) or 0)
        costo_total = costo_p + imp + trans
        precio_unit = (costo_total / cant) if cant > 0 else 0
        pid   = request.form.get('producto_id') or None
        obj.producto_id=int(pid) if pid else None
        obj.nombre_item=request.form['nombre_item']; obj.proveedor=request.form.get('proveedor','')
        obj.fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else obj.fecha
        obj.nro_factura=request.form.get('nro_factura','')
        obj.cantidad=cant; obj.costo_producto=costo_p; obj.impuestos=imp; obj.transporte=trans
        obj.costo_total=costo_total; obj.precio_unitario=precio_unit
        obj.notas=request.form.get('notas','')
        if pid:
            prod = Producto.query.get(int(pid))
            if prod: prod.costo = precio_unit
        db.session.commit()
        flash('Compra actualizada y costo actualizado.','success')
        return redirect(url_for('compras'))
    return render_template('produccion/compra_form.html', obj=obj, titulo='Editar Compra',
                           productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/produccion/compras/<int:id>/eliminar', methods=['POST'])
@login_required
def compra_eliminar(id):
    obj=CompraMateria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Compra eliminada.','info'); return redirect(url_for('compras'))

# --- Cotizaciones Granel ---

@app.route('/produccion/granel')
@login_required
def granel():
    estado_f=request.args.get('estado','')
    q=CotizacionGranel.query
    if estado_f: q=q.filter_by(estado=estado_f)
    return render_template('produccion/granel.html', items=q.order_by(CotizacionGranel.creado_en.desc()).all(),
                           estado_f=estado_f)

@app.route('/produccion/granel/nueva', methods=['GET','POST'])
@login_required
def granel_nuevo():
    if request.method == 'POST':
        fc = request.form.get('fecha_cotizacion')
        fv = request.form.get('vigencia')
        pid = request.form.get('producto_id') or None
        estado = request.form.get('estado','vigente')
        precio_u = float(request.form.get('precio_unitario',0) or 0)
        g = CotizacionGranel(
            producto_id=int(pid) if pid else None,
            nombre_producto=request.form['nombre_producto'],
            sku=request.form.get('sku',''), nso=request.form.get('nso',''),
            proveedor=request.form.get('proveedor',''),
            precio_unitario=precio_u,
            unidades_minimas=int(request.form.get('unidades_minimas',1) or 1),
            fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else None,
            vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
            estado=estado, notas=request.form.get('notas',''), creado_por=current_user.id)
        db.session.add(g)
        if pid and estado == 'vigente':
            prod = Producto.query.get(int(pid))
            if prod: prod.costo = precio_u
        db.session.commit()
        flash('Cotización guardada.','success')
        return redirect(url_for('granel'))
    return render_template('produccion/granel_form.html', obj=None, titulo='Nueva Cotización Granel',
                           productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/produccion/granel/<int:id>/editar', methods=['GET','POST'])
@login_required
def granel_editar(id):
    obj=CotizacionGranel.query.get_or_404(id)
    if request.method == 'POST':
        fc = request.form.get('fecha_cotizacion')
        fv = request.form.get('vigencia')
        pid = request.form.get('producto_id') or None
        estado = request.form.get('estado','vigente')
        precio_u = float(request.form.get('precio_unitario',0) or 0)
        obj.producto_id=int(pid) if pid else None
        obj.nombre_producto=request.form['nombre_producto']
        obj.sku=request.form.get('sku',''); obj.nso=request.form.get('nso','')
        obj.proveedor=request.form.get('proveedor',''); obj.precio_unitario=precio_u
        obj.unidades_minimas=int(request.form.get('unidades_minimas',1) or 1)
        obj.fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else None
        obj.vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None
        obj.estado=estado; obj.notas=request.form.get('notas','')
        if pid and estado == 'vigente':
            prod = Producto.query.get(int(pid))
            if prod: prod.costo = precio_u
        db.session.commit()
        flash('Cotización actualizada.','success')
        return redirect(url_for('granel'))
    return render_template('produccion/granel_form.html', obj=obj, titulo='Editar Cotización Granel',
                           productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/produccion/granel/<int:id>/eliminar', methods=['POST'])
@login_required
def granel_eliminar(id):
    obj=CotizacionGranel.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Cotización eliminada.','info'); return redirect(url_for('granel'))

# --- Reglas Tributarias ---

@app.route('/produccion/impuestos')
@login_required
def impuestos():
    return render_template('produccion/impuestos.html',
                           items=ReglaTributaria.query.order_by(ReglaTributaria.nombre).all())

@app.route('/produccion/impuestos/nuevo', methods=['GET','POST'])
@login_required
def impuesto_nuevo():
    if request.method == 'POST':
        db.session.add(ReglaTributaria(
            nombre=request.form['nombre'],
            descripcion=request.form.get('descripcion',''),
            porcentaje=float(request.form.get('porcentaje',0) or 0),
            aplica_a=request.form.get('aplica_a',''),
            activo=True))
        db.session.commit(); flash('Regla tributaria creada.','success')
        return redirect(url_for('impuestos'))
    return render_template('produccion/impuesto_form.html', obj=None, titulo='Nueva Regla Tributaria')

@app.route('/produccion/impuestos/<int:id>/editar', methods=['GET','POST'])
@login_required
def impuesto_editar(id):
    obj=ReglaTributaria.query.get_or_404(id)
    if request.method == 'POST':
        obj.nombre=request.form['nombre']
        obj.descripcion=request.form.get('descripcion','')
        obj.porcentaje=float(request.form.get('porcentaje',0) or 0)
        obj.aplica_a=request.form.get('aplica_a','')
        obj.activo = request.form.get('activo') == '1'
        db.session.commit(); flash('Regla actualizada.','success')
        return redirect(url_for('impuestos'))
    return render_template('produccion/impuesto_form.html', obj=obj, titulo='Editar Regla Tributaria')

@app.route('/produccion/impuestos/<int:id>/eliminar', methods=['POST'])
@login_required
def impuesto_eliminar(id):
    obj=ReglaTributaria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Regla eliminada.','info'); return redirect(url_for('impuestos'))

# =============================================================
# GASTOS OPERATIVOS
# =============================================================

@app.route('/gastos')
@login_required
def gastos():
    from datetime import date
    tipo_f  = request.args.get('tipo','')
    desde_f = request.args.get('desde','')
    hasta_f = request.args.get('hasta','')
    q = GastoOperativo.query
    if tipo_f:  q = q.filter_by(tipo=tipo_f)
    if desde_f: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_f,'%Y-%m-%d').date())
    if hasta_f: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_f,'%Y-%m-%d').date())
    items = q.order_by(GastoOperativo.fecha.desc()).all()
    total_g  = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
    mes_ini  = date.today().replace(day=1)
    total_mes= db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha>=mes_ini).scalar() or 0
    tipos    = [t[0] for t in db.session.query(GastoOperativo.tipo).distinct().order_by(GastoOperativo.tipo).all()]
    return render_template('gastos/index.html', items=items, tipo_f=tipo_f,
        desde_f=desde_f, hasta_f=hasta_f, total_general=total_g,
        total_mes=total_mes, total_registros=GastoOperativo.query.count(), tipos=tipos)

@app.route('/gastos/nuevo', methods=['GET','POST'])
@login_required
def gasto_nuevo():
    if request.method == 'POST':
        fd = request.form.get('fecha')
        db.session.add(GastoOperativo(
            fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
            tipo=request.form['tipo'], descripcion=request.form.get('descripcion',''),
            monto=float(request.form.get('monto',0) or 0),
            notas=request.form.get('notas',''), creado_por=current_user.id))
        db.session.commit(); flash('Gasto registrado.','success'); return redirect(url_for('gastos'))
    return render_template('gastos/form.html', obj=None, titulo='Nuevo Gasto',
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/gastos/<int:id>/editar', methods=['GET','POST'])
@login_required
def gasto_editar(id):
    obj = GastoOperativo.query.get_or_404(id)
    if request.method == 'POST':
        fd = request.form.get('fecha')
        obj.fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else obj.fecha
        obj.tipo=request.form['tipo']; obj.descripcion=request.form.get('descripcion','')
        obj.monto=float(request.form.get('monto',0) or 0); obj.notas=request.form.get('notas','')
        db.session.commit(); flash('Gasto actualizado.','success'); return redirect(url_for('gastos'))
    return render_template('gastos/form.html', obj=obj, titulo='Editar Gasto',
                           today=datetime.utcnow().strftime('%Y-%m-%d'))

@app.route('/gastos/<int:id>/eliminar', methods=['POST'])
@login_required
def gasto_eliminar(id):
    obj=GastoOperativo.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Gasto eliminado.','info'); return redirect(url_for('gastos'))

# =============================================================
# ADMIN
# =============================================================

@app.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if current_user.rol != 'admin':
        flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
    return render_template('admin/usuarios.html', items=User.query.order_by(User.nombre).all())

@app.route('/admin/usuarios/nuevo', methods=['GET','POST'])
@login_required
def admin_usuario_nuevo():
    if current_user.rol != 'admin':
        flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash('Ya existe ese email.','danger')
        else:
            u=User(nombre=request.form['nombre'],email=request.form['email'],rol=request.form.get('rol','usuario'))
            u.set_password(request.form['password']); db.session.add(u); db.session.commit()
            flash('Usuario creado.','success'); return redirect(url_for('admin_usuarios'))
    return render_template('admin/usuario_form.html', obj=None, titulo='Nuevo Usuario')

@app.route('/admin/usuarios/<int:id>/toggle', methods=['POST'])
@login_required
def admin_usuario_toggle(id):
    if current_user.rol != 'admin':
        flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
    u=User.query.get_or_404(id)
    if u.id != current_user.id:
        u.activo=not u.activo; db.session.commit()
        flash(f'Usuario {"activado" if u.activo else "desactivado"}.','info')
    return redirect(url_for('admin_usuarios'))

# =============================================================
# PERFIL DE USUARIO
# =============================================================

@app.route('/perfil', methods=['GET','POST'])
@login_required
def perfil():
    if request.method == 'POST':
        accion = request.form.get('accion')
        if accion == 'datos':
            nuevo_email = request.form.get('email','').strip()
            if nuevo_email != current_user.email and User.query.filter_by(email=nuevo_email).first():
                flash('Ese email ya está en uso.','danger')
            else:
                current_user.nombre = request.form.get('nombre','').strip() or current_user.nombre
                current_user.email  = nuevo_email or current_user.email
                db.session.commit()
                flash('Datos actualizados.','success')
        elif accion == 'password':
            pw_actual    = request.form.get('password_actual','')
            pw_nueva     = request.form.get('password_nueva','')
            pw_confirmar = request.form.get('password_confirmar','')
            if not current_user.check_password(pw_actual):
                flash('La contraseña actual es incorrecta.','danger')
            elif len(pw_nueva) < 6:
                flash('La nueva contraseña debe tener al menos 6 caracteres.','danger')
            elif pw_nueva != pw_confirmar:
                flash('Las contraseñas nuevas no coinciden.','danger')
            else:
                current_user.set_password(pw_nueva)
                db.session.commit()
                flash('Contraseña cambiada exitosamente.','success')
    return render_template('perfil.html')

# =============================================================
# REPORTES
# =============================================================

@app.route('/reportes')
@login_required
def reportes():
    from datetime import date
    from calendar import month_abbr
    # Estadísticas generales
    ingresos_totales = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['ganado','anticipo_pagado'])).scalar() or 0
    gastos_totales   = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
    balance          = ingresos_totales - gastos_totales
    total_clientes   = Cliente.query.filter_by(estado='activo').count()
    # Ventas por mes (últimos 6 meses)
    hoy = date.today()
    meses_labels, ventas_por_mes = [], []
    for i in range(5, -1, -1):
        mes = (hoy.month - i - 1) % 12 + 1
        anio = hoy.year - ((hoy.month - i - 1) // 12 + (1 if (hoy.month - i - 1) < 0 else 0))
        total_mes = db.session.query(db.func.sum(Venta.total)).filter(
            db.extract('month', Venta.creado_en) == mes,
            db.extract('year', Venta.creado_en) == anio).scalar() or 0
        meses_labels.append(f'{month_abbr[mes]} {str(anio)[2:]}')
        ventas_por_mes.append(round(total_mes))
    # Gastos por tipo
    gastos_por_tipo = db.session.query(GastoOperativo.tipo, db.func.sum(GastoOperativo.monto))\
        .group_by(GastoOperativo.tipo).order_by(db.func.sum(GastoOperativo.monto).desc()).all()
    gastos_tipos_labels = [g[0] for g in gastos_por_tipo]
    gastos_tipos_values = [round(g[1]) for g in gastos_por_tipo]
    # Top 5 clientes por ventas totales
    from sqlalchemy import func as sqlfunc
    top_q = db.session.query(
        Cliente.id, Cliente.nombre, Cliente.empresa,
        sqlfunc.sum(Venta.total).label('total_ventas')
    ).join(Venta, Venta.cliente_id == Cliente.id)\
     .group_by(Cliente.id, Cliente.nombre, Cliente.empresa)\
     .order_by(sqlfunc.sum(Venta.total).desc()).limit(5).all()
    class _C:
        def __init__(self, r): self.id=r[0]; self.nombre=r[1]; self.empresa=r[2]; self.total_ventas=r[3]
    top_clientes = [_C(r) for r in top_q]
    # Stock bajo
    bajo_stock = Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).all()
    return render_template('reportes.html',
        total_clientes=total_clientes, ingresos_totales=ingresos_totales,
        gastos_totales=gastos_totales, balance=balance,
        meses_labels=meses_labels, ventas_por_mes=ventas_por_mes,
        gastos_tipos_labels=gastos_tipos_labels, gastos_tipos_values=gastos_tipos_values,
        top_clientes=top_clientes, bajo_stock=bajo_stock)

# --- Exportar Excel ---

def _make_xlsx(titulo, headers, rows):
    import io, openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo
    # Cabecera empresa
    ws.merge_cells(f'A1:{chr(64+len(headers))}1')
    ws['A1'] = 'Evore CRM — ' + titulo
    ws['A1'].font = Font(bold=True, size=13, color='FFFFFF')
    ws['A1'].fill = PatternFill('solid', fgColor='5E72E4')
    ws['A1'].alignment = Alignment(horizontal='center')
    # Headers
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1A1F36')
        cell.alignment = Alignment(horizontal='center')
    # Datos
    for r_idx, row in enumerate(rows, 3):
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    # Autofit columns
    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

@app.route('/reportes/exportar/ventas.xlsx')
@login_required
def exportar_ventas():
    from flask import send_file
    ventas = Venta.query.order_by(Venta.creado_en.desc()).all()
    headers = ['Título','Cliente','Subtotal COP','IVA COP','Total COP','% Anticipo','Anticipo COP','Saldo COP','Estado','Fecha anticipo','Días entrega','Creada']
    rows = []
    for v in ventas:
        rows.append([
            v.titulo,
            v.cliente.empresa or v.cliente.nombre if v.cliente else '',
            round(v.subtotal), round(v.iva), round(v.total),
            v.porcentaje_anticipo, round(v.monto_anticipo), round(v.saldo),
            v.estado,
            v.fecha_anticipo.strftime('%d/%m/%Y') if v.fecha_anticipo else '',
            v.dias_entrega,
            v.creado_en.strftime('%d/%m/%Y')
        ])
    buf = _make_xlsx('Ventas', headers, rows)
    return send_file(buf, download_name='evore_ventas.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/reportes/exportar/gastos.xlsx')
@login_required
def exportar_gastos():
    from flask import send_file
    items = GastoOperativo.query.order_by(GastoOperativo.fecha.desc()).all()
    headers = ['Fecha','Tipo','Descripción','Monto COP','Notas']
    rows = [[g.fecha.strftime('%d/%m/%Y'), g.tipo, g.descripcion or '', round(g.monto), g.notas or ''] for g in items]
    buf = _make_xlsx('Gastos Operativos', headers, rows)
    return send_file(buf, download_name='evore_gastos.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/reportes/exportar/inventario.xlsx')
@login_required
def exportar_inventario():
    from flask import send_file
    items = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    headers = ['Nombre','SKU','NSO (INVIMA)','Precio COP','Costo COP','Stock','Stock Mínimo','Categoría']
    rows = [[p.nombre, p.sku or '', p.nso or '', round(p.precio), round(p.costo),
             p.stock, p.stock_minimo, p.categoria or ''] for p in items]
    buf = _make_xlsx('Inventario', headers, rows)
    return send_file(buf, download_name='evore_inventario.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.route('/reportes/exportar/clientes.xlsx')
@login_required
def exportar_clientes():
    from flask import send_file
    items = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
    headers = ['Empresa','NIT','Relación','Dirección comercial','Dirección entrega','Estado','Creado']
    rows = [[c.empresa or '', c.nit or '', c.estado_relacion or '', c.dir_comercial or '',
             c.dir_entrega or '', c.estado, c.creado_en.strftime('%d/%m/%Y')] for c in items]
    buf = _make_xlsx('Clientes', headers, rows)
    return send_file(buf, download_name='evore_clientes.xlsx',
                     as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# =============================================================
# INICIALIZACIÓN
# =============================================================

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@evore.us').first():
            admin=User(nombre='Administrador',email='admin@evore.us',rol='admin')
            admin.set_password('Evore2024!')
            db.session.add(admin); db.session.commit()
            print('Admin creado: admin@evore.us / Evore2024!')

try:
    init_db()
except Exception as _e:
    print(f'init_db() error (no crítico): {_e}')

if __name__ == '__main__':
    app.run(debug=True)
