# routes/admin.py
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
    @app.route('/admin/empresa', methods=['GET','POST'])
    @login_required
    def admin_config():
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
            db.session.commit(); flash('Configuración guardada.','success')
        return render_template('admin/config.html', obj=obj)

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

    @app.route('/admin/usuarios')
    @login_required
    def admin_usuarios():
        if current_user.rol != 'admin':
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        return render_template('admin/usuarios.html',
            items=User.query.order_by(User.nombre).all(),
            clientes_all=Cliente.query.filter_by(estado='activo').all(),
            proveedores_all=Proveedor.query.filter_by(activo=True).all())

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

    @app.route('/contable')
    @login_required
    def contable_index():
        from datetime import timedelta
        hoy = datetime.utcnow().date()
        mes_inicio = hoy.replace(day=1)
        mes_str = request.args.get('mes', hoy.strftime('%Y-%m'))
        try:
            anio, mes = int(mes_str.split('-')[0]), int(mes_str.split('-')[1])
        except: anio, mes = hoy.year, hoy.month
        import calendar as cal_mod
        _, ultimo_dia = cal_mod.monthrange(anio, mes)
        desde = datetime(anio, mes, 1).date()
        hasta = datetime(anio, mes, ultimo_dia).date()
        # Ingresos del mes (ventas ganadas/anticipo)
        ventas_mes = Venta.query.filter(
            Venta.estado.in_(['anticipo_pagado','completado']),
            db.func.date(Venta.creado_en) >= desde,
            db.func.date(Venta.creado_en) <= hasta
        ).all()
        total_ingresos = sum(v.total for v in ventas_mes)
        total_anticipo = sum(v.monto_anticipo for v in ventas_mes)
        # Egresos del mes
        gastos_mes = GastoOperativo.query.filter(
            GastoOperativo.fecha >= desde, GastoOperativo.fecha <= hasta
        ).all()
        compras_mes = CompraMateria.query.filter(
            CompraMateria.fecha >= desde, CompraMateria.fecha <= hasta
        ).all()
        total_gastos = sum(g.monto for g in gastos_mes)
        total_compras = sum(c.costo_total for c in compras_mes)
        total_egresos = total_gastos + total_compras
        utilidad = total_ingresos - total_egresos
        # Impuestos estimados según reglas tributarias activas
        total_impuestos, detalle_impuestos = _calcular_impuestos(total_ingresos, utilidad)
        utilidad_neta = utilidad - total_impuestos
        # Cuentas por cobrar (ventas con saldo > 0)
        cxc = Venta.query.filter(Venta.saldo > 0, Venta.estado.in_(['anticipo_pagado','completado'])).all()
        total_cxc = sum(v.saldo for v in cxc)
        # Inventario valorizado
        inventario_valor = sum((p.stock or 0) * (p.costo or 0) for p in Producto.query.filter_by(activo=True).all())
        meses_nav = []
        for i in range(5, -1, -1):
            d = (hoy.replace(day=1) - timedelta(days=i*28)).replace(day=1)
            meses_nav.append({'val': d.strftime('%Y-%m'), 'lbl': d.strftime('%b %Y')})
        return render_template('contable/index.html',
            total_ingresos=total_ingresos, total_anticipo=total_anticipo,
            total_egresos=total_egresos, total_gastos=total_gastos,
            total_compras=total_compras, utilidad=utilidad,
            total_impuestos=total_impuestos, detalle_impuestos=detalle_impuestos,
            utilidad_neta=utilidad_neta,
            total_cxc=total_cxc, inventario_valor=inventario_valor,
            ventas_mes=ventas_mes, gastos_mes=gastos_mes, compras_mes=compras_mes,
            cxc=cxc, mes_str=mes_str, meses_nav=meses_nav,
            anio=anio, mes=mes)

    @app.route('/contable/ingresos')
    @login_required
    def contable_ingresos():
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        q = Venta.query.filter(Venta.estado.in_(['anticipo_pagado','completado','prospecto','negociacion','perdido']))
        if desde_s:
            try: q = q.filter(db.func.date(Venta.creado_en) >= datetime.strptime(desde_s,'%Y-%m-%d').date())
            except: pass
        if hasta_s:
            try: q = q.filter(db.func.date(Venta.creado_en) <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
            except: pass
        items = q.order_by(Venta.creado_en.desc()).all()
        return render_template('contable/ingresos.html', items=items, desde_s=desde_s, hasta_s=hasta_s)

    @app.route('/contable/egresos')
    @login_required
    def contable_egresos():
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        gastos = GastoOperativo.query
        compras = CompraMateria.query
        if desde_s:
            try:
                d = datetime.strptime(desde_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha >= d)
                compras = compras.filter(CompraMateria.fecha >= d)
            except: pass
        if hasta_s:
            try:
                h = datetime.strptime(hasta_s,'%Y-%m-%d').date()
                gastos = gastos.filter(GastoOperativo.fecha <= h)
                compras = compras.filter(CompraMateria.fecha <= h)
            except: pass
        return render_template('contable/egresos.html',
            gastos=gastos.order_by(GastoOperativo.fecha.desc()).all(),
            compras=compras.order_by(CompraMateria.fecha.desc()).all(),
            desde_s=desde_s, hasta_s=hasta_s)

    @app.route('/contable/libro-diario', methods=['GET','POST'])
    @login_required
    def contable_libro_diario():
        if request.method == 'POST':
            fd = request.form.get('fecha')
            a = AsientoContable(
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                descripcion=request.form['descripcion'],
                tipo=request.form.get('tipo','manual'),
                referencia=request.form.get('referencia',''),
                debe=float(request.form.get('debe') or 0),
                haber=float(request.form.get('haber') or 0),
                cuenta_debe=request.form.get('cuenta_debe',''),
                cuenta_haber=request.form.get('cuenta_haber',''),
                notas=request.form.get('notas',''),
                creado_por=current_user.id
            )
            db.session.add(a); db.session.flush()
            hoy = datetime.utcnow().date()
            ultimo = AsientoContable.query.filter(
                AsientoContable.numero.like(f'AC-{hoy.year}-%')
            ).order_by(AsientoContable.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            a.numero = f'AC-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Asiento {a.numero} registrado.','success')
            return redirect(url_for('contable_libro_diario'))
        asientos = AsientoContable.query.order_by(AsientoContable.fecha.desc(), AsientoContable.id.desc()).limit(100).all()
        return render_template('contable/libro_diario.html', asientos=asientos)

    @app.route('/contable/exportar')
    @login_required
    def contable_exportar():
        tipo = request.args.get('tipo','ventas')
        desde_s = request.args.get('desde','')
        hasta_s = request.args.get('hasta','')
        import csv, io
        si = io.StringIO()
        writer = csv.writer(si)
        if tipo == 'ventas':
            writer.writerow(['Numero','Titulo','Cliente','Fecha','Estado','Subtotal','IVA','Total','Anticipo','Saldo'])
            q = Venta.query
            if desde_s:
                try: q = q.filter(db.func.date(Venta.creado_en) >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(db.func.date(Venta.creado_en) <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for v in q.order_by(Venta.creado_en).all():
                writer.writerow([v.numero or '', v.titulo,
                    v.cliente.empresa or v.cliente.nombre if v.cliente else '',
                    v.creado_en.strftime('%Y-%m-%d'), v.estado,
                    v.subtotal, v.iva, v.total, v.monto_anticipo, v.saldo])
        elif tipo == 'gastos':
            writer.writerow(['Fecha','Tipo','Descripcion','Monto','Recurrencia'])
            q = GastoOperativo.query
            if desde_s:
                try: q = q.filter(GastoOperativo.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(GastoOperativo.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for g in q.order_by(GastoOperativo.fecha).all():
                writer.writerow([g.fecha.strftime('%Y-%m-%d'), g.tipo, g.descripcion or '', g.monto, g.recurrencia])
        elif tipo == 'compras':
            writer.writerow(['Fecha','Item','Proveedor','Cantidad','Unidad','Costo Total','Factura'])
            q = CompraMateria.query
            if desde_s:
                try: q = q.filter(CompraMateria.fecha >= datetime.strptime(desde_s,'%Y-%m-%d').date())
                except: pass
            if hasta_s:
                try: q = q.filter(CompraMateria.fecha <= datetime.strptime(hasta_s,'%Y-%m-%d').date())
                except: pass
            for c in q.order_by(CompraMateria.fecha).all():
                writer.writerow([c.fecha.strftime('%Y-%m-%d'), c.nombre_item, c.proveedor or '',
                    c.cantidad, c.unidad, c.costo_total, c.nro_factura or ''])
        elif tipo == 'asientos':
            writer.writerow(['Numero','Fecha','Descripcion','Tipo','Referencia','Debe','Haber','Cuenta Debe','Cuenta Haber'])
            for a in AsientoContable.query.order_by(AsientoContable.fecha).all():
                writer.writerow([a.numero or '', a.fecha.strftime('%Y-%m-%d'), a.descripcion,
                    a.tipo, a.referencia or '', a.debe, a.haber, a.cuenta_debe or '', a.cuenta_haber or ''])
        output = si.getvalue()
        from flask import Response
        return Response(output, mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename=contable_{tipo}_{desde_s or "todo"}.csv'})

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

    @app.route('/legal/<int:id>/eliminar', methods=['POST'])
    @login_required
    def legal_eliminar(id):
        obj = DocumentoLegal.query.get_or_404(id)
        obj.activo = False; db.session.commit()
        flash('Documento eliminado.','info')
        return redirect(url_for('legal_index'))

    @app.route('/finanzas/impuestos')
    @login_required
    def impuestos():
        return render_template('finanzas/impuestos.html',
                               items=ReglaTributaria.query.order_by(ReglaTributaria.nombre).all())

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

    @app.route('/finanzas/impuestos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def impuesto_eliminar(id):
        obj=ReglaTributaria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Regla eliminada.','info'); return redirect(url_for('impuestos'))

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

    @app.route('/gastos/nuevo', methods=['GET','POST'])
    @login_required
    def gasto_nuevo():
        if request.method == 'POST':
            fd = request.form.get('fecha')
            rec = request.form.get('recurrencia','unico')
            es_pl = request.form.get('es_plantilla') == '1' and rec == 'mensual'
            db.session.add(GastoOperativo(
                fecha=datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date(),
                tipo=request.form['tipo'],
                tipo_custom=request.form.get('tipo_custom','') or None,
                descripcion=request.form.get('descripcion',''),
                monto=float(request.form.get('monto',0) or 0),
                recurrencia=rec,
                es_plantilla=es_pl,
                notas=request.form.get('notas',''), creado_por=current_user.id))
            db.session.commit(); flash('Gasto registrado.','success'); return redirect(url_for('gastos'))
        return render_template('gastos/form.html', obj=None, titulo='Nuevo Gasto',
                               today=datetime.utcnow().strftime('%Y-%m-%d'))

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
            db.session.commit(); flash('Gasto actualizado.','success'); return redirect(url_for('gastos'))
        return render_template('gastos/form.html', obj=obj, titulo='Editar Gasto',
                               today=datetime.utcnow().strftime('%Y-%m-%d'))

    @app.route('/gastos/<int:id>/eliminar', methods=['POST'])
    @login_required
    def gasto_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=GastoOperativo.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Gasto eliminado.','info'); return redirect(url_for('gastos'))

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
        db.session.add(nuevo); db.session.commit()
        flash(f'Gasto "{plantilla.tipo_custom or plantilla.tipo}" registrado para este mes.','success')
        return redirect(url_for('gastos'))

    @app.route('/reportes')
    @login_required
    def reportes():
        from datetime import date
        from calendar import month_abbr
        # Estadísticas generales
        ingresos_totales = db.session.query(db.func.sum(Venta.total)).filter(Venta.estado.in_(['completado','anticipo_pagado'])).scalar() or 0
        gastos_totales   = db.session.query(db.func.sum(GastoOperativo.monto)).scalar() or 0
        balance          = ingresos_totales - gastos_totales
        total_clientes   = Cliente.query.filter_by(estado='activo').count()
        # Ventas por mes (últimos 6 meses)
        hoy = date.today()
        meses_labels, ventas_por_mes = [], []
        for i in range(5, -1, -1):
            mes = (hoy.month - i - 1) % 12 + 1
            anio = hoy.year - ((hoy.month - i - 1) // 12 + (1 if (hoy.month - i - 1) < 0 else 0))
            total_mes = db.session.query(db.func.sum(Venta.total)).filter(
                db.extract('month', Venta.creado_en) == mes,
                db.extract('year', Venta.creado_en) == anio).scalar() or 0
            meses_labels.append(f'{month_abbr[mes]} {str(anio)[2:]}')
            ventas_por_mes.append(round(total_mes))
        # Gastos por tipo
        gastos_por_tipo = db.session.query(GastoOperativo.tipo, db.func.sum(GastoOperativo.monto))\
            .group_by(GastoOperativo.tipo).order_by(db.func.sum(GastoOperativo.monto).desc()).all()
        gastos_tipos_labels = [g[0] for g in gastos_por_tipo]
        gastos_tipos_values = [round(g[1]) for g in gastos_por_tipo]
        # Top 5 clientes por ventas totales
        from sqlalchemy import func as sqlfunc
        top_q = db.session.query(
            Cliente.id, Cliente.nombre, Cliente.empresa,
            sqlfunc.sum(Venta.total).label('total_ventas')
        ).join(Venta, Venta.cliente_id == Cliente.id)\
         .group_by(Cliente.id, Cliente.nombre, Cliente.empresa)\
         .order_by(sqlfunc.sum(Venta.total).desc()).limit(5).all()
        class _C:
            def __init__(self, r): self.id=r[0]; self.nombre=r[1]; self.empresa=r[2]; self.total_ventas=r[3]
        top_clientes = [_C(r) for r in top_q]
        # Stock bajo
        bajo_stock = Producto.query.filter(Producto.activo==True, Producto.stock<=Producto.stock_minimo).all()
        return render_template('reportes.html',
            total_clientes=total_clientes, ingresos_totales=ingresos_totales,
            gastos_totales=gastos_totales, balance=balance,
            meses_labels=meses_labels, ventas_por_mes=ventas_por_mes,
            gastos_tipos_labels=gastos_tipos_labels, gastos_tipos_values=gastos_tipos_values,
            top_clientes=top_clientes, bajo_stock=bajo_stock)

    @app.route('/reportes/exportar/ventas.xlsx')
    @login_required
    def exportar_ventas():
        from flask import send_file
        ventas = Venta.query.order_by(Venta.creado_en.desc()).all()
        headers = ['Título','Cliente','Subtotal COP','IVA COP','Total COP','% Anticipo','Anticipo COP','Saldo COP','Estado','Fecha anticipo','Días entrega','Creada']
        rows = []
        for v in ventas:
            rows.append([
                v.titulo,
                v.cliente.empresa or v.cliente.nombre if v.cliente else '',
                round(v.subtotal), round(v.iva), round(v.total),
                v.porcentaje_anticipo, round(v.monto_anticipo), round(v.saldo),
                v.estado,
                v.fecha_anticipo.strftime('%d/%m/%Y') if v.fecha_anticipo else '',
                v.dias_entrega,
                v.creado_en.strftime('%d/%m/%Y')
            ])
        buf = _make_xlsx('Ventas', headers, rows)
        return send_file(buf, download_name='evore_ventas.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/reportes/exportar/clientes.xlsx')
    @login_required
    def exportar_clientes():
        from flask import send_file
        items = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        headers = ['Empresa','NIT','Relación','Dirección comercial','Dirección entrega','Estado','Creado']
        rows = [[c.empresa or '', c.nit or '', c.estado_relacion or '', c.dir_comercial or '',
                 c.dir_entrega or '', c.estado, c.creado_en.strftime('%d/%m/%Y')] for c in items]
        buf = _make_xlsx('Clientes', headers, rows)
        return send_file(buf, download_name='evore_clientes.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/reportes/exportar/inventario.xlsx')
    @login_required
    def exportar_inventario():
        from flask import send_file
        items = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        headers = ['Nombre','SKU','NSO (INVIMA)','Precio COP','Costo COP','Stock','Stock Mínimo','Categoría']
        rows = [[p.nombre, p.sku or '', p.nso or '', round(p.precio), round(p.costo),
                 p.stock, p.stock_minimo, p.categoria or ''] for p in items]
        buf = _make_xlsx('Inventario', headers, rows)
        return send_file(buf, download_name='evore_inventario.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/reportes/exportar/gastos.xlsx')
    @login_required
    def exportar_gastos():
        from flask import send_file
        items = GastoOperativo.query.order_by(GastoOperativo.fecha.desc()).all()
        headers = ['Fecha','Tipo','Descripción','Monto COP','Notas']
        rows = [[g.fecha.strftime('%d/%m/%Y'), g.tipo, g.descripcion or '', round(g.monto), g.notas or ''] for g in items]
        buf = _make_xlsx('Gastos Operativos', headers, rows)
        return send_file(buf, download_name='evore_gastos.xlsx',
                         as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
