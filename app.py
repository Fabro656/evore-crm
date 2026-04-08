# =============================================================
# EVORE CRM — v6 (archivo único, fix Jinja2 CSS comment bug)
# =============================================================

from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from jinja2 import DictLoader

# =============================================================
# CONFIGURACIÓN
# =============================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'evore-crm-2024-key')

_db_url = os.environ.get('DATABASE_URL', 'sqlite:///crm.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Inicia sesión para continuar.'
login_manager.login_message_category = 'warning'


@app.context_processor
def inject_globals():
    return {'now': datetime.utcnow()}


@app.template_filter('moneda')
def moneda(value):
    try:
        return '${:,.2f}'.format(float(value or 0))
    except Exception:
        return '$0.00'


@app.template_filter('moneda0')
def moneda0(value):
    try:
        return '${:,.0f}'.format(float(value or 0))
    except Exception:
        return '$0'


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


class Cliente(db.Model):
    __tablename__ = 'clientes'
    id             = db.Column(db.Integer, primary_key=True)
    nombre         = db.Column(db.String(100), nullable=False)
    empresa        = db.Column(db.String(100))
    email          = db.Column(db.String(120))
    telefono       = db.Column(db.String(20))
    direccion      = db.Column(db.Text)
    notas          = db.Column(db.Text)
    estado         = db.Column(db.String(20), default='activo')
    creado_en      = db.Column(db.DateTime, default=datetime.utcnow)
    actualizado_en = db.Column(db.DateTime, default=datetime.utcnow)
    ventas         = db.relationship('Venta', backref='cliente', lazy=True)


class Venta(db.Model):
    __tablename__ = 'ventas'
    id           = db.Column(db.Integer, primary_key=True)
    titulo       = db.Column(db.String(200), nullable=False)
    cliente_id   = db.Column(db.Integer, db.ForeignKey('clientes.id'), nullable=True)
    monto        = db.Column(db.Float, default=0)
    estado       = db.Column(db.String(30), default='prospecto')
    fecha_cierre = db.Column(db.Date)
    notas        = db.Column(db.Text)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)
    creado_por   = db.Column(db.Integer, db.ForeignKey('users.id'))


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


class Producto(db.Model):
    __tablename__ = 'productos'
    id           = db.Column(db.Integer, primary_key=True)
    nombre       = db.Column(db.String(200), nullable=False)
    descripcion  = db.Column(db.Text)
    precio       = db.Column(db.Float, default=0)
    stock        = db.Column(db.Integer, default=0)
    stock_minimo = db.Column(db.Integer, default=5)
    categoria    = db.Column(db.String(100))
    sku          = db.Column(db.String(50))
    activo       = db.Column(db.Boolean, default=True)
    creado_en    = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))


# =============================================================
# TEMPLATES
# =============================================================

