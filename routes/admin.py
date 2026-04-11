# routes/admin.py — reconstruido desde v27 con CRUD completo
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

    # ── impuestos (/finanzas/impuestos)
    @app.route('/finanzas/impuestos')
    @login_required
    def impuestos():
        return render_template('finanzas/impuestos.html',
                               items=ReglaTributaria.query.order_by(ReglaTributaria.nombre).all())
    

    # ── impuesto_nuevo (/finanzas/impuestos/nuevo)
    @app.route('/finanzas/impuestos/nuevo', methods=['GET','POST'])
    @login_required
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
    def impuesto_eliminar(id):
        obj=ReglaTributaria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Regla eliminada.','info'); return redirect(url_for('impuestos'))
    

    # ── gastos (/gastos)
    @app.route('/gastos')
    @login_required
    def gastos():
        from datetime import date as date_t
        tipo_f  = request.args.get('tipo','')
        desde_f = request.args.get('desde','')
        hasta_f = request.args.get('hasta','')
        try:
            q = GastoOperativo.query.filter_by(es_plantilla=False)
            if tipo_f:  q = q.filter_by(tipo=tipo_f)
            if desde_f: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_f,'%Y-%m-%d').date())
            if hasta_f: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_f,'%Y-%m-%d').date())
            items = q.order_by(GastoOperativo.fecha.desc()).all()
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
            items = q2.order_by(GastoOperativo.fecha.desc()).all()
            total_g = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
            mes_ini = date_t.today().replace(day=1)
            total_mes = db.session.query(db.func.sum(GastoOperativo.monto)).filter(GastoOperativo.fecha>=mes_ini).scalar() or 0
            tipos = [t[0] for t in db.session.query(GastoOperativo.tipo).distinct().order_by(GastoOperativo.tipo).all()]
            plantillas = []; total_reg = len(items)
        return render_template('gastos/index.html', items=items, tipo_f=tipo_f,
            desde_f=desde_f, hasta_f=hasta_f, total_general=total_g,
            total_mes=total_mes, total_registros=total_reg,
            tipos=tipos, plantillas=plantillas)
    

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
                u = User(nombre=request.form['nombre'], email=request.form['email'],
                         rol=rol,
                         modulos_permitidos=json.dumps(modulos_sel) if modulos_sel else '[]')
                if rol == 'cliente':
                    cli_id = request.form.get('cliente_id')
                    u.cliente_id = int(cli_id) if cli_id else None
                if rol == 'proveedor':
                    prov_id = request.form.get('proveedor_id')
                    u.proveedor_id = int(prov_id) if prov_id else None
                u.set_password(_pwd); db.session.add(u); db.session.commit()
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
            u.activo=not u.activo; db.session.commit()
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
    @app.route('/demo/activar', methods=['POST'])
    @login_required
    def activar_demo():
        """Carga datos demo sin afectar datos reales existentes."""
        if Cliente.query.count() > 0:
            flash('Ya hay datos en el sistema. El demo solo funciona en un sistema vacio.', 'warning')
            return redirect(url_for('dashboard'))
        try:
            from models import _seed_demo_data
            _seed_demo_data()
            flash('Datos demo cargados exitosamente. Puedes explorar el sistema con datos de ejemplo.', 'success')
        except Exception as e:
            flash(f'Error al cargar demo: {e}', 'danger')
        return redirect(url_for('dashboard'))

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

            db.session.commit(); flash('Configuración guardada.','success')
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
            # Roles de portal: vincular empresa
            if u.rol == 'cliente':
                cli_id = request.form.get('cliente_id')
                u.cliente_id = int(cli_id) if cli_id else None
            else:
                u.cliente_id = None
            if u.rol == 'proveedor':
                prov_id = request.form.get('proveedor_id')
                u.proveedor_id = int(prov_id) if prov_id else None
            else:
                u.proveedor_id = None
            # Guardar módulos personalizados
            modulos_sel = request.form.getlist('modulos')
            u.modulos_permitidos = json.dumps(modulos_sel) if modulos_sel else '[]'
            db.session.commit()
            flash('Usuario actualizado.','success'); return redirect(url_for('admin_usuarios'))
        clientes_list  = Cliente.query.filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
        proveedores_list = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
        return render_template('admin/usuario_form.html', obj=u, titulo='Editar Usuario',
                               clientes_list=clientes_list, proveedores_list=proveedores_list)
    

    # ── legal_index (/legal)
    @app.route('/legal')
    @login_required
    def legal_index():
        tipo_f = request.args.get('tipo','')
        estado_f = request.args.get('estado','')
        q = DocumentoLegal.query.filter_by(activo=True)
        if tipo_f: q = q.filter_by(tipo=tipo_f)
        if estado_f: q = q.filter_by(estado=estado_f)
        items = q.order_by(DocumentoLegal.fecha_vencimiento).all()
        # Alertas: vencimientos próximos
        from datetime import timedelta
        hoy = datetime.utcnow().date()
        alertas = [d for d in items if d.fecha_vencimiento and
                   (d.fecha_vencimiento - hoy).days <= d.recordatorio_dias
                   and d.estado == 'vigente']
        return render_template('legal/index.html', items=items,
                               tipo_f=tipo_f, estado_f=estado_f, alertas=alertas)
    

    # ── legal_nuevo (/legal/nuevo)
    @app.route('/legal/nuevo', methods=['GET','POST'])
    @login_required
    def legal_nuevo():
        if request.method == 'POST':
            fe = request.form.get('fecha_emision')
            fv = request.form.get('fecha_vencimiento')
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
                activo=True, creado_por=current_user.id
            )
            db.session.add(d); db.session.commit()
            flash('Documento legal creado.','success')
            return redirect(url_for('legal_index'))
        return render_template('legal/form.html', obj=None, titulo='Nuevo Documento Legal')
    

    # ── legal_editar (/legal/<int:id>/editar)
    @app.route('/legal/<int:id>/editar', methods=['GET','POST'])
    @login_required
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
            db.session.commit()
            flash('Documento actualizado.','success')
            return redirect(url_for('legal_index'))
        return render_template('legal/form.html', obj=obj, titulo='Editar Documento Legal')
    

    # ── legal_eliminar (/legal/<int:id>/eliminar)
    @app.route('/legal/<int:id>/eliminar', methods=['POST'])
    @login_required
    def legal_eliminar(id):
        obj = DocumentoLegal.query.get_or_404(id)
        obj.activo = False; db.session.commit()
        flash('Documento eliminado.','info')
        return redirect(url_for('legal_index'))


    # ── admin_reset_total (/admin/reset-total) ─────────────────────────────────
    @app.route('/admin/reset-total', methods=['POST'])
    @login_required
    def admin_reset_total():
        """Borra TODOS los datos operativos. Solo accesible para admin.
        Requiere confirmación con contraseña del administrador."""
        from werkzeug.security import check_password_hash
        if current_user.rol != 'admin':
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        password_confirm = request.form.get('password_confirm', '')
        if not check_password_hash(current_user.password_hash, password_confirm):
            flash('Contraseña incorrecta. El reset no fue ejecutado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        def _safe_delete(sql):
            """Ejecuta un DELETE usando un savepoint. Si la tabla no existe,
            descarta solo ese paso y continúa — nunca aborta el reset completo."""
            sp = db.session.begin_nested()
            try:
                db.session.execute(db.text(sql))
                sp.commit()
            except Exception as _e:
                sp.rollback()
                logging.info(f'admin_reset_total: skip "{sql}" — {_e.__class__.__name__}')

        try:
            # ── Borrar en orden respetando FKs (dependientes primero) ──────────
            # Nivel 5 — registros de asociación y comentarios
            _safe_delete('DELETE FROM tarea_asignados')
            _safe_delete('DELETE FROM tarea_comentarios')
            # Nivel 4 — ítems de documentos
            _safe_delete('DELETE FROM reservas_produccion')
            _safe_delete('DELETE FROM cotizacion_items')
            _safe_delete('DELETE FROM pre_cotizacion_items')
            _safe_delete('DELETE FROM ordenes_compra_items')
            _safe_delete('DELETE FROM venta_productos')
            _safe_delete('DELETE FROM materia_prima_productos')
            _safe_delete('DELETE FROM receta_items')
            # Nivel 3 — entidades con FKs a otras entidades
            _safe_delete('DELETE FROM ordenes_produccion')
            _safe_delete('DELETE FROM lotes_materia_prima')
            _safe_delete('DELETE FROM lotes_producto')
            _safe_delete('DELETE FROM compras_materia')
            _safe_delete('DELETE FROM cotizaciones_proveedor')   # nombre real del modelo
            _safe_delete('DELETE FROM cotizaciones_granel')
            _safe_delete('DELETE FROM empaques_secundarios')
            _safe_delete('DELETE FROM asientos_contables')
            _safe_delete('DELETE FROM tareas')
            _safe_delete('DELETE FROM eventos')
            _safe_delete('DELETE FROM notas')
            _safe_delete('DELETE FROM notificaciones')
            _safe_delete('DELETE FROM actividades')              # nombre real del modelo
            # Nivel 2 — documentos principales
            _safe_delete('DELETE FROM ventas')
            _safe_delete('DELETE FROM cotizaciones')
            _safe_delete('DELETE FROM pre_cotizaciones')
            _safe_delete('DELETE FROM ordenes_compra')
            _safe_delete('DELETE FROM gastos_operativos')
            _safe_delete('DELETE FROM documentos_legales')
            _safe_delete('DELETE FROM empleados')
            _safe_delete('DELETE FROM recetas_producto')
            _safe_delete('DELETE FROM servicios')
            # Nivel 1 — catálogos y configuración operativa
            _safe_delete('DELETE FROM reglas_tributarias')
            _safe_delete('DELETE FROM materias_primas')
            _safe_delete('DELETE FROM productos')
            _safe_delete('DELETE FROM contactos_cliente')
            _safe_delete('DELETE FROM clientes')
            _safe_delete('DELETE FROM proveedores')
            # Sesiones y usuarios (mantener solo admin actual)
            _safe_delete(f'DELETE FROM user_sesiones WHERE user_id != {current_user.id}')
            _safe_delete(f'DELETE FROM users WHERE id != {current_user.id}')
            db.session.commit()
            logging.warning(f'RESET TOTAL ejecutado por admin user_id={current_user.id} '
                            f'({current_user.email}) desde IP {request.remote_addr}')
            flash('✓ Reset total ejecutado. Todos los datos han sido eliminados. '
                  'La cuenta administradora se conservó.', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'admin_reset_total ERROR: {e}')
            flash(f'Error durante el reset: {e}', 'danger')

        return redirect(url_for('admin_usuarios'))

