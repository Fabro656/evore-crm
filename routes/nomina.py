# routes/nomina.py
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
    @app.route('/nomina')
    @login_required
    @requiere_modulo('nomina')
    def nomina_index():
        estado_filter = request.args.get('estado', 'activo')
        departamento_filter = request.args.get('departamento', '')
        query = Empleado.query
        if estado_filter and estado_filter != 'todos':
            query = query.filter_by(estado=estado_filter)
        if departamento_filter:
            query = query.filter_by(departamento=departamento_filter)
        empleados = query.all()
        departamentos = db.session.query(Empleado.departamento).distinct().filter(Empleado.departamento != None).all()
        departamentos = [d[0] for d in departamentos if d[0]]
        # Stats
        activos = Empleado.query.filter_by(estado='activo').count()
        masa_salarial = sum(e.salario_base for e in Empleado.query.filter_by(estado='activo').all())
        costo_empresa = sum(_calcular_nomina(e)['costo_total_empresa'] for e in Empleado.query.filter_by(estado='activo').all())
        retirados = Empleado.query.filter_by(estado='retirado').count()
        return render_template('nomina/index.html', empleados=empleados, departamentos=departamentos,
                              estado_filter=estado_filter, departamento_filter=departamento_filter,
                              activos=activos, masa_salarial=masa_salarial, costo_empresa=costo_empresa, retirados=retirados)

    @app.route('/nomina/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_nuevo():
        if request.method == 'POST':
            try:
                e = Empleado(
                    nombre=request.form.get('nombre',''),
                    apellido=request.form.get('apellido',''),
                    cedula=request.form.get('cedula',''),
                    email=request.form.get('email',''),
                    telefono=request.form.get('telefono',''),
                    cargo=request.form.get('cargo',''),
                    departamento=request.form.get('departamento',''),
                    tipo_contrato=request.form.get('tipo_contrato','indefinido'),
                    salario_base=float(request.form.get('salario_base',0)),
                    auxilio_transporte=request.form.get('auxilio_transporte')=='on',
                    nivel_riesgo_arl=int(request.form.get('nivel_riesgo_arl',1)),
                    estado='activo',
                    fecha_ingreso=datetime.strptime(request.form.get('fecha_ingreso',''), '%Y-%m-%d').date() if request.form.get('fecha_ingreso') else None,
                    notas=request.form.get('notas',''),
                    creado_por=current_user.id
                )
                db.session.add(e)
                db.session.commit()
                flash(f'Empleado {e.nombre} creado exitosamente.','success')
                return redirect(url_for('empleado_ver', id=e.id))
            except Exception as ex:
                db.session.rollback()
                flash(f'Error al crear empleado: {str(ex)}','danger')
        return render_template('nomina/form.html', empleado=None)

    @app.route('/nomina/<int:id>')
    @login_required
    @requiere_modulo('nomina')
    def empleado_ver(id):
        empleado = Empleado.query.get_or_404(id)
        calc = _calcular_nomina(empleado)
        return render_template('nomina/ver.html', empleado=empleado, calc=calc)

    @app.route('/nomina/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_editar(id):
        empleado = Empleado.query.get_or_404(id)
        if request.method == 'POST':
            try:
                empleado.nombre=request.form.get('nombre','')
                empleado.apellido=request.form.get('apellido','')
                empleado.cedula=request.form.get('cedula','')
                empleado.email=request.form.get('email','')
                empleado.telefono=request.form.get('telefono','')
                empleado.cargo=request.form.get('cargo','')
                empleado.departamento=request.form.get('departamento','')
                empleado.tipo_contrato=request.form.get('tipo_contrato','indefinido')
                empleado.salario_base=float(request.form.get('salario_base',0))
                empleado.auxilio_transporte=request.form.get('auxilio_transporte')=='on'
                empleado.nivel_riesgo_arl=int(request.form.get('nivel_riesgo_arl',1))
                empleado.notas=request.form.get('notas','')
                if request.form.get('fecha_ingreso'):
                    empleado.fecha_ingreso=datetime.strptime(request.form.get('fecha_ingreso',''), '%Y-%m-%d').date()
                db.session.commit()
                flash('Empleado actualizado.','success')
                return redirect(url_for('empleado_ver', id=empleado.id))
            except Exception as ex:
                db.session.rollback()
                flash(f'Error al actualizar: {str(ex)}','danger')
        return render_template('nomina/form.html', empleado=empleado)

    @app.route('/nomina/<int:id>/liquidacion')
    @login_required
    @requiere_modulo('nomina')
    def empleado_liquidacion(id):
        empleado = Empleado.query.get_or_404(id)
        motivo = request.args.get('motivo', 'renuncia')
        liq = _calcular_liquidacion(empleado, motivo)
        if not liq:
            flash('No se puede calcular liquidación sin fecha de ingreso.','danger')
            return redirect(url_for('empleado_ver', id=id))
        return render_template('nomina/liquidacion.html', empleado=empleado, liq=liq)

    @app.route('/nomina/<int:id>/retirar', methods=['POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_retirar(id):
        empleado = Empleado.query.get_or_404(id)
        motivo = request.form.get('motivo', 'renuncia')
        empleado.motivo_retiro = motivo
        empleado.fecha_retiro = date_type.today()
        if motivo in ('despido_justa', 'despido_sin_justa'):
            empleado.estado = 'despedido'
        else:
            empleado.estado = 'retirado'
        _log('editar', 'empleado', empleado.id, f'Marcado como {empleado.estado} por: {motivo}')
        db.session.commit()
        flash(f'Empleado {empleado.nombre} marcado como {empleado.estado}.','success')
        return redirect(url_for('nomina_index'))

    @app.route('/nomina/cerrar-mes', methods=['POST'])
    @login_required
    @requiere_modulo('nomina')
    def nomina_cerrar_mes():
        """Create a monthly payroll expense entry for all active employees."""
        mes = request.form.get('mes', '')  # format: YYYY-MM
        if not mes:
            from datetime import date as date_obj
            today = date_obj.today()
            mes = today.strftime('%Y-%m')

        empleados_activos = Empleado.query.filter_by(estado='activo').all()
        if not empleados_activos:
            flash('No hay empleados activos para cerrar nómina.', 'warning')
            return redirect(url_for('nomina_index'))

        total_costo = sum(_calcular_nomina(e)['costo_total_empresa'] for e in empleados_activos)
        total_neto = sum(_calcular_nomina(e)['salario_neto'] for e in empleados_activos)
        n_empleados = len(empleados_activos)

        from datetime import date as date_obj
        try:
            year, month = int(mes.split('-')[0]), int(mes.split('-')[1])
            fecha_gasto = date_obj(year, month, 1)
        except:
            fecha_gasto = date_obj.today()

        # Check if already closed for this month
        desc_check = f'Nómina mensual {mes}'
        existing = GastoOperativo.query.filter(
            GastoOperativo.descripcion == desc_check,
            GastoOperativo.tipo == 'Nómina'
        ).first()
        if existing:
            flash(f'La nómina de {mes} ya fue cerrada anteriormente.', 'warning')
            return redirect(url_for('nomina_index'))

        g = GastoOperativo(
            fecha=fecha_gasto,
            tipo='Nómina',
            descripcion=desc_check,
            monto=round(total_costo, 0),
            recurrencia='unico',
            notas=f'{n_empleados} empleados activos. Masa salarial neta: ${total_neto:,.0f}',
            creado_por=current_user.id
        )
        db.session.add(g)
        _log('crear', 'gasto', g.id, f'Nómina mensual {mes}: ${total_costo:,.0f}')
        db.session.commit()
        flash(f'Nómina de {mes} cerrada. Gasto registrado: ${total_costo:,.0f} ({n_empleados} empleados).', 'success')
        return redirect(url_for('nomina_index'))
