# routes/contable.py — BLOQUE 5: Contabilidad Completa (v31)
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import logging

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

    # ── contable_asientos: Lista todos los asientos contables (/contable/asientos)
    @app.route('/contable/asientos')
    @login_required
    @requiere_modulo('finanzas')
    def contable_asientos():
        filtro = request.args.get('filtro', 'todos')
        desde  = request.args.get('desde', '')
        hasta  = request.args.get('hasta', '')
        vista  = request.args.get('vista', 'generados')  # generados | manuales

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

        # Dividir en generados y manuales
        TIPOS_GENERADOS = {'compra', 'venta', 'nomina', 'gasto'}
        if vista == 'manuales':
            asientos_filtrados = [a for a in asientos if a.tipo not in TIPOS_GENERADOS]
        else:
            asientos_filtrados = [a for a in asientos if a.tipo in TIPOS_GENERADOS]

        total_ingresos_list = sum(float(a.haber or 0) for a in asientos_filtrados if a.clasificacion == 'ingreso')
        total_egresos_list  = sum(float(a.debe or 0)  for a in asientos_filtrados if a.clasificacion == 'egreso')

        # Stats del mes actual
        mes_ini = date_type.today().replace(day=1)
        asientos_mes = AsientoContable.query.filter(AsientoContable.fecha >= mes_ini).all()
        ingresos_mes = sum(float(a.haber or 0) for a in asientos_mes if a.clasificacion == 'ingreso')
        gastos_mes   = sum(float(a.debe or 0)  for a in asientos_mes if a.clasificacion == 'egreso')

        return render_template('contable/asientos.html',
            asientos=asientos, asientos_filtrados=asientos_filtrados,
            filtro=filtro, desde=desde, hasta=hasta, vista=vista,
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
            oc_id_raw          = request.form.get('orden_compra_id', '')
            venta_id           = int(venta_id_raw) if venta_id_raw.isdigit() else None
            proveedor_id       = int(proveedor_id_raw) if proveedor_id_raw.isdigit() else None
            orden_compra_id    = int(oc_id_raw) if oc_id_raw.isdigit() else None

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

            cuenta_debe_val = request.form.get('cuenta_debe', '') or None
            cuenta_haber_val = request.form.get('cuenta_haber', '') or None
            asiento = AsientoContable(
                numero=numero, fecha=fecha_obj, descripcion=descripcion,
                tipo=tipo, referencia=referencia, notas=notas,
                debe=debe, haber=haber,
                cuenta_debe=cuenta_debe_val,
                cuenta_haber=cuenta_haber_val,
                clasificacion=clasificacion,
                venta_id=venta_id, proveedor_id=proveedor_id,
                orden_compra_id=orden_compra_id,
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
        ordenes_compra = OrdenCompra.query.filter(OrdenCompra.estado != 'cancelada').order_by(OrdenCompra.creado_en.desc()).limit(50).all()
        return render_template('contable/asiento_form.html',
            obj=None, ventas=ventas, proveedores=proveedores,
            ordenes_compra=ordenes_compra,
            titulo='Nuevo asiento contable',
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
            asiento.cuenta_debe     = request.form.get('cuenta_debe', '') or asiento.cuenta_debe
            asiento.cuenta_haber    = request.form.get('cuenta_haber', '') or asiento.cuenta_haber

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
        ordenes_compra = OrdenCompra.query.filter(OrdenCompra.estado != 'cancelada').order_by(OrdenCompra.creado_en.desc()).limit(50).all()
        return render_template('contable/asiento_form.html',
            obj=asiento, ventas=ventas, proveedores=proveedores,
            ordenes_compra=ordenes_compra,
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

    # ── Helper: procesar pago/cobro en asiento contable
    def _procesar_pago_asiento(asiento, campo_total):
        """
        Procesa la logica comun de confirmar pago/cobro.
        campo_total: 'debe' para egresos, 'haber' para ingresos.
        Retorna (monto_aplicado, error_msg) — si error_msg no es None, abortar.
        Usa SELECT FOR UPDATE (PostgreSQL) para prevenir race conditions.
        """
        # Re-leer con lock para prevenir doble pago concurrente
        asiento = db.session.get(AsientoContable, asiento.id, with_for_update=True)
        if not asiento:
            return 0, 'Asiento no encontrado.'
        if asiento.estado_pago == 'completo':
            return 0, 'Este asiento ya esta completamente pagado.'

        tipo_pago = request.form.get('tipo_pago', 'parcial')
        monto = float(request.form.get('monto_pago') or 0)
        metodo = request.form.get('metodo_pago', '')
        ref = request.form.get('referencia_pago', '')

        total_asiento = float(getattr(asiento, campo_total) or 0)
        if total_asiento <= 0:
            return 0, 'El asiento no tiene monto registrado.'
        ya_pagado = float(asiento.monto_pagado or 0)
        restante = max(0, total_asiento - ya_pagado)

        if restante <= 0:
            return 0, 'No hay saldo pendiente en este asiento.'

        if tipo_pago == 'total':
            monto = restante

        if monto <= 0:
            return 0, 'El monto debe ser mayor a cero.'
        # Cap: nunca exceder el restante
        monto = min(monto, restante)

        nuevo_pagado = ya_pagado + monto
        # Cap final: nunca exceder total
        asiento.monto_pagado = min(nuevo_pagado, total_asiento)
        asiento.metodo_pago = metodo or asiento.metodo_pago
        asiento.nro_transaccion = ref or asiento.nro_transaccion
        asiento.fecha_pago = date_type.today()

        if asiento.monto_pagado >= total_asiento:
            asiento.estado_pago = 'completo'
            asiento.estado_asiento = 'aprobado'
        else:
            asiento.estado_pago = 'parcial'

        return monto, None

    # ── confirmar_pago: Confirmar pago de egreso vinculado a OC (/contable/asientos/<id>/confirmar-pago)
    @app.route('/contable/asientos/<int:id>/confirmar-pago', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_confirmar_pago(id):
        asiento = AsientoContable.query.get_or_404(id)
        if asiento.estado_pago == 'completo':
            flash('Este asiento ya esta completamente pagado.', 'warning')
            return redirect(url_for('contable_asientos', vista='generados'))

        monto, error = _procesar_pago_asiento(asiento, 'debe')
        if error:
            flash(error, 'warning')
            return redirect(url_for('contable_asientos', vista='generados'))

        # Actualizar OC vinculada (con cap al total)
        if asiento.orden_compra_id:
            oc = db.session.get(OrdenCompra, asiento.orden_compra_id)
            if oc:
                nuevo_pagado_oc = min(float(oc.monto_pagado or 0) + monto, float(oc.total or 0))
                oc.monto_pagado = nuevo_pagado_oc
                if asiento.estado_pago == 'completo':
                    oc.estado = 'en_espera_producto'
                    oc.estado_proveedor = 'anticipo_enviado'
                else:
                    oc.estado = 'anticipo_pagado'
                    oc.estado_proveedor = 'anticipo_enviado'

        db.session.commit()
        flash(f'Pago de {moneda(monto)} confirmado para asiento {asiento.numero}.', 'success')
        # Redirect preservando _embed si aplica
        if request.args.get('_embed') == '1' or request.form.get('_embed') == '1':
            return redirect(url_for('contable_asientos', vista='generados', _embed='1'))
        return redirect(url_for('contable_asientos', vista='generados'))


    # ── confirmar_ingreso: Confirmar cobro recibido vinculado a venta (/contable/asientos/<id>/confirmar-ingreso)
    @app.route('/contable/asientos/<int:id>/confirmar-ingreso', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_confirmar_ingreso(id):
        asiento = AsientoContable.query.get_or_404(id)
        if asiento.estado_pago == 'completo':
            flash('Este asiento ya esta completamente cobrado.', 'warning')
            return redirect(url_for('contable_asientos', vista='generados'))

        monto, error = _procesar_pago_asiento(asiento, 'haber')
        if error:
            flash(error, 'warning')
            return redirect(url_for('contable_asientos', vista='generados'))

        # Actualizar venta vinculada (con cap al total)
        if asiento.venta_id:
            venta = db.session.get(Venta, asiento.venta_id)
            if venta:
                total_venta = float(venta.total or 0)
                venta.monto_anticipo_recibido = min(float(venta.monto_anticipo_recibido or 0) + monto, total_venta)
                venta.monto_pagado_total = min(float(venta.monto_pagado_total or 0) + monto, total_venta)
                venta.estado_cliente_pago = 'recibido'
                if asiento.estado_pago == 'completo':
                    if venta.estado in ('negociacion', 'prospecto'):
                        venta.estado = 'anticipo_pagado'
                        # Disparar side effects: reservar stock y generar OC automaticas
                        try:
                            from services.inventario import InventarioService
                            InventarioService.reservar_stock_venta(venta)
                        except Exception as ex_inv:
                            logging.warning(f'confirmar_ingreso: reservar_stock error: {ex_inv}')

        db.session.commit()
        flash(f'Cobro de {moneda(monto)} confirmado para asiento {asiento.numero}.', 'success')
        if request.args.get('_embed') == '1' or request.form.get('_embed') == '1':
            return redirect(url_for('contable_asientos', vista='generados', _embed='1'))
        return redirect(url_for('contable_asientos', vista='generados'))


    # ── PDF caja chica (/contable/asientos/<id>/pdf-caja-chica)
    @app.route('/contable/asientos/<int:id>/pdf-caja-chica')
    @login_required
    @requiere_modulo('finanzas')
    def contable_pdf_caja_chica(id):
        asiento = AsientoContable.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('contable/comprobante_caja_chica.html',
            asiento=asiento, empresa=empresa)


    # ── contable_comprobante: Generar PDF/comprobante (/contable/asientos/<id>/comprobante)
    @app.route('/contable/asientos/<int:id>/comprobante')
    @login_required
    @requiere_modulo('finanzas')
    def contable_comprobante(id):
        asiento = AsientoContable.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('contable/comprobante.html',
            asiento=asiento, empresa=empresa)


    # ══════════════════════════════════════════════════════════════════════════
    # PUC — Plan Único de Cuentas (v34)
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/contable/puc')
    @login_required
    @requiere_modulo('finanzas')
    def contable_puc():
        """Navegador del Plan Único de Cuentas."""
        buscar = request.args.get('q', '').strip()
        clase_f = request.args.get('clase', '')
        q = CuentaPUC.query.filter_by(activo=True)
        if buscar:
            q = q.filter(db.or_(
                CuentaPUC.codigo.ilike(f'%{buscar}%'),
                CuentaPUC.nombre.ilike(f'%{buscar}%')
            ))
        if clase_f:
            q = q.filter(CuentaPUC.codigo.startswith(clase_f))
        cuentas = q.order_by(CuentaPUC.codigo).all()
        clases = CuentaPUC.query.filter_by(nivel=1, activo=True).order_by(CuentaPUC.codigo).all()
        return render_template('contable/puc.html', cuentas=cuentas, clases=clases,
                               buscar=buscar, clase_f=clase_f)

    @app.route('/contable/puc/nuevo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_puc_nuevo():
        """Agregar cuenta auxiliar al PUC."""
        if current_user.rol not in ('admin', 'director_financiero', 'contador'):
            flash('Solo contadores o directores pueden agregar cuentas.', 'danger')
            return redirect(url_for('contable_puc'))
        if request.method == 'POST':
            codigo = request.form.get('codigo', '').strip()
            nombre = request.form.get('nombre', '').strip()
            padre = request.form.get('padre_codigo', '').strip()
            if not codigo or not nombre:
                flash('Código y nombre son requeridos.', 'danger')
                return redirect(url_for('contable_puc_nuevo'))
            if CuentaPUC.query.filter_by(codigo=codigo).first():
                flash(f'Ya existe la cuenta {codigo}.', 'warning')
                return redirect(url_for('contable_puc_nuevo'))
            # Determinar naturaleza y tipo del padre
            padre_obj = CuentaPUC.query.filter_by(codigo=padre).first() if padre else None
            c = CuentaPUC(
                codigo=codigo, nombre=nombre,
                nivel=len(codigo) if len(codigo) <= 2 else (3 if len(codigo) <= 4 else 5),
                naturaleza=padre_obj.naturaleza if padre_obj else request.form.get('naturaleza', 'debito'),
                tipo=padre_obj.tipo if padre_obj else request.form.get('tipo', 'gasto'),
                padre_codigo=padre or None,
                acepta_mov=True, activo=True,
                descripcion=request.form.get('descripcion', '')
            )
            db.session.add(c); db.session.commit()
            flash(f'Cuenta {codigo} — {nombre} creada.', 'success')
            return redirect(url_for('contable_puc'))
        padres = CuentaPUC.query.filter(CuentaPUC.acepta_mov == False, CuentaPUC.activo == True)\
                     .order_by(CuentaPUC.codigo).all()
        return render_template('contable/puc_form.html', padres=padres)

    @app.route('/contable/puc/api/buscar')
    @login_required
    @requiere_modulo('finanzas')
    def api_puc_buscar():
        """API para autocompletar cuentas PUC. Sin query devuelve todas las que aceptan movimiento."""
        q = request.args.get('q', '').strip()
        todas = request.args.get('todas', '')
        query = CuentaPUC.query.filter(CuentaPUC.activo == True)
        if todas:
            # Todas las cuentas (incluye padres para estructura)
            query = query.order_by(CuentaPUC.codigo)
        elif q and len(q) >= 1:
            query = query.filter(
                CuentaPUC.acepta_mov == True,
                db.or_(CuentaPUC.codigo.ilike(f'%{q}%'), CuentaPUC.nombre.ilike(f'%{q}%'))
            ).order_by(CuentaPUC.codigo).limit(30)
        else:
            # Sin query: devolver las mas usadas (acepta_mov=True)
            query = query.filter(CuentaPUC.acepta_mov == True).order_by(CuentaPUC.codigo)
        cuentas = query.all()
        return jsonify([{
            'id': c.id, 'codigo': c.codigo, 'nombre': c.nombre,
            'naturaleza': c.naturaleza, 'tipo': c.tipo, 'nivel': c.nivel,
            'acepta_mov': c.acepta_mov,
            'descripcion': c.descripcion or ''
        } for c in cuentas])


    # ══════════════════════════════════════════════════════════════════════════
    # REPORTES FINANCIEROS (v34)
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/contable/balance-prueba')
    @login_required
    @requiere_modulo('finanzas')
    def contable_balance_prueba():
        """Balance de Prueba — saldo de cada cuenta con movimiento."""
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        from calendar import monthrange
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        # Obtener todas las líneas del periodo
        lineas = db.session.query(
            LineaAsiento.cuenta_puc_id,
            db.func.sum(LineaAsiento.debe).label('total_debe'),
            db.func.sum(LineaAsiento.haber).label('total_haber')
        ).join(AsientoContable).filter(
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin,
            AsientoContable.estado_asiento != 'anulado'
        ).group_by(LineaAsiento.cuenta_puc_id).all()

        filas = []
        total_debe = total_haber = 0
        for cuenta_id, td, th in lineas:
            cuenta = db.session.get(CuentaPUC, cuenta_id)
            if not cuenta: continue
            td = float(td or 0); th = float(th or 0)
            saldo = td - th if cuenta.naturaleza == 'debito' else th - td
            filas.append({'cuenta': cuenta, 'debe': td, 'haber': th, 'saldo': saldo})
            total_debe += td; total_haber += th

        filas.sort(key=lambda x: x['cuenta'].codigo)
        return render_template('contable/balance_prueba.html', filas=filas,
                               total_debe=total_debe, total_haber=total_haber,
                               periodo=periodo)

    @app.route('/contable/balance-general')
    @login_required
    @requiere_modulo('finanzas')
    def contable_balance_general():
        """Balance General — Activos = Pasivos + Patrimonio."""
        corte = request.args.get('corte', date_type.today().isoformat())
        try:
            fecha_corte = datetime.strptime(corte, '%Y-%m-%d').date()
        except:
            fecha_corte = date_type.today()

        def _saldo_clase(prefijo):
            lineas = db.session.query(
                db.func.sum(LineaAsiento.debe).label('td'),
                db.func.sum(LineaAsiento.haber).label('th')
            ).join(AsientoContable).join(CuentaPUC, LineaAsiento.cuenta_puc_id == CuentaPUC.id).filter(
                AsientoContable.fecha <= fecha_corte,
                AsientoContable.estado_asiento != 'anulado',
                CuentaPUC.codigo.startswith(prefijo)
            ).first()
            td = float(lineas.td or 0) if lineas else 0
            th = float(lineas.th or 0) if lineas else 0
            return td, th

        td1, th1 = _saldo_clase('1')
        activos = td1 - th1

        td2, th2 = _saldo_clase('2')
        pasivos = th2 - td2

        td3, th3 = _saldo_clase('3')
        patrimonio = th3 - td3

        # Cuentas detalladas por grupo
        def _detalle_clase(prefijo):
            return CuentaPUC.query.filter(
                CuentaPUC.codigo.startswith(prefijo),
                CuentaPUC.nivel == 3, CuentaPUC.activo == True
            ).order_by(CuentaPUC.codigo).all()

        empresa = ConfigEmpresa.query.first()
        return render_template('contable/balance_general.html',
            activos=activos, pasivos=pasivos, patrimonio=patrimonio,
            activos_det=_detalle_clase('1'), pasivos_det=_detalle_clase('2'),
            patrimonio_det=_detalle_clase('3'),
            fecha_corte=fecha_corte, empresa=empresa)

    @app.route('/contable/estado-resultados')
    @login_required
    @requiere_modulo('finanzas')
    def contable_estado_resultados():
        """Estado de Resultados — Ingresos - Gastos - Costos = Utilidad."""
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        from calendar import monthrange
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        def _total_clase(prefijo):
            r = db.session.query(
                db.func.sum(LineaAsiento.debe).label('td'),
                db.func.sum(LineaAsiento.haber).label('th')
            ).join(AsientoContable).join(CuentaPUC, LineaAsiento.cuenta_puc_id == CuentaPUC.id).filter(
                AsientoContable.fecha >= mes_ini, AsientoContable.fecha <= mes_fin,
                AsientoContable.estado_asiento != 'anulado',
                CuentaPUC.codigo.startswith(prefijo)
            ).first()
            td = float(r.td or 0) if r else 0
            th = float(r.th or 0) if r else 0
            return td, th

        td4, th4 = _total_clase('4')
        ingresos = th4 - td4  # Clase 4: naturaleza crédito

        td5, th5 = _total_clase('5')
        gastos = td5 - th5  # Clase 5: naturaleza débito

        td6, th6 = _total_clase('6')
        costos_venta = td6 - th6  # Clase 6

        td7, th7 = _total_clase('7')
        costos_produccion = td7 - th7  # Clase 7

        utilidad_bruta = ingresos - costos_venta - costos_produccion
        utilidad_operacional = utilidad_bruta - gastos
        # Simplificado: utilidad neta = operacional (sin impuestos por ahora)
        utilidad_neta = utilidad_operacional

        empresa = ConfigEmpresa.query.first()
        return render_template('contable/estado_resultados.html',
            ingresos=ingresos, gastos=gastos, costos_venta=costos_venta,
            costos_produccion=costos_produccion, utilidad_bruta=utilidad_bruta,
            utilidad_operacional=utilidad_operacional, utilidad_neta=utilidad_neta,
            periodo=periodo, empresa=empresa)

    @app.route('/contable/auxiliar/<codigo>')
    @login_required
    @requiere_modulo('finanzas')
    def contable_auxiliar(codigo):
        """Libro auxiliar por cuenta PUC."""
        cuenta = CuentaPUC.query.filter_by(codigo=codigo).first_or_404()
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        from calendar import monthrange
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        movimientos = LineaAsiento.query.join(AsientoContable).filter(
            LineaAsiento.cuenta_puc_id == cuenta.id,
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin,
            AsientoContable.estado_asiento != 'anulado'
        ).order_by(AsientoContable.fecha, AsientoContable.numero).all()

        saldo = 0
        filas = []
        for m in movimientos:
            if cuenta.naturaleza == 'debito':
                saldo += (m.debe or 0) - (m.haber or 0)
            else:
                saldo += (m.haber or 0) - (m.debe or 0)
            filas.append({'linea': m, 'saldo_acum': saldo})

        return render_template('contable/auxiliar.html', cuenta=cuenta, filas=filas,
                               periodo=periodo, saldo_final=saldo)


    # ══════════════════════════════════════════════════════════════════════════
    # CIERRE DE PERIODO + IVA + RETENCION (v38 — Ley colombiana)
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/contable/cierre-periodo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_cierre_periodo():
        """Cierre contable mensual — marca asientos como cerrados y genera resumen."""
        if current_user.rol not in ('admin', 'director_financiero', 'contador'):
            flash('Solo admin, director financiero o contador pueden cerrar periodos.', 'danger')
            return redirect(url_for('contable_index'))

        from calendar import monthrange
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except Exception:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        if request.method == 'POST':
            # Marcar todos los asientos del periodo como aprobados
            asientos_periodo = AsientoContable.query.filter(
                AsientoContable.fecha >= mes_ini,
                AsientoContable.fecha <= mes_fin,
                AsientoContable.estado_asiento != 'anulado'
            ).all()
            cerrados = 0
            for a in asientos_periodo:
                if a.estado_asiento == 'borrador':
                    a.estado_asiento = 'aprobado'
                a.periodo = periodo
                cerrados += 1
            db.session.commit()
            flash(f'Periodo {periodo} cerrado. {cerrados} asiento(s) marcados.', 'success')
            return redirect(url_for('contable_cierre_periodo', periodo=periodo))

        # Estadisticas del periodo
        asientos = AsientoContable.query.filter(
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin,
            AsientoContable.estado_asiento != 'anulado'
        ).all()
        total_debe = sum(float(a.debe or 0) for a in asientos)
        total_haber = sum(float(a.haber or 0) for a in asientos)
        n_borrador = sum(1 for a in asientos if a.estado_asiento == 'borrador')
        n_aprobado = sum(1 for a in asientos if a.estado_asiento == 'aprobado')
        ya_cerrado = all(a.periodo == periodo for a in asientos) if asientos else False

        return render_template('contable/cierre_periodo.html',
            periodo=periodo, anio=anio, mes=mes,
            total_asientos=len(asientos), n_borrador=n_borrador, n_aprobado=n_aprobado,
            total_debe=total_debe, total_haber=total_haber,
            diferencia=abs(total_debe - total_haber),
            ya_cerrado=ya_cerrado)


    @app.route('/contable/iva')
    @login_required
    @requiere_modulo('finanzas')
    def contable_iva():
        """Cruce de IVA generado (ventas) vs IVA descontable (compras) del periodo."""
        from calendar import monthrange
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except Exception:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        # IVA generado: IVA de ventas del periodo
        ventas_periodo = Venta.query.filter(
            Venta.creado_en >= datetime(anio, mes, 1),
            Venta.estado.in_(['anticipo_pagado', 'pagado', 'completado'])
        ).all()
        iva_generado = sum(float(v.iva or 0) for v in ventas_periodo)

        # IVA descontable: IVA de compras (OC) del periodo
        ocs_periodo = OrdenCompra.query.filter(
            OrdenCompra.fecha_emision >= mes_ini,
            OrdenCompra.fecha_emision <= mes_fin,
            OrdenCompra.estado.notin_(['cancelada'])
        ).all()
        iva_descontable = sum(float(oc.iva or 0) for oc in ocs_periodo)

        iva_a_pagar = max(0, iva_generado - iva_descontable)

        return render_template('contable/iva.html',
            periodo=periodo,
            iva_generado=iva_generado, n_ventas=len(ventas_periodo),
            iva_descontable=iva_descontable, n_compras=len(ocs_periodo),
            iva_a_pagar=iva_a_pagar)


    @app.route('/contable/retenciones')
    @login_required
    @requiere_modulo('finanzas')
    def contable_retenciones():
        """Resumen de retenciones en la fuente del periodo."""
        from calendar import monthrange
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except Exception:
            anio, mes = datetime.utcnow().year, datetime.utcnow().month
        mes_ini = date_type(anio, mes, 1)
        mes_fin = date_type(anio, mes, monthrange(anio, mes)[1])

        # Compras del periodo para calcular retenciones
        compras = CompraMateria.query.filter(
            CompraMateria.fecha >= mes_ini,
            CompraMateria.fecha <= mes_fin
        ).all()

        # Retencion en la fuente: 2.5% sobre compras > 27 UVT (aprox $1,300,000 COP 2025)
        UVT_2025 = 49799  # UVT 2025
        BASE_RETEFUENTE = 27 * UVT_2025  # ~$1,344,573
        TASA_RETE = 0.025  # 2.5% compras
        total_base_rete = 0
        total_retenido = 0
        detalles = []
        for c in compras:
            if float(c.costo_total or 0) >= BASE_RETEFUENTE:
                rete = round(float(c.costo_total) * TASA_RETE)
                total_base_rete += float(c.costo_total)
                total_retenido += rete
                detalles.append({
                    'nombre': c.nombre_item,
                    'proveedor': c.proveedor or '',
                    'fecha': c.fecha,
                    'base': float(c.costo_total),
                    'retencion': rete
                })

        # Gastos del periodo
        gastos = GastoOperativo.query.filter(
            GastoOperativo.fecha >= mes_ini,
            GastoOperativo.fecha <= mes_fin
        ).all()
        for g in gastos:
            if float(g.monto or 0) >= BASE_RETEFUENTE and g.tipo != 'Nomina':
                rete = round(float(g.monto) * TASA_RETE)
                total_base_rete += float(g.monto)
                total_retenido += rete
                detalles.append({
                    'nombre': g.descripcion or g.tipo,
                    'proveedor': '',
                    'fecha': g.fecha,
                    'base': float(g.monto),
                    'retencion': rete
                })

        return render_template('contable/retenciones.html',
            periodo=periodo,
            total_base=total_base_rete, total_retenido=total_retenido,
            base_minima=BASE_RETEFUENTE, tasa=TASA_RETE*100,
            detalles=detalles)


    # ══════════════════════════════════════════════════════════════════════════
    # CONCILIACIÓN BANCARIA (v40)
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/contable/conciliacion')
    @login_required
    @requiere_modulo('finanzas')
    def contable_conciliacion():
        """Página principal de conciliación bancaria."""
        banco_filtro = request.args.get('banco', '')
        desde_str    = request.args.get('desde', '')
        hasta_str    = request.args.get('hasta', '')

        q = MovimientoBancario.query
        if banco_filtro:
            q = q.filter(MovimientoBancario.banco == banco_filtro)
        if desde_str:
            try:
                q = q.filter(MovimientoBancario.fecha >= datetime.strptime(desde_str, '%Y-%m-%d').date())
            except Exception:
                pass
        if hasta_str:
            try:
                q = q.filter(MovimientoBancario.fecha <= datetime.strptime(hasta_str, '%Y-%m-%d').date())
            except Exception:
                pass

        movimientos = q.order_by(MovimientoBancario.fecha.desc(), MovimientoBancario.id.desc()).all()

        total_movs      = len(movimientos)
        total_conciliados   = sum(1 for m in movimientos if m.conciliado)
        total_pendientes    = total_movs - total_conciliados
        suma_debitos        = sum(m.monto for m in movimientos if m.tipo == 'debito')
        suma_creditos       = sum(m.monto for m in movimientos if m.tipo == 'credito')

        # Lista de bancos cargados (para el filtro)
        bancos = [r[0] for r in db.session.query(MovimientoBancario.banco).distinct().all() if r[0]]

        # Asientos sin conciliar para el dropdown de match manual
        asientos_disponibles = AsientoContable.query.filter(
            ~AsientoContable.id.in_(
                db.session.query(MovimientoBancario.asiento_id).filter(
                    MovimientoBancario.asiento_id != None
                )
            )
        ).order_by(AsientoContable.fecha.desc()).limit(200).all()

        return render_template('contable/conciliacion.html',
            movimientos=movimientos,
            total_movs=total_movs,
            total_conciliados=total_conciliados,
            total_pendientes=total_pendientes,
            suma_debitos=suma_debitos,
            suma_creditos=suma_creditos,
            bancos=bancos,
            banco_filtro=banco_filtro,
            desde=desde_str,
            hasta=hasta_str,
            asientos_disponibles=asientos_disponibles,
            hoy=date_type.today().isoformat())


    @app.route('/contable/conciliacion/upload', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_conciliacion_upload():
        """Importar extracto bancario CSV."""
        import csv, io

        archivo = request.files.get('archivo')
        banco   = request.form.get('banco', '').strip()

        if not archivo or not archivo.filename:
            flash('Selecciona un archivo CSV.', 'warning')
            return redirect(url_for('contable_conciliacion'))
        if not banco:
            flash('Indica el nombre del banco.', 'warning')
            return redirect(url_for('contable_conciliacion'))

        try:
            contenido = archivo.read().decode('utf-8-sig', errors='replace')
        except Exception:
            flash('No se pudo leer el archivo. Asegúrate de que esté en UTF-8.', 'danger')
            return redirect(url_for('contable_conciliacion'))

        # Auto-detectar delimitador: semicolon o comma
        muestra = contenido[:2000]
        dialecto = csv.Sniffer().sniff(muestra, delimiters=';,')
        reader = csv.DictReader(io.StringIO(contenido), dialect=dialecto)

        # Normalizar nombres de columnas (minúsculas, sin espacios)
        def _norm(k):
            return k.lower().strip().replace(' ', '_').replace('ó', 'o').replace('é', 'e')

        importados = 0
        errores    = 0
        for fila in reader:
            fila_norm = {_norm(k): v.strip() if v else '' for k, v in fila.items() if k}

            # Fecha — acepta dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd
            fecha_raw = (fila_norm.get('fecha') or fila_norm.get('date') or '').strip()
            fecha_obj = None
            for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%Y/%m/%d'):
                try:
                    fecha_obj = datetime.strptime(fecha_raw, fmt).date()
                    break
                except Exception:
                    pass
            if not fecha_obj:
                errores += 1
                continue

            descripcion = (fila_norm.get('descripcion') or fila_norm.get('description')
                           or fila_norm.get('concepto') or fila_norm.get('detalle') or '')
            referencia  = (fila_norm.get('referencia') or fila_norm.get('ref')
                           or fila_norm.get('numero') or fila_norm.get('nro') or '')

            # Débito / Crédito — admite columna única 'monto' con signo o columnas separadas
            debito_raw  = (fila_norm.get('debito') or fila_norm.get('debitos')
                           or fila_norm.get('cargo') or fila_norm.get('cargos') or '0')
            credito_raw = (fila_norm.get('credito') or fila_norm.get('creditos')
                           or fila_norm.get('abono') or fila_norm.get('abonos') or '0')
            monto_raw   = fila_norm.get('monto') or fila_norm.get('valor') or ''

            def _to_float(s):
                """Limpia formato colombiano: 1.234.567,89 → 1234567.89"""
                s = s.strip().replace('$', '').replace(' ', '')
                # Si tiene coma Y punto: asumir punto=miles, coma=decimales
                if ',' in s and '.' in s:
                    s = s.replace('.', '').replace(',', '.')
                elif ',' in s:
                    s = s.replace(',', '.')
                else:
                    s = s.replace('.', '', s.count('.') - 1) if s.count('.') > 1 else s
                try:
                    return abs(float(s))
                except Exception:
                    return 0.0

            debito  = _to_float(debito_raw)
            credito = _to_float(credito_raw)

            # Si viene en columna única 'monto'
            if debito == 0 and credito == 0 and monto_raw:
                val = _to_float(monto_raw)
                raw_s = monto_raw.strip().replace('$', '').replace(' ', '')
                if raw_s.startswith('-'):
                    debito = val
                else:
                    credito = val

            if debito == 0 and credito == 0:
                errores += 1
                continue

            saldo_raw = fila_norm.get('saldo') or fila_norm.get('saldo_disponible') or ''
            saldo     = _to_float(saldo_raw) if saldo_raw else None

            if debito > 0:
                mov = MovimientoBancario(
                    fecha=fecha_obj, descripcion=descripcion[:300], referencia=referencia[:100],
                    monto=debito, tipo='debito', saldo=saldo, banco=banco, conciliado=False
                )
                db.session.add(mov)
                importados += 1
            if credito > 0:
                mov = MovimientoBancario(
                    fecha=fecha_obj, descripcion=descripcion[:300], referencia=referencia[:100],
                    monto=credito, tipo='credito', saldo=saldo, banco=banco, conciliado=False
                )
                db.session.add(mov)
                importados += 1

        db.session.commit()
        if importados:
            flash(f'{importados} movimiento(s) importado(s) correctamente.{" " + str(errores) + " fila(s) omitidas." if errores else ""}', 'success')
        else:
            flash(f'No se importaron movimientos. Verifica el formato del CSV. ({errores} filas con error)', 'warning')
        return redirect(url_for('contable_conciliacion', banco=banco))


    @app.route('/contable/conciliacion/auto-match', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_conciliacion_auto_match():
        """Conciliar automáticamente movimientos vs asientos por monto y fecha (±3 días)."""
        pendientes = MovimientoBancario.query.filter_by(conciliado=False).all()
        if not pendientes:
            flash('No hay movimientos pendientes de conciliar.', 'info')
            return redirect(url_for('contable_conciliacion'))

        conciliados = 0
        for mov in pendientes:
            fecha_min = mov.fecha - timedelta(days=3)
            fecha_max = mov.fecha + timedelta(days=3)
            clasificacion_buscada = 'egreso' if mov.tipo == 'debito' else 'ingreso'

            # Buscar asiento con mismo monto y fecha cercana que no esté ya vinculado
            candidatos = AsientoContable.query.filter(
                AsientoContable.clasificacion == clasificacion_buscada,
                AsientoContable.fecha >= fecha_min,
                AsientoContable.fecha <= fecha_max,
                ~AsientoContable.id.in_(
                    db.session.query(MovimientoBancario.asiento_id).filter(
                        MovimientoBancario.asiento_id != None
                    )
                )
            ).all()

            mejor = None
            for a in candidatos:
                monto_asiento = float(a.debe or 0) if clasificacion_buscada == 'egreso' else float(a.haber or 0)
                if abs(monto_asiento - mov.monto) < 1.0:
                    mejor = a
                    break

            if mejor:
                mov.asiento_id = mejor.id
                mov.conciliado = True
                conciliados += 1

        db.session.commit()
        flash(f'Conciliación automática completada: {conciliados} movimiento(s) conciliado(s).', 'success')
        return redirect(url_for('contable_conciliacion'))


    @app.route('/contable/conciliacion/<int:id>/match', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_conciliacion_match(id):
        """Vincular manualmente un movimiento bancario con un asiento contable."""
        mov = MovimientoBancario.query.get_or_404(id)
        asiento_id_raw = request.form.get('asiento_id', '')
        if not asiento_id_raw or not asiento_id_raw.isdigit():
            flash('Selecciona un asiento válido.', 'warning')
            return redirect(url_for('contable_conciliacion'))
        asiento = AsientoContable.query.get_or_404(int(asiento_id_raw))
        mov.asiento_id = asiento.id
        mov.conciliado = True
        db.session.commit()
        flash(f'Movimiento vinculado al asiento {asiento.numero}.', 'success')
        return redirect(url_for('contable_conciliacion'))


    @app.route('/contable/conciliacion/<int:id>/unmatch', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def contable_conciliacion_unmatch(id):
        """Deshacer la vinculación de un movimiento bancario."""
        mov = MovimientoBancario.query.get_or_404(id)
        mov.asiento_id = None
        mov.conciliado = False
        db.session.commit()
        flash('Conciliación deshecha.', 'info')
        return redirect(url_for('contable_conciliacion'))
