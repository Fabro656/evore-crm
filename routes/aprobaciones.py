# routes/aprobaciones.py — Sistema de aprobaciones financieras v34
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime
import json, logging


def register(app):

    def _requiere_aprobacion(tipo_accion, descripcion, monto, datos_form):
        """
        Verifica si el usuario actual necesita aprobación.
        Directores financieros y admin NO necesitan aprobación.
        Retorna (necesita: bool, aprobacion_obj o None)
        """
        roles_auto_aprobados = ('admin', 'director_financiero')
        if current_user.rol in roles_auto_aprobados:
            return False, None

        aprobacion = Aprobacion(
            tipo_accion=tipo_accion,
            descripcion=descripcion[:300],
            monto=float(monto or 0),
            datos_json=json.dumps(datos_form, ensure_ascii=False, default=str),
            estado='pendiente',
            solicitado_por=current_user.id
        )
        db.session.add(aprobacion)
        db.session.commit()

        # Notificar a directores financieros y admins
        directores = User.query.filter(
            User.rol.in_(['admin', 'director_financiero']),
            User.activo == True
        ).all()
        for d in directores:
            _crear_notificacion(
                d.id, 'alerta',
                f'Aprobación requerida: {descripcion[:80]}',
                f'{current_user.nombre} solicita aprobación para: {descripcion}. Monto: ${monto:,.0f}',
                url_for('aprobaciones_pendientes')
            )

        return True, aprobacion

    app.jinja_env.globals['_requiere_aprobacion_fn'] = _requiere_aprobacion

    # ── Lista de aprobaciones pendientes
    @app.route('/aprobaciones')
    @login_required
    def aprobaciones_pendientes():
        if current_user.rol not in ('admin', 'director_financiero', 'director_operativo'):
            flash('Sin permisos para ver aprobaciones.', 'danger')
            return redirect(url_for('dashboard'))
        pendientes = Aprobacion.query.filter_by(estado='pendiente').order_by(Aprobacion.creado_en.desc()).all()
        historial = Aprobacion.query.filter(Aprobacion.estado != 'pendiente').order_by(Aprobacion.resuelto_en.desc()).limit(50).all()
        return render_template('aprobaciones/index.html', pendientes=pendientes, historial=historial)

    # ── Aprobar solicitud
    @app.route('/aprobaciones/<int:id>/aprobar', methods=['POST'])
    @login_required
    def aprobacion_aprobar(id):
        if current_user.rol not in ('admin', 'director_financiero'):
            flash('Solo el director financiero o admin pueden aprobar.', 'danger')
            return redirect(url_for('aprobaciones_pendientes'))
        a = Aprobacion.query.get_or_404(id)
        if a.estado != 'pendiente':
            flash('Esta solicitud ya fue procesada.', 'warning')
            return redirect(url_for('aprobaciones_pendientes'))

        a.estado = 'aprobado'
        a.aprobado_por = current_user.id
        a.notas_aprobador = request.form.get('notas', '')
        a.resuelto_en = datetime.utcnow()
        db.session.commit()

        # Notificar al solicitante
        _crear_notificacion(
            a.solicitado_por, 'info',
            f'Solicitud aprobada: {a.descripcion[:80]}',
            f'Tu solicitud fue aprobada por {current_user.nombre}. Puedes proceder.',
            url_for('aprobaciones_pendientes')
        )

        flash(f'Solicitud aprobada. Se notificó a {a.solicitante.nombre}.', 'success')
        return redirect(url_for('aprobaciones_pendientes'))

    # ── Rechazar solicitud
    @app.route('/aprobaciones/<int:id>/rechazar', methods=['POST'])
    @login_required
    def aprobacion_rechazar(id):
        if current_user.rol not in ('admin', 'director_financiero'):
            flash('Solo el director financiero o admin pueden rechazar.', 'danger')
            return redirect(url_for('aprobaciones_pendientes'))
        a = Aprobacion.query.get_or_404(id)
        if a.estado != 'pendiente':
            flash('Esta solicitud ya fue procesada.', 'warning')
            return redirect(url_for('aprobaciones_pendientes'))

        a.estado = 'rechazado'
        a.aprobado_por = current_user.id
        a.notas_aprobador = request.form.get('notas', 'Sin observaciones')
        a.resuelto_en = datetime.utcnow()
        db.session.commit()

        _crear_notificacion(
            a.solicitado_por, 'alerta',
            f'Solicitud rechazada: {a.descripcion[:80]}',
            f'Tu solicitud fue rechazada por {current_user.nombre}. Motivo: {a.notas_aprobador}',
            url_for('aprobaciones_pendientes')
        )

        flash(f'Solicitud rechazada.', 'warning')
        return redirect(url_for('aprobaciones_pendientes'))

    # ── Mis solicitudes (para el solicitante)
    @app.route('/aprobaciones/mis-solicitudes')
    @login_required
    def mis_solicitudes():
        items = Aprobacion.query.filter_by(solicitado_por=current_user.id).order_by(Aprobacion.creado_en.desc()).all()
        return render_template('aprobaciones/mis_solicitudes.html', items=items)

    # ── API: verificar si necesita aprobación (para uso en formularios)
    @app.route('/api/aprobacion/requerida')
    @login_required
    def api_aprobacion_requerida():
        roles_auto = ('admin', 'director_financiero')
        return jsonify({'requiere': current_user.rol not in roles_auto, 'rol': current_user.rol})
