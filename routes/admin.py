# routes/admin.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging

def register(app):

    # ── impuestos (/finanzas/impuestos)
    @app.route('/finanzas/impuestos')
    @login_required
    def impuestos():
        return render_template('finanzas/impuestos.html',
                               items=ReglaTributaria.query.order_by(ReglaTributaria.nombre).all())
    

    # ── impuesto_nuevo (/finanzas/impuestos/nuevo)
    @app.route('/finanzas/impuestos/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('finanzas')
    def impuesto_nuevo():
        if request.method == 'POST':
            db.session.add(ReglaTributaria(
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion',''),
                porcentaje=float(request.form.get('porcentaje',0) or 0),
                aplica_a=request.form.get('aplica_a','ventas'),
                proveedor_nombre=request.form.get('proveedor_nombre','') or None,
                activo=True))
            db.session.commit(); flash('Regla tributaria creada.','success')
            return redirect(url_for('impuestos'))
        return render_template('finanzas/impuesto_form.html', obj=None, titulo='Nueva Regla Tributaria')
    

    # ── impuesto_editar (/finanzas/impuestos/<int:id>/editar)
    @app.route('/finanzas/impuestos/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('finanzas')
    def impuesto_editar(id):
        obj=ReglaTributaria.query.get_or_404(id)
        if request.method == 'POST':
            obj.nombre=request.form['nombre']
            obj.descripcion=request.form.get('descripcion','')
            obj.porcentaje=float(request.form.get('porcentaje',0) or 0)
            obj.aplica_a=request.form.get('aplica_a','ventas')
            obj.proveedor_nombre=request.form.get('proveedor_nombre','') or None
            obj.activo = request.form.get('activo') == '1'
            db.session.commit(); flash('Regla actualizada.','success')
            return redirect(url_for('impuestos'))
        return render_template('finanzas/impuesto_form.html', obj=obj, titulo='Editar Regla Tributaria')
    

    # ── impuesto_eliminar (/finanzas/impuestos/<int:id>/eliminar)
    @app.route('/finanzas/impuestos/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('finanzas')
    def impuesto_eliminar(id):
        obj=ReglaTributaria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Regla eliminada.','info'); return redirect(url_for('impuestos'))
    

    # ── gastos (/gastos)
    @app.route('/gastos')
    @login_required
    @requiere_modulo('gastos')
    def gastos():
        from datetime import date as date_t
        tipo_f  = request.args.get('tipo','')
        desde_f = request.args.get('desde','')
        hasta_f = request.args.get('hasta','')
        page = request.args.get('page', 1, type=int)
        try:
            q = GastoOperativo.query.filter_by(es_plantilla=False)
            if tipo_f:  q = q.filter_by(tipo=tipo_f)
            if desde_f: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_f,'%Y-%m-%d').date())
            if hasta_f: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_f,'%Y-%m-%d').date())
            pagination = q.order_by(GastoOperativo.fecha.desc()).paginate(page=page, per_page=25, error_out=False)
            items = pagination.items
            total_g   = db.session.query(db.func.sum(GastoOperativo.monto)).filter_by(es_plantilla=False).scalar() or 0
            mes_ini   = date_t.today().replace(day=1)
            total_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(
                GastoOperativo.es_plantilla==False, GastoOperativo.fecha>=mes_ini).scalar() or 0
            tipos     = [t[0] for t in db.session.query(GastoOperativo.tipo).filter_by(es_plantilla=False).distinct().order_by(GastoOperativo.tipo).all()]
            plantillas = GastoOperativo.query.filter_by(es_plantilla=True).order_by(GastoOperativo.tipo).all()
            total_reg = GastoOperativo.query.filter_by(es_plantilla=False).count()
        except Exception:
            db.session.rollback()
            q2 = GastoOperativo.query
            if tipo_f: q2 = q2.filter_by(tipo=tipo_f)
            pagination = q2.order_by(GastoOperativo.fecha.desc()).paginate(page=page, per_page=25, error_out=False)
            items = pagination.items
            total_g = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
            mes_ini = date_t.today().replace(day=1)
            total_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha>=mes_ini).scalar() or 0
            tipos = [t[0] for t in db.session.query(GastoOperativo.tipo).distinct().order_by(GastoOperativo.tipo).all()]
            plantillas = []; total_reg = pagination.total
        return render_template('gastos/index.html', items=items, tipo_f=tipo_f,
            desde_f=desde_f, hasta_f=hasta_f, total_general=total_g,
            total_mes=total_mes, total_registros=total_reg,
            tipos=tipos, plantillas=plantillas, pagination=pagination)
    

    # ── gasto_nuevo (/gastos/nuevo)
    @app.route('/gastos/nuevo', methods=['GET','POST'])
    @login_required
    def gasto_nuevo():
        if request.method == 'POST':
            # Sistema de aprobación: roles no financieros requieren autorización
            monto_gasto = float(request.form.get('monto',0) or 0)
            if current_user.rol not in ('admin', 'director_financiero') and monto_gasto > 0:
                from routes.aprobaciones import register as _
                desc = f'Gasto: {request.form.get("descripcion","")[:100]} — ${monto_gasto:,.0f}'
                a = Aprobacion(
                    tipo_accion='gasto_nuevo', descripcion=desc, monto=monto_gasto,
                    datos_json=json.dumps(dict(request.form), ensure_ascii=False),
                    estado='pendiente', solicitado_por=current_user.id)
                db.session.add(a); db.session.commit()
                directores = User.query.filter(User.rol.in_(['admin','director_financiero']), User.activo==True).all()
                for d in directores:
                    _crear_notificacion(d.id, 'alerta', f'Aprobacion requerida: {desc[:80]}',
                        f'{current_user.nombre} solicita registrar gasto de ${monto_gasto:,.0f}',
                        url_for('aprobaciones_pendientes'))
                flash(f'Solicitud de aprobacion enviada al director financiero. Monto: ${monto_gasto:,.0f}', 'info')
                return redirect(url_for('gastos'))
            fd = request.form.get('fecha')
            rec = request.form.get('recurrencia','unico')
            es_pl = request.form.get('es_plantilla') == '1' and rec == 'mensual'
            g = GastoOperativo(
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                tipo=request.form['tipo'],
                tipo_custom=request.form.get('tipo_custom','') or None,
                descripcion=request.form.get('descripcion',''),
                monto=float(request.form.get('monto',0) or 0),
                recurrencia=rec,
                es_plantilla=es_pl,
                notas=request.form.get('notas',''), creado_por=current_user.id)
            db.session.add(g); db.session.flush()
            tipo_gasto = request.form['tipo']
            monto_gasto = float(request.form.get('monto',0) or 0)
            if monto_gasto > 0 and not es_pl:
                _crear_asiento_auto(
                    tipo='gasto', subtipo=f'gasto_{tipo_gasto}',
                    descripcion=f'Gasto: {g.descripcion or tipo_gasto}',
                    monto=monto_gasto,
                    cuenta_debe=f'Gastos {tipo_gasto}',
                    cuenta_haber='Bancos / Caja',
                    clasificacion='egreso',
                    gasto_id=g.id
                )
            db.session.commit(); flash('Gasto registrado.','success'); return redirect(url_for('gastos'))
        return render_template('gastos/form.html', obj=None, titulo='Nuevo Gasto',
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── gasto_editar (/gastos/<int:id>/editar)
    @app.route('/gastos/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def gasto_editar(id):
        obj = GastoOperativo.query.get_or_404(id)
        if request.method == 'POST':
            fd = request.form.get('fecha')
            rec = request.form.get('recurrencia','unico')
            obj.fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else obj.fecha
            obj.tipo=request.form['tipo']
            obj.tipo_custom=request.form.get('tipo_custom','') or None
            obj.descripcion=request.form.get('descripcion','')
            obj.monto=float(request.form.get('monto',0) or 0)
            obj.recurrencia=rec
            obj.es_plantilla=request.form.get('es_plantilla') == '1' and rec == 'mensual'
            obj.notas=request.form.get('notas','')
            # Sincronizar asiento contable vinculado
            asiento_link = AsientoContable.query.filter_by(gasto_id=obj.id).first()
            if asiento_link:
                asiento_link.debe = float(obj.monto)
                asiento_link.haber = float(obj.monto)
                asiento_link.descripcion = f'Gasto: {obj.descripcion or obj.tipo}'[:300]
                asiento_link.fecha = obj.fecha
            db.session.commit(); flash('Gasto actualizado.','success'); return redirect(url_for('gastos'))
        return render_template('gastos/form.html', obj=obj, titulo='Editar Gasto',
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── gasto_eliminar (/gastos/<int:id>/eliminar)
    @app.route('/gastos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def gasto_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=GastoOperativo.query.get_or_404(id)
        # Eliminar asientos contables vinculados
        AsientoContable.query.filter_by(gasto_id=obj.id).delete()
        db.session.delete(obj); db.session.commit()
        flash('Gasto y asiento contable eliminados.','info'); return redirect(url_for('gastos'))
    

    # ── gasto_marcar_pagado (/gastos/<int:id>/marcar-pagado)
    @app.route('/gastos/<int:id>/marcar-pagado', methods=['POST'])
    @login_required
    def gasto_marcar_pagado(id):
        obj = GastoOperativo.query.get_or_404(id)
        obj.estado_pago = 'pagado'
        # Tambien marcar el asiento contable vinculado
        asiento = AsientoContable.query.filter_by(gasto_id=obj.id).first()
        if asiento:
            asiento.estado_pago = 'completo'
            asiento.fecha_pago = date_type.today()
        db.session.commit()
        flash(f'Gasto marcado como pagado.', 'success')
        return redirect(url_for('gastos'))


    # ── gasto_plantilla_usar (/gastos/plantilla/<int:id>/usar)
    @app.route('/gastos/plantilla/<int:id>/usar', methods=['POST'])
    @login_required
    def gasto_plantilla_usar(id):
        from datetime import date as date_t
        plantilla = GastoOperativo.query.get_or_404(id)
        nuevo = GastoOperativo(
            fecha=date_t.today(),
            tipo=plantilla.tipo,
            tipo_custom=plantilla.tipo_custom,
            descripcion=plantilla.descripcion,
            monto=plantilla.monto,
            recurrencia='mensual',
            es_plantilla=False,
            notas=f'Registrado desde plantilla mensual',
            creado_por=current_user.id)
        db.session.add(nuevo); db.session.flush()
        if nuevo.monto and nuevo.monto > 0:
            _crear_asiento_auto(
                tipo='gasto', subtipo=f'gasto_{nuevo.tipo}',
                descripcion=f'Gasto (plantilla): {nuevo.descripcion or nuevo.tipo}',
                monto=float(nuevo.monto),
                cuenta_debe=f'Gastos {nuevo.tipo}',
                cuenta_haber='Bancos / Caja',
                clasificacion='egreso',
                gasto_id=nuevo.id
            )
        db.session.commit()
        flash(f'Gasto "{plantilla.tipo_custom or plantilla.tipo}" registrado para este mes.','success')
        return redirect(url_for('gastos'))
    

    # ══════════════════════════════════════════════════════════════
    # MULTI-TENANCY: Company management (solo admin de Company principal)
    # ══════════════════════════════════════════════════════════════

    @app.route('/admin/empresas')
    @login_required
    def admin_empresas():
        """Lista de empresas — solo visible para admin de la plataforma."""
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Solo el administrador de la plataforma puede gestionar empresas.', 'danger')
            return redirect(url_for('dashboard'))
        empresas = Company.query.order_by(Company.id).all()
        # Count users per company
        for emp in empresas:
            emp._user_count = UserCompany.query.filter_by(company_id=emp.id, activo=True).count()
        return render_template('admin/empresas.html', empresas=empresas)

    @app.route('/admin/empresas/nueva', methods=['GET','POST'])
    @login_required
    def admin_empresa_nueva():
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()
            nit = request.form.get('nit', '').strip()
            max_users = int(request.form.get('max_users', 3))
            plan = request.form.get('plan', 'free')
            if not nombre:
                flash('El nombre es obligatorio.', 'danger')
                return render_template('admin/empresa_form.html', obj=None)
            slug = nombre.lower().replace(' ', '-').replace('.', '').replace(',', '')
            # Check slug unique
            if Company.query.filter_by(slug=slug).first():
                slug = f'{slug}-{Company.query.count()}'
            emp = Company(nombre=nombre, slug=slug, nit=nit, max_users=max_users,
                          plan=plan, activo=True, creado_por=current_user.id)
            db.session.add(emp)
            db.session.flush()
            # Create ConfigEmpresa for the new company
            db.session.add(ConfigEmpresa(nombre=nombre, company_id=emp.id))
            # Seed PUC for new company
            try:
                from company_config import COMPANY as _CC
                if _CC.get('chart_of_accounts') == 'co_puc':
                    for cuenta in CuentaPUC.query.filter_by(company_id=company.id).all():
                        new_cuenta = CuentaPUC(codigo=cuenta.codigo, nombre=cuenta.nombre,
                                               tipo=cuenta.tipo, nivel=cuenta.nivel,
                                               company_id=emp.id)
                        db.session.add(new_cuenta)
            except Exception:
                pass
            _log('crear', 'empresa', emp.id, f'Empresa creada: {emp.nombre} (max_users={max_users})')
            db.session.commit()
            flash(f'Empresa "{nombre}" creada. Ahora crea un usuario admin para ella.', 'success')
            return redirect(url_for('admin_empresa_usuario', empresa_id=emp.id))
        return render_template('admin/empresa_form.html', obj=None)

    @app.route('/admin/empresas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def admin_empresa_editar(id):
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        emp = Company.query.get_or_404(id)
        if request.method == 'POST':
            emp.nombre = request.form.get('nombre', emp.nombre).strip()
            emp.nit = request.form.get('nit', '').strip()
            emp.max_users = int(request.form.get('max_users', emp.max_users))
            emp.plan = request.form.get('plan', emp.plan)
            emp.activo = request.form.get('activo') == 'on'
            _log('editar', 'empresa', emp.id, f'Empresa editada: {emp.nombre}')
            db.session.commit()
            flash(f'Empresa "{emp.nombre}" actualizada.', 'success')
            return redirect(url_for('admin_empresas'))
        return render_template('admin/empresa_form.html', obj=emp)

    @app.route('/admin/empresas/<int:empresa_id>/usuario', methods=['GET','POST'])
    @login_required
    def admin_empresa_usuario(empresa_id):
        """Crear un usuario para una empresa específica."""
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        emp = Company.query.get_or_404(empresa_id)
        # Check user limit
        current_count = UserCompany.query.filter_by(company_id=emp.id, activo=True).count()
        if request.method == 'POST':
            if current_count >= emp.max_users:
                flash(f'Limite alcanzado: {emp.nombre} tiene {current_count}/{emp.max_users} usuarios.', 'danger')
                return redirect(url_for('admin_empresas'))
            email = request.form.get('email', '').strip()
            nombre = request.form.get('nombre', '').strip()
            rol = request.form.get('rol', 'usuario')
            password = request.form.get('password', '')
            if len(password) < 8:
                flash('Contraseña mínimo 8 caracteres.', 'danger')
                return render_template('admin/empresa_usuario_form.html', empresa=emp, current_count=current_count)
            # Check if user already exists
            existing = User.query.filter_by(email=email).first()
            if existing:
                # User exists — just add to this company
                existing_uc = UserCompany.query.filter_by(user_id=existing.id, company_id=emp.id).first()
                if existing_uc:
                    flash(f'{email} ya pertenece a {emp.nombre}.', 'warning')
                else:
                    db.session.add(UserCompany(user_id=existing.id, company_id=emp.id, rol=rol))
                    db.session.commit()
                    flash(f'{existing.nombre} agregado a {emp.nombre} como {rol}.', 'success')
            else:
                # Create new user
                u = User(nombre=nombre, email=email, rol=rol, company_id=emp.id)
                u.set_password(password)
                db.session.add(u)
                db.session.flush()
                db.session.add(UserCompany(user_id=u.id, company_id=emp.id, rol=rol))
                db.session.commit()
                flash(f'Usuario {nombre} creado en {emp.nombre}.', 'success')
            return redirect(url_for('admin_empresas'))
        return render_template('admin/empresa_usuario_form.html', empresa=emp, current_count=current_count)

    # ── admin_usuarios (/admin/usuarios)
    @app.route('/admin/usuarios')
    @login_required
    def admin_usuarios():
        if current_user.rol not in ('admin', 'tester'):
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        return render_template('admin/usuarios.html',
            items=User.query.order_by(User.nombre).all(),
            clientes_all=Cliente.query.filter_by(estado='activo').all(),
            proveedores_all=Proveedor.query.filter_by(activo=True).all())
    

    # ── admin_usuario_nuevo (/admin/usuarios/nuevo)
    @app.route('/admin/usuarios/nuevo', methods=['GET','POST'])
    @login_required
    def admin_usuario_nuevo():
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        if request.method == 'POST':
            _pwd = request.form.get('password','')
            if len(_pwd) < 8:
                flash('La contraseña debe tener al menos 8 caracteres.','danger')
            elif User.query.filter_by(email=request.form['email']).first():
                flash('Ya existe ese email.','danger')
            else:
                modulos_sel = request.form.getlist('modulos')
                rol = request.form.get('rol','usuario')
                roles_extra = request.form.getlist('roles_extra')
                u = User(nombre=request.form['nombre'], email=request.form['email'],
                         rol=rol,
                         modulos_permitidos=json.dumps(modulos_sel) if modulos_sel else '[]',
                         roles_asignados=json.dumps(roles_extra) if roles_extra else '[]')
                if rol == 'cliente':
                    cli_id = request.form.get('cliente_id')
                    u.cliente_id = int(cli_id) if cli_id else None
                if rol == 'proveedor':
                    prov_id = request.form.get('proveedor_id')
                    u.proveedor_id = int(prov_id) if prov_id else None
                u.set_password(_pwd); db.session.add(u); _log('crear', 'usuario', u.id, f'Usuario creado: {u.nombre} ({u.email}), rol={u.rol}')
                db.session.commit()
                flash('Usuario creado.','success'); return redirect(url_for('admin_usuarios'))
        clientes_list  = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
        proveedores_list = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
        return render_template('admin/usuario_form.html', obj=None, titulo='Nuevo Usuario',
                               clientes_list=clientes_list, proveedores_list=proveedores_list)
    

    # ── admin_usuario_toggle (/admin/usuarios/<int:id>/toggle)
    @app.route('/admin/usuarios/<int:id>/toggle', methods=['POST'])
    @login_required
    def admin_usuario_toggle(id):
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        u=User.query.get_or_404(id)
        if u.id != current_user.id:
            u.activo=not u.activo; _log('editar', 'usuario', u.id, f'Usuario {"activado" if u.activo else "desactivado"}: {u.nombre} ({u.email})')
            db.session.commit()
            flash(f'Usuario {"activado" if u.activo else "desactivado"}.','info')
        return redirect(url_for('admin_usuarios'))
    

    # ── admin_impersonar (/admin/impersonar/<int:id>)
    @app.route('/admin/impersonar/<int:id>', methods=['POST'])
    @login_required
    def admin_impersonar(id):
        """Admin can temporarily view the app as another user."""
        from flask import session as flask_session
        from flask_login import login_user
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        target = User.query.get_or_404(id)
        # Save real admin id in session
        _log('impersonar', 'usuario', target.id, f'Admin impersonando a: {target.nombre} ({target.rol})')
        db.session.commit()
        flask_session['admin_real_id'] = current_user.id
        login_user(target, remember=False)
        flash(f'Viendo la app como: {target.nombre} ({target.rol}). Usa "Volver a admin" para regresar.','warning')
        # Redirect to appropriate portal
        if target.rol == 'cliente':
            return redirect(url_for('portal_cliente'))
        elif target.rol == 'proveedor':
            return redirect(url_for('portal_proveedor'))
        return redirect(url_for('dashboard'))
    

    # ── admin_volver (/admin/volver)
    @app.route('/admin/volver', methods=['POST'])
    @login_required
    def admin_volver():
        """Return to real admin account after impersonation."""
        from flask import session as flask_session
        from flask_login import login_user
        admin_id = flask_session.pop('admin_real_id', None)
        if not admin_id:
            flash('No hay sesión de administrador guardada.','warning')
            return redirect(url_for('dashboard'))
        admin_user = db.session.get(User, admin_id)
        if not admin_user or admin_user.rol != 'admin':
            flash('Administrador no encontrado.','danger')
            return redirect(url_for('dashboard'))
        login_user(admin_user, remember=False)
        flash(f'Bienvenido de vuelta, {admin_user.nombre}.','success')
        return redirect(url_for('admin_usuarios'))
    

    # ── admin_config (/admin/empresa)
    # ── Activar datos demo (cualquier usuario puede activar en su cuenta)

    @app.route('/admin/empresa', methods=['GET','POST'])
    @login_required
    def admin_config():
        from werkzeug.utils import secure_filename
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        obj = ConfigEmpresa.query.first()
        if not obj:
            obj = ConfigEmpresa(nombre='Evore'); db.session.add(obj); db.session.commit()
        if request.method == 'POST':
            obj.nombre   = request.form.get('nombre','Evore')
            obj.nit      = request.form.get('nit','')
            obj.ciudad   = request.form.get('ciudad','')
            obj.telefono = request.form.get('telefono','')
            obj.email    = request.form.get('email','')
            obj.sitio_web= request.form.get('sitio_web','')
            obj.direccion= request.form.get('direccion','')

            # ── BLOQUE 6: Manejar upload de firma digital ──
            firma_file = request.files.get('firma_imagen')
            if firma_file and firma_file.filename:
                ext = firma_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'gif'):
                    firma_dir = os.path.join(current_app.root_path, 'static', 'firmas')
                    os.makedirs(firma_dir, exist_ok=True)
                    fname = secure_filename(f'firma_empresa.{ext}')
                    firma_path = os.path.join(firma_dir, fname)
                    firma_file.save(firma_path)
                    obj.firma_path = f'static/firmas/{fname}'
                    flash('Firma digital actualizada.', 'success')
                else:
                    flash('Formato de imagen no válido (PNG, JPG, JPEG, GIF).', 'warning')

            _log('editar', 'config_empresa', obj.id, f'Configuración empresa actualizada: {obj.nombre}')
            db.session.commit()
            flash('Configuración guardada.','success')
        return render_template('admin/config.html', obj=obj)
    

    # ── admin_usuario_editar (/admin/usuarios/<int:id>/editar)
    @app.route('/admin/usuarios/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def admin_usuario_editar(id):
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        u = User.query.get_or_404(id)
        if request.method == 'POST':
            _pwd = request.form.get('password','')
            u.nombre = request.form.get('nombre', u.nombre)
            u.email  = request.form.get('email', u.email)
            u.rol    = request.form.get('rol', u.rol)
            if _pwd and len(_pwd) >= 8:
                u.set_password(_pwd)
            elif _pwd and len(_pwd) < 8:
                flash('Contraseña muy corta (mín. 8 caracteres).','danger')
                clientes_list  = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
                proveedores_list = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
                return render_template('admin/usuario_form.html', obj=u, titulo='Editar Usuario',
                                       clientes_list=clientes_list, proveedores_list=proveedores_list)
            # Roles de portal: vincular empresa (solo modificar si el rol coincide)
            if u.rol == 'cliente':
                cli_id = request.form.get('cliente_id')
                u.cliente_id = int(cli_id) if cli_id else u.cliente_id
            if u.rol == 'proveedor':
                prov_id = request.form.get('proveedor_id')
                u.proveedor_id = int(prov_id) if prov_id else u.proveedor_id
            # Guardar módulos personalizados y roles extra
            modulos_sel = request.form.getlist('modulos')
            u.modulos_permitidos = json.dumps(modulos_sel) if modulos_sel else '[]'
            roles_extra = request.form.getlist('roles_extra')
            u.roles_asignados = json.dumps(roles_extra) if roles_extra else '[]'
            _log('editar', 'usuario', u.id, f'Usuario editado: {u.nombre} ({u.email}), rol={u.rol}')
            db.session.commit()
            flash('Usuario actualizado.','success'); return redirect(url_for('admin_usuarios'))
        clientes_list  = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
        proveedores_list = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
        return render_template('admin/usuario_form.html', obj=u, titulo='Editar Usuario',
                               clientes_list=clientes_list, proveedores_list=proveedores_list)
    

    # ── legal_nosotros (/legal/nosotros) — Info legal de la empresa
    @app.route('/legal/nosotros', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('legal')
    def legal_nosotros():
        empresa = ConfigEmpresa.query.first()
        if not empresa:
            empresa = ConfigEmpresa(nombre='Mi Empresa')
            db.session.add(empresa)
            db.session.commit()
        if request.method == 'POST':
            empresa.nombre = request.form.get('nombre', '') or empresa.nombre
            empresa.nit = request.form.get('nit', '') or empresa.nit
            empresa.representante_legal = request.form.get('representante_legal', '') or empresa.representante_legal
            empresa.representante_cedula = request.form.get('representante_cedula', '') or empresa.representante_cedula
            empresa.representante_cargo = request.form.get('representante_cargo', '') or empresa.representante_cargo
            empresa.tipo_sociedad = request.form.get('tipo_sociedad', '') or empresa.tipo_sociedad
            empresa.matricula_mercantil = request.form.get('matricula_mercantil', '') or empresa.matricula_mercantil
            empresa.camara_comercio = request.form.get('camara_comercio', '') or empresa.camara_comercio
            empresa.regimen_tributario = request.form.get('regimen_tributario', '') or empresa.regimen_tributario
            empresa.actividad_economica = request.form.get('actividad_economica', '') or empresa.actividad_economica
            empresa.contador_nombre = request.form.get('contador_nombre', '') or empresa.contador_nombre
            empresa.contador_tarjeta = request.form.get('contador_tarjeta', '') or empresa.contador_tarjeta
            empresa.revisor_fiscal = request.form.get('revisor_fiscal', '') or empresa.revisor_fiscal
            empresa.revisor_tarjeta = request.form.get('revisor_tarjeta', '') or empresa.revisor_tarjeta
            db.session.commit()
            flash('Informacion legal actualizada.', 'success')
            return redirect(url_for('legal_nosotros'))
        return render_template('legal/nosotros.html', empresa=empresa)


    # ── legal_generar (/legal/generar) — Generador de documentos legales
    @app.route('/legal/generar', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('legal')
    def legal_generar():
        """Generador de documentos legales con plantillas colombianas."""
        empresa = ConfigEmpresa.query.first()
        clientes_list = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa).all()
        proveedores_list = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all()
        empleados_list = Empleado.query.filter_by(estado='activo').order_by(Empleado.nombre).all()

        if request.method == 'POST':
            plantilla = request.form.get('plantilla', '')
            genero = request.form.get('genero', 'M')
            accion = request.form.get('accion', 'preview')  # preview | guardar
            firma_data = request.form.get('firma_data', '')
            selfie_data = request.form.get('selfie_data', '')
            firmante_nombre = request.form.get('firmante_nombre', '') or (getattr(empresa, 'representante_legal', '') or '')
            firmante_cedula = request.form.get('firmante_cedula', '') or (getattr(empresa, 'representante_cedula', '') or '')
            firmante_cargo = request.form.get('firmante_cargo', '') or 'Representante Legal'
            datos = {
                'empresa': empresa,
                'empresa_nombre': empresa.nombre if empresa else 'Empresa',
                'empresa_nit': empresa.nit if empresa else '',
                'empresa_direccion': empresa.direccion if empresa else '',
                'empresa_representante': getattr(empresa, 'representante_legal', '') or request.form.get('representante', ''),
                'empresa_representante_cedula': getattr(empresa, 'representante_cedula', '') or '',
                'empresa_representante_cargo': getattr(empresa, 'representante_cargo', '') or 'Representante Legal',
                'empresa_tipo_sociedad': getattr(empresa, 'tipo_sociedad', '') or 'SAS',
                'empresa_matricula': getattr(empresa, 'matricula_mercantil', '') or '',
                'empresa_camara': getattr(empresa, 'camara_comercio', '') or '',
                'empresa_regimen': getattr(empresa, 'regimen_tributario', '') or '',
                'empresa_actividad': getattr(empresa, 'actividad_economica', '') or '',
                'empresa_telefono': getattr(empresa, 'telefono', '') or '',
                'empresa_ciudad': getattr(empresa, 'ciudad', '') or request.form.get('ciudad', 'Bogota'),
                'fecha': request.form.get('fecha', datetime.utcnow().strftime('%d de %B de %Y')),
                'ciudad': request.form.get('ciudad', 'Bogota'),
                'genero': genero,
                'el_la': 'la' if genero == 'F' else 'el',
                'El_La': 'La' if genero == 'F' else 'El',
                'del_de_la': 'de la' if genero == 'F' else 'del',
                'al_a_la': 'a la' if genero == 'F' else 'al',
                'senor_senora': 'senora' if genero == 'F' else 'senor',
                'Senor_Senora': 'Senora' if genero == 'F' else 'Senor',
                'identificado_identificada': 'identificada' if genero == 'F' else 'identificado',
                'domiciliado_domiciliada': 'domiciliada' if genero == 'F' else 'domiciliado',
                'llamado_llamada': 'llamada' if genero == 'F' else 'llamado',
                'contratado_contratada': 'contratada' if genero == 'F' else 'contratado',
                'trabajador_trabajadora': 'trabajadora' if genero == 'F' else 'trabajador',
                'tercero_nombre': request.form.get('tercero_nombre', ''),
                'tercero_cedula': request.form.get('tercero_cedula', ''),
                'tercero_direccion': request.form.get('tercero_direccion', ''),
                'tercero_cargo': request.form.get('tercero_cargo', ''),
                'tercero_salario': request.form.get('tercero_salario', ''),
                'tercero_empresa': request.form.get('tercero_empresa', ''),
                'tercero_nit': request.form.get('tercero_nit', ''),
                'objeto': request.form.get('objeto', ''),
                'vigencia': request.form.get('vigencia', '12 meses'),
                'valor': request.form.get('valor', ''),
                'firma_data': firma_data,
                'selfie_empresa': selfie_data,
                'firmante_nombre': firmante_nombre,
                'firmante_cedula': firmante_cedula,
                'firmante_cargo': firmante_cargo,
            }

            if accion == 'guardar':
                # Determinar contraparte
                cargar_desde = request.form.get('cargar_desde_id', '')
                cliente_id = proveedor_id = None
                tipo_entidad = None
                if cargar_desde.startswith('cli_'):
                    cliente_id = int(cargar_desde.replace('cli_', ''))
                    tipo_entidad = 'cliente'
                elif cargar_desde.startswith('prov_'):
                    proveedor_id = int(cargar_desde.replace('prov_', ''))
                    tipo_entidad = 'proveedor'
                # Renderizar HTML del contrato
                contenido = render_template(f'legal/plantillas/{plantilla}.html', **datos)
                # Mapear plantilla a tipo
                tipo_map = {
                    'contrato_indefinido': 'contrato', 'contrato_fijo': 'contrato',
                    'contrato_prestacion': 'contrato', 'contrato_proveedor': 'contrato',
                    'contrato_cliente': 'contrato', 'nda': 'contrato',
                    'acta_entrega': 'certificado', 'carta_terminacion': 'otro',
                    'autorizacion_datos': 'otro',
                }
                tercero = request.form.get('tercero_nombre', '') or request.form.get('tercero_empresa', '')
                doc = DocumentoLegal(
                    tipo=tipo_map.get(plantilla, 'contrato'),
                    titulo=f'{plantilla.replace("_"," ").title()} — {tercero}',
                    entidad=empresa.nombre if empresa else '',
                    descripcion=request.form.get('objeto', '')[:200],
                    estado='en_tramite',
                    fecha_emision=datetime.utcnow().date(),
                    cliente_id=cliente_id,
                    proveedor_id=proveedor_id,
                    tipo_entidad=tipo_entidad,
                    requiere_firma_portal=bool(cliente_id or proveedor_id),
                    contenido_html=contenido,
                    activo=True,
                    creado_por=current_user.id
                )
                # Firma empresa
                if firma_data and len(firma_data) > 100:
                    doc.firma_empresa_data = firma_data
                    doc.firma_empresa_por = firmante_nombre
                    doc.firma_empresa_en = datetime.utcnow()
                if selfie_data and len(selfie_data) > 100:
                    doc.selfie_empresa_data = selfie_data
                db.session.add(doc)
                db.session.flush()
                doc.numero = f'DOC-{datetime.utcnow().year}-{doc.id:04d}'
                # Notificar contraparte en portal
                if cliente_id:
                    user_cli = User.query.filter_by(cliente_id=cliente_id, rol='cliente', activo=True).first()
                    if user_cli:
                        _crear_notificacion(user_cli.id, 'info', 'Nuevo documento para firmar',
                            f'{doc.titulo} — revisa tu portal de documentos legales.',
                            url_for('portal_cliente_docs'))
                elif proveedor_id:
                    user_prov = User.query.filter_by(proveedor_id=proveedor_id, rol='proveedor', activo=True).first()
                    if user_prov:
                        _crear_notificacion(user_prov.id, 'info', 'Nuevo documento para firmar',
                            f'{doc.titulo} — revisa tu portal de documentos legales.',
                            url_for('portal_prov_docs'))
                db.session.commit()
                flash(f'Documento "{doc.titulo}" guardado y enviado al portal para firma.', 'success')
                return redirect(url_for('legal_index'))

            # Preview: solo renderizar
            return render_template(f'legal/plantillas/{plantilla}.html', **datos)

        return render_template('legal/generar.html',
            empresa=empresa, clientes_list=clientes_list,
            proveedores_list=proveedores_list, empleados_list=empleados_list)


    # ── legal_desde_entidad (/legal/generar-desde/<tipo>/<int:id>)
    @app.route('/legal/generar-desde/<tipo>/<int:id>')
    @login_required
    def legal_desde_entidad(tipo, id):
        """Genera documento legal pre-llenado desde una entidad del CRM."""
        empresa = ConfigEmpresa.query.first()
        plantilla = request.args.get('plantilla', '')
        genero = request.args.get('genero', 'M')

        # Datos base empresa
        datos = {
            'empresa': empresa,
            'empresa_nombre': empresa.nombre if empresa else 'Empresa',
            'empresa_nit': empresa.nit if empresa else '',
            'empresa_direccion': getattr(empresa, 'direccion', '') or '',
            'empresa_representante': getattr(empresa, 'representante_legal', '') or '',
            'empresa_representante_cedula': getattr(empresa, 'representante_cedula', '') or '',
            'empresa_representante_cargo': getattr(empresa, 'representante_cargo', '') or 'Representante Legal',
            'empresa_tipo_sociedad': getattr(empresa, 'tipo_sociedad', '') or '',
            'empresa_matricula': getattr(empresa, 'matricula_mercantil', '') or '',
            'empresa_camara': getattr(empresa, 'camara_comercio', '') or '',
            'empresa_telefono': getattr(empresa, 'telefono', '') or '',
            'empresa_ciudad': getattr(empresa, 'ciudad', '') or 'Bogota',
            'fecha': datetime.utcnow().strftime('%d de %B de %Y'),
            'ciudad': getattr(empresa, 'ciudad', '') or 'Bogota',
            'genero': genero,
            'el_la': 'la' if genero == 'F' else 'el',
            'El_La': 'La' if genero == 'F' else 'El',
            'del_de_la': 'de la' if genero == 'F' else 'del',
            'al_a_la': 'a la' if genero == 'F' else 'al',
            'senor_senora': 'senora' if genero == 'F' else 'senor',
            'Senor_Senora': 'Senora' if genero == 'F' else 'Senor',
            'identificado_identificada': 'identificada' if genero == 'F' else 'identificado',
            'domiciliado_domiciliada': 'domiciliada' if genero == 'F' else 'domiciliado',
            'trabajador_trabajadora': 'trabajadora' if genero == 'F' else 'trabajador',
            'contratado_contratada': 'contratada' if genero == 'F' else 'contratado',
            'llamado_llamada': 'llamada' if genero == 'F' else 'llamado',
        }

        if tipo == 'venta':
            venta = Venta.query.get_or_404(id)
            try:
                cli = db.session.get(Cliente, venta.cliente_id) if venta.cliente_id else None
            except Exception:
                cli = None
            datos.update({
                'tercero_nombre': getattr(cli, 'nombre', '') or '' if cli else '',
                'tercero_cedula': getattr(cli, 'nit', '') or '' if cli else '',
                'tercero_empresa': getattr(cli, 'empresa', '') or '' if cli else '',
                'tercero_direccion': getattr(cli, 'direccion', '') or '' if cli else '',
                'objeto': f'Fabricacion y entrega de los productos del pedido {venta.numero or venta.titulo}',
                'valor': f'${venta.total:,.0f} COP' if venta.total else '',
                'vigencia': f'{venta.dias_entrega or 30} dias',
                'items': [{'nombre': getattr(it, 'nombre_prod', '') or '', 'cantidad': getattr(it, 'cantidad', 0) or 0,
                           'unidad': getattr(it, 'unidad', 'unidades') or 'unidades',
                           'descripcion': ''} for it in (venta.items or [])],
                'venta': venta,
            })
            if not plantilla:
                plantilla = 'acta_entrega'

        elif tipo == 'orden_compra':
            oc = OrdenCompra.query.get_or_404(id)
            prov = oc.proveedor if oc.proveedor_id else None
            datos.update({
                'tercero_nombre': prov.nombre if prov else '',
                'tercero_cedula': prov.nit if prov else '',
                'tercero_empresa': prov.empresa if prov else '',
                'tercero_nit': prov.nit if prov else '',
                'tercero_direccion': prov.direccion if prov else '',
                'objeto': f'Suministro de materiales segun OC {oc.numero}',
                'valor': f'${oc.total:,.0f} COP' if oc.total else '',
                'vigencia': '12 meses',
                'items': [{'nombre': it.nombre_item, 'cantidad': it.cantidad, 'unidad': it.unidad or 'unidades',
                           'descripcion': it.descripcion or ''} for it in oc.items] if oc.items else [],
            })
            if not plantilla:
                plantilla = 'contrato_proveedor'

        elif tipo == 'empleado':
            emp = Empleado.query.get_or_404(id)
            datos.update({
                'tercero_nombre': f'{emp.nombre} {emp.apellido}',
                'tercero_cedula': emp.cedula or '',
                'tercero_direccion': '',
                'tercero_cargo': emp.cargo or '',
                'tercero_salario': str(int(emp.salario_base)) if emp.salario_base else '',
            })
            if not plantilla:
                plantilla = 'contrato_indefinido' if emp.tipo_contrato == 'indefinido' else 'contrato_fijo'

        elif tipo == 'cliente':
            cli = Cliente.query.get_or_404(id)
            datos.update({
                'tercero_nombre': cli.nombre or '',
                'tercero_cedula': cli.nit or '',
                'tercero_empresa': cli.empresa or '',
                'tercero_direccion': cli.direccion or '',
            })
            if not plantilla:
                plantilla = 'contrato_cliente'

        elif tipo == 'proveedor':
            prov = Proveedor.query.get_or_404(id)
            datos.update({
                'tercero_nombre': prov.nombre or '',
                'tercero_cedula': prov.nit or '',
                'tercero_empresa': prov.empresa or '',
                'tercero_nit': prov.nit or '',
                'tercero_direccion': prov.direccion or '',
            })
            if not plantilla:
                plantilla = 'contrato_proveedor'

        # Asegurar que todos los campos tengan un default
        defaults = {
            'tercero_nombre':'','tercero_cedula':'','tercero_direccion':'',
            'tercero_cargo':'','tercero_salario':'','tercero_empresa':'',
            'tercero_nit':'','objeto':'','vigencia':'12 meses','valor':'',
            'items':[],'venta':None,'firma_data':'',
            'firmante_nombre': getattr(empresa, 'representante_legal', '') or '',
            'firmante_cedula': getattr(empresa, 'representante_cedula', '') or '',
            'firmante_cargo': getattr(empresa, 'representante_cargo', '') or 'Representante Legal',
        }
        for k,v in defaults.items():
            datos.setdefault(k, v)

        return render_template(f'legal/plantillas/{plantilla}.html', **datos)


    # ── legal_index (/legal)
    @app.route('/legal')
    @login_required
    @requiere_modulo('legal')
    def legal_index():
        tipo_f = request.args.get('tipo','')
        estado_f = request.args.get('estado','')
        buscar = request.args.get('q','').strip()
        q = DocumentoLegal.query.filter_by(activo=True)
        if tipo_f: q = q.filter_by(tipo=tipo_f)
        if estado_f: q = q.filter_by(estado=estado_f)
        if buscar:
            q = q.filter(db.or_(
                DocumentoLegal.titulo.ilike(f'%{buscar}%'),
                DocumentoLegal.numero.ilike(f'%{buscar}%'),
                DocumentoLegal.entidad.ilike(f'%{buscar}%'),
                DocumentoLegal.descripcion.ilike(f'%{buscar}%')
            ))
        items = q.order_by(DocumentoLegal.fecha_vencimiento).all()
        from datetime import timedelta
        hoy = datetime.utcnow().date()
        alertas = [d for d in items if d.fecha_vencimiento and
                   (d.fecha_vencimiento - hoy).days <= d.recordatorio_dias
                   and d.estado == 'vigente']
        return render_template('legal/index.html', items=items,
                               tipo_f=tipo_f, estado_f=estado_f, alertas=alertas, q=buscar)
    

    # ── legal_nuevo (/legal/nuevo)
    @app.route('/legal/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('legal')
    def legal_nuevo():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fe = request.form.get('fecha_emision')
            fv = request.form.get('fecha_vencimiento')
            prod_id = request.form.get('producto_id')
            d = DocumentoLegal(
                tipo=request.form.get('tipo','otro'),
                titulo=request.form['titulo'],
                numero=request.form.get('numero',''),
                entidad=request.form.get('entidad',''),
                descripcion=request.form.get('descripcion',''),
                estado=request.form.get('estado','vigente'),
                fecha_emision=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None,
                fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
                recordatorio_dias=int(request.form.get('recordatorio_dias') or 30),
                archivo_url=request.form.get('archivo_url',''),
                notas=request.form.get('notas',''),
                producto_id=int(prod_id) if prod_id else None,
                tipo_entidad='producto' if prod_id else None,
                requiere_firma_portal=request.form.get('requiere_firma_portal') == '1',
                activo=True, creado_por=current_user.id
            )
            # Firma empresa
            firma_emp = request.form.get('firma_empresa_data', '')
            if firma_emp and len(firma_emp) > 100:
                d.firma_empresa_data = firma_emp
                d.firma_empresa_por = request.form.get('firma_empresa_por', current_user.nombre)
                d.firma_empresa_en = datetime.utcnow()
            db.session.add(d); db.session.commit()
            flash('Documento legal creado.','success')
            return redirect(url_for('legal_index'))
        return render_template('legal/form.html', obj=None, titulo='Nuevo Documento Legal', productos=productos)
    

    # ── legal_editar (/legal/<int:id>/editar)
    @app.route('/legal/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('legal')
    def legal_editar(id):
        obj = DocumentoLegal.query.get_or_404(id)
        if request.method == 'POST':
            fe = request.form.get('fecha_emision')
            fv = request.form.get('fecha_vencimiento')
            obj.tipo=request.form.get('tipo','otro')
            obj.titulo=request.form.get('titulo','')
            obj.numero=request.form.get('numero','')
            obj.entidad=request.form.get('entidad','')
            obj.descripcion=request.form.get('descripcion','')
            obj.estado=request.form.get('estado','vigente')
            obj.fecha_emision=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None
            obj.fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None
            obj.recordatorio_dias=int(request.form.get('recordatorio_dias') or 30)
            obj.archivo_url=request.form.get('archivo_url','')
            obj.notas=request.form.get('notas','')
            obj.requiere_firma_portal = request.form.get('requiere_firma_portal') == '1'
            # Firma empresa
            firma_emp = request.form.get('firma_empresa_data', '')
            if firma_emp and len(firma_emp) > 100:
                obj.firma_empresa_data = firma_emp
                obj.firma_empresa_por = request.form.get('firma_empresa_por', current_user.nombre)
                obj.firma_empresa_en = datetime.utcnow()
            db.session.commit()
            flash('Documento actualizado.','success')
            return redirect(url_for('legal_index'))
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        return render_template('legal/form.html', obj=obj, titulo='Editar Documento Legal', productos=productos)
    

    # ── legal_eliminar (/legal/<int:id>/eliminar)
    @app.route('/legal/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('legal')
    def legal_eliminar(id):
        obj = DocumentoLegal.query.get_or_404(id)
        obj.activo = False; db.session.commit()
        flash('Documento eliminado.','info')
        return redirect(url_for('legal_index'))


    # ── legal_documento_firmado (/legal/<id>/firmado) — Documento con ambas firmas + selfies
    @app.route('/legal/<int:id>/firmado')
    @login_required
    def legal_documento_firmado(id):
        """Renderiza documento legal con ambas firmas y selfies incrustadas."""
        doc = DocumentoLegal.query.get_or_404(id)
        # Acceso: admin/legal o el firmante portal
        if current_user.rol not in ('admin', 'director_financiero', 'director_operativo', 'contador'):
            if current_user.rol == 'cliente' and doc.cliente_id != current_user.cliente_id:
                flash('Sin permisos.', 'danger'); return redirect(url_for('portal_cliente'))
            elif current_user.rol == 'proveedor' and doc.proveedor_id != current_user.proveedor_id:
                flash('Sin permisos.', 'danger'); return redirect(url_for('portal_proveedor'))
        empresa = ConfigEmpresa.query.first()
        # Datos para el template
        datos = {
            'doc': doc,
            'empresa': empresa,
            'empresa_nombre': empresa.nombre if empresa else '',
            'empresa_nit': empresa.nit if empresa else '',
            'empresa_direccion': getattr(empresa, 'direccion', '') or '',
            'empresa_representante': getattr(empresa, 'representante_legal', '') or '',
            'firma_empresa': doc.firma_empresa_data,
            'selfie_empresa': doc.selfie_empresa_data,
            'firma_portal': doc.firma_portal_data,
            'selfie_portal': doc.selfie_portal_data,
            'firmante_empresa': doc.firma_empresa_por or '',
            'firmante_portal': doc.firma_portal_por or '',
            'fecha_firma_empresa': doc.firma_empresa_en.strftime('%d/%m/%Y %H:%M') if doc.firma_empresa_en else '',
            'fecha_firma_portal': doc.firma_portal_en.strftime('%d/%m/%Y %H:%M') if doc.firma_portal_en else '',
        }
        return render_template('legal/documento_firmado.html', **datos)


    # ── admin_reset_total (/admin/reset-total) ─────────────────────────────────
    @app.route('/admin/reset-total', methods=['POST'])
    @login_required
    def admin_reset_total():
        """Borra TODOS los datos y usuarios (excepto el admin que ejecuta).
        Requiere confirmacion con contrasena del administrador."""
        from werkzeug.security import check_password_hash
        if current_user.rol not in ('admin', 'director_financiero'):
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        password_confirm = request.form.get('password_confirm', '')
        if not check_password_hash(current_user.password_hash, password_confirm):
            flash('Contrasena incorrecta. El reset no fue ejecutado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        def _safe_delete(sql):
            sp = db.session.begin_nested()
            try:
                db.session.execute(db.text(sql))
                sp.commit()
            except Exception as _e:
                sp.rollback()
                logging.warning(f'Reset: falló "{sql}": {_e}')

        admin_id = current_user.id
        try:
            # ── Nivel 7: líneas contables y asociaciones ──
            _safe_delete('DELETE FROM lineas_asiento')
            _safe_delete('DELETE FROM tarea_asignados')
            _safe_delete('DELETE FROM tarea_comentarios')
            _safe_delete('DELETE FROM pagos_venta')
            # ── Nivel 6: ítems de documentos ──
            _safe_delete('DELETE FROM reservas_produccion')
            _safe_delete('DELETE FROM cotizacion_items')
            _safe_delete('DELETE FROM pre_cotizacion_items')
            _safe_delete('DELETE FROM ordenes_compra_items')
            _safe_delete('DELETE FROM venta_productos')
            _safe_delete('DELETE FROM materia_prima_productos')
            _safe_delete('DELETE FROM receta_items')
            _safe_delete('DELETE FROM marcas_producto')
            _safe_delete('DELETE FROM historial_precios')
            _safe_delete('DELETE FROM historial_cotizaciones')
            # ── Nivel 5: entidades dependientes de empleados ──
            _safe_delete('DELETE FROM horas_extra')
            _safe_delete('DELETE FROM vacaciones_tomadas')
            _safe_delete('DELETE FROM incapacidades')
            # ── Nivel 4: entidades dependientes de asientos/contable ──
            _safe_delete('DELETE FROM movimientos_bancarios')
            _safe_delete('DELETE FROM notas_contables')
            _safe_delete('DELETE FROM movimientos_inventario')
            _safe_delete('DELETE FROM comisiones')
            _safe_delete('DELETE FROM ordenes_produccion')
            _safe_delete('DELETE FROM lotes_materia_prima')
            _safe_delete('DELETE FROM lotes_producto')
            _safe_delete('DELETE FROM compras_materia')
            _safe_delete('DELETE FROM cotizaciones_proveedor')
            _safe_delete('DELETE FROM cotizaciones_granel')
            _safe_delete('DELETE FROM empaques_secundarios')
            _safe_delete('DELETE FROM aprobaciones')
            _safe_delete('DELETE FROM requisiciones')
            _safe_delete('DELETE FROM asientos_contables')
            _safe_delete('DELETE FROM tareas')
            _safe_delete('DELETE FROM eventos')
            _safe_delete('DELETE FROM notas')
            _safe_delete('DELETE FROM notificaciones')
            _safe_delete('DELETE FROM actividades')
            # ── Nivel 3: documentos principales ──
            _safe_delete('DELETE FROM ventas')
            _safe_delete('DELETE FROM cotizaciones')
            _safe_delete('DELETE FROM pre_cotizaciones')
            _safe_delete('DELETE FROM ordenes_compra')
            _safe_delete('DELETE FROM gastos_operativos')
            _safe_delete('DELETE FROM documentos_legales')
            _safe_delete('DELETE FROM empleados')
            _safe_delete('DELETE FROM recetas_producto')
            _safe_delete('DELETE FROM servicios')
            # ── Nivel 2: catálogos ──
            _safe_delete('DELETE FROM reglas_tributarias')
            _safe_delete('DELETE FROM materias_primas')
            _safe_delete('DELETE FROM productos')
            _safe_delete('DELETE FROM contactos_cliente')
            _safe_delete('DELETE FROM clientes')
            _safe_delete('DELETE FROM proveedores')
            # ── Nivel 1: sesiones y usuarios ──
            _safe_delete('DELETE FROM user_sesiones')
            _safe_delete(f'DELETE FROM users WHERE id != {admin_id}')
            _log('eliminar', 'sistema', 0, f'RESET TOTAL ejecutado por {current_user.email}')
            db.session.commit()
            logging.warning(f'RESET TOTAL ejecutado por user_id={current_user.id} ({current_user.email})')
            flash('Reset completo. Todos los datos y usuarios eliminados (tu cuenta admin fue conservada).', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'admin_reset_total ERROR: {e}')
            flash(f'Error durante el reset: {e}', 'danger')

        return redirect(url_for('dashboard'))

