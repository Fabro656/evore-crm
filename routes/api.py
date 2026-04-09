# routes/api.py
from flask import (render_template, redirect, url_for, flash, request,
                   jsonify, send_file, make_response, current_app)
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, secrets, logging


def register(app):
    @app.route('/api/buscar')
    def api_buscar():
        """JSON search API for the overlay search."""
        if not current_user.is_authenticated:
            return jsonify({'results':[], 'error':'not_authenticated'}), 401
        q = request.args.get('q','').strip()
        if not q or len(q) < 2:
            return jsonify({'results': []})
        like = f'%{q}%'
        results = []
        try:
            for c in Cliente.query.filter(
                db.or_(Cliente.nombre.ilike(like), Cliente.empresa.ilike(like), Cliente.nit.ilike(like))
            ).limit(6).all():
                results.append({'type':'Cliente','icon':'people-fill','color':'#0052CC',
                    'label': c.empresa or c.nombre, 'sub': c.nit or '',
                    'url': '/clientes/'+str(c.id)})
        except: pass
        try:
            for p in Proveedor.query.filter(
                db.or_(Proveedor.nombre.ilike(like), Proveedor.empresa.ilike(like), Proveedor.nit.ilike(like))
            ).limit(4).all():
                results.append({'type':'Proveedor','icon':'truck','color':'#00875A',
                    'label': p.empresa or p.nombre, 'sub': p.nit or '',
                    'url': '/proveedores/'+str(p.id)})
        except: pass
        try:
            for pr in Producto.query.filter(
                db.or_(Producto.nombre.ilike(like), Producto.sku.ilike(like))
            ).filter_by(activo=True).limit(4).all():
                results.append({'type':'Producto','icon':'box-seam-fill','color':'#FF8B00',
                    'label': pr.nombre, 'sub': pr.sku or '',
                    'url': '/inventario'})
        except: pass
        try:
            for v in Venta.query.filter(
                db.or_(Venta.titulo.ilike(like), Venta.numero.ilike(like))
            ).limit(4).all():
                results.append({'type':'Venta','icon':'graph-up-arrow','color':'#36B37E',
                    'label': v.titulo or v.numero or f'Venta #{v.id}', 'sub': v.estado or '',
                    'url': '/ventas/'+str(v.id)})
        except: pass
        try:
            for oc in OrdenCompra.query.filter(OrdenCompra.numero.ilike(like)).limit(3).all():
                results.append({'type':'OC','icon':'cart-check','color':'#6554C0',
                    'label': oc.numero or f'OC #{oc.id}', 'sub': oc.estado or '',
                    'url': '/ordenes_compra/'+str(oc.id)})
        except: pass
        return jsonify({'results': results, 'q': q})

    @app.route('/health')
    def health_check():
        """Railway healthcheck — must respond fast without DB queries."""
        return 'OK', 200

    @app.route('/diagnostico')
    @login_required
    def diagnostico():
        if current_user.rol != 'admin':
            return jsonify({'error': 'Sin permisos'}), 403
        critico = []; atencion = []; ok = []
        try:
            # Verificar DB
            db.session.execute(db.text('SELECT 1'))
            ok.append({'msg': 'Base de datos conectada', 'detalle': ''})
        except Exception as e:
            critico.append({'msg': 'Error de base de datos', 'detalle': str(e)})
        try:
            total_users = User.query.count()
            admins = User.query.filter_by(rol='admin', activo=True).count()
            ok.append({'msg': f'{total_users} usuarios ({admins} admins activos)', 'detalle': ''})
        except Exception as e:
            atencion.append({'msg': 'Error consultando usuarios', 'detalle': str(e)})
        try:
            total_prod = Producto.query.filter_by(activo=True).count()
            stock_bajo = Producto.query.filter(
                Producto.activo==True, Producto.stock_cantidad < 10
            ).count()
            if stock_bajo > 0:
                atencion.append({'msg': f'{stock_bajo} productos con stock bajo (<10)', 'detalle': ''})
            else:
                ok.append({'msg': f'{total_prod} productos activos, stock normal', 'detalle': ''})
        except Exception as e:
            atencion.append({'msg': 'Error consultando inventario', 'detalle': str(e)})
        try:
            hoy = datetime.utcnow().date()
            prox = hoy + timedelta(days=30)
            venc = LoteProducto.query.filter(
                LoteProducto.fecha_vencimiento != None,
                LoteProducto.fecha_vencimiento <= prox
            ).count()
            if venc > 0:
                atencion.append({'msg': f'{venc} lote(s) vencen en 30 días', 'detalle': ''})
            else:
                ok.append({'msg': 'Sin lotes próximos a vencer', 'detalle': ''})
        except Exception as e:
            atencion.append({'msg': 'No se pudieron revisar lotes', 'detalle': str(e)})
        try:
            notif_pend = Notificacion.query.filter_by(leida=False).count()
            if notif_pend > 20:
                atencion.append({'msg': f'{notif_pend} notificaciones sin leer en el sistema', 'detalle': ''})
            else:
                ok.append({'msg': f'{notif_pend} notificaciones pendientes', 'detalle': ''})
        except Exception as e:
            atencion.append({'msg': 'Error en notificaciones', 'detalle': str(e)})
        try:
            tareas_vencidas = Tarea.query.filter(
                Tarea.fecha_vencimiento < datetime.utcnow().date(),
                Tarea.estado.notin_(['completada','cancelada'])
            ).count()
            if tareas_vencidas > 0:
                atencion.append({'msg': f'{tareas_vencidas} tarea(s) vencidas sin completar', 'detalle': ''})
            else:
                ok.append({'msg': 'Sin tareas vencidas', 'detalle': ''})
        except Exception as e:
            atencion.append({'msg': 'Error consultando tareas', 'detalle': str(e)})
        try:
            materias_bajo = MateriaPrima.query.filter(
                MateriaPrima.activo==True,
                MateriaPrima.stock_disponible < MateriaPrima.stock_minimo
            ).count()
            if materias_bajo > 0:
                critico.append({'msg': f'{materias_bajo} materia(s) prima(s) bajo stock mínimo', 'detalle': ''})
            else:
                ok.append({'msg': 'Materias primas con stock normal', 'detalle': ''})
        except Exception as e:
            ok.append({'msg': 'Materias primas (módulo nuevo)', 'detalle': ''})
        return jsonify({'critico': critico, 'atencion': atencion, 'ok': ok})