_CSS = """{% raw %}<style>
:root{--sb:#1a1f36;--ac:#5e72e4;--bg:#f4f6fb}
body{background:var(--bg);font-family:'Segoe UI',sans-serif}
#sb{position:fixed;top:0;left:0;height:100vh;width:252px;background:var(--sb);
    display:flex;flex-direction:column;z-index:1000}
.sb-brand{padding:1.3rem 1.2rem .85rem;color:#fff;font-size:1.3rem;font-weight:700;
          border-bottom:1px solid rgba(255,255,255,.08);letter-spacing:1px}
.sb-brand span{color:var(--ac)}
.sb-sec{font-size:.67rem;font-weight:700;letter-spacing:1.5px;text-transform:uppercase;
        color:rgba(255,255,255,.3);padding:.65rem 1.2rem .2rem}
.sb-nav .nav-link{color:#a8b0d3;padding:.53rem 1.2rem;border-radius:8px;
                  margin:.07rem .65rem;display:flex;align-items:center;gap:.65rem;
                  font-size:.87rem;transition:all .2s}
.sb-nav .nav-link:hover{background:rgba(255,255,255,.07);color:#fff}
.sb-nav .nav-link.active{background:var(--ac);color:#fff}
.sb-nav .nav-link i{font-size:1rem;width:19px}
.sb-foot{padding:.85rem 1.2rem;border-top:1px solid rgba(255,255,255,.08);
         color:#a8b0d3;font-size:.82rem;margin-top:auto}
.u-name{color:#fff;font-weight:600}
.u-rol{font-size:.67rem;padding:2px 8px;border-radius:20px;
       background:rgba(94,114,228,.3);color:var(--ac)}
#main{margin-left:252px;min-height:100vh}
.topbar{background:#fff;padding:.68rem 1.4rem;border-bottom:1px solid #e8ecf0;
        display:flex;align-items:center;justify-content:space-between;
        position:sticky;top:0;z-index:100;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.pg-title{font-size:1.1rem;font-weight:600;color:#1a1f36;margin:0}
.content{padding:1.4rem}
.sc{background:#fff;border-radius:12px;padding:1.2rem 1.4rem;
    box-shadow:0 2px 8px rgba(0,0,0,.06);transition:transform .2s}
.sc:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(0,0,0,.1)}
.si{width:46px;height:46px;border-radius:11px;display:flex;align-items:center;justify-content:center;font-size:1.3rem}
.sv{font-size:1.7rem;font-weight:700;color:#1a1f36}
.sl{color:#8898aa;font-size:.82rem}
.tc{background:#fff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.06);overflow:hidden}
.ch{background:#fff;border-bottom:1px solid #f0f0f0;padding:.85rem 1.4rem;font-weight:600;color:#1a1f36}
.table{margin:0}
.table th{font-size:.71rem;font-weight:700;text-transform:uppercase;letter-spacing:.5px;
          color:#8898aa;border-bottom:1px solid #f0f0f0;padding:.65rem 1rem}
.table td{padding:.65rem 1rem;vertical-align:middle;border-bottom:1px solid #f8f9fa;color:#525f7f}
.table tbody tr:last-child td{border-bottom:none}
.table tbody tr:hover{background:#f8f9fe}
.b{padding:3px 10px;border-radius:20px;font-size:.72rem;font-weight:600}
.b-activo,.b-ganado,.b-completada,.b-baja{background:#d4edda;color:#155724}
.b-inactivo,.b-perdido,.b-alta{background:#f8d7da;color:#721c24}
.b-prospecto,.b-pendiente,.b-media{background:#fff3cd;color:#856404}
.b-negociacion,.b-en_progreso{background:#cce5ff;color:#004085}
.fc{background:#fff;border-radius:12px;padding:1.8rem;
    box-shadow:0 2px 8px rgba(0,0,0,.06);max-width:700px}
.form-label{font-weight:600;font-size:.875rem;color:#525f7f}
.form-control,.form-select{border:1.5px solid #e9ecef;border-radius:8px;
    padding:.5rem .75rem;font-size:.9rem;transition:border-color .2s}
.form-control:focus,.form-select:focus{border-color:var(--ac);box-shadow:0 0 0 3px rgba(94,114,228,.15)}
.btn-primary{background:var(--ac);border-color:var(--ac)}
.btn-primary:hover{background:#4a5bd4;border-color:#4a5bd4}
.alert{border-radius:10px;border:none}
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
  <div class="sb-brand">E<span>vore</span><span class="bt"> CRM</span></div>
  <div class="sb-nav py-2">
    <div class="sb-sec">Principal</div>
    <a href="{{ url_for('dashboard') }}" class="nav-link {% if request.endpoint=='dashboard' %}active{% endif %}">
      <i class="bi bi-grid-1x2-fill"></i><span>Dashboard</span></a>
    <div class="sb-sec">Módulos</div>
    <a href="{{ url_for('clientes') }}" class="nav-link {% if 'cliente' in request.endpoint %}active{% endif %}">
      <i class="bi bi-people-fill"></i><span>Clientes</span></a>
    <a href="{{ url_for('ventas') }}" class="nav-link {% if 'venta' in request.endpoint %}active{% endif %}">
      <i class="bi bi-graph-up-arrow"></i><span>Ventas</span></a>
    <a href="{{ url_for('tareas') }}" class="nav-link {% if 'tarea' in request.endpoint %}active{% endif %}">
      <i class="bi bi-check2-square"></i><span>Tareas</span></a>
    <a href="{{ url_for('inventario') }}" class="nav-link {% if 'inventario' in request.endpoint or 'producto' in request.endpoint %}active{% endif %}">
      <i class="bi bi-box-seam-fill"></i><span>Inventario</span></a>
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
<title>Evore CRM — Login</title>
""" + _CDN + """
<style>
body{background:linear-gradient(135deg,#1a1f36,#2d3561);min-height:100vh;
     display:flex;align-items:center;justify-content:center;font-family:'Segoe UI',sans-serif}
.card{border-radius:20px;padding:2.3rem;width:100%;max-width:420px;
      box-shadow:0 20px 60px rgba(0,0,0,.3);border:none}
.brand{font-size:2rem;font-weight:800;color:#1a1f36;letter-spacing:1px}
.brand span{color:#5e72e4}
.form-control{border:1.5px solid #e9ecef;border-radius:10px;padding:.62rem 1rem}
.form-control:focus{border-color:#5e72e4;box-shadow:0 0 0 3px rgba(94,114,228,.15)}
.igt{background:#f8f9fe;border:1.5px solid #e9ecef;border-right:none;color:#8898aa;border-radius:10px 0 0 10px}
.input-group .form-control{border-left:none;border-radius:0 10px 10px 0}
.btn-lg{background:linear-gradient(135deg,#5e72e4,#4a5bd4);border:none;color:#fff;
        padding:.75rem;border-radius:10px;font-weight:600;transition:all .3s;width:100%}
.btn-lg:hover{transform:translateY(-1px);box-shadow:0 4px 15px rgba(94,114,228,.4);color:#fff}
</style></head><body>
<div class="card bg-white">
  <div class="text-center mb-4">
    <div class="brand">E<span>vore</span></div>
    <p class="text-muted mb-0" style="font-size:.9rem">Sistema de Gestión CRM</p>
  </div>
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}{% for cat, msg in messages %}
  <div class="alert alert-{{ cat }} py-2 mb-3" style="border-radius:10px;border:none;font-size:.875rem">{{ msg }}</div>
  {% endfor %}{% endif %}{% endwith %}
  <form method="POST" action="{{ url_for('login') }}">
    <div class="mb-3">
      <label class="form-label fw-semibold" style="font-size:.875rem;color:#525f7f">Correo electrónico</label>
      <div class="input-group">
        <span class="input-group-text igt"><i class="bi bi-envelope"></i></span>
        <input type="email" name="email" class="form-control" placeholder="tu@email.com" required autofocus>
      </div>
    </div>
    <div class="mb-4">
      <label class="form-label fw-semibold" style="font-size:.875rem;color:#525f7f">Contraseña</label>
      <div class="input-group">
        <span class="input-group-text igt"><i class="bi bi-lock"></i></span>
        <input type="password" name="password" class="form-control" placeholder="••••••••" required>
      </div>
    </div>
    <div class="mb-3 form-check">
      <input type="checkbox" class="form-check-input" name="remember" id="rem">
      <label class="form-check-label" for="rem" style="font-size:.875rem;color:#525f7f">Mantener sesión</label>
    </div>
    <button type="submit" class="btn btn-lg">
      <i class="bi bi-box-arrow-in-right me-2"></i>Iniciar Sesión</button>
  </form>
  <hr class="my-3">
  <p class="text-center text-muted mb-0" style="font-size:.8rem;background:#f4f6fb;border-radius:10px;padding:.8rem">
    <i class="bi bi-info-circle me-1"></i>Solo para usuarios autorizados</p>
</div>
""" + _BSJ + """</body></html>"""

