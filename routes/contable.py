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
        mes = request.args.get('mes', '')
        mes_str = mes
        anio = datetime.utcnow().year

        # Navegar por meses
        meses_nav = [
            {'lbl': 'Ene', 'val': '01'}, {'lbl': 'Feb', 'val': '02'},
            {'lbl': 'Mar', 'val': '03'}, {'lbl': 'Abr', 'val': '04'},
            {'lbl': 'May', 'val': '05'}, {'lbl': 'Jun', 'val': '06'},
            {'lbl': 'Jul', 'val': '07'}, {'lbl': 'Ago', 'val': '08'},
            {'lbl': 'Sep', 'val': '09'}, {'lbl': 'Oct', 'val': '10'},
            {'lbl': 'Nov', 'val': '11'}, {'lbl': 'Dic', 'val': '12'}
        ]

        if not mes:
            mes = f"{datetime.utcnow().month:02d}"
            mes_str = mes

        try:
            mes_num = int(mes)
        except:
            mes_num = datetime.utcnow().month
            mes = f"{mes_num:02d}"
            mes_str = mes

        # Fecha inicio y fin del mes
        mes_ini = date_type(anio, mes_num, 1)
        if mes_num == 12:
            mes_fin = date_type(anio + 1, 1, 1) - timedelta(days=1)
        else:
            mes_fin = date_type(anio, mes_num + 1, 1) - timedelta(days=1)

        # Ventas del mes (estado pagado)
        ventas_mes = Venta.query.filter(
            Venta.creado_en >= mes_ini,
            Venta.creado_en <= mes_fin,
            Venta.estado == 'pagado'
        ).all()

        # Total ingresos operacionales (venta, ingreso_externo)
        asientos_ingresos = AsientoContable.query.filter(
            AsientoContable.tipo.in_(['venta', 'ingreso_externo']),
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin
        ).all()
        total_ingresos = sum(float(a.haber or 0) for a in asientos_ingresos)

        # Total inversiones de socios (NO profit)
        asientos_inversiones = AsientoContable.query.filter(
            AsientoContable.tipo == 'inversion_socio',
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin
        ).all()
        total_inversiones = sum(float(a.haber or 0) for a in asientos_inversiones)

        # Total gastos (compra, gasto, gasto_caja_chica)
        asientos_gastos = AsientoContable.query.filter(
            AsientoContable.tipo.in_(['compra', 'gasto', 'gasto_caja_chica']),
            AsientoContable.fecha >= mes_ini,
            AsientoContable.fecha <= mes_fin
        ).all()
        total_gastos = sum(float(a.debe or 0) for a in asientos_gastos)

        # Balance operacional
        balance = total_ingresos - total_gastos

        # Últimos 10 asientos
        ultimos_asientos = AsientoContable.query.order_by(
            AsientoContable.fecha.desc(), AsientoContable.creado_en.desc()
        ).limit(10).all()

        # CXC
        cxc = Venta.query.filter(Venta.estado.in_(['prospecto', 'negociacion', 'anticipo_pagado'])).all()
        total_cxc = sum(float(v.saldo or 0) for v in cxc)

        return render_template('contable/index.html',
            meses_nav=meses_nav, mes_str=mes_str, mes=mes_num, anio=anio,
            total_ingresos=total_ingresos, total_inversiones=total_inversiones,
            total_gastos=total_gastos, balance=balance,
            ultimos_asientos=ultimos_asientos,
            cxc=cxc, total_cxc=total_cxc,
            ventas_mes=ventas_mes)

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
            titulo=f'Editar asiento {asiento.numero}')

    # ── contable_asiento_eliminar: Eliminar asiento (/contable/asientos/<id>/eliminar)
    @app.route('/contable/asientos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def contable_asiento_eliminar(id):
        asiento = AsientoContable.query.get_or_404(id)
        numero = asiento.numero

        # Solo admin puede eliminar
        if not current_user.es_admin:
            flash('Solo administradores pueden eliminar asientos.', 'error')
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
