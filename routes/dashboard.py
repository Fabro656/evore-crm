# routes/dashboard.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db, tenant_query
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging

def register(app):

    # ── landing page (public) — also serves as /
    @app.route('/inicio')
    def landing():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('landing.html', active_module=None)

    # ── contact/purchase form (public)
    @app.route('/contacto', methods=['POST'])
    def landing_contacto():
        import re as _re
        nombre = request.form.get('nombre', '').strip()[:200]
        email = request.form.get('email', '').strip()[:200]
        empresa = request.form.get('empresa', '').strip()[:200]
        telefono = request.form.get('telefono', '').strip()[:50]
        plan = request.form.get('plan', '').strip()[:20]
        mensaje = request.form.get('mensaje', '').strip()[:1000]
        if not nombre or not email:
            flash('Nombre y email son obligatorios.', 'danger')
            return redirect(url_for('landing'))
        if not _re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash('Ingresa un email válido.', 'danger')
            return redirect(url_for('landing'))
        # Create ticket for Evore admin
        try:
            evore = Company.query.filter_by(es_principal=True).first()
            admin_user = User.query.filter_by(rol='admin').first()
            if evore and admin_user:
                plan_label = {'starter': 'Starter ($39.900/mes)', 'pro': 'Profesional', 'free': 'Gratuito', 'demo': 'Demo'}.get(plan, plan or 'No especificado')
                desc = (f'Solicitud desde landing page\n\n'
                        f'Nombre: {nombre}\n'
                        f'Email: {email}\n'
                        f'Empresa: {empresa or "No indicada"}\n'
                        f'Teléfono: {telefono or "No indicado"}\n'
                        f'Plan interesado: {plan_label}\n'
                        f'Mensaje: {mensaje or "Sin mensaje adicional"}')
                db.session.add(Notificacion(
                    usuario_id=admin_user.id,
                    tipo='contacto',
                    titulo=f'Lead: {empresa or nombre}',
                    mensaje=f'Nueva solicitud de {nombre} ({email}) — Plan: {plan_label}',
                    url='/admin/usuarios'))
                db.session.commit()
                # Tarea as separate operation (may fail on local SQLite if company_id missing)
                try:
                    tarea = Tarea(
                        titulo=f'Lead: {empresa or nombre} — {plan_label}',
                        descripcion=desc,
                        prioridad='alta',
                        estado='pendiente',
                        creado_por=admin_user.id,
                        company_id=evore.id)
                    db.session.add(tarea)
                    db.session.commit()
                except Exception:
                    try: db.session.rollback()
                    except: pass
                # Send email notification
                _send_email(admin_user.email,
                    f'Nuevo lead desde evore.co: {empresa or nombre}', desc)
        except Exception as e:
            logging.warning(f'Landing contact error: {e}')
            try: db.session.rollback()
            except: pass
        flash('Solicitud enviada. Nuestro equipo te contactará pronto.', 'success')
        return redirect(url_for('landing'))

    # ── root: landing for visitors, dashboard for logged-in users
    @app.route('/')
    def root():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('landing.html', active_module=None)

    # ── dashboard (/dashboard)
    @app.route('/dashboard')
    @login_required
    def dashboard():
        from datetime import date
        hoy = date.today()
        mes_inicio = hoy.replace(day=1)
        try:
            # Ingresos = efectivo realmente cobrado (asientos ingreso parcial/completo),
            # filtrado por company_id. Antes se usaba Venta.total con estados limitados
            # (['completado','pagado']) y se perdian los anticipos recibidos.
            ingresos = tenant_query(AsientoContable).filter(
                AsientoContable.clasificacion == 'ingreso',
                AsientoContable.tipo != 'inversion_socio',
                AsientoContable.estado_pago.in_(['parcial', 'completo'])
            ).with_entities(db.func.coalesce(db.func.sum(AsientoContable.monto_pagado), 0)).scalar() or 0
            ingresos = float(ingresos)
            gastos_tot = tenant_query(GastoOperativo).with_entities(
                db.func.coalesce(db.func.sum(GastoOperativo.monto), 0)).scalar() or 0
            gastos_mes = tenant_query(GastoOperativo).filter(
                GastoOperativo.fecha >= mes_inicio
            ).with_entities(db.func.coalesce(db.func.sum(GastoOperativo.monto), 0)).scalar() or 0
            compras_tot = tenant_query(CompraMateria).with_entities(
                db.func.coalesce(db.func.sum(CompraMateria.costo_total), 0)).scalar() or 0
            saldo_pend = tenant_query(Venta).filter(
                Venta.saldo > 0,
                Venta.estado.in_(['prospecto', 'negociacion', 'anticipo_pagado'])
            ).with_entities(db.func.coalesce(db.func.sum(Venta.saldo), 0)).scalar() or 0
        except Exception:
            db.session.rollback()
            ingresos = gastos_tot = gastos_mes = compras_tot = saldo_pend = 0
        total_egresos_global = gastos_tot + compras_tot
        utilidad_global = ingresos - total_egresos_global
        try:
            impuestos_estimados, detalle_imp_dash = _calcular_impuestos(ingresos, utilidad_global)
        except Exception:
            impuestos_estimados, detalle_imp_dash = 0, []
        saldo_neto = ingresos - total_egresos_global - impuestos_estimados
        # Auto-alertas de stock bajo (crear ticket y notificación si no existe)
        try:
            prods_bajo = tenant_query(Producto).filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).all()
            for pb in prods_bajo[:5]:  # max 5 alertas
                titulo_alerta = f'Stock bajo: {pb.nombre} ({pb.stock}/{pb.stock_minimo})'
                ya_existe = tenant_query(Tarea).filter(Tarea.titulo==titulo_alerta, Tarea.estado=='pendiente').first()
                if not ya_existe:
                    t = Tarea(company_id=getattr(g, 'company_id', None),
                              titulo=titulo_alerta, descripcion=f'El producto {pb.nombre} tiene stock {pb.stock} por debajo del minimo {pb.stock_minimo}.',
                              estado='pendiente', prioridad='alta', tarea_tipo='alerta_stock', categoria='logistica',
                              creado_por=current_user.id, asignado_a=current_user.id)
                    db.session.add(t)
            if prods_bajo: db.session.commit()
        except Exception as _e:
            logging.warning(f'dashboard stock alerts: {_e}')

        # Productos bajo mínimo para el banner detallado del dashboard
        try:
            alertas_stock = tenant_query(Producto).filter(
                Producto.activo == True,
                Producto.stock_minimo > 0,
                Producto.stock < Producto.stock_minimo
            ).order_by(Producto.nombre).all()
        except Exception:
            alertas_stock = []

        # ── Top 5 Clientes por CLV (Customer Lifetime Value) ──
        try:
            top_clientes_clv = db.session.query(
                Cliente.id, Cliente.empresa, Cliente.nombre,
                db.func.sum(Venta.total).label('total_revenue'),
                db.func.count(Venta.id).label('order_count')
            ).join(Venta, Venta.cliente_id == Cliente.id).filter(
                Venta.estado.in_(['completado', 'pagado', 'entregado'])
            ).group_by(Cliente.id).order_by(db.func.sum(Venta.total).desc()).limit(5).all()
        except Exception:
            db.session.rollback()
            top_clientes_clv = []

        # ── Top 10 Productos por rentabilidad (margen %) ──
        try:
            _recetas_raw = RecetaProducto.query.join(Producto, RecetaProducto.producto_id == Producto.id).filter(
                RecetaProducto.precio_venta_sugerido > 0,
                RecetaProducto.costo_calculado > 0
            ).with_entities(
                Producto.nombre,
                RecetaProducto.costo_calculado,
                RecetaProducto.precio_venta_sugerido
            ).all()
            productos_rentabilidad = []
            for r in _recetas_raw:
                margen = r.precio_venta_sugerido - r.costo_calculado
                margen_pct = (margen / r.precio_venta_sugerido) * 100
                productos_rentabilidad.append({
                    'nombre': r.nombre,
                    'costo': r.costo_calculado,
                    'precio': r.precio_venta_sugerido,
                    'margen_pct': round(margen_pct, 1)
                })
            productos_rentabilidad.sort(key=lambda x: x['margen_pct'], reverse=True)
            productos_rentabilidad = productos_rentabilidad[:10]
        except Exception:
            db.session.rollback()
            productos_rentabilidad = []

        # ── Batch counts (cached 60s) ──
        _cid = getattr(g, 'company_id', None) or current_user.company_id
        from extensions import cache_get, cache_set
        import json as _json
        _cache_key = f'dash_counts:{_cid}'
        _cached = cache_get(_cache_key)
        if _cached:
            try:
                _cc = _json.loads(_cached)
                _total_clientes = _cc['c']; _ventas_completadas = _cc['v']
                _tareas_pendientes = _cc['t']; _productos_bajo = _cc['p']
            except Exception:
                _cached = None
        if not _cached:
            try:
                _total_clientes = tenant_query(Cliente).filter_by(estado='activo', company_id=_cid).count()
                _ventas_completadas = tenant_query(Venta).filter_by(estado='completado', company_id=_cid).count()
                _tareas_pendientes = tenant_query(Tarea).filter(Tarea.estado != 'completada', Tarea.company_id == _cid).count()
                _productos_bajo = tenant_query(Producto).filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo, Producto.company_id==_cid).count()
                cache_set(_cache_key, _json.dumps({'c':_total_clientes,'v':_ventas_completadas,'t':_tareas_pendientes,'p':_productos_bajo}), 60)
            except Exception:
                _total_clientes = _ventas_completadas = _tareas_pendientes = _productos_bajo = 0

        # ── Recent items (limit queries) ──
        _rol = _get_rol_activo(current_user)
        try:
            _tareas_rec = tenant_query(Tarea).filter(Tarea.estado!='completada', Tarea.company_id==_cid).order_by(Tarea.creado_en.desc()).limit(5).all()
            _ventas_rec = tenant_query(Venta).filter_by(company_id=_cid).order_by(Venta.creado_en.desc()).limit(6).all()
            _notas_rec = tenant_query(Nota).filter_by(company_id=_cid).order_by(Nota.actualizado_en.desc()).limit(4).all()
            _eventos_hoy = tenant_query(Evento).filter(Evento.fecha==hoy).order_by(Evento.hora_inicio).all()
            _eventos_prox = tenant_query(Evento).filter(Evento.fecha>hoy, Evento.fecha<=hoy+timedelta(days=7)).order_by(Evento.fecha).limit(5).all()
            _aprob = tenant_query(Aprobacion).filter_by(estado='pendiente').order_by(Aprobacion.creado_en.desc()).limit(5).all() if _rol in ('admin','director_financiero','director_operativo') else []
        except Exception:
            _tareas_rec = _ventas_rec = _notas_rec = _eventos_hoy = _eventos_prox = _aprob = []

        return render_template('dashboard.html',
            total_clientes       = _total_clientes,
            ventas_completadas   = _ventas_completadas,
            tareas_pendientes    = _tareas_pendientes,
            ingresos_totales     = ingresos,
            gastos_totales       = gastos_tot,
            compras_totales      = compras_tot,
            balance              = ingresos - total_egresos_global,
            impuestos_estimados  = impuestos_estimados,
            saldo_neto           = saldo_neto,
            saldo_pendiente      = saldo_pend,
            productos_bajo_stock = _productos_bajo,
            alertas_stock        = alertas_stock,
            tareas_recientes     = _tareas_rec,
            ventas_recientes     = _ventas_rec,
            actividades_recientes= [],
            aprobaciones_pendientes = _aprob,
            notas_recientes      = _notas_rec,
            eventos_hoy          = _eventos_hoy,
            eventos_proximos     = _eventos_prox,
            top_clientes_clv     = top_clientes_clv,
            productos_rentabilidad = productos_rentabilidad,
        )
    

    # ── API: lazy-loaded dashboard data ──
    @app.route('/api/dashboard/lazy')
    @login_required
    def dashboard_lazy():
        """Returns heavy dashboard data as JSON for lazy loading."""
        from routes.api import _check_api_rate
        if _check_api_rate(request.remote_addr):
            return jsonify({'error': 'rate limit'}), 429
        try:
            hoy = date_type.today()
            hace_7d = hoy - timedelta(days=7)
            hace_14d = hoy - timedelta(days=14)
            hace_30d = hoy - timedelta(days=30)

            data = {}

            # Cotizaciones sin respuesta (> 7 dias)
            try:
                cots = tenant_query(Cotizacion).filter(
                    Cotizacion.estado == 'enviada',
                    Cotizacion.fecha_emision <= hace_7d
                ).order_by(Cotizacion.fecha_emision).limit(10).all()
                data['cots_sin_respuesta'] = [{
                    'id': c.id,
                    'numero': c.numero or '',
                    'titulo': c.titulo or '',
                    'dias': (hoy - c.fecha_emision).days if c.fecha_emision else 0,
                    'cliente': (c.cliente.empresa or c.cliente.nombre) if c.cliente else ''
                } for c in cots]
            except Exception:
                data['cots_sin_respuesta'] = []

            # Ventas estancadas en negociacion (> 14 dias)
            try:
                vest = tenant_query(Venta).filter(
                    Venta.estado == 'negociacion',
                    Venta.creado_en <= datetime.combine(hace_14d, datetime.min.time())
                ).order_by(Venta.creado_en).limit(10).all()
                data['ventas_estancadas'] = [{
                    'id': v.id,
                    'titulo': v.titulo or v.numero or '',
                    'dias': (hoy - v.creado_en.date()).days if v.creado_en else 0,
                    'cliente': (v.cliente.empresa or v.cliente.nombre) if v.cliente else ''
                } for v in vest]
            except Exception:
                data['ventas_estancadas'] = []

            # Entregas pendientes (> 30 dias)
            try:
                epend = tenant_query(Venta).filter(
                    Venta.estado.in_(['pagado']),
                    Venta.creado_en <= datetime.combine(hace_30d, datetime.min.time())
                ).order_by(Venta.creado_en).limit(10).all()
                data['entregas_pendientes'] = [{
                    'id': v.id,
                    'titulo': v.titulo or v.numero or '',
                    'dias': (hoy - v.creado_en.date()).days if v.creado_en else 0,
                    'cliente': (v.cliente.empresa or v.cliente.nombre) if v.cliente else ''
                } for v in epend]
            except Exception:
                data['entregas_pendientes'] = []

            return jsonify(data)
        except Exception as e:
            logging.warning(f'dashboard_lazy error: {e}')
            return jsonify({'error': 'Error interno'}), 500


    # ── wiki (/wiki)
    @app.route('/wiki')
    @login_required
    def wiki():
        return render_template('wiki.html')


    # ── mi_actividad (/mi-actividad)
    @app.route('/mi-actividad')
    @login_required
    def mi_actividad():
        from datetime import date as date_type
        hoy = date_type.today()
        # Compute uid ONCE at the beginning
        uid = request.args.get('user_id', type=int, default=current_user.id)
        if uid != current_user.id and _get_rol_activo(current_user) != 'admin':
            uid = current_user.id
        target_user = db.session.get(User, uid) if uid != current_user.id else current_user
        usuarios_lista = User.query.filter_by(activo=True).all() if _get_rol_activo(current_user) == 'admin' else []
    
        # Last 6 months of activity
        meses = []
        for i in range(5, -1, -1):
            if hoy.month - i <= 0:
                m = hoy.month - i + 12; y = hoy.year - 1
            else:
                m = hoy.month - i; y = hoy.year
            inicio = datetime(y, m, 1)
            if m == 12: fin = datetime(y+1, 1, 1)
            else:       fin = datetime(y, m+1, 1)
            tareas_hechas = tenant_query(Tarea).filter(
                db.or_(Tarea.asignado_a==uid, Tarea.creado_por==uid),
                Tarea.estado=='completada',
                Tarea.creado_en>=inicio, Tarea.creado_en<fin
            ).count()
            act_count = Actividad.query.filter(
                Actividad.usuario_id==uid,
                Actividad.creado_en>=inicio, Actividad.creado_en<fin
            ).count()
            clientes_nuevos = Actividad.query.filter(
                Actividad.usuario_id==uid,
                Actividad.entidad=='cliente',
                Actividad.tipo=='crear',
                Actividad.creado_en>=inicio, Actividad.creado_en<fin
            ).count() if _get_rol_activo(current_user) in ['admin','vendedor','sales_manager'] else 0
            tiempo = db.session.query(db.func.sum(UserSesion.duracion_min)).filter(
                UserSesion.user_id==uid,
                UserSesion.login_at>=inicio, UserSesion.login_at<fin
            ).scalar() or 0
            meses.append({
                'mes': inicio.strftime('%b %Y'), 'tareas': tareas_hechas,
                'acciones': act_count, 'clientes': clientes_nuevos,
                'tiempo_min': round(tiempo)
            })
        return render_template('mi_actividad.html', meses=meses, target_user=target_user,
                               usuarios_lista=usuarios_lista, uid=uid)
    

    # ── reportes (/reportes)
    @app.route('/reportes')
    @login_required
    def reportes():
        from datetime import date
        from calendar import month_abbr
        # Estadísticas generales
        _cid2 = getattr(g, 'company_id', None) or current_user.company_id
        # Ingresos reales = efectivo cobrado (asientos ingreso con pago confirmado)
        ingresos_totales = db.session.query(db.func.coalesce(db.func.sum(AsientoContable.monto_pagado), 0)).filter(
            AsientoContable.company_id == _cid2,
            AsientoContable.clasificacion == 'ingreso',
            AsientoContable.tipo != 'inversion_socio',
            AsientoContable.estado_pago.in_(['parcial', 'completo'])
        ).scalar() or 0
        ingresos_totales = float(ingresos_totales)
        gastos_totales   = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.company_id==_cid2).scalar() or 0
        balance          = ingresos_totales - gastos_totales
        total_clientes   = tenant_query(Cliente).filter_by(estado='activo', company_id=_cid2).count()
        # Ventas por mes (últimos 6 meses)
        hoy = date.today()
        meses_labels, ventas_por_mes = [], []
        for i in range(5, -1, -1):
            mes = (hoy.month - i - 1) % 12 + 1
            anio = hoy.year - ((hoy.month - i - 1) // 12 + (1 if (hoy.month - i - 1) < 0 else 0))
            total_mes = db.session.query(db.func.sum(Venta.total)).filter(
                Venta.company_id==_cid2,
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
        bajo_stock = tenant_query(Producto).filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).all()
        return render_template('reportes.html',
            total_clientes=total_clientes, ingresos_totales=ingresos_totales,
            gastos_totales=gastos_totales, balance=balance,
            meses_labels=meses_labels, ventas_por_mes=ventas_por_mes,
            gastos_tipos_labels=gastos_tipos_labels, gastos_tipos_values=gastos_tipos_values,
            top_clientes=top_clientes, bajo_stock=bajo_stock)
    

    # ── exportar_ventas (/reportes/exportar/ventas.xlsx)
    @app.route('/reportes/exportar/ventas.xlsx')
    @login_required
    def exportar_ventas():
        from flask import send_file
        ventas = tenant_query(Venta).order_by(Venta.creado_en.desc()).all()
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
    

    # ── exportar_gastos (/reportes/exportar/gastos.xlsx)
    @app.route('/reportes/exportar/gastos.xlsx')
    @login_required
    def exportar_gastos():
        from flask import send_file
        items = tenant_query(GastoOperativo).order_by(GastoOperativo.fecha.desc()).all()
        headers = ['Fecha','Tipo','Descripción','Monto COP','Notas']
        rows = [[g.fecha.strftime('%d/%m/%Y'), g.tipo, g.descripcion or '', round(g.monto), g.notas or ''] for g in items]
        buf = _make_xlsx('Gastos Operativos', headers, rows)
        return send_file(buf, download_name='evore_gastos.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    

    # ── exportar_inventario (/reportes/exportar/inventario.xlsx)
    @app.route('/reportes/exportar/inventario.xlsx')
    @login_required
    def exportar_inventario():
        from flask import send_file
        items = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
        headers = ['Nombre','SKU','NSO (INVIMA)','Precio COP','Costo COP','Stock','Stock Mínimo','Categoría']
        rows = [[p.nombre, p.sku or '', p.nso or '', round(p.precio), round(p.costo),
                 p.stock, p.stock_minimo, p.categoria or ''] for p in items]
        buf = _make_xlsx('Inventario', headers, rows)
        return send_file(buf, download_name='evore_inventario.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    

    # ── exportar_clientes (/reportes/exportar/clientes.xlsx)
    @app.route('/reportes/exportar/clientes.xlsx')
    @login_required
    def exportar_clientes():
        from flask import send_file
        items = tenant_query(Cliente).order_by(Cliente.empresa, Cliente.nombre).all()
        headers = ['Empresa','NIT','Relación','Dirección comercial','Dirección entrega','Estado','Creado']
        rows = [[c.empresa or '', c.nit or '', c.estado_relacion or '', c.dir_comercial or '',
                 c.dir_entrega or '', c.estado, c.creado_en.strftime('%d/%m/%Y')] for c in items]
        buf = _make_xlsx('Clientes', headers, rows)
        return send_file(buf, download_name='evore_clientes.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    

    # ── calendario (/calendario)
    @app.route('/calendario')
    @login_required
    def calendario():
        from datetime import date as date_t
        hoy = date_t.today()
        anio = int(request.args.get('anio', hoy.year))
        mes  = int(request.args.get('mes',  hoy.month))
        eventos = {}
        # 1. Tareas con fecha de vencimiento
        try:
            for t in tenant_query(Tarea).filter(Tarea.fecha_vencimiento != None).all():
                k = t.fecha_vencimiento.strftime('%Y-%m-%d')
                ref_url = url_for('tarea_ver', id=t.id)
                desc_parts = []
                if t.tarea_tipo in ('comprar_materias', 'verificar_abono') and t.cotizacion_id:
                    try:
                        cot = db.session.get(Cotizacion, t.cotizacion_id)
                        if cot:
                            desc_parts.append('Cotización: ' + (cot.numero or ('#' + str(cot.id))))
                            ref_url = url_for('cotizacion_ver', id=cot.id)
                    except Exception as _e: logging.warning(f'Calendario: cotizacion lookup error: {_e}')
                elif t.tarea_tipo == 'comprar_materias':
                    desc_parts.append('Compra de materias primas')
                elif t.tarea_tipo == 'verificar_abono':
                    desc_parts.append('Verificación de abono')
                if t.descripcion and not desc_parts:
                    desc_parts.append(t.descripcion[:80])
                estado_label = {'pendiente':'Pendiente','en_progreso':'En progreso','completada':'Completada'}.get(t.estado, t.estado)
                desc_parts.append('Estado: ' + estado_label)
                if t.prioridad:
                    desc_parts.append('Prioridad: ' + t.prioridad.title())
                eventos.setdefault(k, []).append({'t':'tarea','n':t.titulo,'s':t.estado,
                    'd':' · '.join(desc_parts),'url':ref_url,'tid':t.id})
        except Exception as _e:
            logging.warning(f'Calendario: tareas error: {_e}'); db.session.rollback()
        # 2. Ventas con fecha entrega estimada
        try:
            for v in tenant_query(Venta).filter(Venta.fecha_entrega_est != None).all():
                k = v.fecha_entrega_est.strftime('%Y-%m-%d')
                cliente_nom = ''
                try:
                    if v.cliente: cliente_nom = v.cliente.empresa or v.cliente.nombre or ''
                except Exception as _e: logging.warning(f'Calendario: cliente lookup error: {_e}')
                desc = ('Cliente: ' + cliente_nom + ' · ' if cliente_nom else '') + 'Estado: ' + v.estado
                if v.numero: desc = 'Venta ' + v.numero + ' · ' + desc
                eventos.setdefault(k, []).append({'t':'venta','n':v.titulo,'s':v.estado,
                    'd':desc,'url':url_for('venta_editar', id=v.id),'tid':v.id})
        except Exception as _e:
            logging.warning(f'Calendario: ventas error: {_e}'); db.session.rollback()
        # 3. Eventos manuales
        try:
            for e in tenant_query(Evento).all():
                k = e.fecha.strftime('%Y-%m-%d')
                desc = (e.descripcion[:80] if e.descripcion else '') or (e.tipo or 'Evento')
                eventos.setdefault(k, []).append({'t':'evento','n':e.titulo,'s':e.tipo,'d':desc,'url':'','tid':e.id})
        except Exception as _e:
            logging.warning(f'Calendario: eventos error: {_e}'); db.session.rollback()
        # 4. Notas con fecha de revisión (columna nueva en v11)
        try:
            for n in tenant_query(Nota).filter(Nota.fecha_revision != None).all():
                k = n.fecha_revision.strftime('%Y-%m-%d')
                desc = (n.contenido[:80] if n.contenido else '') or 'Revisión programada'
                eventos.setdefault(k, []).append({'t':'nota','n':n.titulo or '(nota sin título)','s':'revision',
                    'd':desc,'url':url_for('notas'),'tid':n.id})
        except Exception as _e:
            logging.warning(f'Calendario: notas error: {_e}'); db.session.rollback()
        # 5. Productos con fecha de caducidad (columna nueva en v11)
        try:
            for p in tenant_query(Producto).filter(Producto.fecha_caducidad != None, Producto.activo == True).all():
                k = p.fecha_caducidad.strftime('%Y-%m-%d')
                desc_p = []
                if p.sku: desc_p.append('SKU: ' + p.sku)
                if p.stock is not None: desc_p.append('Stock: ' + str(int(p.stock)))
                eventos.setdefault(k, []).append({'t':'caducidad','n':p.nombre,'s':'caducidad',
                    'd':' · '.join(desc_p) or 'Próximo a caducar','url':url_for('inventario'),'tid':p.id})
        except Exception as _e:
            logging.warning(f'Calendario: caducidad error: {_e}'); db.session.rollback()
        import calendar as cal_mod
        from datetime import date as _date
        # Build week matrix: list of 7-element lists; 0 = filler day from other month
        cal_obj = cal_mod.Calendar(firstweekday=0)   # 0 = Monday first
        month_days = cal_obj.monthdayscalendar(anio, mes)
        # Compute prev / next month for nav links
        prev_mes  = mes - 1 if mes > 1 else 12
        prev_anio = anio if mes > 1 else anio - 1
        next_mes  = mes + 1 if mes < 12 else 1
        next_anio = anio if mes < 12 else anio + 1
        today_str = _date.today().strftime('%Y-%m-%d')
        mes_nombres = ['','Enero','Febrero','Marzo','Abril','Mayo','Junio',
                       'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
        return render_template('calendario.html',
                               eventos=eventos, anio=anio, mes=mes,
                               month_days=month_days,
                               prev_mes=prev_mes, prev_anio=prev_anio,
                               next_mes=next_mes, next_anio=next_anio,
                               today_str=today_str,
                               mes_nombre=mes_nombres[mes])
    

    # ── evento_nuevo (/eventos/nuevo)
    @app.route('/eventos/nuevo', methods=['GET','POST'])
    @login_required
    def evento_nuevo():
        if request.method == 'POST':
            fd = request.form.get('fecha')
            titulo = request.form.get('titulo', '').strip()
            if not titulo:
                flash('El titulo es obligatorio.', 'danger')
                return redirect(url_for('calendario'))
            fecha_ev = datetime.strptime(fd, '%Y-%m-%d').date() if fd else datetime.utcnow().date()
            # Proteccion contra duplicados (mismo titulo+fecha en ultimos 5 seg)
            dup = tenant_query(Evento).filter_by(
                titulo=titulo, fecha=fecha_ev, usuario_id=current_user.id
            ).first()
            if dup:
                flash('Ese evento ya existe.', 'warning')
                return redirect(url_for('calendario', mes=fecha_ev.month, anio=fecha_ev.year))
            ev = Evento(
                titulo=titulo,
                tipo=request.form.get('tipo', 'recordatorio'),
                fecha=fecha_ev,
                hora_inicio=request.form.get('hora_inicio', '') or None,
                hora_fin=request.form.get('hora_fin', '') or None,
                descripcion=request.form.get('descripcion', ''),
                usuario_id=current_user.id)
            db.session.add(ev); db.session.commit()
            flash('Evento creado.', 'success')
            return redirect(url_for('calendario', mes=fecha_ev.month, anio=fecha_ev.year))
        return redirect(url_for('calendario'))
    

    # ── evento_editar (/eventos/<int:id>/editar)
    @app.route('/eventos/<int:id>/editar', methods=['POST'])
    @login_required
    def evento_editar(id):
        obj = Evento.query.get_or_404(id)
        fd = request.form.get('fecha')
        obj.titulo = request.form.get('titulo', obj.titulo)
        obj.tipo = request.form.get('tipo', obj.tipo)
        if fd: obj.fecha = datetime.strptime(fd,'%Y-%m-%d').date()
        obj.hora_inicio = request.form.get('hora_inicio','') or None
        obj.hora_fin    = request.form.get('hora_fin','') or None
        obj.descripcion = request.form.get('descripcion','')
        db.session.commit(); flash('Evento actualizado.','success')
        return redirect(url_for('calendario'))
    

    # ── evento_eliminar (/eventos/<int:id>/eliminar)
    @app.route('/eventos/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('calendario')
    def evento_eliminar(id):
        obj = Evento.query.get_or_404(id)
        if obj.usuario_id != current_user.id and current_user.rol != 'admin':
            flash('No puedes eliminar eventos de otro usuario.', 'danger')
            return redirect(url_for('calendario'))
        db.session.delete(obj); db.session.commit()
        flash('Evento eliminado.','info')
        return redirect(url_for('calendario'))
    

    # ── actividad (/actividad)
    @app.route('/actividad')
    @login_required
    def actividad():
        if _get_rol_activo(current_user) != 'admin':
            items = Actividad.query.filter_by(usuario_id=current_user.id).order_by(Actividad.creado_en.desc()).limit(150).all()
        else:
            items = Actividad.query.order_by(Actividad.creado_en.desc()).limit(300).all()
        return render_template('actividad.html', items=items)
    

    # ── notificaciones (/notificaciones)
    @app.route('/notificaciones')
    @login_required
    def notificaciones():
        items = tenant_query(Notificacion).filter_by(usuario_id=current_user.id)\
                    .order_by(Notificacion.creado_en.desc()).limit(100).all()
        # marcar todas como leídas al abrir
        tenant_query(Notificacion).filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
        db.session.commit()
        return render_template('notificaciones.html', items=items)
    

    # ── notificaciones_recientes (/notificaciones/recientes)
    @app.route('/notificaciones/recientes')
    @login_required
    def notificaciones_recientes():
        items = tenant_query(Notificacion).filter_by(usuario_id=current_user.id, leida=False)\
                    .order_by(Notificacion.creado_en.desc()).limit(10).all()
        return jsonify([{
            'id': n.id, 'tipo': n.tipo, 'titulo': n.titulo,
            'mensaje': n.mensaje, 'url': n.url or '',
            'creado_en': n.creado_en.strftime('%d/%m %H:%M')
        } for n in items])
    

    # ── notificaciones_marcar_todas (/notificaciones/marcar_todas)
    @app.route('/notificaciones/marcar_todas', methods=['POST'])
    @login_required
    def notificaciones_marcar_todas():
        tenant_query(Notificacion).filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
        db.session.commit()
        flash('Todas las notificaciones marcadas como leídas.', 'success')
        return redirect(url_for('notificaciones'))
    

    # ── notificacion_leida (/notificaciones/<int:id>/leida)
    @app.route('/notificaciones/<int:id>/leida', methods=['POST'])
    @login_required
    def notificacion_leida(id):
        n = Notificacion.query.get_or_404(id)
        if n.usuario_id == current_user.id:
            n.leida = True
            db.session.commit()
        return ('', 204)
    

    # contable_index fue movido a routes/contable.py (v30)

    # ── contable_ingresos (/contable/ingresos) — redirige a asientos filtrados
    @app.route('/contable/ingresos')
    @login_required
    def contable_ingresos():
        # La vista unificada de asientos (filtro=ingresos) muestra total + recibido,
        # historial de cobros y botones de confirmar/editar. Este endpoint queda
        # como alias para compatibilidad con dashboards/links antiguos.
        return redirect(url_for('contable_asientos', filtro='ingresos',
                                desde=request.args.get('desde',''),
                                hasta=request.args.get('hasta','')))
    

    # ── contable_egresos (/contable/egresos)
    @app.route('/contable/egresos')
    @login_required
    def contable_egresos():
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        gastos = tenant_query(GastoOperativo)
        compras = tenant_query(CompraMateria)
        if desde_s:
            try:
                d = datetime.strptime(desde_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha >= d)
                compras = compras.filter(CompraMateria.fecha >= d)
            except Exception: pass
        if hasta_s:
            try:
                h = datetime.strptime(hasta_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha <= h)
                compras = compras.filter(CompraMateria.fecha <= h)
            except Exception: pass
        return render_template('contable/egresos.html',
            gastos=gastos.order_by(GastoOperativo.fecha.desc()).all(),
            compras=compras.order_by(CompraMateria.fecha.desc()).all(),
            desde_s=desde_s, hasta_s=hasta_s)
    

    # ── contable_libro_diario (/contable/libro-diario)
    @app.route('/contable/libro-diario', methods=['GET','POST'])
    @login_required
    def contable_libro_diario():
        if request.method == 'POST':
            fd = request.form.get('fecha')
            a = AsientoContable(
                company_id=getattr(g, 'company_id', None),
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                descripcion=request.form['descripcion'],
                tipo=request.form.get('tipo','manual'),
                referencia=request.form.get('referencia',''),
                debe=float(request.form.get('debe') or 0),
                haber=float(request.form.get('haber') or 0),
                cuenta_debe=request.form.get('cuenta_debe',''),
                cuenta_haber=request.form.get('cuenta_haber',''),
                notas=request.form.get('notas',''),
                creado_por=current_user.id
            )
            db.session.add(a); db.session.flush()
            hoy = datetime.utcnow().date()
            ultimo = tenant_query(AsientoContable).filter(
                AsientoContable.numero.like(f'AC-{hoy.year}-%')
            ).order_by(AsientoContable.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except Exception: seq = 1
            else: seq = 1
            a.numero = f'AC-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Asiento {a.numero} registrado.','success')
            return redirect(url_for('contable_libro_diario'))
        asientos = tenant_query(AsientoContable).order_by(AsientoContable.fecha.desc(), AsientoContable.id.desc()).limit(100).all()
        from datetime import date as _d
        return render_template('contable/libro_diario.html', asientos=asientos, today=_d.today().strftime('%Y-%m-%d'))
    

    # ── contable_exportar (/contable/exportar)
    @app.route('/contable/exportar')
    @login_required
    def contable_exportar():
        tipo = request.args.get('tipo','ventas')
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        import csv, io
        si = io.StringIO()
        writer = csv.writer(si)
        if tipo == 'ventas':
            writer.writerow(['Numero','Titulo','Cliente','Fecha','Estado','Subtotal','IVA','Total','Anticipo','Saldo'])
            q = tenant_query(Venta)
            if desde_s:
                try: q = q.filter(db.func.date(Venta.creado_en) >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except Exception: pass
            if hasta_s:
                try: q = q.filter(db.func.date(Venta.creado_en) <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except Exception: pass
            for v in q.order_by(Venta.creado_en).all():
                writer.writerow([v.numero or '', v.titulo,
                    v.cliente.empresa or v.cliente.nombre if v.cliente else '',
                    v.creado_en.strftime('%Y-%m-%d'), v.estado,
                    v.subtotal, v.iva, v.total, v.monto_anticipo, v.saldo])
        elif tipo == 'gastos':
            writer.writerow(['Fecha','Tipo','Descripcion','Monto','Recurrencia'])
            q = tenant_query(GastoOperativo)
            if desde_s:
                try: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except Exception: pass
            if hasta_s:
                try: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except Exception: pass
            for g in q.order_by(GastoOperativo.fecha).all():
                writer.writerow([g.fecha.strftime('%Y-%m-%d'), g.tipo, g.descripcion or '', g.monto, g.recurrencia])
        elif tipo == 'compras':
            writer.writerow(['Fecha','Item','Proveedor','Cantidad','Unidad','Costo Total','Factura'])
            q = tenant_query(CompraMateria)
            if desde_s:
                try: q = q.filter(CompraMateria.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except Exception: pass
            if hasta_s:
                try: q = q.filter(CompraMateria.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except Exception: pass
            for c in q.order_by(CompraMateria.fecha).all():
                writer.writerow([c.fecha.strftime('%Y-%m-%d'), c.nombre_item, c.proveedor or '',
                    c.cantidad, c.unidad, c.costo_total, c.nro_factura or ''])
        elif tipo == 'asientos':
            writer.writerow(['Numero','Fecha','Descripcion','Tipo','Referencia','Debe','Haber','Cuenta Debe','Cuenta Haber'])
            for a in tenant_query(AsientoContable).order_by(AsientoContable.fecha).all():
                writer.writerow([a.numero or '', a.fecha.strftime('%Y-%m-%d'), a.descripcion,
                    a.tipo, a.referencia or '', a.debe, a.haber, a.cuenta_debe or '', a.cuenta_haber or ''])
        output = si.getvalue()
        from flask import Response
        return Response(output, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename=contable_{tipo}_{desde_s or "todo"}.csv'})
    

    # ── buscador (/buscador)
    @app.route('/buscador')
    @login_required
    def buscador():
        q = request.args.get('q','').strip()
        resultados = {}
        if q:
            like = f'%{q}%'
            try:
                resultados['clientes'] = tenant_query(Cliente).filter(
                    db.or_(Cliente.nombre.ilike(like), Cliente.empresa.ilike(like), Cliente.nit.ilike(like))
                ).limit(20).all()
            except Exception: resultados['clientes'] = []
            try:
                resultados['proveedores'] = tenant_query(Proveedor).filter(
                    db.or_(Proveedor.nombre.ilike(like), Proveedor.empresa.ilike(like), Proveedor.nit.ilike(like))
                ).limit(20).all()
            except Exception: resultados['proveedores'] = []
            try:
                resultados['productos'] = tenant_query(Producto).filter(
                    db.or_(Producto.nombre.ilike(like), Producto.sku.ilike(like), Producto.nso.ilike(like))
                ).filter_by(activo=True).limit(20).all()
            except Exception: resultados['productos'] = []
            try:
                resultados['ventas'] = tenant_query(Venta).filter(
                    db.or_(Venta.titulo.ilike(like), Venta.numero.ilike(like))
                ).limit(20).all()
            except Exception: resultados['ventas'] = []
            try:
                resultados['ordenes_prod'] = tenant_query(OrdenProduccion).join(Producto).filter(
                    db.or_(Producto.nombre.ilike(like),
                           db.cast(OrdenProduccion.id, db.String).ilike(like))
                ).limit(20).all()
            except Exception: resultados['ordenes_prod'] = []
            try:
                resultados['ordenes_compra'] = tenant_query(OrdenCompra).filter(
                    OrdenCompra.numero.ilike(like)
                ).limit(20).all()
            except Exception: resultados['ordenes_compra'] = []
        return render_template('buscador.html', q=q, resultados=resultados)