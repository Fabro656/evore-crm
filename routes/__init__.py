# routes/__init__.py
from routes import auth
from routes import dashboard
from routes import notas
from routes import clientes
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

def register_all(app):
    auth.register(app)
    dashboard.register(app)
    notas.register(app)
    clientes.register(app)
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