T['dashboard.html'] = """{% extends 'base.html' %}
{% block title %}Dashboard — Evore CRM{% endblock %}
{% block page_title %}Dashboard{% endblock %}
{% block content %}
<div class="row g-3 mb-4">
  <div class="col-6 col-lg-3"><div class="sc">
    <div class="d-flex justify-content-between align-items-start">
      <div><div class="sv">{{ total_clientes }}</div><div class="sl">Clientes activos</div></div>
      <div class="si" style="background:#e8eeff"><i class="bi bi-people-fill" style="color:#5e72e4"></i></div>
    </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc">
    <div class="d-flex justify-content-between align-items-start">
      <div><div class="sv">{{ ventas_ganadas }}</div><div class="sl">Ventas ganadas</div></div>
      <div class="si" style="background:#e3f9ee"><i class="bi bi-graph-up-arrow" style="color:#2dce89"></i></div>
    </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc">
    <div class="d-flex justify-content-between align-items-start">
      <div><div class="sv">{{ tareas_pendientes }}</div><div class="sl">Tareas pendientes</div></div>
      <div class="si" style="background:#fff4e5"><i class="bi bi-check2-square" style="color:#fb6340"></i></div>
    </div></div></div>
  <div class="col-6 col-lg-3"><div class="sc">
    <div class="d-flex justify-content-between align-items-start">
      <div><div class="sv">{{ monto_total | moneda0 }}</div><div class="sl">Ingresos totales</div></div>
      <div class="si" style="background:#fce8ff"><i class="bi bi-currency-dollar" style="color:#c300ff"></i></div>
    </div></div></div>
</div>
{% if productos_bajo_stock > 0 %}
<div class="alert alert-warning d-flex align-items-center gap-2 mb-4">
  <i class="bi bi-exclamation-triangle-fill"></i>
  <span><strong>{{ productos_bajo_stock }} producto(s)</strong> con stock bajo.
    <a href="{{ url_for('inventario') }}" class="alert-link">Ver inventario →</a></span>
</div>{% endif %}
<div class="row g-4">
  <div class="col-lg-6"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-check2-square me-2 text-warning"></i>Tareas pendientes</span>
      <a href="{{ url_for('tarea_nueva') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i> Nueva</a>
    </div>
    {% if tareas_recientes %}<table class="table"><tbody>
    {% for t in tareas_recientes %}<tr>
      <td><div class="fw-semibold" style="color:#1a1f36">{{ t.titulo }}</div>
        <small class="text-muted">{% if t.fecha_vencimiento %}<i class="bi bi-calendar3"></i> {{ t.fecha_vencimiento.strftime('%d/%m/%Y') }}{% endif %}</small></td>
      <td><span class="b b-{{ t.prioridad }}">{{ t.prioridad.title() }}</span></td>
      <td><form method="POST" action="{{ url_for('tarea_completar', id=t.id) }}">
        <button type="submit" class="btn btn-sm btn-outline-success"><i class="bi bi-check2"></i></button></form></td>
    </tr>{% endfor %}
    </tbody></table>
    {% else %}<div class="text-center text-muted py-4">
      <i class="bi bi-check2-all" style="font-size:2rem"></i><p class="mt-2 mb-0">Sin pendientes</p></div>
    {% endif %}
  </div></div>
  <div class="col-lg-6"><div class="tc">
    <div class="ch d-flex justify-content-between align-items-center">
      <span><i class="bi bi-people-fill me-2 text-primary"></i>Clientes recientes</span>
      <a href="{{ url_for('cliente_nuevo') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i> Nuevo</a>
    </div>
    {% if clientes_recientes %}<table class="table"><tbody>
    {% for c in clientes_recientes %}<tr>
      <td><a href="{{ url_for('cliente_ver', id=c.id) }}" class="fw-semibold text-decoration-none" style="color:#1a1f36">{{ c.nombre }}</a>
        {% if c.empresa %}<div><small class="text-muted">{{ c.empresa }}</small></div>{% endif %}</td>
      <td><span class="b b-{{ c.estado }}">{{ c.estado.title() }}</span></td>
      <td><small class="text-muted">{{ c.creado_en.strftime('%d/%m/%Y') }}</small></td>
    </tr>{% endfor %}
    </tbody></table>
    {% else %}<div class="text-center text-muted py-4">
      <i class="bi bi-people" style="font-size:2rem"></i><p class="mt-2 mb-0">Sin clientes aún</p>
      <a href="{{ url_for('cliente_nuevo') }}" class="btn btn-sm btn-primary mt-2">Agregar primero</a></div>
    {% endif %}
  </div></div>
</div>{% endblock %}"""

T['clientes/index.html'] = """{% extends 'base.html' %}
{% block title %}Clientes{% endblock %}
{% block page_title %}Clientes{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('cliente_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nuevo</a>{% endblock %}
{% block content %}
<div class="tc mb-4"><div class="p-3">
  <form method="GET" class="row g-2 align-items-end">
    <div class="col-sm-5"><input type="text" name="buscar" class="form-control form-control-sm" placeholder="Buscar..." value="{{ busqueda }}"></div>
    <div class="col-sm-3"><select name="estado" class="form-select form-select-sm">
      <option value="">Todos</option>
      <option value="activo" {% if estado_f=='activo' %}selected{% endif %}>Activo</option>
      <option value="prospecto" {% if estado_f=='prospecto' %}selected{% endif %}>Prospecto</option>
      <option value="inactivo" {% if estado_f=='inactivo' %}selected{% endif %}>Inactivo</option>
    </select></div>
    <div class="col-auto">
      <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-search"></i></button>
      <a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm">Limpiar</a>
    </div>
  </form>
</div></div>
<div class="tc"><div class="ch"><i class="bi bi-people-fill me-2"></i>{{ items|length }} cliente(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Nombre</th><th>Empresa</th><th>Email</th><th>Teléfono</th><th>Estado</th><th>Alta</th><th></th></tr></thead>
  <tbody>{% for c in items %}<tr>
    <td><a href="{{ url_for('cliente_ver', id=c.id) }}" class="fw-semibold text-decoration-none" style="color:#1a1f36">{{ c.nombre }}</a></td>
    <td>{{ c.empresa or '—' }}</td><td>{{ c.email or '—' }}</td><td>{{ c.telefono or '—' }}</td>
    <td><span class="b b-{{ c.estado }}">{{ c.estado.title() }}</span></td>
    <td><small class="text-muted">{{ c.creado_en.strftime('%d/%m/%Y') }}</small></td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('cliente_ver', id=c.id) }}" class="btn btn-sm btn-outline-primary"><i class="bi bi-eye"></i></a>
      <a href="{{ url_for('cliente_editar', id=c.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('cliente_eliminar', id=c.id) }}" onsubmit="return confirm('Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5">
  <i class="bi bi-people" style="font-size:3rem"></i><p class="mt-3">Sin clientes.</p>
  <a href="{{ url_for('cliente_nuevo') }}" class="btn btn-primary">Agregar</a></div>
{% endif %}</div>{% endblock %}"""

