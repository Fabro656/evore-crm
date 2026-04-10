# routes/nomina.py — reconstruido desde v27 con CRUD completo
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

    # ── Helpers ─────────────────────────────────────────────────────
    def _calcular_nomina(empleado):
        from services.nomina import NominaService
        return NominaService.calcular_nomina(empleado)

    def _calcular_liquidacion(empleado, motivo):
        from services.nomina import NominaService
        return NominaService.calcular_liquidacion(empleado, motivo)


    # ── nomina_index (/nomina)
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
        _activos_list = Empleado.query.filter_by(estado='activo').all()
        masa_salarial = sum(float(e.salario_base or 0) for e in _activos_list)
        costo_empresa = 0
        for _e in _activos_list:
            try:
                costo_empresa += _calcular_nomina(_e)['costo_total_empresa']
            except Exception as _ne:
                logging.warning(f'nomina_index: calcular_nomina({_e.id}) error: {_ne}')
        retirados = Empleado.query.filter_by(estado='retirado').count()
        return render_template('nomina/index.html', empleados=empleados, departamentos=departamentos,
                              estado_filter=estado_filter, departamento_filter=departamento_filter,
                              activos=activos, masa_salarial=masa_salarial, costo_empresa=costo_empresa, retirados=retirados)
    

    # ── nomina_cerrar_mes (/nomina/cerrar-mes)
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
    
        total_costo = 0
        total_neto = 0
        for _e2 in empleados_activos:
            try:
                _c = _calcular_nomina(_e2)
                total_costo += _c['costo_total_empresa']
                total_neto  += _c['salario_neto']
            except Exception as _ce:
                logging.warning(f'nomina_cerrar_mes: calcular_nomina({_e2.id}) error: {_ce}')
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
        _noop('crear', 'gasto', g.id, f'Nómina mensual {mes}: ${total_costo:,.0f}')
        db.session.commit()
        flash(f'Nómina de {mes} cerrada. Gasto registrado: ${total_costo:,.0f} ({n_empleados} empleados).', 'success')
        return redirect(url_for('nomina_index'))
    

    # ── empleado_nuevo (/nomina/nuevo)
    @app.route('/nomina/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_nuevo():
        if request.method == 'POST':
            try:
                fecha_ingreso = None
                if request.form.get('fecha_ingreso'):
                    try:
                        fecha_ingreso = datetime.strptime(request.form.get('fecha_ingreso'), '%Y-%m-%d').date()
                    except (ValueError, TypeError) as fe:
                        logging.warning(f'empleado_nuevo: error parsing fecha_ingreso: {fe}')
                        fecha_ingreso = None

                e = Empleado(
                    nombre=request.form.get('nombre','').strip(),
                    apellido=request.form.get('apellido','').strip(),
                    cedula=request.form.get('cedula','').strip(),
                    email=request.form.get('email','').strip(),
                    telefono=request.form.get('telefono','').strip(),
                    cargo=request.form.get('cargo','').strip(),
                    departamento=request.form.get('departamento','').strip(),
                    tipo_contrato=request.form.get('tipo_contrato','indefinido'),
                    salario_base=float(request.form.get('salario_base') or 0),
                    auxilio_transporte=request.form.get('auxilio_transporte')=='on',
                    nivel_riesgo_arl=int(request.form.get('nivel_riesgo_arl',1)),
                    estado='activo',
                    fecha_ingreso=fecha_ingreso,
                    notas=request.form.get('notas','').strip(),
                    creado_por=current_user.id
                )
                if not e.nombre or not e.apellido:
                    flash('El nombre y apellido son obligatorios.','danger')
                    return render_template('nomina/form.html', empleado=None)
                db.session.add(e)
                db.session.commit()
                flash(f'Empleado {e.nombre} {e.apellido} creado exitosamente.','success')
                return redirect(url_for('empleado_ver', id=e.id))
            except Exception as ex:
                db.session.rollback()
                logging.error(f'empleado_nuevo error: {str(ex)}')
                flash(f'Error al crear empleado: {str(ex)}','danger')
        return render_template('nomina/form.html', empleado=None)
    

    # ── empleado_ver (/nomina/<int:id>)
    @app.route('/nomina/<int:id>')
    @login_required
    @requiere_modulo('nomina')
    def empleado_ver(id):
        empleado = Empleado.query.get_or_404(id)
        calc = _calcular_nomina(empleado)
        return render_template('nomina/ver.html', empleado=empleado, calc=calc)
    

    # ── empleado_editar (/nomina/<int:id>/editar)
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
                empleado.salario_base=float(request.form.get('salario_base') or 0)
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
    

    # ── empleado_liquidacion (/nomina/<int:id>/liquidacion)
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
    

    # ── empleado_retirar (/nomina/<int:id>/retirar)
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
        _noop('editar', 'empleado', empleado.id, f'Marcado como {empleado.estado} por: {motivo}')
        db.session.commit()
        flash(f'Empleado {empleado.nombre} marcado como {empleado.estado}.','success')
        return redirect(url_for('nomina_index'))


    # ── parametros_nomina_editar (/nomina/parametros)
    @app.route('/nomina/parametros', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def parametros_nomina_editar():
        """Permite a admin/contador editar los parámetros globales de nómina (tasas, SMLMV, auxilio transporte)."""
        if current_user.rol not in ('admin', 'contador'):
            flash('Solo administradores y contadores pueden editar parámetros de nómina.','danger')
            return redirect(url_for('nomina_index'))

        from utils import (
            SMLMV_2025, AUXILIO_TRANSPORTE_2025,
            TASA_SALUD_EMP, TASA_PENSION_EMP,
            TASA_SALUD_EMPR, TASA_PENSION_EMPR,
            TASA_ARL, TASA_CAJA_COMP, TASA_SENA, TASA_ICBF,
            TASA_CESANTIAS, TASA_INT_CESANTIAS,
            TASA_PRIMA, TASA_VACACIONES
        )

        if request.method == 'POST':
            # Nota: Los parámetros se editan en utils.py. Este formulario es informativo
            # y en una implementación completa, se almacenarían en la BD en una tabla de configuración.
            flash('Los parámetros de nómina se editan directamente en utils.py.', 'info')
            return redirect(url_for('nomina_index'))

        # Mostrar parámetros actuales
        return render_template('nomina/parametros.html',
            smlmv=SMLMV_2025,
            auxilio_transporte=AUXILIO_TRANSPORTE_2025,
            tasa_salud_emp=TASA_SALUD_EMP,
            tasa_pension_emp=TASA_PENSION_EMP,
            tasa_salud_empr=TASA_SALUD_EMPR,
            tasa_pension_empr=TASA_PENSION_EMPR,
            tasa_caja=TASA_CAJA_COMP,
            tasa_sena=TASA_SENA,
            tasa_icbf=TASA_ICBF,
            tasa_cesantias=TASA_CESANTIAS,
            tasa_int_cesantias=TASA_INT_CESANTIAS,
            tasa_prima=TASA_PRIMA,
            tasa_vacaciones=TASA_VACACIONES
        )
    
