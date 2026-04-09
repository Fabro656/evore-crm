# routes/dashboard.py
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
    @app.route('/')
    @login_required
    def dashboard():
        from datetime import date
        hoy = date.today()
        mes_inicio = hoy.replace(day=1)
        ingresos = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['completado','anticipo_pagado'])).scalar() or 0
        gastos_tot = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
        gastos_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha >= mes_inicio).scalar() or 0
        compras_tot = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
        saldo_pend = db.session.query(db.func.sum(Venta.saldo)).filter(Venta.estado.in_(['anticipo_pagado','negociacion'])).scalar() or 0
        # Impuestos estimados globales (acumulado total, no solo mes)
        total_egresos_global = gastos_tot + compras_tot
        utilidad_global = ingresos - total_egresos_global
        impuestos_estimados, detalle_imp_dash = _calcular_impuestos(ingresos, utilidad_global)
        saldo_neto = ingresos - total_egresos_global - impuestos_estimados
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
            tareas_recientes     = Tarea.query.filter(Tarea.estado!='completada').order_by(Tarea.creado_en.desc()).limit(5).all(),
            ventas_recientes     = Venta.query.order_by(Venta.creado_en.desc()).limit(6).all(),
            actividades_recientes= Actividad.query.order_by(Actividad.creado_en.desc()).limit(8).all(),
        )

    @app.route('/actividad')
    @login_required
    def actividad():
        if current_user.rol != 'admin':
            items = Actividad.query.filter_by(user_id=current_user.id).order_by(Actividad.creado_en.desc()).limit(150).all()
        else:
            items = Actividad.query.order_by(Actividad.creado_en.desc()).limit(300).all()
        return render_template('actividad.html', items=items)

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
                    except Exception: pass
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
        except Exception: db.session.rollback()
        # 2. Ventas con fecha entrega estimada
        try:
            for v in Venta.query.filter(Venta.fecha_entrega_est != None).all():
                k = v.fecha_entrega_est.strftime('%Y-%m-%d')
                cliente_nom = ''
                try:
                    if v.cliente: cliente_nom = v.cliente.empresa or v.cliente.nombre or ''
                except Exception: pass
                desc = ('Cliente: ' + cliente_nom + ' · ' if cliente_nom else '') + 'Estado: ' + v.estado
                if v.numero: desc = 'Venta ' + v.numero + ' · ' + desc
                eventos.setdefault(k, []).append({'t':'venta','n':v.titulo,'s':v.estado,
                    'd':desc,'url':url_for('venta_editar', id=v.id),'tid':v.id})
        except Exception: db.session.rollback()
        # 3. Eventos manuales
        try:
            for e in Evento.query.all():
                k = e.fecha.strftime('%Y-%m-%d')
                desc = (e.descripcion[:80] if e.descripcion else '') or (e.tipo or 'Evento')
                eventos.setdefault(k, []).append({'t':'evento','n':e.titulo,'s':e.tipo,'d':desc,'url':'','tid':e.id})
        except Exception: db.session.rollback()
        # 4. Notas con fecha de revisión (columna nueva en v11)
        try:
            for n in Nota.query.filter(Nota.fecha_revision != None).all():
                k = n.fecha_revision.strftime('%Y-%m-%d')
                desc = (n.contenido[:80] if n.contenido else '') or 'Revisión programada'
                eventos.setdefault(k, []).append({'t':'nota','n':n.titulo or '(nota sin título)','s':'revision',
                    'd':desc,'url':url_for('notas'),'tid':n.id})
        except Exception: db.session.rollback()
        # 5. Productos con fecha de caducidad (columna nueva en v11)
        try:
            for p in Producto.query.filter(Producto.fecha_caducidad != None, Producto.activo == True).all():
                k = p.fecha_caducidad.strftime('%Y-%m-%d')
                desc_p = []
                if p.sku: desc_p.append('SKU: ' + p.sku)
                if p.stock_disponible is not None: desc_p.append('Stock: ' + str(int(p.stock_disponible)))
                eventos.setdefault(k, []).append({'t':'caducidad','n':p.nombre,'s':'caducidad',
                    'd':' · '.join(desc_p) or 'Próximo a caducar','url':url_for('inventario'),'tid':p.id})
        except Exception: db.session.rollback()
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

    @app.route('/notificaciones')
    @login_required
    def notificaciones():
        items = Notificacion.query.filter_by(usuario_id=current_user.id)\
                    .order_by(Notificacion.creado_en.desc()).limit(100).all()
        # marcar todas como leídas al abrir
        Notificacion.query.filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
        db.session.commit()
        return render_template('notificaciones.html', items=items)

    @app.route('/notificaciones/<int:id>/leida', methods=['POST'])
    @login_required
    def notificacion_leida(id):
        n = Notificacion.query.get_or_404(id)
        if n.usuario_id == current_user.id:
            n.leida = True
            db.session.commit()
        return ('', 204)

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

    @app.route('/notificaciones/marcar_todas', methods=['POST'])
    @login_required
    def notificaciones_marcar_todas():
        Notificacion.query.filter_by(usuario_id=current_user.id, leida=False).update({'leida': True})
        db.session.commit()
        flash('Todas las notificaciones marcadas como leídas.', 'success')
        return redirect(url_for('notificaciones'))

    @app.route('/eventos/nuevo', methods=['GET','POST'])
    @login_required
    def evento_nuevo():
        if request.method == 'POST':
            fd = request.form.get('fecha')
            ev = Evento(
                titulo=request.form['titulo'],
                tipo=request.form.get('tipo','recordatorio'),
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                hora_inicio=request.form.get('hora_inicio','') or None,
                hora_fin=request.form.get('hora_fin','') or None,
                descripcion=request.form.get('descripcion',''),
                usuario_id=current_user.id)
            db.session.add(ev); db.session.commit()
            flash('Evento creado.','success')
            return redirect(url_for('calendario'))
        return redirect(url_for('calendario'))

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

    @app.route('/eventos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def evento_eliminar(id):
        obj = Evento.query.get_or_404(id)
        db.session.delete(obj); db.session.commit()
        flash('Evento eliminado.','info')
        return redirect(url_for('calendario'))
