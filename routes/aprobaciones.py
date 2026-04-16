# routes/aprobaciones.py — Sistema de aprobaciones v37 (bloquean flujo)
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db, tenant_query
from models import *
from utils import *
from datetime import datetime
import json, logging


def register(app):

    def _solicitar_aprobacion(tipo_accion, descripcion, monto=0,
                               orden_compra_id=None, venta_id=None,
                               cotizacion_id=None, asiento_id=None):
        """Crea una solicitud de aprobacion y bloquea la entidad.
        Admin/director_financiero se auto-aprueban.
        Retorna (necesita_aprobacion: bool, aprobacion_obj o None)"""
        roles_auto = ('admin', 'director_financiero')
        if _get_rol_activo(current_user) in roles_auto:
            return False, None

        a = Aprobacion(
            tipo_accion=tipo_accion,
            descripcion=descripcion[:300],
            monto=float(monto or 0),
            estado='pendiente',
            solicitado_por=current_user.id,
            orden_compra_id=orden_compra_id,
            venta_id=venta_id,
            cotizacion_id=cotizacion_id,
            asiento_id=asiento_id
        )
        db.session.add(a)

        # Bloquear la entidad
        if orden_compra_id:
            oc = db.session.get(OrdenCompra, orden_compra_id)
            if oc: oc.pendiente_aprobacion = True
        if venta_id:
            v = db.session.get(Venta, venta_id)
            if v: v.pendiente_aprobacion = True

        db.session.commit()

        # Notificar a aprobadores
        aprobadores = User.query.filter(
            User.rol.in_(['admin', 'director_financiero']),
            User.activo == True
        ).all()
        for d in aprobadores:
            _crear_notificacion(
                d.id, 'alerta',
                f'Aprobacion requerida: {descripcion[:80]}',
                f'{current_user.nombre} solicita aprobacion. Monto: ${monto:,.0f}',
                url_for('aprobaciones_pendientes')
            )

        return True, a

    # Exponer para uso en otros modulos
    app.jinja_env.globals['_requiere_aprobacion_fn'] = _solicitar_aprobacion


    # ── Solicitar aprobacion desde OC/venta/cotizacion/asiento
    @app.route('/aprobaciones/solicitar', methods=['POST'])
    @login_required
    def solicitar_aprobacion():
        tipo = request.form.get('tipo_accion', '')
        desc = request.form.get('descripcion', '')
        monto = float(request.form.get('monto', 0) or 0)
        oc_id = request.form.get('orden_compra_id', type=int)
        venta_id = request.form.get('venta_id', type=int)
        cot_id = request.form.get('cotizacion_id', type=int)
        asiento_id = request.form.get('asiento_id', type=int)

        necesita, aprob = _solicitar_aprobacion(
            tipo, desc, monto,
            orden_compra_id=oc_id, venta_id=venta_id,
            cotizacion_id=cot_id, asiento_id=asiento_id
        )
        if necesita:
            flash(f'Solicitud de aprobacion enviada. El proceso queda bloqueado hasta que se apruebe.', 'info')
        else:
            flash('Tu rol no requiere aprobacion. Puedes continuar.', 'success')

        # Redirigir de vuelta
        if oc_id: return redirect(url_for('ordenes_compra'))
        if venta_id: return redirect(url_for('ventas'))
        if cot_id: return redirect(url_for('cotizaciones'))
        if asiento_id: return redirect(url_for('contable_asientos'))
        return redirect(url_for('aprobaciones_pendientes'))


    # ── Lista de aprobaciones pendientes
    @app.route('/aprobaciones')
    @login_required
    def aprobaciones_pendientes():
        if _get_rol_activo(current_user) not in ('admin', 'director_financiero', 'director_operativo'):
            flash('Sin permisos para ver aprobaciones.', 'danger')
            return redirect(url_for('dashboard'))
        pendientes = tenant_query(Aprobacion).filter_by(estado='pendiente').order_by(Aprobacion.creado_en.desc()).all()
        en_revision = tenant_query(Aprobacion).filter_by(estado='revision').order_by(Aprobacion.creado_en.desc()).all()
        historial = tenant_query(Aprobacion).filter(Aprobacion.estado.in_(['aprobado', 'rechazado'])).order_by(Aprobacion.resuelto_en.desc()).limit(50).all()
        return render_template('aprobaciones/index.html',
                               pendientes=pendientes, en_revision=en_revision, historial=historial)


    def _desbloquear_entidad(a):
        """Desbloquea la entidad vinculada a una aprobacion."""
        if a.orden_compra_id:
            oc = db.session.get(OrdenCompra, a.orden_compra_id)
            if oc: oc.pendiente_aprobacion = False
        if a.venta_id:
            v = db.session.get(Venta, a.venta_id)
            if v: v.pendiente_aprobacion = False


    # ── Aprobar
    @app.route('/aprobaciones/<int:id>/aprobar', methods=['POST'])
    @login_required
    def aprobacion_aprobar(id):
        if _get_rol_activo(current_user) not in ('admin', 'director_financiero', 'director_operativo'):
            flash('Solo admin, director financiero u operativo pueden aprobar.', 'danger')
            return redirect(url_for('aprobaciones_pendientes'))
        a = Aprobacion.query.get_or_404(id)
        if a.estado not in ('pendiente', 'revision'):
            flash('Esta solicitud ya fue procesada.', 'warning')
            return redirect(url_for('aprobaciones_pendientes'))

        a.estado = 'aprobado'
        a.aprobado_por = current_user.id
        a.notas_aprobador = request.form.get('notas', '')
        a.resuelto_en = datetime.utcnow()

        _desbloquear_entidad(a)
        db.session.commit()

        _crear_notificacion(
            a.solicitado_por, 'info',
            f'Aprobado: {a.descripcion[:80]}',
            f'Aprobado por {current_user.nombre}. Puedes continuar.',
            url_for('aprobaciones_pendientes')
        )
        flash(f'Solicitud aprobada.', 'success')
        return redirect(url_for('aprobaciones_pendientes'))


    # ── Enviar a revision (desbloquea solo para edicion)
    @app.route('/aprobaciones/<int:id>/revision', methods=['POST'])
    @login_required
    def aprobacion_revision(id):
        if _get_rol_activo(current_user) not in ('admin', 'director_financiero'):
            flash('Sin permisos.', 'danger')
            return redirect(url_for('aprobaciones_pendientes'))
        a = Aprobacion.query.get_or_404(id)
        if a.estado != 'pendiente':
            flash('Solo se pueden revisar solicitudes pendientes.', 'warning')
            return redirect(url_for('aprobaciones_pendientes'))

        a.estado = 'revision'
        a.notas_aprobador = request.form.get('notas', 'Requiere correccion')
        # Desbloquear entidad para edicion
        _desbloquear_entidad(a)
        db.session.commit()

        _crear_notificacion(
            a.solicitado_por, 'alerta',
            f'Revision requerida: {a.descripcion[:80]}',
            f'{current_user.nombre} devolvio para revision: {a.notas_aprobador}',
            url_for('mis_solicitudes')
        )
        flash('Enviado a revision. El solicitante puede editar y reenviar.', 'info')
        return redirect(url_for('aprobaciones_pendientes'))


    # ── Rechazar (cancela la entidad)
    @app.route('/aprobaciones/<int:id>/rechazar', methods=['POST'])
    @login_required
    def aprobacion_rechazar(id):
        if _get_rol_activo(current_user) not in ('admin', 'director_financiero'):
            flash('Sin permisos.', 'danger')
            return redirect(url_for('aprobaciones_pendientes'))
        a = Aprobacion.query.get_or_404(id)
        if a.estado not in ('pendiente', 'revision'):
            flash('Ya fue procesada.', 'warning')
            return redirect(url_for('aprobaciones_pendientes'))

        a.estado = 'rechazado'
        a.aprobado_por = current_user.id
        a.notas_aprobador = request.form.get('notas', 'Rechazado')
        a.resuelto_en = datetime.utcnow()

        # Cancelar la entidad vinculada
        if a.orden_compra_id:
            oc = db.session.get(OrdenCompra, a.orden_compra_id)
            if oc:
                oc.estado = 'cancelada'
                oc.pendiente_aprobacion = False
        if a.venta_id:
            v = db.session.get(Venta, a.venta_id)
            if v:
                v.estado = 'cancelado'
                v.pendiente_aprobacion = False

        db.session.commit()

        _crear_notificacion(
            a.solicitado_por, 'alerta',
            f'Rechazado: {a.descripcion[:80]}',
            f'Rechazado por {current_user.nombre}. Motivo: {a.notas_aprobador}',
            url_for('mis_solicitudes')
        )
        flash('Solicitud rechazada. La entidad fue cancelada.', 'warning')
        return redirect(url_for('aprobaciones_pendientes'))


    # ── Reenviar (desde revision a pendiente)
    @app.route('/aprobaciones/<int:id>/reenviar', methods=['POST'])
    @login_required
    def aprobacion_reenviar(id):
        a = Aprobacion.query.get_or_404(id)
        if a.solicitado_por != current_user.id:
            flash('Solo el solicitante puede reenviar.', 'danger')
            return redirect(url_for('mis_solicitudes'))
        if a.estado != 'revision':
            flash('Solo se pueden reenviar solicitudes en revision.', 'warning')
            return redirect(url_for('mis_solicitudes'))

        a.estado = 'pendiente'
        a.notas_aprobador = None
        # Volver a bloquear la entidad
        if a.orden_compra_id:
            oc = db.session.get(OrdenCompra, a.orden_compra_id)
            if oc: oc.pendiente_aprobacion = True
        if a.venta_id:
            v = db.session.get(Venta, a.venta_id)
            if v: v.pendiente_aprobacion = True

        db.session.commit()
        flash('Solicitud reenviada para aprobacion.', 'success')
        return redirect(url_for('mis_solicitudes'))


    # ── Mis solicitudes
    @app.route('/aprobaciones/mis-solicitudes')
    @login_required
    def mis_solicitudes():
        items = tenant_query(Aprobacion).filter_by(solicitado_por=current_user.id).order_by(Aprobacion.creado_en.desc()).all()
        return render_template('aprobaciones/mis_solicitudes.html', items=items)


    # ── API: verificar si necesita aprobacion
    @app.route('/api/aprobacion/requerida')
    @login_required
    def api_aprobacion_requerida():
        roles_auto = ('admin', 'director_financiero')
        return jsonify({'requiere': _get_rol_activo(current_user) not in roles_auto, 'rol': _get_rol_activo(current_user)})
