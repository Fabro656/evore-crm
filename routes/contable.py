# routes/contable.py — BLOQUE 5: Contabilidad Completa (v30)
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
    def _noop(*a, **kw): pass

    # ── contable_index: Dashboard contable (/contable)
    @app.route('/contable')
    @login_required
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

        # ── Egresos: gastos operativos + compras de materia prima ─────────────
        try:
            gastos_mes = GastoOperativo.query.filter(
                GastoOperativo.fecha >= mes_ini,
                GastoOperativo.fecha <= mes_fin
            ).all()
            total_gastos = sum(float(g.monto or 0) for g in gastos_mes)
        except Exception:
            gastos_mes, total_gastos = [], 0

        try:
            compras_mes = CompraMateria.query.filter(
                CompraMateria.fecha >= mes_ini,
                CompraMateria.fecha <= mes_fin
            ).all()
            total_compras = sum(float(c.costo_total or 0) for c in compras_mes)
        except Exception:
            compras_mes, total_compras = [], 0

        total_egresos = total_gastos + total_compras
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

    # ── contable_asientos: Lista todos los asientos (/contable/asientos)
    @app.route('/contable/asientos')
    @login_required
    def contable_asientos():
        filtro = request.args.get('filtro', 'todos')
        desde = request.args.get('desde', '')
        hasta = request.args.get('hasta', '')

        q = AsientoContable.query

        if filtro == 'ingresos':
            q = q.filter(AsientoContable.tipo.in_(['venta', 'ingreso_externo']))
        elif filtro == 'gastos':
            q = q.filter(AsientoContable.tipo.in_(['compra', 'gasto', 'gasto_caja_chica']))
        elif filtro == 'inversiones':
            q = q.filter(AsientoContable.tipo == 'inversion_socio')
        elif filtro == 'manual':
            q = q.filter(AsientoContable.tipo == 'manual')

        if desde:
            try:
                fecha_desde = datetime.strptime(desde, '%Y-%m-%d').date()
                q = q.filter(AsientoContable.fecha >= fecha_desde)
            except:
                pass

        if hasta:
            try:
                fecha_hasta = datetime.strptime(hasta, '%Y-%m-%d').date()
                q = q.filter(AsientoContable.fecha <= fecha_hasta)
            except:
                pass

        asientos = q.order_by(AsientoContable.fecha.desc(), AsientoContable.creado_en.desc()).all()

        # Totales
        total_debe = sum(float(a.debe or 0) for a in asientos)
        total_haber = sum(float(a.haber or 0) for a in asientos)

        # Stats del mes actual
        mes_ini = date_type.today().replace(day=1)
        asientos_mes = AsientoContable.query.filter(
            AsientoContable.fecha >= mes_ini
        ).all()

        ingresos_mes = sum(float(a.haber or 0) for a in asientos_mes
                          if a.tipo in ['venta', 'ingreso_externo'])
        gastos_mes = sum(float(a.debe or 0) for a in asientos_mes
                        if a.tipo in ['compra', 'gasto', 'gasto_caja_chica'])

        return render_template('contable/asientos.html',
            asientos=asientos, filtro=filtro, desde=desde, hasta=hasta,
            total_debe=total_debe, total_haber=total_haber,
            ingresos_mes=ingresos_mes, gastos_mes=gastos_mes,
            balance_mes=ingresos_mes - gastos_mes)

    # ── contable_asiento_nuevo: Crear asiento manual (/contable/asientos/nuevo)
    @app.route('/contable/asientos/nuevo', methods=['GET', 'POST'])
    @login_required
    def contable_asiento_nuevo():
        if request.method == 'POST':
            fecha = request.form.get('fecha', '')
            descripcion = request.form.get('descripcion', '')
            tipo = request.form.get('tipo', 'manual')
            subtipo = request.form.get('subtipo', '')
            referencia = request.form.get('referencia', '')
            debe = float(request.form.get('debe', 0) or 0)
            haber = float(request.form.get('haber', 0) or 0)
            cuenta_debe = request.form.get('cuenta_debe', '')
            cuenta_haber = request.form.get('cuenta_haber', '')
            notas = request.form.get('notas', '')

            try:
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            except:
                fecha_obj = date_type.today()

            # Generar número automático: AC-YYYY-{n:04d}
            ultimo = AsientoContable.query.order_by(AsientoContable.id.desc()).first()
            n_ac = (ultimo.id + 1) if ultimo else 1
            numero = f'AC-{fecha_obj.year}-{n_ac:04d}'

            asiento = AsientoContable(
                numero=numero,
                fecha=fecha_obj,
                descripcion=descripcion,
                tipo=tipo,
                subtipo=subtipo,
                referencia=referencia,
                debe=debe,
                haber=haber,
                cuenta_debe=cuenta_debe,
                cuenta_haber=cuenta_haber,
                notas=notas,
                creado_por=current_user.id
            )
            db.session.add(asiento)
            db.session.commit()

            flash(f'Asiento {numero} creado exitosamente.', 'success')
            return redirect(url_for('contable_asientos'))

        tipos_asiento = [
            ('manual', 'Manual'),
            ('venta', 'Venta'),
            ('compra', 'Compra'),
            ('gasto', 'Gasto'),
            ('ingreso_externo', 'Ingreso externo'),
            ('inversion_socio', 'Inversión socio'),
            ('gasto_caja_chica', 'Gasto caja chica')
        ]

        return render_template('contable/asiento_form.html',
            obj=None, tipos_asiento=tipos_asiento,
            titulo='Nuevo asiento contable',
            hoy=date_type.today().isoformat())

    # ── contable_asiento_editar: Editar asiento (/contable/asientos/<id>/editar)
    @app.route('/contable/asientos/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    def contable_asiento_editar(id):
        asiento = AsientoContable.query.get_or_404(id)

        if request.method == 'POST':
            asiento.fecha = datetime.strptime(request.form.get('fecha', asiento.fecha.isoformat()), '%Y-%m-%d').date()
            asiento.descripcion = request.form.get('descripcion', asiento.descripcion)
            asiento.tipo = request.form.get('tipo', asiento.tipo)
            asiento.subtipo = request.form.get('subtipo', '')
            asiento.referencia = request.form.get('referencia', '')
            asiento.debe = float(request.form.get('debe', asiento.debe) or 0)
            asiento.haber = float(request.form.get('haber', asiento.haber) or 0)
            asiento.cuenta_debe = request.form.get('cuenta_debe', '')
            asiento.cuenta_haber = request.form.get('cuenta_haber', '')
            asiento.notas = request.form.get('notas', '')

            db.session.commit()
            flash(f'Asiento {asiento.numero} actualizado.', 'success')
            return redirect(url_for('contable_asientos'))

        tipos_asiento = [
            ('manual', 'Manual'),
            ('venta', 'Venta'),
            ('compra', 'Compra'),
            ('gasto', 'Gasto'),
            ('ingreso_externo', 'Ingreso externo'),
            ('inversion_socio', 'Inversión socio'),
            ('gasto_caja_chica', 'Gasto caja chica')
        ]

        return render_template('contable/asiento_form.html',
            obj=asiento, tipos_asiento=tipos_asiento,
            titulo=f'Editar asiento {asiento.numero}',
            hoy=date_type.today().isoformat())

    # ── contable_asiento_eliminar: Eliminar asiento (/contable/asientos/<id>/eliminar)
    @app.route('/contable/asientos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def contable_asiento_eliminar(id):
        asiento = AsientoContable.query.get_or_404(id)
        numero = asiento.numero

        # Solo admin puede eliminar
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar asientos.', 'danger')
            return redirect(url_for('contable_asientos'))

        db.session.delete(asiento)
        db.session.commit()

        flash(f'Asiento {numero} eliminado.', 'info')
        return redirect(url_for('contable_asientos'))

    # ── contable_comprobante: Generar PDF comprobante (/contable/asientos/<id>/comprobante)
    @app.route('/contable/asientos/<int:id>/comprobante')
    @login_required
    def contable_comprobante(id):
        asiento = AsientoContable.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()

        return render_template('contable/comprobante.html',
            asiento=asiento, empresa=empresa)
