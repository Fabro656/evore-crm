# routes/tareas.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, secrets, logging


# ══════════════════════════════════════════════════════════════════════════════
# BLOQUE 7 — Funciones Helper de Automatización (nivel de módulo)
# ══════════════════════════════════════════════════════════════════════════════

def _crear_tarea_unica(titulo_patron, tarea_tipo, descripcion, prioridad='media',
                        creado_por=None, entidad_id=None, entidad_tipo=None):
    """
    Crea una tarea solo si no existe otra pendiente con el mismo patrón de título y tipo.
    Retorna (tarea, creada: bool)

    Args:
        titulo_patron: Patrón de título para búsqueda (se usa LIKE)
        tarea_tipo: Tipo de tarea (produccion_detenida, compra_urgente, etc.)
        descripcion: Descripción de la tarea
        prioridad: nivel de prioridad (baja, media, alta)
        creado_por: ID del usuario que crea (default: usuario actual)
        entidad_id: ID de la entidad relacionada (orden, venta, etc.)
        entidad_tipo: Tipo de entidad (orden_produccion, venta, etc.)

    Returns:
        tuple: (tarea_obj, fue_creada: bool)
    """
    try:
        # Buscar si existe una tarea pendiente con patrón similar
        existente = Tarea.query.filter(
            Tarea.titulo.like(f'%{titulo_patron}%'),
            Tarea.tarea_tipo == tarea_tipo,
            Tarea.estado == 'pendiente'
        ).first()

        if existente:
            return existente, False

        # Crear nueva tarea
        t = Tarea(
            titulo=titulo_patron,
            descripcion=descripcion,
            prioridad=prioridad,
            estado='pendiente',
            tarea_tipo=tarea_tipo,
            creado_por=creado_por or 1,
            creado_en=datetime.utcnow()
        )
        db.session.add(t)
        db.session.flush()
        return t, True
    except Exception as e:
        logging.warning(f'Error en _crear_tarea_unica: {e}')
        return None, False


def _crear_evento_automatico(titulo, descripcion, tipo='evento', fecha=None, creado_por=None):
    """
    Crea un evento en el calendario solo si no existe uno con ese título hoy.

    Args:
        titulo: Título del evento
        descripcion: Descripción
        tipo: Tipo de evento (evento, alerta, recordatorio)
        fecha: Fecha del evento (default: hoy)
        creado_por: ID del usuario creador

    Returns:
        evento_obj o None si ya existe
    """
    try:
        hoy = fecha or date_type.today()

        # Verificar si existe evento con ese título para hoy
        existente = Evento.query.filter(
            Evento.titulo == titulo,
            Evento.fecha == hoy
        ).first()

        if existente:
            return existente

        # Crear nuevo evento
        e = Evento(
            titulo=titulo,
            descripcion=descripcion,
            tipo=tipo,
            fecha=hoy,
            creado_por=creado_por or 1,
            creado_en=datetime.utcnow()
        )
        db.session.add(e)
        return e
    except Exception as e:
        logging.warning(f'Error en _crear_evento_automatico: {e}')
        return None


# ══════════════════════════════════════════════════════════════════════════════

