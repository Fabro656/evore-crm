# routes/dashboard.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, secrets, logging

def register(app):

    # ── API: guardar/cargar workspace tabs del usuario
    @app.route('/api/workspace/tabs', methods=['GET', 'POST'])
    @login_required
    def api_workspace_tabs():
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            tabs = data.get('tabs', [])
            current_user.workspace_tabs = json.dumps(tabs)
            db.session.commit()
            return jsonify({'ok': True})
        # GET
        try:
            tabs = json.loads(current_user.workspace_tabs or '[]')
        except Exception:
            tabs = []
        return jsonify({'tabs': tabs})


    # ── dashboard (/)
    @app.route('/')
    @login_required
    def dashboard():
        from datetime import date
        hoy = date.today()
        mes_inicio = hoy.replace(day=1)
        try:
            ingresos = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['completado','pagado'])).scalar() or 0
            gastos_tot = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
            gastos_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha >= mes_inicio).scalar() or 0
            compras_tot = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
            saldo_pend = db.session.query(db.func.sum(Venta.saldo)).filter(Venta.estado.in_(['anticipo_pagado','negociacion'])).scalar() or 0
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
            prods_bajo = Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).all()
            for pb in prods_bajo[:5]:  # max 5 alertas
                titulo_alerta = f'Stock bajo: {pb.nombre} ({pb.stock}/{pb.stock_minimo})'
                ya_existe = Tarea.query.filter(Tarea.titulo==titulo_alerta, Tarea.estado=='pendiente').first()
                if not ya_existe:
                    t = Tarea(titulo=titulo_alerta, descripcion=f'El producto {pb.nombre} tiene stock {pb.stock} por debajo del minimo {pb.stock_minimo}.',
                              estado='pendiente', prioridad='alta', tarea_tipo='alerta_stock', categoria='logistica',
                              creado_por=current_user.id, asignado_a=current_user.id)
                    db.session.add(t)
            if prods_bajo: db.session.commit()
        except Exception: pass

        # Notificaciones de stock bajo en el panel de campana
        try:
            _verificar_stock_minimo()
        except Exception: pass

        # Productos bajo mínimo para el banner detallado del dashboard
        try:
            alertas_stock = Producto.query.filter(
                Producto.activo == True,
                Producto.stock_minimo > 0,
                Producto.stock < Producto.stock_minimo
            ).order_by(Producto.nombre).all()
        except Exception:
            alertas_stock = []

        return render_template('dashboard.html',
            total_clientes       = Cliente.query.filter_by(estado='activo').count(),
            ventas_completadas       = Venta.query.filter_by(estado='completado').count(),
            tareas_pendientes    = Tarea.query.filter(Tarea.estado != 'completada').count(),
            ingresos_totales     = ingresos,
            gastos_totales       = gastos_tot,
            compras_totales      = compras_tot,
            balance              = ingresos - total_egresos_global,
            impuestos_estimados  = impuestos_estimados,
            saldo_neto           = saldo_neto,
            saldo_pendiente      = saldo_pend,
            productos_bajo_stock = Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).count(),
            alertas_stock        = alertas_stock,
            tareas_recientes     = Tarea.query.filter(Tarea.estado!='completada').order_by(Tarea.creado_en.desc()).limit(5).all(),
            ventas_recientes     = Venta.query.order_by(Venta.creado_en.desc()).limit(6).all(),
            actividades_recientes= Actividad.query.order_by(Actividad.creado_en.desc()).limit(8).all(),
            aprobaciones_pendientes = Aprobacion.query.filter_by(estado='pendiente').order_by(Aprobacion.creado_en.desc()).limit(5).all() if current_user.rol in ('admin','director_financiero','director_operativo') else [],
            notas_recientes      = Nota.query.order_by(Nota.actualizado_en.desc()).limit(4).all(),
            eventos_hoy          = Evento.query.filter(Evento.fecha==hoy).order_by(Evento.hora_inicio).all(),
            eventos_proximos     = Evento.query.filter(Evento.fecha>hoy, Evento.fecha<=hoy+timedelta(days=7)).order_by(Evento.fecha).limit(5).all(),
        )
    

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
        if uid != current_user.id and current_user.rol != 'admin':
            uid = current_user.id
        target_user = db.session.get(User, uid) if uid != current_user.id else current_user
        usuarios_lista = User.query.filter_by(activo=True).all() if current_user.rol == 'admin' else []
    
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
            tareas_hechas = Tarea.query.filter(
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
            ).count() if current_user.rol in ['admin','vendedor','sales_manager'] else 0
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
        ingresos_totales = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['completado','anticipo_pagado'])).scalar() or 0
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
    

    # ── exportar_ventas (/reportes/exportar/ventas.xlsx)
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
    

    # ── exportar_gastos (/reportes/exportar/gastos.xlsx)
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
    

    # ── exportar_inventario (/reportes/exportar/inventario.xlsx)
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
    

    # ── exportar_clientes (/reportes/exportar/clientes.xlsx)
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
            for t in Tarea.query.filter(Tarea.fecha_vencimiento != None).all():
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
            for v in Venta.query.filter(Venta.fecha_entrega_est != None).all():
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
            for e in Evento.query.all():
                k = e.fecha.strftime('%Y-%m-%d')
                desc = (e.descripcion[:80] if e.descripcion else '') or (e.tipo or 'Evento')
                eventos.setdefault(k, []).append({'t':'evento','n':e.titulo,'s':e.tipo,'d':desc,'url':'','tid':e.id})
        except Exception as _e:
            logging.warning(f'Calendario: eventos error: {_e}'); db.session.rollback()
        # 4. Notas con fecha de revisión (columna nueva en v11)
        try:
            for n in Nota.query.filter(Nota.fecha_revision != None).all():
                k = n.fecha_revision.strftime('%Y-%m-%d')
                desc = (n.contenido[:80] if n.contenido else '') or 'Revisión programada'
                eventos.setdefault(k, []).append({'t':'nota','n':n.titulo or '(nota sin título)','s':'revision',
                    'd':desc,'url':url_for('notas'),'tid':n.id})
        except Exception as _e:
            logging.warning(f'Calendario: notas error: {_e}'); db.session.rollback()
        # 5. Productos con fecha de caducidad (columna nueva en v11)
        try:
            for p in Producto.query.filter(Producto.fecha_caducidad != None, Producto.activo == True).all():
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
            dup = Evento.query.filter_by(
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
    def evento_eliminar(id):
        obj = Evento.query.get_or_404(id)
        db.session.delete(obj); db.session.commit()
        flash('Evento eliminado.','info')
        return redirect(url_for('calendario'))
    

    # ── actividad (/actividad)
    @app.route('/actividad')
    @login_required
    def actividad():
        if current_user.rol != 'admin':
            items = Actividad.query.filter_by(usuario_id=current_user.id).order_by(Actividad.creado_en.desc()).limit(150).all()
        else:
            items = Actividad.query.order_by(Actividad.creado_en.desc()).limit(300).all()
        return render_template('actividad.html', items=items)
    

    # ── notificaciones (/notificaciones)
    @app.route('/notificaciones')
    @login_required
    def notificaciones():
        items = Notificacion.query.filter_by(usuario_id=current_user.id)\
                    .order_by(Notificacion.creado_en.desc()).limit(100).all()
        # marcar todas como leídas al abrir
        Notificacion.query.filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
        db.session.commit()
        return render_template('notificaciones.html', items=items)
    

    # ── notificaciones_recientes (/notificaciones/recientes)
    @app.route('/notificaciones/recientes')
    @login_required
    def notificaciones_recientes():
        items = Notificacion.query.filter_by(usuario_id=current_user.id, leida=False)\
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
        Notificacion.query.filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
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

    # ── contable_ingresos (/contable/ingresos)
    @app.route('/contable/ingresos')
    @login_required
    def contable_ingresos():
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        q = Venta.query.filter(Venta.estado.in_(['anticipo_pagado','completado','prospecto','negociacion','perdido']))
        if desde_s:
            try: q = q.filter(db.func.date(Venta.creado_en) >= datetime.strptime(desde_s,'%Y-%m-%d').date())
            except: pass
        if hasta_s:
            try: q = q.filter(db.func.date(Venta.creado_en) <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
            except: pass
        items = q.order_by(Venta.creado_en.desc()).all()
        return render_template('contable/ingresos.html', items=items, desde_s=desde_s, hasta_s=hasta_s)
    

    # ── contable_egresos (/contable/egresos)
    @app.route('/contable/egresos')
    @login_required
    def contable_egresos():
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        gastos = GastoOperativo.query
        compras = CompraMateria.query
        if desde_s:
            try:
                d = datetime.strptime(desde_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha >= d)
                compras = compras.filter(CompraMateria.fecha >= d)
            except: pass
        if hasta_s:
            try:
                h = datetime.strptime(hasta_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha <= h)
                compras = compras.filter(CompraMateria.fecha <= h)
            except: pass
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
            ultimo = AsientoContable.query.filter(
                AsientoContable.numero.like(f'AC-{hoy.year}-%')
            ).order_by(AsientoContable.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            a.numero = f'AC-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Asiento {a.numero} registrado.','success')
            return redirect(url_for('contable_libro_diario'))
        asientos = AsientoContable.query.order_by(AsientoContable.fecha.desc(), AsientoContable.id.desc()).limit(100).all()
        return render_template('contable/libro_diario.html', asientos=asientos)
    

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
            q = Venta.query
            if desde_s:
                try: q = q.filter(db.func.date(Venta.creado_en) >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(db.func.date(Venta.creado_en) <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for v in q.order_by(Venta.creado_en).all():
                writer.writerow([v.numero or '', v.titulo,
                    v.cliente.empresa or v.cliente.nombre if v.cliente else '',
                    v.creado_en.strftime('%Y-%m-%d'), v.estado,
                    v.subtotal, v.iva, v.total, v.monto_anticipo, v.saldo])
        elif tipo == 'gastos':
            writer.writerow(['Fecha','Tipo','Descripcion','Monto','Recurrencia'])
            q = GastoOperativo.query
            if desde_s:
                try: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for g in q.order_by(GastoOperativo.fecha).all():
                writer.writerow([g.fecha.strftime('%Y-%m-%d'), g.tipo, g.descripcion or '', g.monto, g.recurrencia])
        elif tipo == 'compras':
            writer.writerow(['Fecha','Item','Proveedor','Cantidad','Unidad','Costo Total','Factura'])
            q = CompraMateria.query
            if desde_s:
                try: q = q.filter(CompraMateria.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(CompraMateria.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for c in q.order_by(CompraMateria.fecha).all():
                writer.writerow([c.fecha.strftime('%Y-%m-%d'), c.nombre_item, c.proveedor or '',
                    c.cantidad, c.unidad, c.costo_total, c.nro_factura or ''])
        elif tipo == 'asientos':
            writer.writerow(['Numero','Fecha','Descripcion','Tipo','Referencia','Debe','Haber','Cuenta Debe','Cuenta Haber'])
            for a in AsientoContable.query.order_by(AsientoContable.fecha).all():
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
                resultados['clientes'] = Cliente.query.filter(
                    db.or_(Cliente.nombre.ilike(like), Cliente.empresa.ilike(like), Cliente.nit.ilike(like))
                ).limit(20).all()
            except: resultados['clientes'] = []
            try:
                resultados['proveedores'] = Proveedor.query.filter(
                    db.or_(Proveedor.nombre.ilike(like), Proveedor.empresa.ilike(like), Proveedor.nit.ilike(like))
                ).limit(20).all()
            except: resultados['proveedores'] = []
            try:
                resultados['productos'] = Producto.query.filter(
                    db.or_(Producto.nombre.ilike(like), Producto.sku.ilike(like), Producto.nso.ilike(like))
                ).filter_by(activo=True).limit(20).all()
            except: resultados['productos'] = []
            try:
                resultados['ventas'] = Venta.query.filter(
                    db.or_(Venta.titulo.ilike(like), Venta.numero.ilike(like))
                ).limit(20).all()
            except: resultados['ventas'] = []
            try:
                resultados['ordenes_prod'] = OrdenProduccion.query.join(Producto).filter(
                    db.or_(Producto.nombre.ilike(like),
                           db.cast(OrdenProduccion.id, db.String).ilike(like))
                ).limit(20).all()
            except: resultados['ordenes_prod'] = []
            try:
                resultados['ordenes_compra'] = OrdenCompra.query.filter(
                    OrdenCompra.numero.ilike(like)
                ).limit(20).all()
            except: resultados['ordenes_compra'] = []
        return render_template('buscador.html', q=q, resultados=resultados)