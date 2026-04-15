# routes/proyectos.py — Gestion de Proyectos (Jira/Notion style)
from flask import render_template, redirect, url_for, flash, request, jsonify, g, session
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, date as date_type
from sqlalchemy import func
import json, logging

_ESTADOS_PROYECTO = ['planificacion', 'en_progreso', 'pausado', 'completado', 'cancelado']
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
        return render_template('proyectos/index.html',
            proyectos=proyectos, stats=stats, estado_f=estado_f, buscar=buscar,
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
        vista = request.args.get('vista', 'kanban')
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
        # Stats
        total_t = sum(len(v) for v in tareas_por_estado.values())
        done_t = len(tareas_por_estado.get('completada', []))
        pct = round(done_t / total_t * 100) if total_t else 0
        usuarios = User.query.filter_by(company_id=getattr(g, 'company_id', None), activo=True).order_by(User.nombre).all()
        return render_template('proyectos/ver.html', p=p, vista=vista,
            tareas_por_estado=tareas_por_estado, estados=_ESTADOS_TAREA,
            tipos=_TIPOS_TAREA, gastos=gastos_q, gasto_total=gasto_total,
            total_t=total_t, done_t=done_t, pct=pct, usuarios=usuarios)

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
            return jsonify({'error': 'Acceso denegado'}), 403
        p = Proyecto.query.get_or_404(pid)
        max_orden = db.session.query(func.max(ProyectoFase.orden)).filter_by(proyecto_id=pid).scalar() or 0
        f = ProyectoFase(
            proyecto_id=pid,
            nombre=request.form.get('nombre', 'Nueva fase'),
            orden=max_orden + 1
        )
        db.session.add(f)
        db.session.commit()
        flash('Fase creada.', 'success')
        return redirect(url_for('proyecto_ver', id=pid))

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
        desc = request.form.get('descripcion', '').strip() or f'Gasto proyecto {p.codigo}'
        gasto = GastoOperativo(
            company_id=cid, tipo='proyecto', tipo_custom=f'Proyecto {p.codigo}',
            descripcion=desc, monto=monto, fecha=date_type.today(),
            creado_por=current_user.id, notas=f'Vinculado a proyecto {p.codigo}'
        )
        db.session.add(gasto)
        db.session.flush()
        db.session.add(ProyectoGasto(proyecto_id=pid, gasto_id=gasto.id, descripcion=desc))
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
