# routes/admin.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db, tenant_query
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
                               items=tenant_query(ReglaTributaria).order_by(ReglaTributaria.nombre).all())
    

    # ── impuesto_nuevo (/finanzas/impuestos/nuevo)
    @app.route('/finanzas/impuestos/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('finanzas')
    def impuesto_nuevo():
        if request.method == 'POST':
            db.session.add(ReglaTributaria(
                company_id=getattr(g, 'company_id', None),
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
            q = tenant_query(GastoOperativo).filter_by(es_plantilla=False)
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
            plantillas = tenant_query(GastoOperativo).filter_by(es_plantilla=True).order_by(GastoOperativo.tipo).all()
            total_reg = tenant_query(GastoOperativo).filter_by(es_plantilla=False).count()
        except Exception:
            db.session.rollback()
            q2 = tenant_query(GastoOperativo)
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
            gasto_new = GastoOperativo(
                company_id=getattr(g, 'company_id', None),
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                tipo=request.form['tipo'],
                tipo_custom=request.form.get('tipo_custom','') or None,
                descripcion=request.form.get('descripcion',''),
                monto=float(request.form.get('monto',0) or 0),
                recurrencia=rec,
                es_plantilla=es_pl,
                notas=request.form.get('notas',''), creado_por=current_user.id)
            db.session.add(gasto_new); db.session.flush()
            tipo_gasto = request.form['tipo']
            monto_gasto = float(request.form.get('monto',0) or 0)
            if monto_gasto > 0 and not es_pl:
                _crear_asiento_auto(
                    tipo='gasto', subtipo=f'gasto_{tipo_gasto}',
                    descripcion=f'Gasto: {gasto_new.descripcion or tipo_gasto}',
                    monto=monto_gasto,
                    cuenta_debe=f'5135 Gastos {tipo_gasto}',
                    cuenta_haber='110505 Caja',
                    clasificacion='egreso',
                    gasto_id=gasto_new.id
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
            asiento_link = tenant_query(AsientoContable).filter_by(gasto_id=obj.id).first()
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
        tenant_query(AsientoContable).filter_by(gasto_id=obj.id).delete()
        db.session.delete(obj); db.session.commit()
        flash('Gasto y asiento contable eliminados.','info'); return redirect(url_for('gastos'))
    

    # ── gasto_marcar_pagado (/gastos/<int:id>/marcar-pagado)
    @app.route('/gastos/<int:id>/marcar-pagado', methods=['POST'])
    @login_required
    def gasto_marcar_pagado(id):
        obj = GastoOperativo.query.get_or_404(id)
        obj.estado_pago = 'pagado'
        # Tambien marcar el asiento contable vinculado
        asiento = tenant_query(AsientoContable).filter_by(gasto_id=obj.id).first()
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
            company_id=getattr(g, 'company_id', None),
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
                cuenta_debe=f'5135 Gastos {nuevo.tipo}',
                cuenta_haber='110505 Caja',
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
            tipo_relacion = request.form.get('tipo_relacion', '')
            tipo_doc = request.form.get('tipo_documento', 'NIT')
            emp = Company(nombre=nombre, slug=slug, tipo_documento=tipo_doc, nit=nit,
                          max_users=max_users, plan=plan, activo=True, creado_por=current_user.id)
            db.session.add(emp)
            db.session.flush()
            # Create ConfigEmpresa for the new company
            db.session.add(ConfigEmpresa(nombre=nombre, company_id=emp.id))
            # ALWAYS create relationship with Evore (platform company)
            tipo_rel = tipo_relacion if tipo_relacion in ('cliente', 'proveedor', 'ambos') else 'cliente'
            rel = CompanyRelationship(
                company_from_id=company.id,
                company_to_id=emp.id,
                tipo=tipo_rel,
                activo=True
            )
            db.session.add(rel)
            db.session.flush()
            # Auto-create chat room for the relationship
            chat_room = ChatRoom(
                company_id=company.id,
                tipo=tipo_rel,
                nombre=f'{tipo_rel.capitalize()}: {nombre}',
                company_relationship_id=rel.id,
                creado_por=current_user.id
            )
            db.session.add(chat_room)
            db.session.flush()
            db.session.add(ChatParticipant(
                room_id=chat_room.id, user_id=current_user.id,
                rol='admin', agregado_por=current_user.id
            ))
            # Handle logo upload
            logo_file = request.files.get('logo')
            if logo_file and logo_file.filename:
                ext = logo_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp'):
                    from werkzeug.utils import secure_filename as _sf
                    logo_dir = os.path.join(current_app.root_path, 'static', 'logos')
                    os.makedirs(logo_dir, exist_ok=True)
                    fname = _sf(f'company_{emp.id}.{ext}')
                    logo_file.save(os.path.join(logo_dir, fname))
                    emp.logo_url = f'static/logos/{fname}'
            # Commit company + relationship + chat FIRST (critical path)
            db.session.commit()
            # Seed PUC as separate operation (non-critical, may fail on local SQLite)
            try:
                from company_config import COMPANY as _CC
                if _CC.get('chart_of_accounts') == 'co_puc':
                    cuentas_src = CuentaPUC.query.filter_by(company_id=company.id).all()
                    for cuenta in cuentas_src:
                        db.session.add(CuentaPUC(codigo=cuenta.codigo, nombre=cuenta.nombre,
                                                 tipo=cuenta.tipo, nivel=cuenta.nivel,
                                                 company_id=emp.id))
                    db.session.commit()
            except Exception as puc_err:
                logging.warning(f'PUC seeding skipped: {puc_err}')
                try: db.session.rollback()
                except Exception: pass
            try:
                _log('crear', 'empresa', emp.id, f'Empresa creada: {emp.nombre} (max_users={max_users})')
                db.session.commit()
            except Exception:
                try: db.session.rollback()
                except Exception: pass
            flash(f'Empresa "{nombre}" creada. Ahora crea un usuario admin para ella.', 'success')
            return redirect(url_for('admin_empresa_usuario', empresa_id=emp.id))
        return render_template('admin/empresa_form.html', obj=None)

    @app.route('/admin/empresas/<int:id>/eliminar', methods=['POST'])
    @login_required
    def admin_empresa_eliminar(id):
        """Eliminar empresa completa — solo admin Evore con contraseña."""
        from flask import g
        from werkzeug.security import check_password_hash
        from sqlalchemy import inspect as sa_inspect
        my_company = db.session.get(Company, g.company_id) if g.company_id else None
        if not my_company or not my_company.es_principal or current_user.rol != 'admin':
            flash('Solo el administrador de Evore puede eliminar empresas.', 'danger')
            return redirect(url_for('admin_empresas'))
        target = db.session.get(Company, id)
        if not target:
            flash('Empresa no encontrada.', 'danger')
            return redirect(url_for('admin_empresas'))
        if target.es_principal:
            flash('No se puede eliminar la empresa principal.', 'danger')
            return redirect(url_for('admin_empresas'))
        password = request.form.get('password_confirm', '')
        if not check_password_hash(current_user.password_hash, password):
            flash('Contraseña incorrecta. La empresa no fue eliminada.', 'danger')
            return redirect(url_for('admin_empresas'))

        target_name = target.nombre
        target_id = target.id
        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        # Reuse the same delete order as reset
        delete_sql = [
            'DELETE FROM proyecto_comentarios WHERE tarea_id IN (SELECT id FROM proyecto_tareas WHERE company_id = :cid)',
            'DELETE FROM proyecto_solicitudes_pago WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_plan_gastos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_objetivos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_notas WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_gastos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_tareas WHERE company_id = :cid',
            'DELETE FROM proyecto_miembros WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_fases WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyectos WHERE company_id = :cid',
            'DELETE FROM cap_evaluaciones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM cap_progresos WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM lineas_asiento WHERE asiento_id IN (SELECT id FROM asientos_contables WHERE company_id = :cid)',
            'DELETE FROM tarea_asignados WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
            'DELETE FROM tarea_comentarios WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
            'DELETE FROM pagos_venta WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
            'DELETE FROM reservas_produccion WHERE company_id = :cid',
            'DELETE FROM cotizacion_items WHERE cotizacion_id IN (SELECT id FROM cotizaciones WHERE company_id = :cid)',
            'DELETE FROM pre_cotizacion_items WHERE precot_id IN (SELECT id FROM pre_cotizaciones WHERE company_id = :cid)',
            'DELETE FROM ordenes_compra_items WHERE orden_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)',
            'DELETE FROM venta_productos WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
            'DELETE FROM materia_prima_productos WHERE materia_prima_id IN (SELECT id FROM materias_primas WHERE company_id = :cid)',
            'DELETE FROM receta_items WHERE receta_id IN (SELECT id FROM recetas_producto WHERE company_id = :cid)',
            'DELETE FROM marcas_producto WHERE producto_id IN (SELECT id FROM productos WHERE company_id = :cid)',
            'DELETE FROM historial_precios WHERE producto_id IN (SELECT id FROM productos WHERE company_id = :cid)',
            'DELETE FROM historial_cotizaciones WHERE cotizacion_id IN (SELECT id FROM cotizaciones WHERE company_id = :cid)',
            'DELETE FROM horas_extra WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM vacaciones_tomadas WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM incapacidades WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM contactos_cliente WHERE cliente_id IN (SELECT id FROM clientes WHERE company_id = :cid)',
            'DELETE FROM movimientos_bancarios WHERE company_id = :cid',
            'DELETE FROM notas_contables WHERE company_id = :cid',
            'DELETE FROM movimientos_inventario WHERE company_id = :cid',
            'DELETE FROM comisiones WHERE company_id = :cid',
            'DELETE FROM ordenes_produccion WHERE company_id = :cid',
            'DELETE FROM lotes_materia_prima WHERE company_id = :cid',
            'DELETE FROM lotes_producto WHERE company_id = :cid',
            'DELETE FROM compras_materia WHERE company_id = :cid',
            'DELETE FROM cotizaciones_proveedor WHERE company_id = :cid',
            'DELETE FROM cotizaciones_granel WHERE company_id = :cid',
            'DELETE FROM empaques_secundarios WHERE company_id = :cid',
            'DELETE FROM aprobaciones WHERE company_id = :cid',
            'DELETE FROM requisiciones WHERE company_id = :cid',
            'DELETE FROM asientos_contables WHERE company_id = :cid',
            'DELETE FROM tareas WHERE company_id = :cid',
            'DELETE FROM eventos WHERE company_id = :cid',
            'DELETE FROM notas WHERE company_id = :cid',
            'DELETE FROM notificaciones WHERE company_id = :cid',
            'DELETE FROM actividades WHERE company_id = :cid',
            'DELETE FROM ventas WHERE company_id = :cid',
            'DELETE FROM cotizaciones WHERE company_id = :cid',
            'DELETE FROM pre_cotizaciones WHERE company_id = :cid',
            'DELETE FROM ordenes_compra WHERE company_id = :cid',
            'DELETE FROM gastos_operativos WHERE company_id = :cid',
            'DELETE FROM documentos_legales WHERE company_id = :cid',
            'DELETE FROM empleados WHERE company_id = :cid',
            'DELETE FROM recetas_producto WHERE company_id = :cid',
            'DELETE FROM servicios WHERE company_id = :cid',
            'DELETE FROM reglas_tributarias WHERE company_id = :cid',
            'DELETE FROM materias_primas WHERE company_id = :cid',
            'DELETE FROM productos WHERE company_id = :cid',
            'DELETE FROM clientes WHERE company_id = :cid',
            'DELETE FROM proveedores WHERE company_id = :cid',
            'DELETE FROM chat_messages WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM chat_participants WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM foro_apelaciones WHERE solicitado_por IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM foro_valoraciones WHERE cliente_user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM foro_publicaciones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
            'DELETE FROM user_companies WHERE company_id = :cid',
            'DELETE FROM user_sesiones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid)',
        ]

        try:
            # Nullify all FK refs to users of this company
            for tbl in existing_tables:
                if tbl == 'users':
                    continue
                try:
                    for fk in inspector.get_foreign_keys(tbl):
                        if fk['referred_table'] == 'users' and len(fk['constrained_columns']) == 1:
                            col = fk['constrained_columns'][0]
                            col_info = next((c for c in inspector.get_columns(tbl) if c['name'] == col), None)
                            if col_info and col_info.get('nullable', True):
                                db.session.execute(db.text(
                                    f"UPDATE {tbl} SET {col} = NULL WHERE {col} IN (SELECT id FROM users WHERE company_id = :cid)"
                                ), {'cid': target_id})
                except Exception:
                    pass

            # Delete all company data
            for sql in delete_sql:
                tbl_part = sql.split('FROM ')[1].split(' ')[0]
                if tbl_part not in existing_tables:
                    continue
                db.session.execute(db.text(sql), {'cid': target_id})

            # Delete ALL users (no exceptions — entire company goes)
            db.session.execute(db.text('DELETE FROM users WHERE company_id = :cid'), {'cid': target_id})

            # Delete config
            db.session.execute(db.text('DELETE FROM config_empresa WHERE company_id = :cid'), {'cid': target_id})

            # Delete chat rooms linked to company relationships, then relationships
            db.session.execute(db.text(
                'DELETE FROM chat_messages WHERE room_id IN (SELECT id FROM chat_rooms WHERE company_relationship_id IN (SELECT id FROM company_relationships WHERE company_from_id = :cid OR company_to_id = :cid))'
            ), {'cid': target_id})
            db.session.execute(db.text(
                'DELETE FROM chat_participants WHERE room_id IN (SELECT id FROM chat_rooms WHERE company_relationship_id IN (SELECT id FROM company_relationships WHERE company_from_id = :cid OR company_to_id = :cid))'
            ), {'cid': target_id})
            db.session.execute(db.text(
                'DELETE FROM chat_rooms WHERE company_relationship_id IN (SELECT id FROM company_relationships WHERE company_from_id = :cid OR company_to_id = :cid)'
            ), {'cid': target_id})
            db.session.execute(db.text(
                'DELETE FROM company_relationships WHERE company_from_id = :cid OR company_to_id = :cid'
            ), {'cid': target_id})

            # Delete suscripciones
            db.session.execute(db.text('DELETE FROM suscripciones WHERE company_id = :cid'), {'cid': target_id})

            # Finally delete the company
            db.session.execute(db.text('DELETE FROM companies WHERE id = :cid'), {'cid': target_id})

            db.session.commit()
            logging.warning(f'EMPRESA ELIMINADA: {target_name} (id={target_id}) por {current_user.email}')
            flash(f'Empresa "{target_name}" y todos sus datos han sido eliminados.', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'admin_empresa_eliminar ERROR: {e}')
            flash(f'Error al eliminar empresa: {e}', 'danger')

        return redirect(url_for('admin_empresas'))

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
            emp.tipo_documento = request.form.get('tipo_documento', emp.tipo_documento or 'NIT')
            emp.nit = request.form.get('nit', '').strip()
            emp.max_users = int(request.form.get('max_users', emp.max_users))
            emp.plan = request.form.get('plan', emp.plan)
            emp.activo = request.form.get('activo') == 'on'
            logo_file = request.files.get('logo')
            if logo_file and logo_file.filename:
                ext = logo_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp'):
                    from werkzeug.utils import secure_filename as _sf
                    logo_dir = os.path.join(current_app.root_path, 'static', 'logos')
                    os.makedirs(logo_dir, exist_ok=True)
                    fname = _sf(f'company_{emp.id}.{ext}')
                    logo_file.save(os.path.join(logo_dir, fname))
                    emp.logo_url = f'static/logos/{fname}'
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
            if emp.plan == 'free' and current_count >= 1:
                flash(f'Plan gratuito: solo permite 1 usuario. Cambia el plan a Starter o Pro.', 'danger')
                return redirect(url_for('admin_empresas'))
            if current_count >= emp.max_users and emp.plan != 'pro':
                flash(f'Limite alcanzado: {emp.nombre} tiene {current_count}/{emp.max_users} usuarios.', 'danger')
                return redirect(url_for('admin_empresas'))
            # Auto-upgrade starter→pro when adding 4th user (starter max = 3)
            if emp.plan == 'starter' and current_count >= 3:
                emp.plan = 'pro'
                emp.max_users = max(emp.max_users, current_count + 1)
                flash(f'{emp.nombre} paso automaticamente a plan Profesional. Base $39.900/mes (4 usuarios) + $9.900/mes por cada usuario extra.', 'info')
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
                    # Pro: auto-expand max_users
                    if emp.plan == 'pro':
                        new_count = current_count + 1
                        if new_count > emp.max_users:
                            emp.max_users = new_count
                    db.session.commit()
                    flash(f'{existing.nombre} agregado a {emp.nombre} como {rol}.', 'success')
            else:
                # Create new user
                u = User(nombre=nombre, email=email, rol=rol, company_id=emp.id)
                u.set_password(password)
                db.session.add(u)
                db.session.flush()
                db.session.add(UserCompany(user_id=u.id, company_id=emp.id, rol=rol))
                # Pro: auto-expand max_users
                if emp.plan == 'pro':
                    new_count = current_count + 1
                    if new_count > emp.max_users:
                        emp.max_users = new_count
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
        active_cid = getattr(g, 'company_id', None) or current_user.company_id

        def _users_for_company(cid):
            """Usuarios vinculados a una empresa via UserCompany o User.company_id."""
            if not cid:
                return []
            uc_ids = {r[0] for r in db.session.query(UserCompany.user_id)
                      .filter_by(company_id=cid, activo=True).all()}
            direct_ids = {u.id for u in User.query.filter_by(company_id=cid).all()}
            all_ids = uc_ids | direct_ids
            if not all_ids:
                return []
            return User.query.filter(User.id.in_(all_ids)).order_by(User.nombre).all()

        evore = Company.query.filter_by(es_principal=True).first()
        is_evore = bool(evore and active_cid == evore.id)
        items = _users_for_company(active_cid)

        # Para Evore: usuarios de OTRAS empresas agrupados por empresa
        other_companies_data = []
        if is_evore:
            for c in Company.query.filter(Company.id != evore.id,
                                          Company.activo == True).order_by(Company.nombre).all():
                users = _users_for_company(c.id)
                if users:
                    other_companies_data.append({'company': c, 'users': users})

        return render_template('admin/usuarios.html',
            items=items,
            is_evore=is_evore,
            other_companies_data=other_companies_data,
            clientes_all=tenant_query(Cliente).filter_by(estado='activo').all(),
            proveedores_all=tenant_query(Proveedor).filter_by(activo=True).all())
    

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
        clientes_list  = tenant_query(Cliente).filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
        proveedores_list = tenant_query(Proveedor).filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
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
            obj.banco_nombre  = request.form.get('banco_nombre','').strip() or None
            obj.banco_tipo    = request.form.get('banco_tipo','').strip() or None
            obj.banco_cuenta  = request.form.get('banco_cuenta','').strip() or None
            obj.banco_titular = request.form.get('banco_titular','').strip() or None
            obj.banco_nit     = request.form.get('banco_nit','').strip() or None

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
                clientes_list  = tenant_query(Cliente).filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
                proveedores_list = tenant_query(Proveedor).filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
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
        clientes_list  = tenant_query(Cliente).filter_by(estado='activo').order_by(Cliente.empresa, Cliente.nombre).all()
        proveedores_list = tenant_query(Proveedor).filter_by(activo=True).order_by(Proveedor.empresa, Proveedor.nombre).all()
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
        clientes_list = tenant_query(Cliente).filter_by(estado='activo').order_by(Cliente.empresa).all()
        proveedores_list = tenant_query(Proveedor).filter_by(activo=True).order_by(Proveedor.empresa).all()
        empleados_list = tenant_query(Empleado).filter_by(estado='activo').order_by(Empleado.nombre).all()

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
                    company_id=getattr(g, 'company_id', None) or current_user.company_id,
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
        q = tenant_query(DocumentoLegal).filter_by(activo=True)
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
        productos = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fe = request.form.get('fecha_emision')
            fv = request.form.get('fecha_vencimiento')
            prod_id = request.form.get('producto_id')
            d = DocumentoLegal(
                company_id=getattr(g, 'company_id', None) or current_user.company_id,
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
        productos = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
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
        """Reset de datos por empresa. Borra SOLO datos de la empresa del admin."""
        from werkzeug.security import check_password_hash
        if current_user.rol not in ('admin', 'director_financiero'):
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        password_confirm = request.form.get('password_confirm', '')
        if not check_password_hash(current_user.password_hash, password_confirm):
            flash('Contrasena incorrecta. El reset no fue ejecutado.', 'danger')
            return redirect(url_for('admin_usuarios'))

        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())

        admin_id = current_user.id
        admin_email = current_user.email
        my_company_id = getattr(g, 'company_id', None)
        if not my_company_id:
            # Fallback: get from user
            my_company_id = current_user.company_id
        if not my_company_id:
            flash('Error: no se pudo determinar tu empresa.', 'danger')
            return redirect(url_for('admin_usuarios'))

        # Tables with company_id that should be filtered
        tables_with_company = [
            # Nivel 8: proyectos
            'proyecto_solicitudes_pago', 'proyecto_plan_gastos', 'proyecto_objetivos',
            'proyecto_notas', 'proyecto_comentarios', 'proyecto_gastos',
            'proyecto_tareas', 'proyecto_miembros', 'proyecto_fases', 'proyectos',
            # Nivel 7: capacitacion (user progress)
            'cap_evaluaciones', 'cap_progresos',
            # Nivel 6: líneas y asociaciones
            'lineas_asiento', 'tarea_asignados', 'tarea_comentarios', 'pagos_venta',
            # Nivel 5: ítems de documentos
            'reservas_produccion', 'cotizacion_items', 'pre_cotizacion_items',
            'ordenes_compra_items', 'venta_productos', 'materia_prima_productos',
            'receta_items', 'marcas_producto', 'historial_precios',
            'historial_cotizaciones',
            # Nivel 4: dependientes de empleados
            'horas_extra', 'vacaciones_tomadas', 'incapacidades',
            # Nivel 3: entidades con company_id
            'movimientos_bancarios', 'notas_contables', 'movimientos_inventario',
            'comisiones', 'ordenes_produccion', 'lotes_materia_prima',
            'lotes_producto', 'compras_materia', 'cotizaciones_proveedor',
            'cotizaciones_granel', 'empaques_secundarios', 'aprobaciones',
            'requisiciones', 'asientos_contables', 'tareas', 'eventos',
            'notas', 'notificaciones', 'actividades',
            # Nivel 2: documentos principales
            'ventas', 'cotizaciones', 'pre_cotizaciones', 'ordenes_compra',
            'gastos_operativos', 'documentos_legales', 'empleados',
            'recetas_producto', 'servicios',
            # Nivel 1: catálogos
            'reglas_tributarias', 'materias_primas', 'productos',
            'contactos_cliente', 'clientes', 'proveedores',
        ]

        # ALL deletes in strict FK order. NO try/except inside — one transaction.
        # If ANY fails, the whole thing rolls back and shows the real error.
        delete_sql = [
            # ── Leaf children (FK to company-owned parents) ──
            'DELETE FROM proyecto_comentarios WHERE tarea_id IN (SELECT id FROM proyecto_tareas WHERE company_id = :cid)',
            'DELETE FROM proyecto_solicitudes_pago WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_plan_gastos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_objetivos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_notas WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_gastos WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_tareas WHERE company_id = :cid',
            'DELETE FROM proyecto_miembros WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyecto_fases WHERE proyecto_id IN (SELECT id FROM proyectos WHERE company_id = :cid)',
            'DELETE FROM proyectos WHERE company_id = :cid',
            'DELETE FROM cap_evaluaciones WHERE company_id = :cid',
            'DELETE FROM cap_progresos WHERE company_id = :cid',
            'DELETE FROM lineas_asiento WHERE asiento_id IN (SELECT id FROM asientos_contables WHERE company_id = :cid)',
            'DELETE FROM tarea_asignados WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
            'DELETE FROM tarea_comentarios WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
            'DELETE FROM pagos_venta WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
            'DELETE FROM reservas_produccion WHERE company_id = :cid',
            'DELETE FROM cotizacion_items WHERE cotizacion_id IN (SELECT id FROM cotizaciones WHERE company_id = :cid)',
            'DELETE FROM pre_cotizacion_items WHERE precot_id IN (SELECT id FROM pre_cotizaciones WHERE company_id = :cid)',
            'DELETE FROM ordenes_compra_items WHERE orden_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)',
            'DELETE FROM venta_productos WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
            'DELETE FROM materia_prima_productos WHERE materia_prima_id IN (SELECT id FROM materias_primas WHERE company_id = :cid)',
            'DELETE FROM receta_items WHERE receta_id IN (SELECT id FROM recetas_producto WHERE company_id = :cid)',
            'DELETE FROM marcas_producto WHERE producto_id IN (SELECT id FROM productos WHERE company_id = :cid)',
            'DELETE FROM historial_precios WHERE producto_id IN (SELECT id FROM productos WHERE company_id = :cid)',
            'DELETE FROM historial_cotizaciones WHERE cotizacion_id IN (SELECT id FROM cotizaciones WHERE company_id = :cid)',
            'DELETE FROM horas_extra WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM vacaciones_tomadas WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM incapacidades WHERE empleado_id IN (SELECT id FROM empleados WHERE company_id = :cid)',
            'DELETE FROM contactos_cliente WHERE cliente_id IN (SELECT id FROM clientes WHERE company_id = :cid)',
            # ── Mid-level (have company_id) ──
            'DELETE FROM movimientos_bancarios WHERE company_id = :cid',
            'DELETE FROM notas_contables WHERE company_id = :cid',
            'DELETE FROM movimientos_inventario WHERE company_id = :cid',
            'DELETE FROM comisiones WHERE company_id = :cid',
            'DELETE FROM ordenes_produccion WHERE company_id = :cid',
            'DELETE FROM lotes_materia_prima WHERE company_id = :cid',
            'DELETE FROM lotes_producto WHERE company_id = :cid',
            'DELETE FROM compras_materia WHERE company_id = :cid',
            'DELETE FROM cotizaciones_proveedor WHERE company_id = :cid',
            'DELETE FROM cotizaciones_granel WHERE company_id = :cid',
            'DELETE FROM empaques_secundarios WHERE company_id = :cid',
            'DELETE FROM aprobaciones WHERE company_id = :cid',
            'DELETE FROM requisiciones WHERE company_id = :cid',
            'DELETE FROM asientos_contables WHERE company_id = :cid',
            'DELETE FROM tareas WHERE company_id = :cid',
            'DELETE FROM eventos WHERE company_id = :cid',
            'DELETE FROM notas WHERE company_id = :cid',
            'DELETE FROM notificaciones WHERE company_id = :cid',
            'DELETE FROM actividades WHERE company_id = :cid',
            # ── Documents & main entities ──
            'DELETE FROM ventas WHERE company_id = :cid',
            'DELETE FROM cotizaciones WHERE company_id = :cid',
            'DELETE FROM pre_cotizaciones WHERE company_id = :cid',
            'DELETE FROM ordenes_compra WHERE company_id = :cid',
            'DELETE FROM gastos_operativos WHERE company_id = :cid',
            'DELETE FROM documentos_legales WHERE company_id = :cid',
            'DELETE FROM empleados WHERE company_id = :cid',
            'DELETE FROM recetas_producto WHERE company_id = :cid',
            'DELETE FROM servicios WHERE company_id = :cid',
            # ── Catalogs ──
            'DELETE FROM reglas_tributarias WHERE company_id = :cid',
            'DELETE FROM materias_primas WHERE company_id = :cid',
            'DELETE FROM productos WHERE company_id = :cid',
            'DELETE FROM clientes WHERE company_id = :cid',
            'DELETE FROM proveedores WHERE company_id = :cid',
            # ── Capacitacion (may have NULL company_id) ──
            'DELETE FROM cap_evaluaciones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            'DELETE FROM cap_progresos WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            # ── Chat + Foro (cross-company, reference users) ──
            'DELETE FROM chat_messages WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            'DELETE FROM chat_participants WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            'DELETE FROM foro_apelaciones WHERE solicitado_por IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            'DELETE FROM foro_valoraciones WHERE cliente_user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            'DELETE FROM foro_publicaciones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
            # ── Users (except admin) ──
            'DELETE FROM user_companies WHERE company_id = :cid AND user_id != :aid',
            'DELETE FROM user_sesiones WHERE user_id IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)',
        ]

        my_company = db.session.get(Company, my_company_id)
        company_name = my_company.nombre if my_company else f'ID {my_company_id}'

        # Build dynamic SET NULL for ALL remaining FK refs to users being deleted
        _user_fk_nullify = []
        for tbl in existing_tables:
            if tbl == 'users':
                continue
            try:
                for fk in inspector.get_foreign_keys(tbl):
                    if fk['referred_table'] == 'users' and len(fk['constrained_columns']) == 1:
                        col = fk['constrained_columns'][0]
                        # Check if column is nullable
                        col_info = next((c for c in inspector.get_columns(tbl) if c['name'] == col), None)
                        if col_info and col_info.get('nullable', True):
                            _user_fk_nullify.append(
                                f"UPDATE {tbl} SET {col} = NULL WHERE {col} IN (SELECT id FROM users WHERE company_id = :cid AND id != :aid)"
                            )
            except Exception:
                pass

        try:
            deleted_count = 0
            params = {'cid': my_company_id, 'aid': admin_id}

            # Step 1: delete company data (commit every 10 queries to avoid SSL timeout)
            batch = []
            for sql in delete_sql:
                tbl_part = sql.split('FROM ')[1].split(' ')[0]
                if tbl_part not in existing_tables:
                    continue
                batch.append(sql)
                if len(batch) >= 10:
                    for s in batch:
                        r = db.session.execute(db.text(s), params)
                        deleted_count += r.rowcount
                    db.session.commit()
                    batch = []
            # Flush remaining
            for s in batch:
                r = db.session.execute(db.text(s), params)
                deleted_count += r.rowcount
            db.session.commit()

            # Step 2: nullify FK refs to users (separate transaction)
            for sql in _user_fk_nullify:
                tbl_part = sql.split('UPDATE ')[1].split(' ')[0]
                if tbl_part not in existing_tables:
                    continue
                db.session.execute(db.text(sql), params)
            db.session.commit()

            # Step 3: clean orphan NULL records
            for tbl in ['clientes','proveedores','ventas','productos','materias_primas',
                        'empleados','ordenes_compra','cotizaciones','gastos_operativos',
                        'tareas','notas','actividades','eventos','notificaciones',
                        'asientos_contables','servicios','reglas_tributarias',
                        'recetas_producto','documentos_legales']:
                if tbl in existing_tables:
                    try:
                        r = db.session.execute(db.text(f'DELETE FROM {tbl} WHERE company_id IS NULL'))
                        deleted_count += r.rowcount
                    except Exception:
                        db.session.rollback()
            db.session.commit()

            # Step 4: delete users (separate transaction)
            if 'users' in existing_tables:
                r = db.session.execute(db.text(
                    'DELETE FROM users WHERE company_id = :cid AND id != :aid'
                ), params)
                deleted_count += r.rowcount
            db.session.commit()
            logging.warning(f'RESET EMPRESA OK: {company_name} por {admin_email} — {deleted_count} registros eliminados')
            flash(f'Reset completo para "{company_name}". {deleted_count} registros eliminados.', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'admin_reset_total ERROR en {company_name}: {e}')
            flash(f'Error durante el reset: {e}', 'danger')

        return redirect(url_for('dashboard'))


    # ── admin_reset_contable (/admin/reset-contable) ──────────────────────────
    @app.route('/admin/reset-contable', methods=['POST'])
    @login_required
    def admin_reset_contable():
        """Borra transacciones huerfanas y resetea secuencias: ventas,
        cotizaciones, OCs, asientos, reservas, OPs. Preserva: clientes,
        proveedores, productos, empleados, PUC, config."""
        from werkzeug.security import check_password_hash
        if current_user.rol not in ('admin', 'director_financiero'):
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('contable_index'))

        password_confirm = request.form.get('password_confirm', '')
        if not check_password_hash(current_user.password_hash, password_confirm):
            flash('Contrasena incorrecta. Reset no ejecutado.', 'danger')
            return redirect(url_for('contable_index'))

        cid = getattr(g, 'company_id', None) or current_user.company_id
        if not cid:
            flash('No se pudo determinar empresa activa.', 'danger')
            return redirect(url_for('contable_index'))

        from sqlalchemy import inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        existing = set(inspector.get_table_names())

        # Orden FK-safe: hijos antes que padres
        delete_sql = [
            # Lineas de asiento (hijos de asientos)
            ('lineas_asiento',
             'DELETE FROM lineas_asiento WHERE asiento_id IN (SELECT id FROM asientos_contables WHERE company_id = :cid)'),
            # Hijos de venta
            ('pagos_venta',
             'DELETE FROM pagos_venta WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)'),
            ('comisiones',
             'DELETE FROM comisiones WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)'),
            ('venta_productos',
             'DELETE FROM venta_productos WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)'),
            ('reservas_produccion',
             'DELETE FROM reservas_produccion WHERE company_id = :cid'),
            ('ordenes_produccion',
             'DELETE FROM ordenes_produccion WHERE company_id = :cid'),
            # Hijos de OC
            ('ordenes_compra_items',
             'DELETE FROM ordenes_compra_items WHERE orden_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)'),
            # Desvincular FKs opcionales antes de borrar padres
            ('tareas_venta_null',
             'UPDATE tareas SET venta_id = NULL WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)'),
            ('tareas_oc_null',
             'UPDATE tareas SET orden_compra_id = NULL WHERE orden_compra_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)'),
            ('docs_legales_oc',
             'UPDATE documentos_legales SET orden_compra_id = NULL WHERE orden_compra_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)'),
            ('oc_venta_origen',
             'UPDATE ordenes_compra SET venta_origen_id = NULL WHERE venta_origen_id IN (SELECT id FROM ventas WHERE company_id = :cid)'),
            # Al borrar ventas, liberar cotizaciones vinculadas (pueden re-convertirse)
            ('cotizaciones_liberar',
             "UPDATE cotizaciones SET estado = 'aprobada' WHERE estado = 'confirmacion_orden' AND id IN (SELECT cotizacion_id FROM ventas WHERE company_id = :cid AND cotizacion_id IS NOT NULL)"),
            # Ahora si: padres transaccionales
            ('asientos_contables',
             'DELETE FROM asientos_contables WHERE company_id = :cid'),
            ('ventas',
             'DELETE FROM ventas WHERE company_id = :cid'),
            ('ordenes_compra',
             'DELETE FROM ordenes_compra WHERE company_id = :cid'),
            ('compras_materia',
             'DELETE FROM compras_materia WHERE company_id = :cid'),
            ('movimientos_bancarios',
             'DELETE FROM movimientos_bancarios WHERE company_id = :cid'),
            ('notas_contables',
             'DELETE FROM notas_contables WHERE company_id = :cid'),
            ('gastos_operativos',
             'DELETE FROM gastos_operativos WHERE company_id = :cid'),
        ]

        # Pre-cache columnas existentes por tabla — para skip si no existe
        cols_cache = {}
        def _cols(tbl):
            if tbl not in cols_cache:
                try:
                    cols_cache[tbl] = {c['name'] for c in inspector.get_columns(tbl)}
                except Exception:
                    cols_cache[tbl] = set()
            return cols_cache[tbl]

        def _tabla_y_columnas_requeridas(sql):
            """Extrae tabla target + columnas referenciadas. Retorna None si
            la query es imposible (tabla o columna inexistente)."""
            import re as _re
            s = sql.strip()
            # UPDATE table SET col = ... WHERE col IN ...
            m = _re.match(r'UPDATE\s+(\w+)\s+SET\s+(\w+)', s, _re.IGNORECASE)
            if m:
                tbl, col = m.group(1), m.group(2)
                if tbl not in existing: return False
                if col not in _cols(tbl): return False
                return True
            # DELETE FROM table ...
            m = _re.match(r'DELETE\s+FROM\s+(\w+)', s, _re.IGNORECASE)
            if m:
                tbl = m.group(1)
                if tbl not in existing: return False
                return True
            return True

        resumen = []
        errores = []
        for nombre, sql in delete_sql:
            if not _tabla_y_columnas_requeridas(sql):
                continue
            # Aislar cada sentencia con savepoint para que un error no
            # aborte toda la transaccion.
            sp = db.session.begin_nested()
            try:
                r = db.session.execute(db.text(sql), {'cid': cid})
                sp.commit()
                if r.rowcount:
                    resumen.append(f'{nombre}: {r.rowcount}')
            except Exception as _e:
                sp.rollback()
                errores.append(f'{nombre}: {_e}')
                logging.warning(f'reset_contable {nombre}: {_e}')
        try:
            db.session.commit()

            # Resetear secuencias PG para tablas limpiadas (por empresa, no global)
            # Solo aplica en PostgreSQL — SQLite auto-adjusts
            # Nota: en multi-tenant, la secuencia es global — el reset afecta
            # a todas las empresas. Solo resetear si la tabla quedo vacia.
            seq_candidates = [
                ('ventas', 'ventas_id_seq'),
                ('ordenes_compra', 'ordenes_compra_id_seq'),
                ('asientos_contables', 'asientos_contables_id_seq'),
                ('pagos_venta', 'pagos_venta_id_seq'),
                ('comisiones', 'comisiones_id_seq'),
                ('reservas_produccion', 'reservas_produccion_id_seq'),
                ('ordenes_produccion', 'ordenes_produccion_id_seq'),
                ('compras_materia', 'compras_materia_id_seq'),
                ('gastos_operativos', 'gastos_operativos_id_seq'),
            ]
            for tbl, seq in seq_candidates:
                if tbl not in existing:
                    continue
                try:
                    count = db.session.execute(db.text(f'SELECT COUNT(*) FROM {tbl}')).scalar()
                    if count == 0:
                        # Reset secuencia a 1 solo si la tabla esta vacia globalmente
                        try:
                            db.session.execute(db.text(f'ALTER SEQUENCE {seq} RESTART WITH 1'))
                        except Exception:
                            pass  # SQLite o permisos
                except Exception:
                    pass
            db.session.commit()

            _log('reset', 'contable', 0, f'Reset contable por {current_user.email}: ' + ', '.join(resumen))
            db.session.commit()
            msg = 'Reset contable completado. Transacciones borradas: ' + (', '.join(resumen) if resumen else '(ninguna)') + '.'
            if errores:
                msg += ' Advertencias: ' + '; '.join(errores[:3])
                if len(errores) > 3:
                    msg += f' (+{len(errores)-3} mas, ver logs)'
            flash(msg, 'success' if not errores else 'warning')
        except Exception as e:
            db.session.rollback()
            logging.exception(f'admin_reset_contable commit/seq error: {e}')
            flash(f'Error en commit/secuencias: {e}', 'danger')

        return redirect(url_for('contable_index'))


    # ══════════════════════════════════════════════════════════════
    # MARKETPLACE BANNERS (Evore admin only)
    # ══════════════════════════════════════════════════════════════

    @app.route('/admin/banners')
    @login_required
    def admin_banners():
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        banners = ForoBanner.query.order_by(ForoBanner.orden, ForoBanner.creado_en.desc()).all()
        return render_template('admin/banners.html', banners=banners)

    @app.route('/admin/banners/nuevo', methods=['GET', 'POST'])
    @login_required
    def admin_banner_nuevo():
        from flask import g
        from werkzeug.utils import secure_filename
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            if not titulo:
                flash('El titulo es obligatorio.', 'danger')
                return render_template('admin/banner_form.html', obj=None)
            banner = ForoBanner(
                titulo=titulo,
                descripcion=request.form.get('descripcion', '').strip(),
                link_url=request.form.get('link_url', '').strip(),
                industria=request.form.get('industria', '').strip() or None,
                tipo=request.form.get('tipo', 'evore'),
                activo='activo' in request.form,
                orden=int(request.form.get('orden', 0) or 0),
                creado_por=current_user.id)
            # Handle image upload
            img = request.files.get('imagen')
            if img and img.filename:
                fname = secure_filename(img.filename)
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'banners')
                os.makedirs(upload_dir, exist_ok=True)
                path = os.path.join(upload_dir, fname)
                img.save(path)
                banner.imagen_url = f'static/uploads/banners/{fname}'
            db.session.add(banner)
            db.session.commit()
            flash('Banner creado.', 'success')
            return redirect(url_for('admin_banners'))
        return render_template('admin/banner_form.html', obj=None)

    @app.route('/admin/banners/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    def admin_banner_editar(id):
        from flask import g
        from werkzeug.utils import secure_filename
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        banner = ForoBanner.query.get_or_404(id)
        if request.method == 'POST':
            banner.titulo = request.form.get('titulo', '').strip()
            banner.descripcion = request.form.get('descripcion', '').strip()
            banner.link_url = request.form.get('link_url', '').strip()
            banner.industria = request.form.get('industria', '').strip() or None
            banner.tipo = request.form.get('tipo', 'evore')
            banner.activo = 'activo' in request.form
            banner.orden = int(request.form.get('orden', 0) or 0)
            img = request.files.get('imagen')
            if img and img.filename:
                fname = secure_filename(img.filename)
                upload_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'banners')
                os.makedirs(upload_dir, exist_ok=True)
                path = os.path.join(upload_dir, fname)
                img.save(path)
                banner.imagen_url = f'static/uploads/banners/{fname}'
            db.session.commit()
            flash('Banner actualizado.', 'success')
            return redirect(url_for('admin_banners'))
        return render_template('admin/banner_form.html', obj=banner)

    @app.route('/admin/banners/<int:id>/eliminar', methods=['POST'])
    @login_required
    def admin_banner_eliminar(id):
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        banner = ForoBanner.query.get_or_404(id)
        db.session.delete(banner)
        db.session.commit()
        flash('Banner eliminado.', 'success')
        return redirect(url_for('admin_banners'))

    @app.route('/admin/banners/seed', methods=['POST'])
    @login_required
    def admin_banners_seed():
        """Seed initial Evore banners."""
        from flask import g
        company = db.session.get(Company, g.company_id) if g.company_id else None
        if not company or not company.es_principal or current_user.rol != 'admin':
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        if ForoBanner.query.count() == 0:
            seeds = [
                ForoBanner(titulo='Conoce Evore CRM', descripcion='Gestiona tu empresa completa: ventas, produccion, inventario, contabilidad y mas.', link_url='/inicio', tipo='evore', activo=True, orden=1, creado_por=current_user.id),
                ForoBanner(titulo='Somos Evore', descripcion='Publica tus productos en el marketplace y conecta con nuevos clientes.', link_url='/foro', tipo='evore', activo=True, orden=2, creado_por=current_user.id),
                ForoBanner(titulo='Starter gratis', descripcion='Activa tu CRM hoy — gratis para siempre con hasta 3 usuarios.', link_url='/planes', tipo='evore', activo=True, orden=3, creado_por=current_user.id),
            ]
            for b in seeds:
                db.session.add(b)
            db.session.commit()
            flash('3 banners iniciales creados.', 'success')
        else:
            flash('Ya existen banners. No se crearon nuevos.', 'info')
        return redirect(url_for('admin_banners'))