T['clientes/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre *</label>
    <input type="text" name="nombre" class="form-control" value="{{ obj.nombre if obj else '' }}" required></div>
  <div class="col-md-6"><label class="form-label">Empresa</label>
    <input type="text" name="empresa" class="form-control" value="{{ obj.empresa if obj else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Email</label>
    <input type="email" name="email" class="form-control" value="{{ obj.email if obj else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Teléfono</label>
    <input type="text" name="telefono" class="form-control" value="{{ obj.telefono if obj else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      <option value="activo" {% if not obj or obj.estado=='activo' %}selected{% endif %}>Activo</option>
      <option value="prospecto" {% if obj and obj.estado=='prospecto' %}selected{% endif %}>Prospecto</option>
      <option value="inactivo" {% if obj and obj.estado=='inactivo' %}selected{% endif %}>Inactivo</option>
    </select></div>
  <div class="col-12"><label class="form-label">Dirección</label>
    <input type="text" name="direccion" class="form-control" value="{{ obj.direccion if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="3">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Cliente' }}</button>
  <a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['clientes/ver.html'] = """{% extends 'base.html' %}
{% block title %}{{ obj.nombre }}{% endblock %}{% block page_title %}{{ obj.nombre }}{% endblock %}
{% block topbar_actions %}
<a href="{{ url_for('cliente_editar', id=obj.id) }}" class="btn btn-primary btn-sm"><i class="bi bi-pencil me-1"></i>Editar</a>
<a href="{{ url_for('clientes') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>
{% endblock %}
{% block content %}<div class="row g-4">
  <div class="col-lg-4"><div class="fc">
    <div class="d-flex align-items-center gap-3 mb-3">
      <div class="rounded-circle d-flex align-items-center justify-content-center text-white fw-bold"
           style="width:46px;height:46px;background:#5e72e4;font-size:1.1rem">{{ obj.nombre[0].upper() }}</div>
      <div><h5 class="mb-1">{{ obj.nombre }}</h5><span class="b b-{{ obj.estado }}">{{ obj.estado.title() }}</span></div>
    </div><hr>
    <dl class="row mb-0" style="font-size:.9rem">
      <dt class="col-5 text-muted">Empresa</dt><dd class="col-7">{{ obj.empresa or '—' }}</dd>
      <dt class="col-5 text-muted">Email</dt><dd class="col-7">{{ obj.email or '—' }}</dd>
      <dt class="col-5 text-muted">Teléfono</dt><dd class="col-7">{{ obj.telefono or '—' }}</dd>
      <dt class="col-5 text-muted">Alta</dt><dd class="col-7">{{ obj.creado_en.strftime('%d/%m/%Y') }}</dd>
    </dl>
    {% if obj.notas %}<hr><p class="text-muted small mb-1">Notas:</p><p style="font-size:.9rem">{{ obj.notas }}</p>{% endif %}
    <hr>
    <form method="POST" action="{{ url_for('cliente_eliminar', id=obj.id) }}" onsubmit="return confirm('Eliminar?')">
      <button class="btn btn-outline-danger btn-sm"><i class="bi bi-trash me-1"></i>Eliminar</button></form>
  </div></div>
  <div class="col-lg-8"><div class="tc">
    <div class="ch d-flex justify-content-between">
      <span><i class="bi bi-graph-up me-2"></i>Ventas</span>
      <a href="{{ url_for('venta_nueva') }}" class="btn btn-sm btn-primary"><i class="bi bi-plus"></i> Nueva</a>
    </div>
    {% if obj.ventas %}<table class="table">
      <thead><tr><th>Título</th><th>Monto</th><th>Estado</th><th>Fecha</th></tr></thead>
      <tbody>{% for v in obj.ventas %}<tr>
        <td>{{ v.titulo }}</td>
        <td>{{ v.monto | moneda }}</td>
        <td><span class="b b-{{ v.estado }}">{{ v.estado.replace('_',' ').title() }}</span></td>
        <td><small class="text-muted">{{ v.creado_en.strftime('%d/%m/%Y') }}</small></td>
      </tr>{% endfor %}</tbody>
    </table>
    {% else %}<div class="text-center text-muted py-4">
      <i class="bi bi-graph-up" style="font-size:2rem"></i><p class="mt-2 mb-0">Sin ventas</p></div>
    {% endif %}
  </div></div>
</div>{% endblock %}"""

T['ventas/index.html'] = """{% extends 'base.html' %}
{% block title %}Ventas{% endblock %}{% block page_title %}Ventas{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('venta_nueva') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva</a>{% endblock %}
{% block content %}
<div class="mb-3 d-flex gap-2 flex-wrap">
  <a href="{{ url_for('ventas') }}" class="btn btn-sm {{ 'btn-primary' if not estado_f else 'btn-outline-secondary' }}">Todas</a>
  <a href="{{ url_for('ventas', estado='prospecto') }}" class="btn btn-sm {{ 'btn-warning' if estado_f=='prospecto' else 'btn-outline-secondary' }}">Prospecto</a>
  <a href="{{ url_for('ventas', estado='negociacion') }}" class="btn btn-sm {{ 'btn-info' if estado_f=='negociacion' else 'btn-outline-secondary' }}">Negociación</a>
  <a href="{{ url_for('ventas', estado='ganado') }}" class="btn btn-sm {{ 'btn-success' if estado_f=='ganado' else 'btn-outline-secondary' }}">Ganado</a>
  <a href="{{ url_for('ventas', estado='perdido') }}" class="btn btn-sm {{ 'btn-danger' if estado_f=='perdido' else 'btn-outline-secondary' }}">Perdido</a>
</div>
<div class="tc"><div class="ch"><i class="bi bi-graph-up-arrow me-2"></i>{{ items|length }} venta(s)
  {% if items %} — Total: <strong>{{ items|sum(attribute='monto') | moneda }}</strong>{% endif %}</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Título</th><th>Cliente</th><th>Monto</th><th>Estado</th><th>Cierre</th><th></th></tr></thead>
  <tbody>{% for v in items %}<tr>
    <td class="fw-semibold" style="color:#1a1f36">{{ v.titulo }}</td>
    <td>{% if v.cliente %}<a href="{{ url_for('cliente_ver', id=v.cliente.id) }}" class="text-decoration-none">{{ v.cliente.nombre }}</a>{% else %}—{% endif %}</td>
    <td class="fw-semibold">{{ v.monto | moneda }}</td>
    <td><span class="b b-{{ v.estado }}">{{ v.estado.replace('_',' ').title() }}</span></td>
    <td>{% if v.fecha_cierre %}<small>{{ v.fecha_cierre.strftime('%d/%m/%Y') }}</small>{% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('venta_editar', id=v.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('venta_eliminar', id=v.id) }}" onsubmit="return confirm('Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5">
  <i class="bi bi-graph-up-arrow" style="font-size:3rem"></i><p class="mt-3">Sin ventas.</p>
  <a href="{{ url_for('venta_nueva') }}" class="btn btn-primary">Crear primera</a></div>
{% endif %}</div>{% endblock %}"""

T['ventas/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('ventas') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-12"><label class="form-label">Título *</label>
    <input type="text" name="titulo" class="form-control" value="{{ obj.titulo if obj else '' }}" required></div>
  <div class="col-md-6"><label class="form-label">Cliente</label>
    <select name="cliente_id" class="form-select"><option value="">Sin cliente</option>
      {% for c in clientes_list %}<option value="{{ c.id }}" {% if obj and obj.cliente_id==c.id %}selected{% endif %}>
        {{ c.nombre }}{% if c.empresa %} ({{ c.empresa }}){% endif %}</option>{% endfor %}
    </select></div>
  <div class="col-md-6"><label class="form-label">Monto ($)</label>
    <input type="number" name="monto" class="form-control" step="0.01" min="0" value="{{ obj.monto if obj else '0' }}"></div>
  <div class="col-md-6"><label class="form-label">Estado</label>
    <select name="estado" class="form-select">
      <option value="prospecto" {% if not obj or obj.estado=='prospecto' %}selected{% endif %}>Prospecto</option>
      <option value="negociacion" {% if obj and obj.estado=='negociacion' %}selected{% endif %}>Negociación</option>
      <option value="ganado" {% if obj and obj.estado=='ganado' %}selected{% endif %}>Ganado</option>
      <option value="perdido" {% if obj and obj.estado=='perdido' %}selected{% endif %}>Perdido</option>
    </select></div>
  <div class="col-md-6"><label class="form-label">Fecha de cierre</label>
    <input type="date" name="fecha_cierre" class="form-control"
           value="{{ obj.fecha_cierre.strftime('%Y-%m-%d') if obj and obj.fecha_cierre else '' }}"></div>
  <div class="col-12"><label class="form-label">Notas</label>
    <textarea name="notas" class="form-control" rows="3">{{ obj.notas if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Venta' }}</button>
  <a href="{{ url_for('ventas') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['tareas/index.html'] = """{% extends 'base.html' %}
{% block title %}Tareas{% endblock %}{% block page_title %}Tareas{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('tarea_nueva') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nueva</a>{% endblock %}
{% block content %}
<div class="mb-3 d-flex gap-2 flex-wrap">
  <a href="{{ url_for('tareas') }}" class="btn btn-sm {{ 'btn-primary' if not estado_f else 'btn-outline-secondary' }}">Todas</a>
  <a href="{{ url_for('tareas', estado='pendiente') }}" class="btn btn-sm {{ 'btn-warning' if estado_f=='pendiente' else 'btn-outline-secondary' }}">Pendiente</a>
  <a href="{{ url_for('tareas', estado='en_progreso') }}" class="btn btn-sm {{ 'btn-info' if estado_f=='en_progreso' else 'btn-outline-secondary' }}">En progreso</a>
  <a href="{{ url_for('tareas', estado='completada') }}" class="btn btn-sm {{ 'btn-success' if estado_f=='completada' else 'btn-outline-secondary' }}">Completada</a>
  <span class="text-muted mx-1">|</span>
  <a href="{{ url_for('tareas', prioridad='alta') }}" class="btn btn-sm {{ 'btn-danger' if prioridad_f=='alta' else 'btn-outline-secondary' }}">Alta prioridad</a>
</div>
<div class="tc"><div class="ch"><i class="bi bi-check2-square me-2"></i>{{ items|length }} tarea(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Tarea</th><th>Prioridad</th><th>Estado</th><th>Asignada a</th><th>Vence</th><th></th></tr></thead>
  <tbody>{% for t in items %}<tr {% if t.estado == 'completada' %}style="opacity:.6"{% endif %}>
    <td><div class="fw-semibold {% if t.estado=='completada' %}text-decoration-line-through{% endif %}" style="color:#1a1f36">{{ t.titulo }}</div>
      {% if t.descripcion %}<small class="text-muted">{{ t.descripcion[:55] }}{% if t.descripcion|length > 55 %}...{% endif %}</small>{% endif %}</td>
    <td><span class="b b-{{ t.prioridad }}">{{ t.prioridad.title() }}</span></td>
    <td><span class="b b-{{ t.estado }}">{{ t.estado.replace('_',' ').title() }}</span></td>
    <td>{{ t.asignado_user.nombre if t.asignado_user else '—' }}</td>
    <td>{% if t.fecha_vencimiento %}
      <small class="{{ 'text-danger fw-bold' if t.estado != 'completada' and t.fecha_vencimiento < now.date() else 'text-muted' }}">
        {{ t.fecha_vencimiento.strftime('%d/%m/%Y') }}</small>
      {% else %}—{% endif %}</td>
    <td><div class="d-flex gap-1">
      {% if t.estado != 'completada' %}<form method="POST" action="{{ url_for('tarea_completar', id=t.id) }}">
        <button class="btn btn-sm btn-outline-success"><i class="bi bi-check2"></i></button></form>{% endif %}
      <a href="{{ url_for('tarea_editar', id=t.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('tarea_eliminar', id=t.id) }}" onsubmit="return confirm('Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5">
  <i class="bi bi-check2-all" style="font-size:3rem"></i><p class="mt-3">Sin tareas.</p>
  <a href="{{ url_for('tarea_nueva') }}" class="btn btn-primary">Crear primera</a></div>
{% endif %}</div>{% endblock %}"""

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
  <div class="col-md-4"><label class="form-label">Fecha de vencimiento</label>
    <input type="date" name="fecha_vencimiento" class="form-control"
           value="{{ obj.fecha_vencimiento.strftime('%Y-%m-%d') if obj and obj.fecha_vencimiento else '' }}"></div>
  <div class="col-md-6"><label class="form-label">Asignar a</label>
    <select name="asignado_a" class="form-select">
      {% for u in usuarios %}<option value="{{ u.id }}"
        {% if (obj and obj.asignado_a==u.id) or (not obj and u.id==current_user.id) %}selected{% endif %}>
        {{ u.nombre }}{% if u.id==current_user.id %} (yo){% endif %}</option>{% endfor %}
    </select></div>
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
<div class="tc mb-4"><div class="p-3">
  <form method="GET" class="row g-2 align-items-end">
    <div class="col-sm-5"><input type="text" name="buscar" class="form-control form-control-sm" placeholder="Buscar nombre, SKU..." value="{{ busqueda }}"></div>
    <div class="col-sm-3"><select name="categoria" class="form-select form-select-sm">
      <option value="">Todas las categorías</option>
      {% for cat in categorias %}<option value="{{ cat }}" {% if categoria_f==cat %}selected{% endif %}>{{ cat }}</option>{% endfor %}
    </select></div>
    <div class="col-auto">
      <button type="submit" class="btn btn-primary btn-sm"><i class="bi bi-search"></i></button>
      <a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary btn-sm">Limpiar</a>
    </div>
  </form>
</div></div>
<div class="tc"><div class="ch"><i class="bi bi-box-seam-fill me-2"></i>{{ items|length }} producto(s)</div>
{% if items %}<div class="table-responsive"><table class="table">
  <thead><tr><th>Producto</th><th>SKU</th><th>Categoría</th><th>Precio</th><th>Stock</th><th></th></tr></thead>
  <tbody>{% for p in items %}<tr>
    <td><div class="fw-semibold" style="color:#1a1f36">{{ p.nombre }}</div>
      {% if p.descripcion %}<small class="text-muted">{{ p.descripcion[:50] }}{% if p.descripcion|length>50 %}...{% endif %}</small>{% endif %}</td>
    <td><small class="text-muted">{{ p.sku or '—' }}</small></td>
    <td>{{ p.categoria or '—' }}</td>
    <td class="fw-semibold">{{ p.precio | moneda }}</td>
    <td>
      <span class="fw-semibold {{ 'text-danger' if p.stock <= p.stock_minimo else 'text-success' }}">{{ p.stock }}</span>
      <small class="text-muted"> / mín {{ p.stock_minimo }}</small>
      {% if p.stock <= p.stock_minimo %}<span class="badge bg-danger ms-1" style="font-size:.65rem">BAJO</span>{% endif %}
    </td>
    <td><div class="d-flex gap-1">
      <a href="{{ url_for('producto_editar', id=p.id) }}" class="btn btn-sm btn-outline-secondary"><i class="bi bi-pencil"></i></a>
      <form method="POST" action="{{ url_for('producto_eliminar', id=p.id) }}" onsubmit="return confirm('Eliminar?')">
        <button class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>
    </div></td>
  </tr>{% endfor %}</tbody>
</table></div>
{% else %}<div class="text-center text-muted py-5">
  <i class="bi bi-box-seam" style="font-size:3rem"></i><p class="mt-3">Sin productos.</p>
  <a href="{{ url_for('producto_nuevo') }}" class="btn btn-primary">Agregar</a></div>
{% endif %}</div>{% endblock %}"""

T['inventario/form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-8"><label class="form-label">Nombre *</label>
    <input type="text" name="nombre" class="form-control" value="{{ obj.nombre if obj else '' }}" required></div>
  <div class="col-md-4"><label class="form-label">SKU / Código</label>
    <input type="text" name="sku" class="form-control" value="{{ obj.sku if obj else '' }}"></div>
  <div class="col-md-4"><label class="form-label">Precio ($)</label>
    <input type="number" name="precio" class="form-control" step="0.01" min="0" value="{{ obj.precio if obj else '0' }}"></div>
  <div class="col-md-4"><label class="form-label">Stock actual</label>
    <input type="number" name="stock" class="form-control" min="0" value="{{ obj.stock if obj else '0' }}"></div>
  <div class="col-md-4"><label class="form-label">Stock mínimo</label>
    <input type="number" name="stock_minimo" class="form-control" min="0" value="{{ obj.stock_minimo if obj else '5' }}">
    <div class="form-text">Alerta cuando llegue a este nivel.</div></div>
  <div class="col-md-6"><label class="form-label">Categoría</label>
    <input type="text" name="categoria" class="form-control" value="{{ obj.categoria if obj else '' }}"></div>
  <div class="col-12"><label class="form-label">Descripción</label>
    <textarea name="descripcion" class="form-control" rows="3">{{ obj.descripcion if obj else '' }}</textarea></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>{{ 'Actualizar' if obj else 'Crear Producto' }}</button>
  <a href="{{ url_for('inventario') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

T['admin/usuarios.html'] = """{% extends 'base.html' %}
{% block title %}Usuarios{% endblock %}{% block page_title %}Gestión de Usuarios{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('admin_usuario_nuevo') }}" class="btn btn-primary btn-sm"><i class="bi bi-plus-lg me-1"></i>Nuevo Usuario</a>{% endblock %}
{% block content %}<div class="tc"><div class="ch"><i class="bi bi-shield-person-fill me-2"></i>{{ items|length }} usuario(s)</div>
<div class="table-responsive"><table class="table">
  <thead><tr><th>Nombre</th><th>Email</th><th>Rol</th><th>Estado</th><th>Alta</th><th></th></tr></thead>
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
  </tr>{% endfor %}</tbody>
</table></div></div>{% endblock %}"""

T['admin/usuario_form.html'] = """{% extends 'base.html' %}
{% block title %}{{ titulo }}{% endblock %}{% block page_title %}{{ titulo }}{% endblock %}
{% block topbar_actions %}<a href="{{ url_for('admin_usuarios') }}" class="btn btn-outline-secondary btn-sm"><i class="bi bi-arrow-left me-1"></i>Volver</a>{% endblock %}
{% block content %}<div class="fc"><form method="POST"><div class="row g-3">
  <div class="col-md-6"><label class="form-label">Nombre completo *</label>
    <input type="text" name="nombre" class="form-control" required></div>
  <div class="col-md-6"><label class="form-label">Email *</label>
    <input type="email" name="email" class="form-control" required></div>
  <div class="col-md-6"><label class="form-label">Contraseña *</label>
    <input type="password" name="password" class="form-control" required placeholder="Mínimo 6 caracteres"></div>
  <div class="col-md-6"><label class="form-label">Rol</label>
    <select name="rol" class="form-select">
      <option value="usuario">Usuario</option>
      <option value="admin">Administrador</option>
    </select></div>
</div>
<div class="d-flex gap-2 mt-4">
  <button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i>Crear Usuario</button>
  <a href="{{ url_for('admin_usuarios') }}" class="btn btn-outline-secondary">Cancelar</a>
</div></form></div>{% endblock %}"""

app.jinja_loader = DictLoader(T)


# =============================================================
# RUTAS — AUTENTICACIÓN
# =============================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
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
    logout_user()
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('login'))


# =============================================================
# DASHBOARD
# =============================================================

@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html',
        total_clientes      = Cliente.query.filter_by(estado='activo').count(),
        ventas_ganadas      = Venta.query.filter_by(estado='ganado').count(),
        tareas_pendientes   = Tarea.query.filter(Tarea.estado != 'completada').count(),
        monto_total         = db.session.query(db.func.sum(Venta.monto)).filter_by(estado='ganado').scalar() or 0,
        productos_bajo_stock= Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).count(),
        tareas_recientes    = Tarea.query.filter(Tarea.estado!='completada').order_by(Tarea.creado_en.desc()).limit(5).all(),
        clientes_recientes  = Cliente.query.order_by(Cliente.creado_en.desc()).limit(5).all(),
    )


# =============================================================
# CLIENTES
# =============================================================

@app.route('/clientes')
@login_required
def clientes():
    busqueda = request.args.get('buscar','')
    estado_f = request.args.get('estado','')
    q = Cliente.query
    if busqueda:
        q = q.filter(db.or_(Cliente.nombre.ilike(f'%{busqueda}%'),
                             Cliente.empresa.ilike(f'%{busqueda}%'),
                             Cliente.email.ilike(f'%{busqueda}%')))
    if estado_f: q = q.filter_by(estado=estado_f)
    return render_template('clientes/index.html', items=q.order_by(Cliente.nombre).all(),
                           busqueda=busqueda, estado_f=estado_f)


@app.route('/clientes/nuevo', methods=['GET','POST'])
@login_required
def cliente_nuevo():
    if request.method == 'POST':
        db.session.add(Cliente(nombre=request.form['nombre'],empresa=request.form.get('empresa',''),
            email=request.form.get('email',''),telefono=request.form.get('telefono',''),
            direccion=request.form.get('direccion',''),notas=request.form.get('notas',''),
            estado=request.form.get('estado','activo')))
        db.session.commit(); flash('Cliente creado.','success')
        return redirect(url_for('clientes'))
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
        obj.nombre=request.form['nombre']; obj.empresa=request.form.get('empresa','')
        obj.email=request.form.get('email',''); obj.telefono=request.form.get('telefono','')
        obj.direccion=request.form.get('direccion',''); obj.notas=request.form.get('notas','')
        obj.estado=request.form.get('estado','activo'); obj.actualizado_en=datetime.utcnow()
        db.session.commit(); flash('Cliente actualizado.','success')
        return redirect(url_for('cliente_ver', id=obj.id))
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


@app.route('/ventas/nueva', methods=['GET','POST'])
@login_required
def venta_nueva():
    cl=Cliente.query.filter_by(estado='activo').order_by(Cliente.nombre).all()
    if request.method == 'POST':
        fs=request.form.get('fecha_cierre')
        db.session.add(Venta(titulo=request.form['titulo'],cliente_id=request.form.get('cliente_id') or None,
            monto=float(request.form.get('monto',0) or 0),estado=request.form.get('estado','prospecto'),
            fecha_cierre=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None,
            notas=request.form.get('notas',''),creado_por=current_user.id))
        db.session.commit(); flash('Venta creada.','success')
        return redirect(url_for('ventas'))
    return render_template('ventas/form.html', obj=None, clientes_list=cl, titulo='Nueva Venta')


@app.route('/ventas/<int:id>/editar', methods=['GET','POST'])
@login_required
def venta_editar(id):
    obj=Venta.query.get_or_404(id)
    cl=Cliente.query.filter_by(estado='activo').order_by(Cliente.nombre).all()
    if request.method == 'POST':
        fs=request.form.get('fecha_cierre')
        obj.titulo=request.form['titulo']; obj.cliente_id=request.form.get('cliente_id') or None
        obj.monto=float(request.form.get('monto',0) or 0); obj.estado=request.form.get('estado','prospecto')
        obj.fecha_cierre=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None
        obj.notas=request.form.get('notas',''); db.session.commit(); flash('Venta actualizada.','success')
        return redirect(url_for('ventas'))
    return render_template('ventas/form.html', obj=obj, clientes_list=cl, titulo='Editar Venta')


@app.route('/ventas/<int:id>/eliminar', methods=['POST'])
@login_required
def venta_eliminar(id):
    obj=Venta.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Venta eliminada.','info'); return redirect(url_for('ventas'))


# =============================================================
# TAREAS
# =============================================================

@app.route('/tareas')
@login_required
def tareas():
    estado_f=request.args.get('estado',''); prioridad_f=request.args.get('prioridad','')
    q=Tarea.query
    if estado_f: q=q.filter_by(estado=estado_f)
    if prioridad_f: q=q.filter_by(prioridad=prioridad_f)
    return render_template('tareas/index.html', items=q.order_by(Tarea.creado_en.desc()).all(),
        usuarios=User.query.filter_by(activo=True).all(), estado_f=estado_f, prioridad_f=prioridad_f)


@app.route('/tareas/nueva', methods=['GET','POST'])
@login_required
def tarea_nueva():
    us=User.query.filter_by(activo=True).all()
    if request.method == 'POST':
        fs=request.form.get('fecha_vencimiento')
        db.session.add(Tarea(titulo=request.form['titulo'],descripcion=request.form.get('descripcion',''),
            estado=request.form.get('estado','pendiente'),prioridad=request.form.get('prioridad','media'),
            fecha_vencimiento=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None,
            asignado_a=int(request.form.get('asignado_a') or current_user.id),creado_por=current_user.id))
        db.session.commit(); flash('Tarea creada.','success')
        return redirect(url_for('tareas'))
    return render_template('tareas/form.html', obj=None, usuarios=us, titulo='Nueva Tarea')


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
        db.session.commit(); flash('Tarea actualizada.','success')
        return redirect(url_for('tareas'))
    return render_template('tareas/form.html', obj=obj, usuarios=us, titulo='Editar Tarea')


@app.route('/tareas/<int:id>/completar', methods=['POST'])
@login_required
def tarea_completar(id):
    obj=Tarea.query.get_or_404(id); obj.estado='completada'; db.session.commit()
    flash('Tarea completada!','success'); return redirect(url_for('tareas'))


@app.route('/tareas/<int:id>/eliminar', methods=['POST'])
@login_required
def tarea_eliminar(id):
    obj=Tarea.query.get_or_404(id); db.session.delete(obj); db.session.commit()
    flash('Tarea eliminada.','info'); return redirect(url_for('tareas'))


# =============================================================
# INVENTARIO
# =============================================================

@app.route('/inventario')
@login_required
def inventario():
    busqueda=request.args.get('buscar',''); categoria_f=request.args.get('categoria','')
    q=Producto.query.filter_by(activo=True)
    if busqueda:
        q=q.filter(db.or_(Producto.nombre.ilike(f'%{busqueda}%'),
                           Producto.sku.ilike(f'%{busqueda}%'),
                           Producto.descripcion.ilike(f'%{busqueda}%')))
    if categoria_f: q=q.filter_by(categoria=categoria_f)
    cats=[c[0] for c in db.session.query(Producto.categoria).filter(
        Producto.activo==True,Producto.categoria!=None,Producto.categoria!='').distinct().all()]
    return render_template('inventario/index.html', items=q.order_by(Producto.nombre).all(),
                           busqueda=busqueda, categoria_f=categoria_f, categorias=cats)


@app.route('/inventario/nuevo', methods=['GET','POST'])
@login_required
def producto_nuevo():
    if request.method == 'POST':
        db.session.add(Producto(nombre=request.form['nombre'],descripcion=request.form.get('descripcion',''),
            precio=float(request.form.get('precio',0) or 0),stock=int(request.form.get('stock',0) or 0),
            stock_minimo=int(request.form.get('stock_minimo',5) or 5),
            categoria=request.form.get('categoria',''),sku=request.form.get('sku') or None))
        db.session.commit(); flash('Producto creado.','success')
        return redirect(url_for('inventario'))
    return render_template('inventario/form.html', obj=None, titulo='Nuevo Producto')


@app.route('/inventario/<int:id>/editar', methods=['GET','POST'])
@login_required
def producto_editar(id):
    obj=Producto.query.get_or_404(id)
    if request.method == 'POST':
        obj.nombre=request.form['nombre']; obj.descripcion=request.form.get('descripcion','')
        obj.precio=float(request.form.get('precio',0) or 0); obj.stock=int(request.form.get('stock',0) or 0)
        obj.stock_minimo=int(request.form.get('stock_minimo',5) or 5)
        obj.categoria=request.form.get('categoria',''); obj.sku=request.form.get('sku') or None
        db.session.commit(); flash('Producto actualizado.','success')
        return redirect(url_for('inventario'))
    return render_template('inventario/form.html', obj=obj, titulo='Editar Producto')


@app.route('/inventario/<int:id>/eliminar', methods=['POST'])
@login_required
def producto_eliminar(id):
    obj=Producto.query.get_or_404(id); obj.activo=False; db.session.commit()
    flash('Producto eliminado.','info'); return redirect(url_for('inventario'))


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
# INICIALIZACIÓN — se ejecuta via railway.toml antes de gunicorn
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
