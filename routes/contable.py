# routes/contable.py — BLOQUE 5: Contabilidad Completa (v31)
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

    # ── contable_index: Dashboard contable (/contable)
    @app.route('/contable')
    @login_required
    @requiere_modulo('finanzas')
    def contable_index():
        import calendar as cal_mod
        hoy = date_type.today()
        anio = hoy.year

        # Navegación por mes
        mes_str = request.args.get('mes', hoy.strftime('%Y-%m'))
        try:
            anio_nav, mes_num = int(mes_str.split('-')[0]), int(mes_str.split('-')[1])
        except Exception:
            anio_nav, mes_num = anio, hoy.month
            mes_str = hoy.strftime('%Y-%m')
        anio = anio_nav

        _, ultimo_dia = cal_mod.monthrange(anio, mes_num)
        mes_ini  = date_type(anio, mes_num, 1)
        mes_fin  = date_type(anio, mes_num, ultimo_dia)

        # Navegador de meses (últimos 6)
        meses_nav = []
        for i in range(5, -1, -1):
            d = (hoy.replace(day=1) - timedelta(days=i * 28)).replace(day=1)
            meses_nav.append({'val': d.strftime('%Y-%m'), 'lbl': d.strftime('%b %Y')})

        # ── Ingresos: ventas pagadas del mes ──────────────────────────────────
        ventas_mes = Venta.query.filter(
            Venta.estado.in_(['pagado', 'anticipo_pagado', 'completado']),
            db.func.date(Venta.creado_en) >= mes_ini,
            db.func.date(Venta.creado_en) <= mes_fin
        ).all()
        total_ingresos = sum(float(v.total or 0) for v in ventas_mes)
        total_anticipo = sum(float(v.monto_anticipo or 0) for v in ventas_mes)

        # Asientos manuales de ingreso del mes (excluyendo inversiones de socio)
        try:
            asientos_ingreso = AsientoContable.query.filter(
                AsientoContable.clasificacion == 'ingreso',
                AsientoContable.tipo != 'inversion_socio',  # Excluir aportaciones de capital
                AsientoContable.fecha >= mes_ini,
                AsientoContable.fecha <= mes_fin
            ).all()
            total_ingresos_manual = sum(float(a.haber or 0) for a in asientos_ingreso)
            total_ingresos += total_ingresos_manual
        except Exception:
            asientos_ingreso = []

        # ── Egresos: gastos operativos (ya incluyen compras de materia prima) ──
        # NOTA: _save_compra() crea GastoOperativo automáticamente por cada compra,
        # por lo tanto NO sumamos CompraMateria por separado para evitar doble conteo.
        try:
            gastos_mes = GastoOperativo.query.filter(
                GastoOperativo.fecha >= mes_ini,
                GastoOperativo.fecha <= mes_fin
            ).all()
            total_gastos = sum(float(g.monto or 0) for g in gastos_mes)
        except Exception:
            gastos_mes, total_gastos = [], 0

        # Compras del mes (solo para desglose visual, NO sumadas en egresos)
        try:
            compras_mes = CompraMateria.query.filter(
                CompraMateria.fecha >= mes_ini,
                CompraMateria.fecha <= mes_fin
            ).all()
            total_compras = sum(float(c.costo_total or 0) for c in compras_mes)
        except Exception:
            compras_mes, total_compras = [], 0

        total_egresos = total_gastos
        utilidad      = total_ingresos - total_egresos

        # ── Impuestos estimados via _calcular_impuestos (utils) ───────────────
        try:
            total_impuestos, detalle_impuestos = _calcular_impuestos(total_ingresos, utilidad)
        except Exception:
            total_impuestos, detalle_impuestos = 0, []
        utilidad_neta = utilidad - total_impuestos

        # ── Cuentas por cobrar ────────────────────────────────────────────────
        cxc = Venta.query.filter(
            Venta.saldo > 0,
            Venta.estado.in_(['prospecto', 'negociacion', 'anticipo_pagado'])
        ).all()
        total_cxc = sum(float(v.saldo or 0) for v in cxc)

        # ── Inventario valorizado ─────────────────────────────────────────────
        try:
            inventario_valor = sum(
                (p.stock or 0) * (p.costo or 0)
                for p in Producto.query.filter_by(activo=True).all()
            )
        except Exception:
            inventario_valor = 0

        return render_template('contable/index.html',
            meses_nav=meses_nav, mes_str=mes_str, mes=mes_num, anio=anio,
            total_ingresos=total_ingresos, total_anticipo=total_anticipo,
            total_egresos=total_egresos, total_gastos=total_gastos,
            total_compras=total_compras, utilidad=utilidad,
            total_impuestos=total_impuestos, detalle_impuestos=detalle_impuestos,
            utilidad_neta=utilidad_neta,
            total_cxc=total_cxc, inventario_valor=inventario_valor,
            ventas_mes=ventas_mes, gastos_mes=gastos_mes, compras_mes=compras_mes,
            cxc=cxc)

    # ── contable_asientos: Lista todos los asientos manuales (/contable/asientos)
    @app.route('/contable/asientos')
    @login_required
    @requiere_modulo('finanzas')
    def contable_asientos():
        filtro = request.args.get('filtro', 'todos')
        desde  = request.args.get('desde', '')
        hasta  = request.args.get('hasta', '')

        q = AsientoContable.query

        if filtro == 'ingresos':
            q = q.filter(AsientoContable.clasificacion == 'ingreso')
        elif filtro == 'egresos':
            q = q.filter(AsientoContable.clasificacion == 'egreso')
        elif filtro == 'caja_chica':
            q = q.filter(AsientoContable.tipo == 'gasto_caja_chica')
        elif filtro == 'inversiones':
            q = q.filter(AsientoContable.tipo == 'inversion_socio')

        if desde:
            try:
                q = q.filter(AsientoContable.fecha >= datetime.strptime(desde, '%Y-%m-%d').date())
            except Exception:
                pass
        if hasta:
            try:
                q = q.filter(AsientoContable.fecha <= datetime.strptime(hasta, '%Y-%m-%d').date())
            except Exception:
                pass

        asientos = q.order_by(AsientoContable.fecha.desc(), AsientoContable.creado_en.desc()).all()

        total_ingresos_list = sum(float(a.haber or 0) for a in asientos if a.clasificacion == 'ingreso')
        total_egresos_list  = sum(float(a.debe or 0)  for a in asientos if a.clasificacion == 'egreso')

        # Stats del mes actual
        mes_ini = date_type.today().replace(day=1)
        asientos_mes = AsientoContable.query.filter(AsientoContable.fecha >= mes_ini).all()
        ingresos_mes = sum(float(a.haber or 0) for a in asientos_mes if a.clasificacion == 'ingreso')
        gastos_mes   = sum(float(a.debe or 0)  for a in asientos_mes if a.clasificacion == 'egreso')

        return render_template('contable/asientos.html',
            asientos=asientos, filtro=filtro, desde=desde, hasta=hasta,
            total_ingresos_list=total_ingresos_list,
            total_egresos_list=total_egresos_list,
            ingresos_mes=ingresos_mes, gastos_mes=gastos_mes,
            balance_mes=ingresos_mes - gastos_mes)

    # ── contable_asiento_nuevo: Crear asiento manual (/contable/asientos/nuevo)
    @app.route('/contable/asientos/nuevo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_asiento_nuevo():
        if request.method == 'POST':
            clasificacion   = request.form.get('clasificacion', 'egreso')
            fecha_str       = request.form.get('fecha', '')
            descripcion     = request.form.get('descripcion', '').strip()
            tipo            = request.form.get('tipo', 'manual')
            referencia      = request.form.get('referencia', '')
            notas           = request.form.get('notas', '')
            monto           = float(request.form.get('monto', 0) or 0)

            # Cuenta debe/haber según clasificación
            debe  = monto if clasificacion == 'egreso'  else 0.0
            haber = monto if clasificacion == 'ingreso' else 0.0

            try:
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            except Exception:
                fecha_obj = date_type.today()

            # FK opcionales
            venta_id_raw       = request.form.get('venta_id', '')
            proveedor_id_raw   = request.form.get('proveedor_id', '')
            venta_id           = int(venta_id_raw) if venta_id_raw.isdigit() else None
            proveedor_id       = int(proveedor_id_raw) if proveedor_id_raw.isdigit() else None

            # Campos de pago
            nro_transaccion = request.form.get('nro_transaccion', '') or None
            banco_nombre    = request.form.get('banco_nombre', '') or None
            banco_cuenta    = request.form.get('banco_cuenta', '') or None
            beneficiario    = request.form.get('beneficiario', '') or None
            metodo_pago     = request.form.get('metodo_pago', '') or None
            fecha_pago_str  = request.form.get('fecha_pago', '')
            try:
                fecha_pago  = datetime.strptime(fecha_pago_str, '%Y-%m-%d').date() if fecha_pago_str else None
            except Exception:
                fecha_pago  = None

            # Número automático
            ultimo  = AsientoContable.query.order_by(AsientoContable.id.desc()).first()
            n_ac    = (ultimo.id + 1) if ultimo else 1
            numero  = f'AC-{fecha_obj.year}-{n_ac:04d}'

            asiento = AsientoContable(
                numero=numero, fecha=fecha_obj, descripcion=descripcion,
                tipo=tipo, referencia=referencia, notas=notas,
                debe=debe, haber=haber,
                clasificacion=clasificacion,
                venta_id=venta_id, proveedor_id=proveedor_id,
                nro_transaccion=nro_transaccion, banco_nombre=banco_nombre,
                banco_cuenta=banco_cuenta, beneficiario=beneficiario,
                metodo_pago=metodo_pago, fecha_pago=fecha_pago,
                creado_por=current_user.id
            )
            db.session.add(asiento)
            db.session.commit()
            flash(f'Asiento {numero} creado correctamente.', 'success')
            return redirect(url_for('contable_asientos'))

        ventas     = Venta.query.order_by(Venta.creado_en.desc()).limit(100).all()
        proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all() if hasattr(Proveedor, 'activo') else Proveedor.query.order_by(Proveedor.nombre).all()
        return render_template('contable/asiento_form.html',
            obj=None, ventas=ventas, proveedores=proveedores,
            titulo='Nuevo asiento manual',
            hoy=date_type.today().isoformat(),
            clasificacion_default=request.args.get('clasificacion', 'egreso'))

    # ── contable_asiento_editar: Editar asiento (/contable/asientos/<id>/editar)
    @app.route('/contable/asientos/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_asiento_editar(id):
        asiento = AsientoContable.query.get_or_404(id)

        if request.method == 'POST':
            clasificacion  = request.form.get('clasificacion', asiento.clasificacion or 'egreso')
            fecha_str      = request.form.get('fecha', asiento.fecha.isoformat())
            monto          = float(request.form.get('monto', 0) or 0)

            asiento.clasificacion   = clasificacion
            asiento.fecha           = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            asiento.descripcion     = request.form.get('descripcion', asiento.descripcion)
            asiento.tipo            = request.form.get('tipo', asiento.tipo)
            asiento.referencia      = request.form.get('referencia', '')
            asiento.notas           = request.form.get('notas', '')
            asiento.debe            = monto if clasificacion == 'egreso'  else 0.0
            asiento.haber           = monto if clasificacion == 'ingreso' else 0.0

            venta_id_raw      = request.form.get('venta_id', '')
            proveedor_id_raw  = request.form.get('proveedor_id', '')
            asiento.venta_id      = int(venta_id_raw) if venta_id_raw.isdigit() else None
            asiento.proveedor_id  = int(proveedor_id_raw) if proveedor_id_raw.isdigit() else None

            asiento.nro_transaccion = request.form.get('nro_transaccion', '') or None
            asiento.banco_nombre    = request.form.get('banco_nombre', '') or None
            asiento.banco_cuenta    = request.form.get('banco_cuenta', '') or None
            asiento.beneficiario    = request.form.get('beneficiario', '') or None
            asiento.metodo_pago     = request.form.get('metodo_pago', '') or None
            fp_str = request.form.get('fecha_pago', '')
            try:
                asiento.fecha_pago = datetime.strptime(fp_str, '%Y-%m-%d').date() if fp_str else None
            except Exception:
                asiento.fecha_pago = None

            db.session.commit()

            # Si admin editó asiento ajeno → notificar al creador via Tarea
            if current_user.rol == 'admin' and asiento.creado_por and asiento.creado_por != current_user.id:
                try:
                    tarea_notif = Tarea(
                        titulo=f'El admin editó tu asiento {asiento.numero}',
                        descripcion=f'El administrador modificó el asiento contable {asiento.numero} '
                                    f'({asiento.descripcion[:80]}). Revisa los cambios si tienes dudas.',
                        estado='pendiente',
                        prioridad='media',
                        asignado_a=asiento.creado_por,
                        creado_por=current_user.id,
                        fecha_vencimiento=date_type.today()
                    )
                    db.session.add(tarea_notif)
                    db.session.commit()
                except Exception as _te:
                    logging.warning(f'No se pudo crear tarea de notificación: {_te}')

            flash(f'Asiento {asiento.numero} actualizado.', 'success')
            return redirect(url_for('contable_asientos'))

        ventas     = Venta.query.order_by(Venta.creado_en.desc()).limit(100).all()
        proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
        return render_template('contable/asiento_form.html',
            obj=asiento, ventas=ventas, proveedores=proveedores,
            titulo=f'Editar asiento {asiento.numero}',
            hoy=date_type.today().isoformat(),
            clasificacion_default=asiento.clasificacion or 'egreso')

    # ── contable_caja_chica: Marcar/desmarcar asiento como caja chica
    @app.route('/contable/asientos/<int:id>/caja-chica', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_caja_chica(id):
        asiento = AsientoContable.query.get_or_404(id)
        if asiento.tipo == 'gasto_caja_chica':
            asiento.tipo = 'gasto'
            msg = f'Asiento {asiento.numero} desmarcado de caja chica.'
        else:
            asiento.tipo = 'gasto_caja_chica'
            msg = f'Asiento {asiento.numero} marcado como gasto de caja chica.'
        db.session.commit()
        flash(msg, 'info')
        return redirect(url_for('contable_asientos'))

    # ── contable_asiento_eliminar: Eliminar asiento (/contable/asientos/<id>/eliminar)
    @app.route('/contable/asientos/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_asiento_eliminar(id):
        asiento = AsientoContable.query.get_or_404(id)
        numero = asiento.numero
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar asientos.', 'danger')
            return redirect(url_for('contable_asientos'))
        db.session.delete(asiento)
        db.session.commit()
        flash(f'Asiento {numero} eliminado.', 'info')
        return redirect(url_for('contable_asientos'))

    # ── contable_comprobante: Generar PDF/comprobante (/contable/asientos/<id>/comprobante)
    @app.route('/contable/asientos/<int:id>/comprobante')
    @login_required
    @requiere_modulo('finanzas')
    def contable_comprobante(id):
        asiento = AsientoContable.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('contable/comprobante.html',
            asiento=asiento, empresa=empresa)
