# routes/proyectos.py — Gestion de Proyectos (Jira/Notion style)
from flask import render_template, redirect, url_for, flash, request, jsonify, g, session
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, date as date_type
from sqlalchemy import func
import json, logging

_ESTADOS_PROYECTO = ['planificacion', 'pendiente_aprobacion', 'desarrollo', 'pausado', 'completado', 'cancelado']
_ESTADOS_TAREA = ['por_hacer', 'en_progreso', 'en_revision', 'completada']
_TIPOS_TAREA = ['tarea', 'compra', 'legal', 'finanzas', 'produccion', 'logistica']

def _requiere_proyecto_access():
    """Check user has project management access."""
    rol = _get_rol_activo(current_user)
    return rol in ('admin', 'director_financiero', 'director_operativo')

def register(app):

    def _gen_codigo():
        last = Proyecto.query.filter_by(company_id=getattr(g, 'company_id', None)) \
            .order_by(Proyecto.id.desc()).first()
        num = (last.id + 1) if last else 1
        return f'PRY-{num:03d}'

    # ══════════════════════════════════════════════════════════════
    # PROYECTOS — CRUD + DASHBOARD
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos')
    @login_required
    def proyectos_index():
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('dashboard'))
        cid = getattr(g, 'company_id', None)
        estado_f = request.args.get('estado', '')
        buscar = request.args.get('buscar', '').strip()
        q = Proyecto.query.filter_by(company_id=cid)
        if estado_f:
            q = q.filter_by(estado=estado_f)
        if buscar:
            q = q.filter(db.or_(
                Proyecto.nombre.ilike(f'%{buscar}%'),
                Proyecto.codigo.ilike(f'%{buscar}%')
            ))
        proyectos = q.order_by(Proyecto.creado_en.desc()).all()
        # Stats
        stats = {}
        for p in proyectos:
            total_t = ProyectoTarea.query.filter_by(proyecto_id=p.id).count()
            done_t = ProyectoTarea.query.filter_by(proyecto_id=p.id, estado='completada').count()
            total_gasto = db.session.query(func.sum(GastoOperativo.monto)).join(
                ProyectoGasto, ProyectoGasto.gasto_id == GastoOperativo.id
            ).filter(ProyectoGasto.proyecto_id == p.id).scalar() or 0
            stats[p.id] = {
                'tareas': total_t, 'completadas': done_t,
                'pct': round(done_t / total_t * 100) if total_t else 0,
                'gasto_total': total_gasto
            }
        # Dashboard totals (all projects, not just filtered)
        all_proys = Proyecto.query.filter_by(company_id=cid).all()
        dash = {
            'total': len(all_proys),
            'planificacion': len([p for p in all_proys if p.estado == 'planificacion']),
            'pendiente_aprobacion': len([p for p in all_proys if p.estado == 'pendiente_aprobacion']),
            'desarrollo': len([p for p in all_proys if p.estado == 'desarrollo']),
            'pausado': len([p for p in all_proys if p.estado == 'pausado']),
            'completado': len([p for p in all_proys if p.estado == 'completado']),
            'cancelado': len([p for p in all_proys if p.estado == 'cancelado']),
            'presupuesto_total': sum(p.presupuesto or 0 for p in all_proys),
            'presupuesto_desarrollo': sum(p.presupuesto or 0 for p in all_proys if p.estado == 'desarrollo'),
            'activos': len([p for p in all_proys if p.estado in ('planificacion', 'pendiente_aprobacion', 'desarrollo')]),
        }
        return render_template('proyectos/index.html',
            proyectos=proyectos, stats=stats, dash=dash, estado_f=estado_f, buscar=buscar,
            estados=_ESTADOS_PROYECTO)

    @app.route('/proyectos/nuevo', methods=['GET', 'POST'])
    @login_required
    def proyecto_nuevo():
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        if request.method == 'POST':
            fi = request.form.get('fecha_inicio')
            ff = request.form.get('fecha_fin')
            p = Proyecto(
                company_id=getattr(g, 'company_id', None),
                codigo=_gen_codigo(),
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion', ''),
                prioridad=request.form.get('prioridad', 'media'),
                color=request.form.get('color', '#0176D3'),
                fecha_inicio=datetime.strptime(fi, '%Y-%m-%d').date() if fi else date_type.today(),
                fecha_fin=datetime.strptime(ff, '%Y-%m-%d').date() if ff else None,
                presupuesto=float(request.form.get('presupuesto') or 0),
                responsable_id=int(request.form.get('responsable_id')) if request.form.get('responsable_id') else current_user.id,
                cliente_id=int(request.form.get('cliente_id')) if request.form.get('cliente_id') else None,
                creado_por=current_user.id
            )
            db.session.add(p)
            db.session.flush()
            # Create default phases
            for i, fase_nombre in enumerate(['Planificacion', 'Ejecucion', 'Cierre'], 1):
                db.session.add(ProyectoFase(
                    proyecto_id=p.id, nombre=fase_nombre, orden=i
                ))
            _log('crear', 'proyecto', p.id, f'Proyecto creado: {p.nombre}')
            db.session.commit()
            flash(f'Proyecto {p.codigo} creado.', 'success')
            return redirect(url_for('proyecto_ver', id=p.id))
        usuarios = User.query.filter_by(company_id=getattr(g, 'company_id', None), activo=True).order_by(User.nombre).all()
        clientes = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa).all()
        return render_template('proyectos/form.html', obj=None, titulo='Nuevo Proyecto',
                               usuarios=usuarios, clientes=clientes)

    @app.route('/proyectos/<int:id>')
    @login_required
    def proyecto_ver(id):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(id)
        vista = request.args.get('vista', 'fases')
        # All tasks grouped by estado for kanban
        tareas_por_estado = {}
        for est in _ESTADOS_TAREA:
            tareas_por_estado[est] = ProyectoTarea.query.filter_by(
                proyecto_id=p.id, estado=est
            ).order_by(ProyectoTarea.orden, ProyectoTarea.prioridad.desc()).all()
        # Gastos
        gastos_q = db.session.query(ProyectoGasto, GastoOperativo).join(
            GastoOperativo, ProyectoGasto.gasto_id == GastoOperativo.id
        ).filter(ProyectoGasto.proyecto_id == p.id).all()
        gasto_total = sum(g_op.monto for _, g_op in gastos_q)
        # Gastos por fase
        gastos_por_fase = {}
        for pg, go in gastos_q:
            fid = pg.fase_id or 0
            gastos_por_fase.setdefault(fid, {'lista': [], 'total': 0})
            gastos_por_fase[fid]['lista'].append((pg, go))
            gastos_por_fase[fid]['total'] += go.monto
        # Stats
        total_t = sum(len(v) for v in tareas_por_estado.values())
        done_t = len(tareas_por_estado.get('completada', []))
        pct = round(done_t / total_t * 100) if total_t else 0
        usuarios = User.query.filter_by(company_id=getattr(g, 'company_id', None), activo=True).order_by(User.nombre).all()
        proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all()
        cotizaciones_prov = CotizacionProveedor.query.filter(
            CotizacionProveedor.estado.in_(['vigente', 'en_revision'])
        ).order_by(CotizacionProveedor.nombre_producto).all()
        # Solicitudes de pago por fase y por objetivo
        solicitudes_por_fase = {}
        solicitudes_por_objetivo = {}
        if p.estado == 'desarrollo':
            for sp in ProyectoSolicitudPago.query.filter_by(proyecto_id=p.id).order_by(ProyectoSolicitudPago.creado_en.desc()).all():
                solicitudes_por_fase.setdefault(sp.fase_id, []).append(sp)
                if sp.objetivo_id:
                    solicitudes_por_objetivo.setdefault(sp.objetivo_id, []).append(sp)
        # Gasto real por objetivo
        gasto_por_objetivo = {}
        for sp_list in solicitudes_por_objetivo.values():
            for sp in sp_list:
                if sp.estado == 'pagada':
                    gasto_por_objetivo[sp.objetivo_id] = gasto_por_objetivo.get(sp.objetivo_id, 0) + sp.monto
        return render_template('proyectos/ver.html', p=p, vista=vista,
            tareas_por_estado=tareas_por_estado, estados=_ESTADOS_TAREA,
            tipos=_TIPOS_TAREA, gastos=gastos_q, gasto_total=gasto_total,
            gastos_por_fase=gastos_por_fase, solicitudes_por_fase=solicitudes_por_fase,
            solicitudes_por_objetivo=solicitudes_por_objetivo,
            gasto_por_objetivo=gasto_por_objetivo,
            total_t=total_t, done_t=done_t, pct=pct, usuarios=usuarios,
            proveedores=proveedores, cotizaciones_prov=cotizaciones_prov)

    @app.route('/proyectos/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    def proyecto_editar(id):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(id)
        if request.method == 'POST':
            p.nombre = request.form['nombre']
            p.descripcion = request.form.get('descripcion', '')
            p.estado = request.form.get('estado', p.estado)
            p.prioridad = request.form.get('prioridad', p.prioridad)
            p.color = request.form.get('color', p.color)
            fi = request.form.get('fecha_inicio')
            ff = request.form.get('fecha_fin')
            p.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else p.fecha_inicio
            p.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else p.fecha_fin
            p.presupuesto = float(request.form.get('presupuesto') or 0)
            p.responsable_id = int(request.form.get('responsable_id')) if request.form.get('responsable_id') else p.responsable_id
            p.cliente_id = int(request.form.get('cliente_id')) if request.form.get('cliente_id') else None
            db.session.commit()
            flash('Proyecto actualizado.', 'success')
            return redirect(url_for('proyecto_ver', id=p.id))
        usuarios = User.query.filter_by(company_id=getattr(g, 'company_id', None), activo=True).order_by(User.nombre).all()
        clientes = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa).all()
        return render_template('proyectos/form.html', obj=p, titulo='Editar Proyecto',
                               usuarios=usuarios, clientes=clientes, estados=_ESTADOS_PROYECTO)

    # ══════════════════════════════════════════════════════════════
    # FASES
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/fases/nueva', methods=['POST'])
    @login_required
    def proyecto_fase_nueva(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        nuevo_ppto = float(request.form.get('presupuesto') or 0)
        # Validate budget doesn't exceed project total
        asignado_fases = sum(f.presupuesto or 0 for f in p.fases)
        disponible = (p.presupuesto or 0) - asignado_fases
        if nuevo_ppto > disponible and p.presupuesto > 0:
            flash(f'Presupuesto de fase (${nuevo_ppto:,.0f}) excede lo disponible (${disponible:,.0f} de ${p.presupuesto:,.0f}).', 'danger')
            return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
        max_orden = db.session.query(func.max(ProyectoFase.orden)).filter_by(proyecto_id=pid).scalar() or 0
        fi = request.form.get('fecha_inicio')
        ff = request.form.get('fecha_fin')
        f = ProyectoFase(
            proyecto_id=pid,
            nombre=request.form.get('nombre', 'Nueva fase'),
            descripcion=request.form.get('descripcion', ''),
            color=request.form.get('color', '#6B7280'),
            fecha_inicio=datetime.strptime(fi, '%Y-%m-%d').date() if fi else None,
            fecha_fin=datetime.strptime(ff, '%Y-%m-%d').date() if ff else None,
            presupuesto=nuevo_ppto,
            orden=max_orden + 1
        )
        db.session.add(f)
        db.session.flush()
        # Assign members
        user_ids = request.form.getlist('miembros[]')
        for uid in user_ids:
            if uid:
                db.session.add(ProyectoMiembro(proyecto_id=pid, fase_id=f.id, user_id=int(uid)))
        db.session.commit()
        flash(f'Fase "{f.nombre}" creada.', 'success')
        return redirect(url_for('proyecto_ver', id=pid))

    @app.route('/proyectos/fases/<int:fid>/editar', methods=['POST'])
    @login_required
    def proyecto_fase_editar(fid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        f = ProyectoFase.query.get_or_404(fid)
        p = Proyecto.query.get_or_404(f.proyecto_id)
        nuevo_ppto = float(request.form.get('presupuesto') or 0)
        # Validate budget: exclude current phase from sum
        asignado_otras = sum(fa.presupuesto or 0 for fa in p.fases if fa.id != fid)
        disponible = (p.presupuesto or 0) - asignado_otras
        if nuevo_ppto > disponible and p.presupuesto > 0:
            flash(f'Presupuesto (${nuevo_ppto:,.0f}) excede lo disponible (${disponible:,.0f}).', 'danger')
            return redirect(url_for('proyecto_ver', id=p.id, vista='fases'))
        f.nombre = request.form.get('nombre', f.nombre)
        f.descripcion = request.form.get('descripcion', '')
        f.estado = request.form.get('estado', f.estado)
        f.color = request.form.get('color', f.color)
        fi = request.form.get('fecha_inicio')
        ff = request.form.get('fecha_fin')
        f.fecha_inicio = datetime.strptime(fi, '%Y-%m-%d').date() if fi else f.fecha_inicio
        f.fecha_fin = datetime.strptime(ff, '%Y-%m-%d').date() if ff else f.fecha_fin
        f.presupuesto = nuevo_ppto
        # Update members
        ProyectoMiembro.query.filter_by(fase_id=fid).delete()
        user_ids = request.form.getlist('miembros[]')
        for uid in user_ids:
            if uid:
                db.session.add(ProyectoMiembro(proyecto_id=f.proyecto_id, fase_id=fid, user_id=int(uid)))
        db.session.commit()
        flash(f'Fase "{f.nombre}" actualizada.', 'success')
        return redirect(url_for('proyecto_ver', id=f.proyecto_id))

    @app.route('/proyectos/fases/<int:fid>/eliminar', methods=['POST'])
    @login_required
    def proyecto_fase_eliminar(fid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        f = ProyectoFase.query.get_or_404(fid)
        pid = f.proyecto_id
        db.session.delete(f)
        db.session.commit()
        flash('Fase eliminada.', 'info')
        return redirect(url_for('proyecto_ver', id=pid))

    # ── Calendario del proyecto ──
    @app.route('/proyectos/<int:id>/calendario')
    @login_required
    def proyecto_calendario(id):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(id)
        # Build calendar events from phases + tasks
        eventos = []
        for f in p.fases:
            if f.fecha_inicio:
                eventos.append({
                    'titulo': f'Fase: {f.nombre}',
                    'inicio': f.fecha_inicio.isoformat(),
                    'fin': f.fecha_fin.isoformat() if f.fecha_fin else f.fecha_inicio.isoformat(),
                    'color': f.color or '#6B7280',
                    'tipo': 'fase',
                    'id': f.id
                })
            for t in f.tareas:
                if t.fecha_inicio or t.fecha_limite:
                    eventos.append({
                        'titulo': t.titulo,
                        'inicio': (t.fecha_inicio or t.fecha_limite).isoformat(),
                        'fin': (t.fecha_limite or t.fecha_inicio).isoformat(),
                        'color': '#3B82F6' if t.estado != 'completada' else '#10B981',
                        'tipo': 'tarea',
                        'id': t.id,
                        'estado': t.estado
                    })
        # Also tasks without phase
        for t in ProyectoTarea.query.filter_by(proyecto_id=p.id, fase_id=None).all():
            if t.fecha_inicio or t.fecha_limite:
                eventos.append({
                    'titulo': t.titulo,
                    'inicio': (t.fecha_inicio or t.fecha_limite).isoformat(),
                    'fin': (t.fecha_limite or t.fecha_inicio).isoformat(),
                    'color': '#F59E0B',
                    'tipo': 'tarea',
                    'id': t.id,
                    'estado': t.estado
                })
        return render_template('proyectos/calendario.html', p=p, eventos_json=json.dumps(eventos))

    # ══════════════════════════════════════════════════════════════
    # TAREAS DE PROYECTO
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/tareas/nueva', methods=['POST'])
    @login_required
    def proyecto_tarea_nueva(pid):
        if not _requiere_proyecto_access():
            return jsonify({'error': 'Acceso denegado'}), 403
        p = Proyecto.query.get_or_404(pid)
        cid = getattr(g, 'company_id', None)
        fase_id = int(request.form.get('fase_id')) if request.form.get('fase_id') else None
        fl = request.form.get('fecha_limite')
        t = ProyectoTarea(
            company_id=cid, proyecto_id=pid, fase_id=fase_id,
            titulo=request.form['titulo'],
            descripcion=request.form.get('descripcion', ''),
            tipo=request.form.get('tipo', 'tarea'),
            prioridad=request.form.get('prioridad', 'media'),
            responsable_id=int(request.form.get('responsable_id')) if request.form.get('responsable_id') else None,
            fecha_limite=datetime.strptime(fl, '%Y-%m-%d').date() if fl else None,
            estimacion_hrs=float(request.form.get('estimacion_hrs') or 0),
            creado_por=current_user.id
        )
        db.session.add(t)
        db.session.flush()

        # ── Auto-crear entidades vinculadas segun tipo ──
        tipo = t.tipo
        try:
            if tipo == 'compra':
                # Crear OC borrador vinculada
                oc = OrdenCompra(company_id=cid, estado='borrador', total=0, creado_por=current_user.id,
                                  notas=f'Generada desde proyecto {p.codigo}: {t.titulo}')
                db.session.add(oc); db.session.flush()
                t.orden_compra_id = oc.id
            elif tipo == 'legal':
                doc = DocumentoLegal(company_id=cid, tipo='contrato', titulo=t.titulo,
                                      estado='borrador', creado_por=current_user.id,
                                      notas=f'Generado desde proyecto {p.codigo}')
                db.session.add(doc); db.session.flush()
                t.documento_legal_id = doc.id
            elif tipo == 'finanzas':
                gasto = GastoOperativo(company_id=cid, tipo='proyecto', descripcion=t.titulo,
                                        monto=0, fecha=date_type.today(), creado_por=current_user.id,
                                        notas=f'Proyecto {p.codigo}')
                db.session.add(gasto); db.session.flush()
                t.gasto_id = gasto.id
                db.session.add(ProyectoGasto(proyecto_id=pid, gasto_id=gasto.id, descripcion=t.titulo))
            elif tipo == 'produccion':
                pass  # User links existing orden_produccion manually
        except Exception as ex:
            logging.warning(f'proyecto_tarea_nueva auto-create {tipo}: {ex}')

        # Create a regular Ticket linked to this project task
        try:
            ticket = Tarea(company_id=cid, titulo=f'[{p.codigo}] {t.titulo}',
                           descripcion=f'Tarea de proyecto: {t.descripcion or t.titulo}\nProyecto: {p.nombre}',
                           estado='pendiente', prioridad=t.prioridad,
                           asignado_a=t.responsable_id, creado_por=current_user.id,
                           tarea_tipo='proyecto', categoria=tipo)
            db.session.add(ticket); db.session.flush()
            t.tarea_id = ticket.id
        except Exception as ex:
            logging.warning(f'proyecto_tarea ticket: {ex}')

        _log('crear', 'proyecto_tarea', t.id, f'Tarea de proyecto: {t.titulo} [{tipo}]')
        db.session.commit()
        flash(f'Tarea creada: {t.titulo}', 'success')
        return redirect(url_for('proyecto_ver', id=pid))

    @app.route('/api/proyectos/tareas/<int:tid>/estado', methods=['POST'])
    @login_required
    def api_proyecto_tarea_estado(tid):
        """Kanban drag: update task state via AJAX."""
        t = ProyectoTarea.query.get_or_404(tid)
        nuevo = request.json.get('estado')
        if nuevo not in _ESTADOS_TAREA:
            return jsonify({'error': 'Estado invalido'}), 400
        t.estado = nuevo
        if nuevo == 'completada':
            t.completado_en = datetime.utcnow()
            t.progreso = 100
            # Also complete the linked ticket
            if t.tarea_id:
                ticket = db.session.get(Tarea, t.tarea_id)
                if ticket:
                    ticket.estado = 'completada'
        elif nuevo == 'por_hacer':
            t.progreso = 0
            t.completado_en = None
        db.session.commit()
        return jsonify({'ok': True, 'estado': nuevo})

    @app.route('/api/proyectos/<int:pid>/estado', methods=['POST'])
    @login_required
    def api_proyecto_estado(pid):
        """Quick status change from index cards."""
        if not _requiere_proyecto_access():
            return jsonify({'error': 'Acceso denegado'}), 403
        p = Proyecto.query.get_or_404(pid)
        nuevo = request.json.get('estado')
        # Only allow certain direct transitions (not approval flow)
        permitidos = ['planificacion', 'desarrollo', 'pausado', 'completado', 'cancelado']
        if nuevo not in permitidos:
            return jsonify({'error': 'Estado invalido'}), 400
        # Block direct jump to desarrollo if not approved
        if nuevo == 'desarrollo' and p.estado not in ('pendiente_aprobacion', 'desarrollo', 'pausado'):
            return jsonify({'error': 'Debe pasar por aprobacion para entrar a desarrollo'}), 400
        p.estado = nuevo
        _log('editar', 'proyecto', p.id, f'Estado cambiado a: {nuevo}')
        db.session.commit()
        return jsonify({'ok': True, 'estado': nuevo})

    @app.route('/proyectos/tareas/<int:tid>/comentar', methods=['POST'])
    @login_required
    def proyecto_tarea_comentar(tid):
        t = ProyectoTarea.query.get_or_404(tid)
        msg = request.form.get('mensaje', '').strip()
        if msg:
            db.session.add(ProyectoComentario(
                tarea_id=tid, autor_id=current_user.id, mensaje=msg
            ))
            db.session.commit()
        return redirect(url_for('proyecto_ver', id=t.proyecto_id))

    # ══════════════════════════════════════════════════════════════
    # GASTOS DE PROYECTO
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/gastos/nuevo', methods=['POST'])
    @login_required
    def proyecto_gasto_nuevo(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        cid = getattr(g, 'company_id', None)
        monto = float(request.form.get('monto') or 0)
        fase_id = int(request.form.get('fase_id')) if request.form.get('fase_id') else None
        desc = request.form.get('descripcion', '').strip() or f'Gasto proyecto {p.codigo}'
        fase_label = ''
        if fase_id:
            fase_obj = db.session.get(ProyectoFase, fase_id)
            if fase_obj:
                fase_label = f' [{fase_obj.nombre}]'
        gasto = GastoOperativo(
            company_id=cid, tipo='proyecto', tipo_custom=f'Proyecto {p.codigo}{fase_label}',
            descripcion=desc, monto=monto, fecha=date_type.today(),
            creado_por=current_user.id, notas=f'Vinculado a proyecto {p.codigo}{fase_label}'
        )
        db.session.add(gasto)
        db.session.flush()
        db.session.add(ProyectoGasto(proyecto_id=pid, fase_id=fase_id, gasto_id=gasto.id, descripcion=desc))
        _log('crear', 'gasto', gasto.id, f'Gasto de proyecto {p.codigo}: {desc} — ${monto:,.0f}')
        db.session.commit()
        flash(f'Gasto de ${monto:,.0f} registrado en proyecto y contabilidad.', 'success')
        return redirect(url_for('proyecto_ver', id=pid))

    @app.route('/proyectos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def proyecto_eliminar(id):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(id)
        nombre = p.nombre
        db.session.delete(p)
        db.session.commit()
        flash(f'Proyecto "{nombre}" eliminado.', 'info')
        return redirect(url_for('proyectos_index'))

    # ══════════════════════════════════════════════════════════════
    # PLAN DE GASTOS POR FASE
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/plan-gastos')
    @login_required
    def proyecto_plan_gastos(pid):
        """Vista del plan de gastos del proyecto — editable en planificacion."""
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        plan = {}
        total_plan = 0
        for f in p.fases:
            items = ProyectoPlanGasto.query.filter_by(proyecto_id=pid, fase_id=f.id).order_by(ProyectoPlanGasto.fecha_desde).all()
            subtotal = sum(pg.monto for pg in items)
            total_plan += subtotal
            plan[f.id] = {'fase': f, 'lista': items, 'subtotal': subtotal}
        editable = p.estado in ('planificacion',)
        return render_template('proyectos/plan_gastos.html', p=p, plan=plan,
            total_plan=total_plan, editable=editable)

    @app.route('/proyectos/<int:pid>/plan-gastos/agregar', methods=['POST'])
    @login_required
    def proyecto_plan_gasto_agregar(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        if p.estado != 'planificacion':
            flash('Solo se puede editar el plan en etapa de planificacion.', 'warning')
            return redirect(url_for('proyecto_plan_gastos', pid=pid))
        fd = request.form.get('fecha_desde')
        fh = request.form.get('fecha_hasta')
        db.session.add(ProyectoPlanGasto(
            proyecto_id=pid,
            fase_id=int(request.form['fase_id']),
            concepto=request.form['concepto'],
            monto=float(request.form.get('monto') or 0),
            fecha_desde=datetime.strptime(fd, '%Y-%m-%d').date() if fd else None,
            fecha_hasta=datetime.strptime(fh, '%Y-%m-%d').date() if fh else None,
            notas=request.form.get('notas', '')
        ))
        db.session.commit()
        flash('Gasto planificado agregado.', 'success')
        return redirect(url_for('proyecto_plan_gastos', pid=pid))

    @app.route('/proyectos/plan-gastos/<int:pgid>/eliminar', methods=['POST'])
    @login_required
    def proyecto_plan_gasto_eliminar(pgid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        pg = ProyectoPlanGasto.query.get_or_404(pgid)
        pid = pg.proyecto_id
        p = Proyecto.query.get_or_404(pid)
        if p.estado != 'planificacion':
            flash('No se puede modificar el plan fuera de planificacion.', 'warning')
            return redirect(url_for('proyecto_plan_gastos', pid=pid))
        db.session.delete(pg)
        db.session.commit()
        flash('Gasto planificado eliminado.', 'info')
        return redirect(url_for('proyecto_plan_gastos', pid=pid))

    # ══════════════════════════════════════════════════════════════
    # ENVIAR A APROBACION / APROBAR
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/enviar-aprobacion', methods=['POST'])
    @login_required
    def proyecto_enviar_aprobacion(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        if p.estado != 'planificacion':
            flash('Solo se puede enviar a aprobacion desde planificacion.', 'warning')
            return redirect(url_for('proyecto_ver', id=pid))
        cid = getattr(g, 'company_id', None)
        # Validate: all phases must have budget
        fases_sin_ppto = [f for f in p.fases if not f.presupuesto]
        if fases_sin_ppto:
            nombres = ', '.join(f.nombre for f in fases_sin_ppto)
            flash(f'Fases sin presupuesto asignado: {nombres}. Define presupuesto por fase antes de enviar.', 'danger')
            return redirect(url_for('proyecto_plan_gastos', pid=pid))
        # Validate: plan de gastos exists
        total_plan = db.session.query(func.sum(ProyectoPlanGasto.monto)).filter_by(proyecto_id=pid).scalar() or 0
        if total_plan <= 0:
            flash('Debes agregar al menos un gasto planificado antes de enviar a aprobacion.', 'danger')
            return redirect(url_for('proyecto_plan_gastos', pid=pid))
        # Update presupuesto total from sum of phases
        p.presupuesto = sum(f.presupuesto for f in p.fases)
        p.estado = 'pendiente_aprobacion'
        # Create approval request
        aprobacion = Aprobacion(
            company_id=cid,
            tipo_accion='proyecto_desarrollo',
            descripcion=f'Aprobacion de plan de gastos: {p.codigo} — {p.nombre} (${p.presupuesto:,.0f})',
            monto=p.presupuesto,
            estado='pendiente',
            solicitado_por=current_user.id,
            proyecto_id=p.id,
            datos_json=json.dumps({
                'proyecto_id': p.id, 'codigo': p.codigo, 'nombre': p.nombre,
                'presupuesto': p.presupuesto, 'fases': len(p.fases),
                'total_plan_gastos': total_plan
            })
        )
        db.session.add(aprobacion)
        # Notify director financiero
        try:
            df = User.query.filter_by(company_id=cid, activo=True).filter(
                User.rol.in_(['director_financiero', 'admin'])
            ).first()
            if df and df.id != current_user.id:
                db.session.add(Notificacion(
                    company_id=cid, user_id=df.id, tipo='aprobacion',
                    titulo=f'Aprobacion requerida: {p.codigo}',
                    mensaje=f'{current_user.nombre} solicita aprobar el plan de gastos del proyecto "{p.nombre}" por ${p.presupuesto:,.0f}',
                    link=url_for('proyecto_plan_gastos', pid=p.id),
                    creado_en=datetime.utcnow()
                ))
        except Exception:
            pass
        _log('crear', 'proyecto', p.id, f'Plan de gastos enviado a aprobacion: {p.codigo} (${p.presupuesto:,.0f})')
        db.session.commit()
        flash('Plan de gastos enviado a aprobacion del Director Financiero.', 'success')
        return redirect(url_for('proyecto_ver', id=pid))

    @app.route('/proyectos/<int:pid>/aprobar', methods=['POST'])
    @login_required
    def proyecto_aprobar(pid):
        rol = _get_rol_activo(current_user)
        if rol not in ('admin', 'director_financiero'):
            flash('Solo el Director Financiero puede aprobar proyectos.', 'danger')
            return redirect(url_for('proyecto_ver', id=pid))
        p = Proyecto.query.get_or_404(pid)
        if p.estado != 'pendiente_aprobacion':
            flash('Este proyecto no esta pendiente de aprobacion.', 'warning')
            return redirect(url_for('proyecto_ver', id=pid))
        accion = request.form.get('accion', 'aprobar')
        cid = getattr(g, 'company_id', None)
        # Find the pending approval
        aprobacion = Aprobacion.query.filter_by(
            proyecto_id=p.id, estado='pendiente'
        ).order_by(Aprobacion.creado_en.desc()).first()
        if accion == 'aprobar':
            p.estado = 'desarrollo'
            if aprobacion:
                aprobacion.estado = 'aprobado'
                aprobacion.aprobado_por = current_user.id
                aprobacion.resuelto_en = datetime.utcnow()
                aprobacion.notas_aprobador = request.form.get('notas', '')
            _log('aprobar', 'proyecto', p.id, f'Plan de gastos aprobado: {p.codigo}')
            flash(f'Proyecto {p.codigo} aprobado. Pasa a desarrollo.', 'success')
        else:
            p.estado = 'planificacion'
            if aprobacion:
                aprobacion.estado = 'rechazado'
                aprobacion.aprobado_por = current_user.id
                aprobacion.resuelto_en = datetime.utcnow()
                aprobacion.notas_aprobador = request.form.get('notas', '')
            _log('rechazar', 'proyecto', p.id, f'Plan de gastos rechazado: {p.codigo}')
            flash(f'Proyecto {p.codigo} rechazado. Vuelve a planificacion.', 'warning')
        # Notify creator
        try:
            if p.creado_por and p.creado_por != current_user.id:
                estado_txt = 'aprobado' if accion == 'aprobar' else 'rechazado'
                db.session.add(Notificacion(
                    company_id=cid, user_id=p.creado_por, tipo='aprobacion',
                    titulo=f'Proyecto {p.codigo} {estado_txt}',
                    mensaje=f'El plan de gastos de "{p.nombre}" fue {estado_txt} por {current_user.nombre}',
                    link=url_for('proyecto_ver', id=p.id),
                    creado_en=datetime.utcnow()
                ))
        except Exception:
            pass
        db.session.commit()
        return redirect(url_for('proyecto_ver', id=pid))

    # ══════════════════════════════════════════════════════════════
    # OBJETIVOS (Checklist por fase)
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/objetivos/agregar', methods=['POST'])
    @login_required
    def proyecto_objetivo_agregar(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        fase_id = int(request.form['fase_id'])
        max_ord = db.session.query(func.max(ProyectoObjetivo.orden)).filter_by(fase_id=fase_id).scalar() or 0
        db.session.add(ProyectoObjetivo(
            proyecto_id=pid, fase_id=fase_id,
            titulo=request.form['titulo'],
            presupuesto=float(request.form.get('presupuesto') or 0),
            orden=max_ord + 1
        ))
        db.session.commit()
        flash('Objetivo agregado.', 'success')
        return redirect(url_for('proyecto_ver', id=pid, vista='fases'))

    @app.route('/proyectos/objetivos/<int:oid>/toggle', methods=['POST'])
    @login_required
    def proyecto_objetivo_toggle(oid):
        obj = ProyectoObjetivo.query.get_or_404(oid)
        obj.completado = not obj.completado
        if obj.completado:
            obj.completado_por = current_user.id
            obj.completado_en = datetime.utcnow()
        else:
            obj.completado_por = None
            obj.completado_en = None
        db.session.commit()
        return redirect(url_for('proyecto_ver', id=obj.proyecto_id, vista='fases'))

    @app.route('/proyectos/objetivos/<int:oid>/eliminar', methods=['POST'])
    @login_required
    def proyecto_objetivo_eliminar(oid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        obj = ProyectoObjetivo.query.get_or_404(oid)
        pid = obj.proyecto_id
        db.session.delete(obj)
        db.session.commit()
        return redirect(url_for('proyecto_ver', id=pid, vista='fases'))

    # ══════════════════════════════════════════════════════════════
    # SOLICITUDES DE PAGO
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/solicitar-pago', methods=['POST'])
    @login_required
    def proyecto_solicitar_pago(pid):
        p = Proyecto.query.get_or_404(pid)
        if p.estado != 'desarrollo':
            flash('Las solicitudes de pago solo aplican en etapa de desarrollo.', 'warning')
            return redirect(url_for('proyecto_ver', id=pid))
        cid = getattr(g, 'company_id', None)
        fase_id = int(request.form['fase_id'])
        fase = db.session.get(ProyectoFase, fase_id)
        monto = float(request.form.get('monto') or 0)
        # Verify phase is unlocked (previous phase objectives completed)
        fases = sorted(p.fases, key=lambda f: f.orden)
        fase_idx = next((i for i, f in enumerate(fases) if f.id == fase_id), 0)
        if fase_idx > 0:
            prev = fases[fase_idx - 1]
            prev_total = len(prev.objetivos)
            prev_done = len([o for o in prev.objetivos if o.completado])
            if prev_total > 0 and prev_done < prev_total:
                flash(f'Debes completar todos los objetivos de "{prev.nombre}" ({prev_done}/{prev_total}) para desbloquear pagos de "{fase.nombre}".', 'danger')
                return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
        # Check budget
        gastado = db.session.query(func.sum(ProyectoSolicitudPago.monto)).filter_by(
            fase_id=fase_id, estado='pagada'
        ).scalar() or 0
        pendiente = db.session.query(func.sum(ProyectoSolicitudPago.monto)).filter_by(
            fase_id=fase_id
        ).filter(ProyectoSolicitudPago.estado.in_(['pendiente', 'aprobada'])).scalar() or 0
        disponible = (fase.presupuesto or 0) - gastado - pendiente
        if monto > disponible and disponible > 0:
            flash(f'El monto (${monto:,.0f}) excede el presupuesto disponible (${disponible:,.0f}).', 'danger')
            return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
        objetivo_id = int(request.form.get('objetivo_id')) if request.form.get('objetivo_id') else None
        proveedor_id = int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None
        cotizacion_prov_id = int(request.form.get('cotizacion_prov_id')) if request.form.get('cotizacion_prov_id') else None
        sp = ProyectoSolicitudPago(
            company_id=cid, proyecto_id=pid, fase_id=fase_id,
            objetivo_id=objetivo_id,
            concepto=request.form.get('concepto', ''),
            descripcion_compra=request.form.get('descripcion_compra', ''),
            monto=monto, solicitado_por=current_user.id,
            proveedor_id=proveedor_id,
            cotizacion_prov_id=cotizacion_prov_id,
            notas=request.form.get('notas', '')
        )
        db.session.add(sp)
        # Notify finance
        try:
            df = User.query.filter_by(company_id=cid, activo=True).filter(
                User.rol.in_(['director_financiero', 'admin', 'contador'])
            ).first()
            if df and df.id != current_user.id:
                db.session.add(Notificacion(
                    company_id=cid, user_id=df.id, tipo='solicitud_pago',
                    titulo=f'Solicitud de pago: {p.codigo} — {fase.nombre}',
                    mensaje=f'{current_user.nombre} solicita pago de ${monto:,.0f} para "{sp.concepto}" en el proyecto "{p.nombre}"',
                    link=url_for('proyecto_ver', id=pid, vista='fases'),
                    creado_en=datetime.utcnow()
                ))
        except Exception:
            pass
        db.session.commit()
        flash(f'Solicitud de pago por ${monto:,.0f} enviada a finanzas.', 'success')
        return redirect(url_for('proyecto_ver', id=pid, vista='fases'))

    @app.route('/proyectos/solicitud-pago/<int:spid>/resolver', methods=['POST'])
    @login_required
    def proyecto_solicitud_pago_resolver(spid):
        rol = _get_rol_activo(current_user)
        if rol not in ('admin', 'director_financiero', 'contador'):
            flash('Solo finanzas puede resolver solicitudes de pago.', 'danger')
            return redirect(url_for('dashboard'))
        sp = ProyectoSolicitudPago.query.get_or_404(spid)
        p = Proyecto.query.get_or_404(sp.proyecto_id)
        cid = getattr(g, 'company_id', None)
        accion = request.form.get('accion', 'aprobar')
        if accion == 'pagar':
            # Create GastoOperativo and link
            fase = db.session.get(ProyectoFase, sp.fase_id)
            fase_label = f' [{fase.nombre}]' if fase else ''
            gasto = GastoOperativo(
                company_id=cid, tipo='proyecto', tipo_custom=f'Proyecto {p.codigo}{fase_label}',
                descripcion=sp.concepto, monto=sp.monto, fecha=date_type.today(),
                creado_por=current_user.id, notas=f'Solicitud de pago aprobada — {p.codigo}'
            )
            db.session.add(gasto); db.session.flush()
            sp.gasto_id = gasto.id
            sp.estado = 'pagada'
            sp.aprobado_por = current_user.id
            sp.resuelto_en = datetime.utcnow()
            sp.notas_aprobador = request.form.get('notas', '')
            # Also link to ProyectoGasto
            db.session.add(ProyectoGasto(
                proyecto_id=sp.proyecto_id, fase_id=sp.fase_id,
                gasto_id=gasto.id, descripcion=sp.concepto
            ))
            _log('pagar', 'proyecto', p.id, f'Pago aprobado: {sp.concepto} — ${sp.monto:,.0f}')
            flash(f'Pago de ${sp.monto:,.0f} realizado y registrado en contabilidad.', 'success')
        else:
            sp.estado = 'rechazada'
            sp.aprobado_por = current_user.id
            sp.resuelto_en = datetime.utcnow()
            sp.notas_aprobador = request.form.get('notas', '')
            flash('Solicitud rechazada.', 'info')
        # Notify requester
        try:
            if sp.solicitado_por != current_user.id:
                estado_txt = 'pagada' if accion == 'pagar' else 'rechazada'
                db.session.add(Notificacion(
                    company_id=cid, user_id=sp.solicitado_por, tipo='solicitud_pago',
                    titulo=f'Solicitud {estado_txt}: {sp.concepto}',
                    mensaje=f'Tu solicitud de ${sp.monto:,.0f} fue {estado_txt} por {current_user.nombre}',
                    link=url_for('proyecto_ver', id=sp.proyecto_id, vista='fases'),
                    creado_en=datetime.utcnow()
                ))
        except Exception:
            pass
        db.session.commit()
        return redirect(url_for('proyecto_ver', id=sp.proyecto_id, vista='fases'))

    # ══════════════════════════════════════════════════════════════
    # CAMBIO DE ASIGNACION DE PRESUPUESTO
    # ══════════════════════════════════════════════════════════════

    @app.route('/proyectos/<int:pid>/reasignar-presupuesto', methods=['POST'])
    @login_required
    def proyecto_reasignar_presupuesto(pid):
        if not _requiere_proyecto_access():
            flash('Acceso denegado.', 'danger'); return redirect(url_for('dashboard'))
        p = Proyecto.query.get_or_404(pid)
        nuevo_total = float(request.form.get('nuevo_presupuesto') or 0)
        motivo = request.form.get('motivo', '').strip()
        if nuevo_total <= 0:
            flash('El presupuesto debe ser mayor a cero.', 'danger')
            return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
        if not motivo:
            flash('Debes indicar el motivo del cambio.', 'danger')
            return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
        anterior = p.presupuesto
        p.presupuesto = nuevo_total
        _log('editar', 'proyecto', p.id,
             f'Reasignacion presupuesto: ${anterior:,.0f} → ${nuevo_total:,.0f}. Motivo: {motivo}')
        # Notify finance
        cid = getattr(g, 'company_id', None)
        try:
            df = User.query.filter_by(company_id=cid, activo=True).filter(
                User.rol.in_(['director_financiero', 'admin'])
            ).first()
            if df and df.id != current_user.id:
                db.session.add(Notificacion(
                    company_id=cid, user_id=df.id, tipo='proyecto',
                    titulo=f'Cambio presupuesto: {p.codigo}',
                    mensaje=f'{current_user.nombre} reasigno presupuesto de {p.nombre}: ${anterior:,.0f} → ${nuevo_total:,.0f}. Motivo: {motivo}',
                    link=url_for('proyecto_ver', id=p.id),
                    creado_en=datetime.utcnow()
                ))
        except Exception:
            pass
        db.session.commit()
        flash(f'Presupuesto actualizado: ${anterior:,.0f} → ${nuevo_total:,.0f}', 'success')
        return redirect(url_for('proyecto_ver', id=pid, vista='fases'))
