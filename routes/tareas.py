# routes/tareas.py
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
    @app.route('/tareas')
    @login_required
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

    @app.route('/tareas/nueva', methods=['GET','POST'])
    @login_required
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

    @app.route('/tareas/<int:id>')
    @login_required
    def tarea_ver(id):
        obj=Tarea.query.get_or_404(id)
        return render_template('tareas/ver.html', obj=obj, tarea=obj)

    @app.route('/tareas/<int:id>/editar', methods=['GET','POST'])
    @login_required
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

    @app.route('/tareas/<int:id>/eliminar', methods=['POST'])
    @login_required
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

    @app.route('/tareas/<int:id>/completar', methods=['POST'])
    @login_required
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

    @app.route('/tareas/<int:id>/comentar', methods=['POST'])
    @login_required
    def tarea_comentar(id):
        obj=Tarea.query.get_or_404(id)
        msg=request.form.get('mensaje','').strip()
        if msg:
            db.session.add(TareaComentario(tarea_id=obj.id, autor_id=current_user.id, mensaje=msg))
            db.session.commit()
            flash('Comentario agregado.','success')
        return redirect(url_for('tarea_ver', id=id))
