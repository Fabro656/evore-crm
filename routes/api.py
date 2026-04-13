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
        except Exception as _e:
            logging.warning(f'search clientes: {_e}')
        try:
            for p in Proveedor.query.filter(
                db.or_(Proveedor.nombre.ilike(like), Proveedor.empresa.ilike(like), Proveedor.nit.ilike(like))
            ).limit(4).all():
                results.append({'type':'Proveedor','icon':'truck','color':'#00875A',
                    'label': p.empresa or p.nombre, 'sub': p.nit or '',
                    'url': '/proveedores/'+str(p.id)})
        except Exception as _e:
            logging.warning(f'search proveedores: {_e}')
        try:
            for pr in Producto.query.filter(
                db.or_(Producto.nombre.ilike(like), Producto.sku.ilike(like))
            ).filter_by(activo=True).limit(4).all():
                results.append({'type':'Producto','icon':'box-seam-fill','color':'#FF8B00',
                    'label': pr.nombre, 'sub': pr.sku or '',
                    'url': '/inventario'})
        except Exception as _e:
            logging.warning(f'search productos: {_e}')
        try:
            for v in Venta.query.filter(
                db.or_(Venta.titulo.ilike(like), Venta.numero.ilike(like))
            ).limit(4).all():
                results.append({'type':'Venta','icon':'graph-up-arrow','color':'#36B37E',
                    'label': v.titulo or v.numero or f'Venta #{v.id}', 'sub': v.estado or '',
                    'url': '/ventas/'+str(v.id)})
        except Exception as _e:
            logging.warning(f'search ventas: {_e}')
        try:
            for oc in OrdenCompra.query.filter(OrdenCompra.numero.ilike(like)).limit(3).all():
                results.append({'type':'OC','icon':'cart-check','color':'#6554C0',
                    'label': oc.numero or f'OC #{oc.id}', 'sub': oc.estado or '',
                    'url': '/ordenes_compra/'+str(oc.id)})
        except Exception as _e:
            logging.warning(f'search ordenes_compra: {_e}')
        return jsonify({'results': results, 'q': q})

    @app.route('/health')
    def health_check():
        """Railway healthcheck — must respond fast without DB queries."""
        return 'OK', 200

    @app.route('/sw.js')
    def pwa_service_worker():
        resp = make_response(send_file('static/sw.js', mimetype='application/javascript', max_age=0))
        resp.headers['Service-Worker-Allowed'] = '/'
        resp.headers['Cache-Control'] = 'no-cache, no-store'
        return resp

    @app.route('/debug-check')
    @login_required
    def debug_check():
        """Debug endpoint — requires admin login."""
        if current_user.rol not in ('admin', 'director_financiero'):
            return jsonify({'error': 'Acceso denegado'}), 403
        from company_config import COMPANY
        return jsonify({
            'company': COMPANY['name'],
            'country': COMPANY['country'],
            'users': User.query.count(),
            'clientes': Cliente.query.count(),
            'productos': Producto.query.count(),
        })

    @app.route('/api/transportistas/capacidad')
    @login_required
    def api_transportistas_capacidad():
        """Filtra transportistas por peso/volumen requerido."""
        peso_kg = float(request.args.get('peso', 0) or 0)
        volumen_m3 = float(request.args.get('volumen', 0) or 0)
        q = Proveedor.query.filter_by(tipo='transportista', activo=True)
        if peso_kg > 0:
            q = q.filter(Proveedor.capacidad_vehiculo_kg >= peso_kg)
        if volumen_m3 > 0:
            q = q.filter(Proveedor.capacidad_vehiculo_m3 >= volumen_m3)
        transportistas = q.order_by(Proveedor.capacidad_vehiculo_kg).all()
        return jsonify([{
            'id': t.id, 'nombre': t.nombre, 'empresa': t.empresa,
            'tipo_vehiculo': t.tipo_vehiculo or '—',
            'capacidad_kg': t.capacidad_vehiculo_kg or 0,
            'capacidad_m3': t.capacidad_vehiculo_m3 or 0,
            'envia_material': t.envia_material,
            'telefono': t.telefono or ''
        } for t in transportistas])

    @app.route('/api/producto/<int:id>/precio-minimo')
    @login_required
    def api_producto_precio_minimo(id):
        """Retorna precio mínimo y sugerido para un producto."""
        cant = float(request.args.get('cantidad', 1) or 1)
        return jsonify(_precio_minimo_venta(id, cant))

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
