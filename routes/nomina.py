# routes/nomina.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging

def register(app):

    # ── Helpers ─────────────────────────────────────────────────────
    def _calcular_nomina(empleado, dias_mes=30, dias_trabajados=None):
        from services.nomina import NominaService
        return NominaService.calcular_nomina(empleado, dias_mes=dias_mes, dias_trabajados=dias_trabajados)

    def _calcular_liquidacion(empleado, motivo):
        from services.nomina import NominaService
        return NominaService.calcular_liquidacion(empleado, motivo)


    # ── Helper: verificar si nomina del mes anterior fue cerrada
    def _verificar_nomina_pendiente():
        """Si el mes anterior no tiene nomina cerrada, crear ticket al admin."""
        import calendar
        hoy = date_type.today()
        # Solo verificar despues del dia 1 del mes (para mes anterior)
        if hoy.day < 2:
            return
        # Mes anterior
        if hoy.month == 1:
            mes_ant = f'{hoy.year - 1}-12'
        else:
            mes_ant = f'{hoy.year}-{hoy.month - 1:02d}'
        desc_check = f'Nomina mensual {mes_ant}'
        ya_cerrada = GastoOperativo.query.filter(
            GastoOperativo.descripcion == desc_check, GastoOperativo.tipo == 'Nomina'
        ).first()
        if ya_cerrada:
            return
        # Verificar si hay empleados activos
        if Empleado.query.filter_by(estado='activo').count() == 0:
            return
        # Verificar si ya existe ticket para esto
        titulo_ticket = f'Nomina pendiente de cerrar: {mes_ant}'
        ya_ticket = Tarea.query.filter(
            Tarea.titulo == titulo_ticket, Tarea.estado == 'pendiente'
        ).first()
        if ya_ticket:
            return
        # Crear ticket al admin
        admin = User.query.filter_by(rol='admin', activo=True).first()
        if admin:
            t = Tarea(company_id=getattr(g, 'company_id', None),
                titulo=titulo_ticket,
                descripcion=f'La nomina del mes {mes_ant} no ha sido cerrada. '
                            f'Ingresa a Nomina y cierra el mes para registrar el gasto.',
                estado='pendiente', prioridad='alta',
                asignado_a=admin.id,
                creado_por=admin.id,
                tarea_tipo='nomina_pendiente',
                categoria='pago',
                fecha_vencimiento=hoy
            )
            db.session.add(t)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()


    # ── nomina_index (/nomina)
    @app.route('/nomina')
    @login_required
    @requiere_modulo('nomina')
    def nomina_index():
        _verificar_nomina_pendiente()
        estado_filter = request.args.get('estado', 'activo')
        departamento_filter = request.args.get('departamento', '')
        buscar = request.args.get('buscar','').strip()
        query = Empleado.query
        if estado_filter and estado_filter != 'todos':
            query = query.filter_by(estado=estado_filter)
        if departamento_filter:
            query = query.filter_by(departamento=departamento_filter)
        if buscar:
            like_term = f'%{buscar}%'
            query = query.filter(
                db.or_(
                    Empleado.nombre.ilike(like_term),
                    Empleado.apellido.ilike(like_term),
                    Empleado.cedula.ilike(like_term),
                    Empleado.cargo.ilike(like_term),
                )
            )
        page = request.args.get('page', 1, type=int)
        per_page = 25
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        empleados = pagination.items
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
        despedidos = Empleado.query.filter_by(estado='despedido').count()
        return render_template('nomina/index.html', empleados=empleados, departamentos=departamentos,
                              estado_filter=estado_filter, departamento_filter=departamento_filter,
                              buscar=buscar,
                              activos=activos, masa_salarial=masa_salarial, costo_empresa=costo_empresa,
                              retirados=retirados, despedidos=despedidos,
                              page=page, total_pages=pagination.pages, total_items=pagination.total)
    

    # ── nomina_empleados_export_csv (/nomina/empleados/export-csv)
    @app.route('/nomina/empleados/export-csv')
    @login_required
    @requiere_modulo('nomina')
    def nomina_empleados_export_csv():
        empleados = Empleado.query.order_by(Empleado.apellido, Empleado.nombre).all()
        rows = []
        for e in empleados:
            nombre_completo = f"{e.nombre or ''} {e.apellido or ''}".strip()
            fecha_ingreso = e.fecha_ingreso.strftime('%d/%m/%Y') if e.fecha_ingreso else ''
            rows.append([
                nombre_completo,
                e.cedula or '',
                e.cargo or '',
                e.departamento or '',
                e.salario_base or 0,
                e.estado or '',
                fecha_ingreso,
            ])
        return generar_csv_response(
            rows,
            ['Nombre', 'Cedula', 'Cargo', 'Departamento', 'Salario', 'Estado', 'Fecha_Ingreso'],
            filename='empleados.csv'
        )

    # ── nomina_cerrar_mes (/nomina/cerrar-mes)
    @app.route('/nomina/cerrar-mes', methods=['POST'])
    @login_required
    @requiere_modulo('nomina')
    def nomina_cerrar_mes():
        """Cierra nomina mensual con prorrateo por dias trabajados."""
        import calendar
        mes = request.form.get('mes', '')
        if not mes:
            mes = date_type.today().strftime('%Y-%m')

        try:
            year, month = int(mes.split('-')[0]), int(mes.split('-')[1])
            fecha_gasto = date_type(year, month, 1)
            dias_del_mes = calendar.monthrange(year, month)[1]
            primer_dia = date_type(year, month, 1)
            ultimo_dia = date_type(year, month, dias_del_mes)
        except Exception:
            flash('Formato de mes invalido.', 'danger')
            return redirect(url_for('nomina_index'))

        # Check si ya se cerro (con lock para prevenir doble ejecucion)
        desc_check = f'Nomina mensual {mes}'
        existente = GastoOperativo.query.filter(
            GastoOperativo.descripcion == desc_check, GastoOperativo.tipo == 'Nomina'
        ).first()
        if existente:
            flash(f'La nomina de {mes} ya fue cerrada anteriormente.', 'warning')
            return redirect(url_for('nomina_index'))
        # Crear placeholder inmediato para prevenir doble ejecucion concurrente
        placeholder = GastoOperativo(
            company_id=getattr(g, 'company_id', None),
            fecha=fecha_gasto, tipo='Nomina', descripcion=desc_check,
            monto=0, creado_por=current_user.id
        )
        db.session.add(placeholder)
        try:
            db.session.flush()  # Si otro request ya creo el placeholder, flush falla en unique check
        except Exception:
            db.session.rollback()
            flash(f'La nómina de {mes} está siendo procesada por otro usuario.', 'warning')
            return redirect(url_for('nomina_index'))

        # Incluir activos + retirados/despedidos en este mes (trabajaron parte del mes)
        empleados = Empleado.query.filter(
            db.or_(
                Empleado.estado == 'activo',
                db.and_(
                    Empleado.estado.in_(['retirado', 'despedido']),
                    Empleado.fecha_retiro >= primer_dia,
                    Empleado.fecha_retiro <= ultimo_dia
                )
            )
        ).all()

        if not empleados:
            flash('No hay empleados para cerrar nomina.', 'warning')
            return redirect(url_for('nomina_index'))

        total_costo = 0
        total_neto = 0
        total_liquidacion = 0
        detalle_empleados = []
        for emp in empleados:
            # Calcular dias trabajados en el mes
            inicio_trabajo = max(emp.fecha_ingreso or primer_dia, primer_dia)
            if emp.estado in ('retirado', 'despedido') and emp.fecha_retiro and emp.fecha_retiro <= ultimo_dia:
                fin_trabajo = emp.fecha_retiro
            else:
                fin_trabajo = ultimo_dia
            dias_trabajados = max((fin_trabajo - inicio_trabajo).days + 1, 0)
            dias_trabajados = min(dias_trabajados, dias_del_mes)

            try:
                calc = _calcular_nomina(emp, dias_mes=dias_del_mes, dias_trabajados=dias_trabajados)
                # Sumar horas extra del periodo
                horas_extra_emp = HoraExtra.query.filter_by(empleado_id=emp.id, periodo=mes).all()
                valor_he = sum(float(h.valor or 0) for h in horas_extra_emp)
                calc['horas_extra'] = valor_he
                calc['salario_neto'] += valor_he
                calc['costo_total_empresa'] += valor_he
                total_costo += calc['costo_total_empresa']
                total_neto += calc['salario_neto']
                he_txt = f' +HE:{moneda(valor_he)}' if valor_he > 0 else ''
                detalle_empleados.append(f'{emp.nombre} {emp.apellido}: {dias_trabajados}d{he_txt}')
            except Exception as _ce:
                logging.warning(f'nomina_cerrar_mes: calc({emp.id}) error: {_ce}')

            # Si fue retirado/despedido este mes, agregar liquidacion a gastos
            if emp.estado in ('retirado', 'despedido') and emp.fecha_retiro and primer_dia <= emp.fecha_retiro <= ultimo_dia:
                try:
                    liq = _calcular_liquidacion(emp, emp.motivo_retiro or 'renuncia')
                    if liq and liq['total'] > 0:
                        total_liquidacion += liq['total']
                        # Crear gasto separado para liquidacion
                        g_liq = GastoOperativo(
                            company_id=getattr(g, 'company_id', None),
                            fecha=emp.fecha_retiro,
                            tipo='Nomina',
                            descripcion=f'Liquidacion {emp.nombre} {emp.apellido} ({emp.motivo_retiro})',
                            monto=round(liq['total'], 0),
                            recurrencia='unico',
                            notas=f'Cesantias: ${liq["cesantias"]:,.0f}, Int: ${liq["int_cesantias"]:,.0f}, '
                                  f'Prima: ${liq["prima"]:,.0f}, Vac: ${liq["vacaciones"]:,.0f}, '
                                  f'Indem: ${liq["indemnizacion"]:,.0f}',
                            creado_por=current_user.id
                        )
                        db.session.add(g_liq)
                        db.session.flush()
                        _crear_asiento_auto(
                            tipo='gasto', subtipo='liquidacion_empleado',
                            descripcion=f'Liquidacion {emp.nombre} {emp.apellido}',
                            monto=round(liq['total'], 0),
                            cuenta_debe='Gastos de nomina - Liquidaciones',
                            cuenta_haber='Bancos / Caja',
                            clasificacion='egreso',
                            referencia=f'LIQ-{emp.cedula or emp.id}',
                            gasto_id=g_liq.id
                        )
                except Exception as ex_liq:
                    logging.warning(f'nomina_cerrar_mes: liquidacion({emp.id}) error: {ex_liq}')

        n_empleados = len(empleados)

        # Actualizar el placeholder creado al inicio (previene duplicados)
        g = placeholder
        g.monto = round(total_costo, 0)
        g.recurrencia = 'unico'
        g.notas = f'{n_empleados} empleados. Neto: ${total_neto:,.0f}. Detalle: {"; ".join(detalle_empleados[:10])}'
        db.session.flush()
        _crear_asiento_auto(
            tipo='gasto', subtipo='nomina_mensual',
            descripcion=f'Nomina {mes}: {n_empleados} empleados',
            monto=round(total_costo, 0),
            cuenta_debe='Gastos de nomina',
            cuenta_haber='Bancos / Caja',
            clasificacion='egreso',
            referencia=f'NOM-{mes}',
            gasto_id=g.id
        )
        _log('crear', 'gasto', g.id, f'Nomina mensual {mes}: ${total_costo:,.0f}')
        db.session.commit()
        msg = f'Nomina de {mes} cerrada. Gasto: ${total_costo:,.0f} ({n_empleados} empleados).'
        if total_liquidacion > 0:
            msg += f' Liquidaciones: ${total_liquidacion:,.0f}'
        flash(msg, 'success')
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
                    company_id=getattr(g, 'company_id', None),
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
                    tipo_sangre=request.form.get('tipo_sangre','').strip() or None,
                    contacto_emergencia_nombre=request.form.get('contacto_emergencia_nombre','').strip() or None,
                    contacto_emergencia_telefono=request.form.get('contacto_emergencia_telefono','').strip() or None,
                    contacto_emergencia_parentesco=request.form.get('contacto_emergencia_parentesco','').strip() or None,
                    eps=request.form.get('eps','').strip() or None,
                    caja_compensacion=request.form.get('caja_compensacion','').strip() or None,
                    fondo_pensiones=request.form.get('fondo_pensiones','').strip() or None,
                    creado_por=current_user.id
                )
                if not e.nombre or not e.apellido:
                    flash('El nombre y apellido son obligatorios.','danger')
                    return render_template('nomina/form.html', empleado=None)
                db.session.add(e)
                db.session.flush()
                eid, enombre, eapellido = e.id, e.nombre, e.apellido
                db.session.commit()
                flash(f'Empleado {enombre} {eapellido} creado exitosamente.','success')
                return redirect(url_for('empleado_ver', id=eid))
            except Exception as ex:
                db.session.rollback()
                logging.error(f'empleado_nuevo error: {str(ex)}')
                flash('Error al crear empleado. Verifica los datos e intenta de nuevo.','danger')
        return render_template('nomina/form.html', empleado=None)
    

    # ── empleado_ver (/nomina/<int:id>)
    @app.route('/nomina/<int:id>')
    @login_required
    @requiere_modulo('nomina')
    def empleado_ver(id):
        empleado = Empleado.query.get_or_404(id)
        calc = _calcular_nomina(empleado)
        return render_template('nomina/ver.html', empleado=empleado, calc=calc)
    

    # ── empleado_recibo (/nomina/<int:id>/recibo)
    @app.route('/nomina/<int:id>/recibo')
    @login_required
    @requiere_modulo('nomina')
    def empleado_recibo(id):
        empleado = Empleado.query.get_or_404(id)
        import calendar
        periodo = request.args.get('periodo', date_type.today().strftime('%Y-%m'))
        try:
            year, month = int(periodo.split('-')[0]), int(periodo.split('-')[1])
            dias_del_mes = calendar.monthrange(year, month)[1]
        except Exception:
            year, month = date_type.today().year, date_type.today().month
            dias_del_mes = 30
        primer_dia = date_type(year, month, 1)
        ultimo_dia = date_type(year, month, dias_del_mes)
        inicio = max(empleado.fecha_ingreso or primer_dia, primer_dia)
        if empleado.estado in ('retirado','despedido') and empleado.fecha_retiro and empleado.fecha_retiro <= ultimo_dia:
            fin = empleado.fecha_retiro
        else:
            fin = ultimo_dia
        dias_trabajados = max((fin - inicio).days + 1, 0)
        dias_trabajados = min(dias_trabajados, dias_del_mes)
        calc = _calcular_nomina(empleado, dias_mes=dias_del_mes, dias_trabajados=dias_trabajados)
        empresa = ConfigEmpresa.query.first()
        return render_template('nomina/recibo.html', empleado=empleado, calc=calc,
                               empresa=empresa, periodo=periodo)


    # ── empleado_editar (/nomina/<int:id>/editar)
    @app.route('/nomina/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_editar(id):
        empleado = Empleado.query.get_or_404(id)
        if request.method == 'POST':
            try:
                salario_anterior = float(empleado.salario_base or 0)
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
                empleado.tipo_sangre=request.form.get('tipo_sangre','').strip() or None
                empleado.contacto_emergencia_nombre=request.form.get('contacto_emergencia_nombre','').strip() or None
                empleado.contacto_emergencia_telefono=request.form.get('contacto_emergencia_telefono','').strip() or None
                empleado.contacto_emergencia_parentesco=request.form.get('contacto_emergencia_parentesco','').strip() or None
                empleado.eps=request.form.get('eps','').strip() or None
                empleado.caja_compensacion=request.form.get('caja_compensacion','').strip() or None
                empleado.fondo_pensiones=request.form.get('fondo_pensiones','').strip() or None
                if request.form.get('fecha_ingreso'):
                    empleado.fecha_ingreso=datetime.strptime(request.form.get('fecha_ingreso',''), '%Y-%m-%d').date()
                db.session.commit()
                salario_nuevo = float(empleado.salario_base or 0)
                if salario_anterior != salario_nuevo:
                    _log('editar', 'empleado', empleado.id, f'Salario cambiado: ${salario_anterior:,.0f} → ${salario_nuevo:,.0f} ({empleado.nombre} {empleado.apellido})')
                else:
                    _log('editar', 'empleado', empleado.id, f'Empleado editado: {empleado.nombre} {empleado.apellido}')
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
        motivo_label = {'renuncia':'Renuncia','despido_justa':'Despido justificado','despido_sin_justa':'Despido sin justa causa'}.get(motivo, motivo)
        config_empresa = ConfigEmpresa.query.first()
        return render_template('nomina/liquidacion.html', empleado=empleado, liq=liq,
                               motivo=motivo, motivo_label=motivo_label, config_empresa=config_empresa)
    

    # ── empleado_retirar (/nomina/<int:id>/retirar)
    @app.route('/nomina/<int:id>/retirar', methods=['POST'])
    @login_required
    @requiere_modulo('nomina')
    def empleado_retirar(id):
        empleado = Empleado.query.get_or_404(id)
        if empleado.estado in ('retirado', 'despedido'):
            flash('Este empleado ya fue retirado.', 'warning')
            return redirect(url_for('empleado_ver', id=id))

        motivo = request.form.get('motivo', 'renuncia')
        fecha_retiro_str = request.form.get('fecha_retiro', '')
        empleado.motivo_retiro = motivo
        empleado.fecha_retiro = datetime.strptime(fecha_retiro_str, '%Y-%m-%d').date() if fecha_retiro_str else date_type.today()

        if motivo in ('despido_justa', 'despido_sin_justa'):
            empleado.estado = 'despedido'
        else:
            empleado.estado = 'retirado'

        # Calcular liquidacion y registrar gasto + asiento de inmediato
        liq = _calcular_liquidacion(empleado, motivo)
        liq_msg = ''
        if liq and liq['total'] > 0:
            motivo_label = {'renuncia':'Renuncia','despido_justa':'Despido justificado','despido_sin_justa':'Despido sin justa causa'}.get(motivo, motivo)
            g = GastoOperativo(
                company_id=getattr(g, 'company_id', None),
                fecha=empleado.fecha_retiro or date_type.today(),
                tipo='Nomina',
                descripcion=f'Liquidacion {empleado.nombre} {empleado.apellido} ({motivo_label})',
                monto=round(liq['total'], 0),
                recurrencia='unico',
                estado_pago='pendiente',
                notas=f'Cesantias: ${liq["cesantias"]:,.0f}, Int: ${liq["int_cesantias"]:,.0f}, '
                      f'Prima: ${liq["prima"]:,.0f}, Vac: ${liq["vacaciones"]:,.0f}, '
                      f'Indem: ${liq["indemnizacion"]:,.0f}. Dias trabajados: {liq["dias_trabajados"]}',
                creado_por=current_user.id
            )
            db.session.add(g)
            db.session.flush()
            _crear_asiento_auto(
                tipo='gasto', subtipo='liquidacion_empleado',
                descripcion=f'Liquidacion {empleado.nombre} {empleado.apellido}',
                monto=round(liq['total'], 0),
                cuenta_debe='Gastos de nomina - Liquidaciones',
                cuenta_haber='Bancos / Caja',
                clasificacion='egreso',
                referencia=f'LIQ-{empleado.cedula or empleado.id}',
                gasto_id=g.id
            )
            liq_msg = f' Liquidacion: ${liq["total"]:,.0f} registrada en gastos y asientos contables.'

        _log('editar', 'empleado', empleado.id, f'Marcado como {empleado.estado} por: {motivo}')
        db.session.commit()
        flash(f'Empleado {empleado.nombre} marcado como {empleado.estado} ({motivo}).{liq_msg}', 'success')
        return redirect(url_for('empleado_liquidacion', id=id, motivo=motivo))


    # ── parametros_nomina_editar (/nomina/parametros)
    @app.route('/nomina/parametros', methods=['GET','POST'])
    @login_required
    @requiere_modulo('nomina')
    def parametros_nomina_editar():
        """Editar parametros de nomina (SMLMV, tasas, aportes). Se guardan en ConfigEmpresa.nomina_params."""
        if current_user.rol not in ('admin', 'contador'):
            flash('Solo administradores y contadores pueden editar parametros.','danger')
            return redirect(url_for('nomina_index'))
        import json as _json
        from company_config import COMPANY
        defaults = COMPANY['payroll']
        empresa = ConfigEmpresa.query.first()
        current = {}
        if empresa and empresa.nomina_params:
            try: current = _json.loads(empresa.nomina_params)
            except Exception as _e:
                logging.warning(f'nomina params JSON parse: {_e}')
        if request.method == 'POST':
            params = {}
            for key in ['min_wage', 'transport_subsidy']:
                v = request.form.get(key, '').strip()
                if v: params[key] = float(v)
            for key in ['health_employee', 'pension_employee', 'health_employer', 'pension_employer',
                        'caja_comp', 'sena', 'icbf']:
                v = request.form.get(key, '').strip()
                if v: params[key] = float(v)
            if not empresa:
                empresa = ConfigEmpresa(nombre='Mi Empresa')
                db.session.add(empresa)
            empresa.nomina_params = _json.dumps(params) if params else None
            db.session.commit()
            from utils import _cargar_nomina_params
            _cargar_nomina_params()
            flash('Parametros de nomina actualizados.', 'success')
            return redirect(url_for('parametros_nomina_editar'))
        fields = [
            ('min_wage', 'Salario minimo mensual (SMLMV)', 'moneda'),
            ('transport_subsidy', 'Auxilio de transporte', 'moneda'),
            ('health_employee', 'Salud empleado', 'pct'),
            ('pension_employee', 'Pension empleado', 'pct'),
            ('health_employer', 'Salud empleador', 'pct'),
            ('pension_employer', 'Pension empleador', 'pct'),
            ('caja_comp', 'Caja de compensacion', 'pct'),
            ('sena', 'SENA', 'pct'),
            ('icbf', 'ICBF', 'pct'),
        ]
        display = {}
        for key, label, tipo in fields:
            display[key] = {
                'label': label, 'tipo': tipo,
                'default': defaults.get(key, 0),
                'value': current.get(key, defaults.get(key, 0)),
                'overridden': key in current
            }
        return render_template('nomina/params.html', fields=fields, display=display)

    # Recargos segun CST Art. 168-170
    RECARGOS_HE = {
        'diurna': 0.25,             # Art. 168: 25% sobre hora ordinaria
        'nocturna': 0.75,           # Art. 168: 75%
        'dominical_diurna': 1.00,   # Art. 171: 100%
        'dominical_nocturna': 1.50, # Art. 171+168: 150%
    }

    # ── horas_extra (/nomina/horas-extra)
    @app.route('/nomina/horas-extra', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('nomina')
    def horas_extra():
        periodo = request.args.get('periodo', datetime.utcnow().strftime('%Y-%m'))
        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.nombre).all()
        if request.method == 'POST':
            emp_id = int(request.form.get('empleado_id') or 0)
            emp = db.session.get(Empleado, emp_id)
            if not emp:
                flash('Empleado no encontrado.', 'danger')
                return redirect(url_for('horas_extra', periodo=periodo))
            tipo = request.form.get('tipo', 'diurna')
            horas = float(request.form.get('horas') or 0)
            fecha = request.form.get('fecha', '')
            if horas <= 0:
                flash('Las horas deben ser mayor a cero.', 'warning')
                return redirect(url_for('horas_extra', periodo=periodo))
            recargo = RECARGOS_HE.get(tipo, 0.25)
            salario_hora = float(emp.salario_base or 0) / 240  # 30 dias * 8 horas
            valor = round(salario_hora * (1 + recargo) * horas)
            he = HoraExtra(
                empleado_id=emp_id,
                fecha=datetime.strptime(fecha, '%Y-%m-%d').date() if fecha else datetime.utcnow().date(),
                tipo=tipo, horas=horas, recargo_pct=recargo, valor=valor,
                periodo=periodo, notas=request.form.get('notas', ''),
                creado_por=current_user.id
            )
            db.session.add(he); db.session.commit()
            flash(f'Hora extra registrada: {horas}h {tipo} = {moneda(valor)}', 'success')
            return redirect(url_for('horas_extra', periodo=periodo))
        registros = HoraExtra.query.filter_by(periodo=periodo).order_by(HoraExtra.fecha.desc()).all()
        total_valor = sum(float(r.valor or 0) for r in registros)
        return render_template('nomina/horas_extra.html', registros=registros, empleados=empleados,
                               periodo=periodo, total_valor=total_valor, recargos=RECARGOS_HE)

    # ── horas_extra_eliminar (/nomina/horas-extra/<id>/eliminar)
    @app.route('/nomina/horas-extra/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('nomina')
    def horas_extra_eliminar(id):
        he = HoraExtra.query.get_or_404(id)
        periodo = he.periodo
        db.session.delete(he); db.session.commit()
        flash('Registro eliminado.', 'info')
        return redirect(url_for('horas_extra', periodo=periodo))


    # ══════════════════════════════════════════════════════════════════════════
    # ARCHIVO PILA (Res. 2388/2016 — Planilla Integrada Liquidación Aportes)
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/nomina/pila')
    @login_required
    @requiere_modulo('nomina')
    def nomina_pila():
        """Página de generación de archivo PILA para el periodo seleccionado."""
        import calendar as cal_mod
        periodo = request.args.get('periodo', date_type.today().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except Exception:
            anio, mes = date_type.today().year, date_type.today().month
            periodo = date_type.today().strftime('%Y-%m')

        dias_del_mes = cal_mod.monthrange(anio, mes)[1]
        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.apellido, Empleado.nombre).all()

        # Vista previa: calcular aportes para cada empleado
        preview = []
        for emp in empleados:
            try:
                calc = _calcular_nomina(emp, dias_mes=dias_del_mes, dias_trabajados=dias_del_mes)
                ibc = float(emp.salario_base or 0)
                preview.append({
                    'empleado': emp,
                    'ibc': ibc,
                    'dias': dias_del_mes,
                    'salud_emp': calc.get('deduccion_salud', 0),
                    'salud_empr': calc.get('aporte_salud_empr', 0),
                    'pension_emp': calc.get('deduccion_pension', 0),
                    'pension_empr': calc.get('aporte_pension_empr', 0),
                    'arl': calc.get('aporte_arl', 0),
                    'caja': calc.get('aporte_caja', 0),
                    'sena': calc.get('aporte_sena', 0),
                    'icbf': calc.get('aporte_icbf', 0),
                    'total_empresa': calc.get('costo_total_empresa', 0),
                })
            except Exception as ex_p:
                logging.warning(f'nomina_pila preview({emp.id}): {ex_p}')
                preview.append({
                    'empleado': emp,
                    'ibc': float(emp.salario_base or 0),
                    'dias': dias_del_mes,
                    'salud_emp': 0, 'salud_empr': 0,
                    'pension_emp': 0, 'pension_empr': 0,
                    'arl': 0, 'caja': 0, 'sena': 0, 'icbf': 0,
                    'total_empresa': 0,
                })

        empresa = ConfigEmpresa.query.first()
        return render_template('nomina/pila.html',
            periodo=periodo, anio=anio, mes=mes,
            empleados=empleados, preview=preview,
            empresa=empresa, dias_del_mes=dias_del_mes)


    @app.route('/nomina/pila/generar')
    @login_required
    @requiere_modulo('nomina')
    def nomina_pila_generar():
        """Genera y descarga el archivo TXT en formato PILA simplificado (Res. 2388/2016)."""
        import calendar as cal_mod
        from flask import make_response
        periodo = request.args.get('periodo', date_type.today().strftime('%Y-%m'))
        try:
            anio, mes = int(periodo.split('-')[0]), int(periodo.split('-')[1])
        except Exception:
            anio, mes = date_type.today().year, date_type.today().month
            periodo = date_type.today().strftime('%Y-%m')

        dias_del_mes = cal_mod.monthrange(anio, mes)[1]
        empresa = ConfigEmpresa.query.first()
        nit_empresa = (empresa.nit or '000000000').replace('-', '').replace('.', '') if empresa else '000000000'
        razon_social = (empresa.nombre or 'EMPRESA').upper() if empresa else 'EMPRESA'

        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.apellido, Empleado.nombre).all()

        lineas = []

        # Registro tipo 01 — Encabezado (Header)
        # Formato: tipo|NIT|razon_social|periodo|tipo_planilla|total_empleados|fecha_generacion
        fecha_gen = date_type.today().strftime('%Y%m%d')
        header = (
            f'01'
            f'|{nit_empresa}'
            f'|{razon_social[:60]}'
            f'|{periodo}'
            f'|E'  # E = empleador
            f'|{len(empleados)}'
            f'|{fecha_gen}'
        )
        lineas.append(header)

        total_salud_emp   = 0.0
        total_salud_empr  = 0.0
        total_pension_emp = 0.0
        total_pension_empr= 0.0
        total_arl         = 0.0
        total_caja        = 0.0
        total_sena        = 0.0
        total_icbf        = 0.0

        # Registro tipo 02 — Detalle por empleado
        # Formato: tipo|cedula|nombre_completo|tipo_doc|IBC|dias|salud_emp|salud_empr|pension_emp|pension_empr|arl|caja|sena|icbf
        for seq, emp in enumerate(empleados, start=1):
            try:
                calc = _calcular_nomina(emp, dias_mes=dias_del_mes, dias_trabajados=dias_del_mes)
            except Exception as ex_g:
                logging.warning(f'nomina_pila_generar({emp.id}): {ex_g}')
                calc = {}

            cedula       = (emp.cedula or '').strip()
            nombre       = f'{(emp.nombre or "").strip()} {(emp.apellido or "").strip()}'.strip().upper()
            ibc          = int(float(emp.salario_base or 0))
            dias         = dias_del_mes
            salud_emp    = int(calc.get('deduccion_salud', 0))
            salud_empr   = int(calc.get('aporte_salud_empr', 0))
            pension_emp  = int(calc.get('deduccion_pension', 0))
            pension_empr = int(calc.get('aporte_pension_empr', 0))
            arl          = int(calc.get('aporte_arl', 0))
            caja         = int(calc.get('aporte_caja', 0))
            sena         = int(calc.get('aporte_sena', 0))
            icbf         = int(calc.get('aporte_icbf', 0))

            total_salud_emp   += salud_emp
            total_salud_empr  += salud_empr
            total_pension_emp += pension_emp
            total_pension_empr+= pension_empr
            total_arl         += arl
            total_caja        += caja
            total_sena        += sena
            total_icbf        += icbf

            detalle = (
                f'02'
                f'|{cedula}'
                f'|{nombre[:60]}'
                f'|CC'  # Cédula de ciudadanía (tipo doc más común)
                f'|{ibc}'
                f'|{dias}'
                f'|{salud_emp}'
                f'|{salud_empr}'
                f'|{pension_emp}'
                f'|{pension_empr}'
                f'|{arl}'
                f'|{caja}'
                f'|{sena}'
                f'|{icbf}'
            )
            lineas.append(detalle)

        # Registro tipo 03 — Totales
        totales = (
            f'03'
            f'|{len(empleados)}'
            f'|{int(total_salud_emp)}'
            f'|{int(total_salud_empr)}'
            f'|{int(total_pension_emp)}'
            f'|{int(total_pension_empr)}'
            f'|{int(total_arl)}'
            f'|{int(total_caja)}'
            f'|{int(total_sena)}'
            f'|{int(total_icbf)}'
            f'|{int(total_salud_emp + total_salud_empr + total_pension_emp + total_pension_empr + total_arl + total_caja + total_sena + total_icbf)}'
        )
        lineas.append(totales)

        contenido = '\r\n'.join(lineas) + '\r\n'
        filename = f'PILA_{nit_empresa}_{periodo.replace("-", "")}.txt'

        resp = make_response(contenido)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp


    # ── incapacidades (/nomina/incapacidades)
    @app.route('/nomina/incapacidades', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('nomina')
    def incapacidades():
        if request.method == 'POST':
            emp_id = int(request.form.get('empleado_id'))
            fi_str = request.form.get('fecha_inicio')
            ff_str = request.form.get('fecha_fin')
            try:
                fi = datetime.strptime(fi_str, '%Y-%m-%d').date()
                ff = datetime.strptime(ff_str, '%Y-%m-%d').date()
                dias = max((ff - fi).days + 1, 0)
            except Exception:
                flash('Fechas invalidas.', 'danger')
                return redirect(url_for('incapacidades'))
            inc = Incapacidad(
                empleado_id=emp_id,
                fecha_inicio=fi,
                fecha_fin=ff,
                dias=dias,
                tipo=request.form.get('tipo', 'general'),
                entidad=request.form.get('entidad', 'EPS'),
                diagnostico=request.form.get('diagnostico', '').strip(),
                notas=request.form.get('notas', '').strip() or None,
                creado_por=current_user.id
            )
            db.session.add(inc)
            db.session.commit()
            flash(f'Incapacidad registrada ({dias} dias).', 'success')
            return redirect(url_for('incapacidades'))
        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.apellido, Empleado.nombre).all()
        items = Incapacidad.query.order_by(Incapacidad.fecha_inicio.desc()).all()
        return render_template('nomina/incapacidades.html', empleados=empleados, items=items)


    # ── vacaciones (/nomina/vacaciones)
    @app.route('/nomina/vacaciones', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('nomina')
    def vacaciones_tomadas():
        if request.method == 'POST':
            emp_id = int(request.form.get('empleado_id'))
            fi_str = request.form.get('fecha_inicio')
            ff_str = request.form.get('fecha_fin')
            try:
                fi = datetime.strptime(fi_str, '%Y-%m-%d').date()
                ff = datetime.strptime(ff_str, '%Y-%m-%d').date()
                dias = max((ff - fi).days + 1, 0)
            except Exception:
                flash('Fechas invalidas.', 'danger')
                return redirect(url_for('vacaciones_tomadas'))
            vac = VacacionTomada(
                empleado_id=emp_id,
                fecha_inicio=fi,
                fecha_fin=ff,
                dias=dias,
                tipo=request.form.get('tipo', 'remuneradas'),
                notas=request.form.get('notas', '').strip() or None,
                creado_por=current_user.id
            )
            db.session.add(vac)
            db.session.commit()
            flash(f'Vacaciones registradas ({dias} dias).', 'success')
            return redirect(url_for('vacaciones_tomadas'))

        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.apellido, Empleado.nombre).all()
        items = VacacionTomada.query.order_by(VacacionTomada.fecha_inicio.desc()).all()

        # Calcular saldo de vacaciones por empleado
        hoy = date_type.today()
        saldos = {}
        for e in empleados:
            if e.fecha_ingreso:
                dias_trabajados = (hoy - e.fecha_ingreso).days
                dias_acumulados = int((dias_trabajados / 365) * 15)
            else:
                dias_acumulados = 0
            dias_tomados = sum(
                v.dias for v in VacacionTomada.query.filter_by(empleado_id=e.id).all()
            )
            saldos[e.id] = {
                'acumulados': dias_acumulados,
                'tomados': dias_tomados,
                'saldo': max(dias_acumulados - dias_tomados, 0)
            }

        return render_template('nomina/vacaciones.html',
                               empleados=empleados, items=items, saldos=saldos)

