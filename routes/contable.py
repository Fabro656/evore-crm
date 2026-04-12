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

            asiento = AsientoContable(
                numero=numero, fecha=fecha_obj, descripcion=descripcion,
                tipo=tipo, referencia=referencia, notas=notas,
                debe=debe, haber=haber,
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
        """
        tipo_pago = request.form.get('tipo_pago', 'parcial')
        monto = float(request.form.get('monto_pago') or 0)
        metodo = request.form.get('metodo_pago', '')
        ref = request.form.get('referencia_pago', '')

        total_asiento = float(getattr(asiento, campo_total) or 0)
        ya_pagado = float(asiento.monto_pagado or 0)
        restante = total_asiento - ya_pagado

        if tipo_pago == 'total':
            monto = restante

        if monto <= 0:
            return 0, 'El monto debe ser mayor a cero.'
        if monto > restante:
            monto = restante

        asiento.monto_pagado = ya_pagado + monto
        asiento.metodo_pago = metodo or asiento.metodo_pago
        asiento.nro_transaccion = ref or asiento.nro_transaccion
        asiento.fecha_pago = date_type.today()

        if asiento.monto_pagado >= total_asiento:
            asiento.estado_pago = 'completo'
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

        # Actualizar OC vinculada
        if asiento.orden_compra_id:
            oc = db.session.get(OrdenCompra, asiento.orden_compra_id)
            if oc:
                oc.monto_pagado = float(oc.monto_pagado or 0) + monto
                if asiento.estado_pago == 'completo':
                    oc.estado = 'en_espera_producto'
                else:
                    oc.estado = 'anticipo_pagado'

        db.session.commit()
        flash(f'Pago de {moneda(monto)} confirmado para asiento {asiento.numero}.', 'success')
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

        # Actualizar venta vinculada
        if asiento.venta_id:
            venta = db.session.get(Venta, asiento.venta_id)
            if venta:
                venta.monto_anticipo_recibido = float(venta.monto_anticipo_recibido or 0) + monto
                venta.monto_pagado_total = float(venta.monto_pagado_total or 0) + monto
                if asiento.estado_pago == 'completo':
                    # Si el pago completo cubre el anticipo, avanzar estado
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
        """API para autocompletar cuentas PUC en formularios."""
        q = request.args.get('q', '').strip()
        if len(q) < 2:
            return jsonify([])
        cuentas = CuentaPUC.query.filter(
            CuentaPUC.acepta_mov == True, CuentaPUC.activo == True,
            db.or_(CuentaPUC.codigo.ilike(f'%{q}%'), CuentaPUC.nombre.ilike(f'%{q}%'))
        ).order_by(CuentaPUC.codigo).limit(15).all()
        return jsonify([{'id': c.id, 'codigo': c.codigo, 'nombre': c.nombre,
                         'naturaleza': c.naturaleza, 'tipo': c.tipo} for c in cuentas])


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
