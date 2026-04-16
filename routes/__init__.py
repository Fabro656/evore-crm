# routes/__init__.py
from routes import auth
from routes import dashboard
from routes import notas
from routes import clientes
from routes import proveedores
from routes import ventas
from routes import inventario
from routes import produccion
from routes import compras
from routes import tareas
from routes import nomina
from routes import admin
from routes import portal
from routes import api
from routes import ai
from routes import contable
from routes import empaques
from routes import servicios
from routes import aprobaciones
from routes import chat
from routes import foro
from routes import site
from routes import capacitacion
from routes import proyectos
from routes import barcode

def register_all(app):
    auth.register(app)
    dashboard.register(app)
    notas.register(app)
    clientes.register(app)
    proveedores.register(app)
    ventas.register(app)
    inventario.register(app)
    produccion.register(app)
    compras.register(app)
    tareas.register(app)
    nomina.register(app)
    admin.register(app)
    portal.register(app)
    api.register(app)
    ai.register(app)
    contable.register(app)
    empaques.register(app)
    servicios.register(app)
    aprobaciones.register(app)
    chat.register(app)
    foro.register(app)
    site.register(app)
    capacitacion.register(app)
    proyectos.register(app)
    barcode.register(app)