def register(app):

    # ── Helpers ─────────────────────────────────────────────────────
    def _save_asignados(tarea_obj):
        TareaAsignado.query.filter_by(tarea_id=tarea_obj.id).delete()
        # Siempre incluir al asignado principal
        principal_id = int(request.form.get('asignado_a') or current_user.id)
        db.session.add(TareaAsignado(tarea_id=tarea_obj.id, usuario_id=principal_id))
        # Agregar asignados adicionales
        uids = request.form.getlist('otros_asignados[]')
        for uid in uids:
            if uid and int(uid) != principal_id:
                db.session.add(TareaAsignado(tarea_id=tarea_obj.id, usuario_id=int(uid)))


    # ── tareas (/tareas)
    @app.route('/tareas')
    @login_required
    @requiere_modulo('tareas')
    def tareas():
        estado_f=request.args.get('estado',''); prioridad_f=request.args.get('prioridad','')
        q=Tarea.query
        # Non-admins only see their own tasks
        if current_user.rol != 'admin':
            q = q.filter(
                db.or_(
                    Tarea.asignado_a == current_user.id,
                    Tarea.creado_por == current_user.id,
                    Tarea.id.in_(
                        db.session.query(TareaAsignado.tarea_id).filter_by(user_id=current_user.id)
                    )
                )
            )
        if estado_f: q=q.filter_by(estado=estado_f)
        if prioridad_f: q=q.filter_by(prioridad=prioridad_f)
        return render_template('tareas/index.html', items=q.order_by(Tarea.creado_en.desc()).all(),
            estado_f=estado_f, prioridad_f=prioridad_f)
    

    # ── tarea_nueva (/tareas/nueva)
    @app.route('/tareas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('tareas')
    def tarea_nueva():
        us=User.query.filter_by(activo=True).all()
        if request.method == 'POST':
            fs=request.form.get('fecha_vencimiento')
            asignado_id=int(request.form.get('asignado_a') or current_user.id)
            t=Tarea(titulo=request.form['titulo'], descripcion=request.form.get('descripcion',''),
                estado=request.form.get('estado','pendiente'), prioridad=request.form.get('prioridad','media'),
                fecha_vencimiento=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None,
                asignado_a=asignado_id, creado_por=current_user.id)
            db.session.add(t); db.session.flush()
            _save_asignados(t)
            _log('crear','tarea',t.id,f'Tarea creada: {t.titulo}'); db.session.commit()
            # Notificación al asignado (si no es quien la crea)
            if asignado_id != current_user.id:
                _crear_notificacion(asignado_id, 'tarea_asignada',
                    f'Nueva tarea asignada: {t.titulo}',
                    f'Te asignó una tarea: {current_user.nombre}',
                    url_for('tarea_ver', id=t.id))
                asignado = db.session.get(User, asignado_id)
                if asignado and asignado.email:
                    _send_email(asignado.email, f'Nueva tarea: {t.titulo}',
                        f'Hola {asignado.nombre},\n\n{current_user.nombre} te asignó la tarea "{t.titulo}".\n\nDescripción: {t.descripcion or "—"}')
            flash('Tarea creada.','success'); return redirect(url_for('tareas'))
        return render_template('tareas/form.html', obj=None, usuarios=us, titulo='Nueva Tarea', asignados_ids=[])
    

    # ── tarea_ver (/tareas/<int:id>)
    @app.route('/tareas/<int:id>')
    @login_required
    @requiere_modulo('tareas')
    def tarea_ver(id):
        obj=Tarea.query.get_or_404(id)
        return render_template('tareas/ver.html', obj=obj, tarea=obj)
    

    # ── tarea_comentar (/tareas/<int:id>/comentar)
    @app.route('/tareas/<int:id>/comentar', methods=['POST'])
    @login_required
    @requiere_modulo('tareas')
    def tarea_comentar(id):
        obj=Tarea.query.get_or_404(id)
        msg=request.form.get('mensaje','').strip()
        if msg:
            db.session.add(TareaComentario(tarea_id=obj.id, autor_id=current_user.id, mensaje=msg))
            db.session.commit()
            flash('Comentario agregado.','success')
        return redirect(url_for('tarea_ver', id=id))
    

    # ── tarea_editar (/tareas/<int:id>/editar)
    @app.route('/tareas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('tareas')
    def tarea_editar(id):
        obj=Tarea.query.get_or_404(id); us=User.query.filter_by(activo=True).all()
        if request.method == 'POST':
            fs=request.form.get('fecha_vencimiento')
            prev_asignado = obj.asignado_a
            obj.titulo=request.form['titulo']; obj.descripcion=request.form.get('descripcion','')
            obj.estado=request.form.get('estado','pendiente'); obj.prioridad=request.form.get('prioridad','media')
            obj.fecha_vencimiento=datetime.strptime(fs,'%Y-%m-%d').date() if fs else None
            obj.asignado_a=int(request.form.get('asignado_a') or current_user.id)
            db.session.flush(); _save_asignados(obj)
            _log('editar','tarea',obj.id,f'Tarea editada: {obj.titulo}'); db.session.commit()
            # Notificar si cambió el asignado
            if obj.asignado_a != prev_asignado and obj.asignado_a != current_user.id:
                _crear_notificacion(obj.asignado_a, 'tarea_asignada',
                    f'Tarea reasignada: {obj.titulo}',
                    f'{current_user.nombre} te reasignó esta tarea.',
                    url_for('tarea_ver', id=obj.id))
                asignado = db.session.get(User, obj.asignado_a)
                if asignado and asignado.email:
                    _send_email(asignado.email, f'Tarea reasignada: {obj.titulo}',
                        f'Hola {asignado.nombre},\n\n{current_user.nombre} te reasignó la tarea "{obj.titulo}".')
            flash('Tarea actualizada.','success'); return redirect(url_for('tarea_ver', id=obj.id))
        asignados_ids=[a.user_id for a in obj.asignados]
        return render_template('tareas/form.html', obj=obj, usuarios=us, titulo='Editar Tarea', asignados_ids=asignados_ids)
    

    # ── tarea_completar (/tareas/<int:id>/completar)
    @app.route('/tareas/<int:id>/completar', methods=['POST'])
    @login_required
    @requiere_modulo('tareas')
    def tarea_completar(id):
        obj = Tarea.query.get_or_404(id)
        obj.estado = 'completada'
        _log('completar','tarea',obj.id,f'Tarea completada: {obj.titulo}')
        db.session.commit()
    
        # Lógica tareas pareadas: comprar_materias + verificar_abono
        if obj.tarea_tipo in ('comprar_materias','verificar_abono') and obj.tarea_pareja_id:
            pareja = db.session.get(Tarea, obj.tarea_pareja_id)
            if pareja and pareja.estado == 'completada' and obj.cotizacion_id:
                # Ambas tareas completadas → enviar email al cliente
                cot = db.session.get(Cotizacion, obj.cotizacion_id)
                if cot and cot.cliente:
                    cliente = cot.cliente
                    email_dest = None
                    # Buscar email del cliente
                    if cliente.contactos:
                        for c in cliente.contactos:
                            if c.email:
                                email_dest = c.email; break
                    # Enviar email
                    empresa = ConfigEmpresa.query.first()
                    nombre_empresa = empresa.nombre if empresa else 'Evore'
                    if email_dest:
                        _send_email(
                            email_dest,
                            f'Producción iniciada — {cot.titulo}',
                            f'Estimado/a {cliente.nombre},\n\n'
                            f'Nos complace informarle que todas las materias primas para su pedido '
                            f'(cotización #{cot.numero or cot.id}) han sido recibidas y el anticipo '
                            f'verificado. La producción ha comenzado.\n\n'
                            f'Producto(s): {", ".join(i.nombre_prod for i in cot.items if i.nombre_prod)}\n\n'
                            f'Saludos,\n{nombre_empresa}'
                        )
                    # Notificar a admins
                    admins = User.query.filter_by(rol='admin', activo=True).all()
                    for adm in admins:
                        _crear_notificacion(
                            adm.id, 'info',
                            f'✅ Producción iniciada — {cot.titulo}',
                            f'Materias y abono confirmados. Email enviado a {cliente.nombre}.',
                            url_for('cotizacion_ver', id=cot.id)
                        )
    
        flash('¡Tarea completada!','success'); return redirect(url_for('tareas'))
    

    # ── tarea_eliminar (/tareas/<int:id>/eliminar)
    @app.route('/tareas/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('tareas')
    def tarea_eliminar(id):
        obj = Tarea.query.get_or_404(id)
        if current_user.rol != 'admin' and obj.creado_por != current_user.id:
            flash('Solo puedes eliminar tareas que tú creaste.', 'danger')
            return redirect(url_for('tareas'))
        try:
            # Clear self-referencing FK: other tareas that point to this one as "pareja"
            Tarea.query.filter_by(tarea_pareja_id=obj.id).update({'tarea_pareja_id': None})
            db.session.flush()
            # cascade='all, delete-orphan' on asignados/comentarios handles those automatically
            db.session.delete(obj)
            db.session.commit()
            _log('eliminar', 'tarea', id, 'Tarea eliminada')
            db.session.commit()
            flash('Tarea eliminada.', 'info')
        except Exception as e:
            db.session.rollback()
            flash('No se pudo eliminar la tarea. Intenta de nuevo.', 'danger')
        return redirect(url_for('tareas'))
    
