# routes/produccion.py — reconstruido desde v27 con CRUD completo
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

    # ── produccion_index (/produccion)
    @app.route('/produccion')
    @login_required
    def produccion_index():
        from datetime import date
        mes_ini = date.today().replace(day=1)
        total_compras  = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
        compras_mes    = db.session.query(db.func.sum(CompraMateria.costo_total)).filter(CompraMateria.fecha >= mes_ini).scalar() or 0
        cotizaciones_vigentes = CotizacionGranel.query.filter_by(estado='vigente').count()
        ordenes_activas = OrdenCompra.query.filter(OrdenCompra.estado.in_(['borrador','enviada','en_transito'])).count()
        compras_recientes = CompraMateria.query.order_by(CompraMateria.fecha.desc()).limit(5).all()
        granel_recientes  = CotizacionGranel.query.order_by(CotizacionGranel.creado_en.desc()).limit(5).all()
        return render_template('produccion/index.html',
            total_compras=total_compras, compras_mes=compras_mes,
            cotizaciones_vigentes=cotizaciones_vigentes, ordenes_activas=ordenes_activas,
            compras_recientes=compras_recientes, granel_recientes=granel_recientes)
    

    # ── compras (/produccion/compras)
    @app.route('/produccion/compras')
    @login_required
    def compras():
        busqueda=request.args.get('buscar','')
        q=CompraMateria.query
        if busqueda:
            q=q.filter(db.or_(CompraMateria.nombre_item.ilike(f'%{busqueda}%'),
                               CompraMateria.proveedor.ilike(f'%{busqueda}%'),
                               CompraMateria.nro_factura.ilike(f'%{busqueda}%')))
        from datetime import date
        mes_ini = date.today().replace(day=1)
        total_general = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
        total_mes = db.session.query(db.func.sum(CompraMateria.costo_total)).filter(CompraMateria.fecha >= mes_ini).scalar() or 0
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        return render_template('produccion/compras.html', items=q.order_by(CompraMateria.fecha.desc()).all(),
                               busqueda=busqueda, total_general=total_general, total_mes=total_mes,
                               materias=materias)
    

    # ── compra_nueva (/produccion/compras/nueva)
    @app.route('/produccion/compras/nueva', methods=['GET','POST'])
    @login_required
    def compra_nueva():
        if request.method == 'POST':
            c = CompraMateria(creado_por=current_user.id)
            _save_compra(c, request.form)
            db.session.add(c); db.session.commit()
            flash('Compra registrada.','success')
            return redirect(url_for('compras'))
        return render_template('produccion/compra_form.html', obj=None, titulo='Nueva Compra',
                               productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                               materias=MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all(),
                               proveedores_list=Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all(),
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── compra_editar (/produccion/compras/<int:id>/editar)
    @app.route('/produccion/compras/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def compra_editar(id):
        obj=CompraMateria.query.get_or_404(id)
        if request.method == 'POST':
            _save_compra(obj, request.form)
            db.session.commit()
            flash('Compra actualizada.','success')
            return redirect(url_for('compras'))
        return render_template('produccion/compra_form.html', obj=obj, titulo='Editar Compra',
                               productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                               materias=MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all(),
                               proveedores_list=Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all(),
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── compra_eliminar (/produccion/compras/<int:id>/eliminar)
    @app.route('/produccion/compras/<int:id>/eliminar', methods=['POST'])
    @login_required
    def compra_eliminar(id):
        obj=CompraMateria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Compra eliminada.','info'); return redirect(url_for('compras'))


    # ── compra_ingresar_mp (/produccion/compras/<int:id>/ingresar_mp)
    @app.route('/produccion/compras/<int:id>/ingresar_mp', methods=['POST'])
    @login_required
    def compra_ingresar_mp(id):
        """Ingresa una compra al stock de materias primas creando un LoteMateriaPrima."""
        from datetime import date as _date
        compra = CompraMateria.query.get_or_404(id)
        materia_id = request.form.get('materia_id')
        if not materia_id:
            flash('Selecciona una materia prima.', 'danger')
            return redirect(url_for('compras'))
        m = MateriaPrima.query.get_or_404(int(materia_id))
        cant = float(request.form.get('cantidad_ingresar') or compra.cantidad or 1)
        # Crear lote
        lote_mp = LoteMateriaPrima(
            materia_prima_id=m.id,
            compra_id=compra.id,
            numero_lote=request.form.get('nro_lote','').strip() or None,
            nro_factura=compra.nro_factura,
            proveedor=compra.proveedor,
            fecha_compra=compra.fecha,
            fecha_vencimiento=compra.fecha_caducidad,
            cantidad_inicial=cant,
            cantidad_disponible=cant,
            cantidad_reservada=0.0,
            costo_unitario=compra.precio_unitario or 0,
            notas=f'Ingresado desde compra #{compra.id} — {compra.nombre_item}',
        )
        db.session.add(lote_mp)
        m.stock_disponible = (m.stock_disponible or 0) + cant
        # Actualizar la compra para vincularla
        compra.materia_id = m.id
        compra.tipo_compra = 'materia_prima'
        db.session.commit()
        flash(f'✅ {cant} {m.unidad} ingresados al stock de "{m.nombre}".', 'success')
        return redirect(url_for('compras'))


    # ── granel (/produccion/granel)
    @app.route('/produccion/granel')
    @login_required
    def granel():
        estado_f=request.args.get('estado','')
        q=CotizacionGranel.query
        if estado_f: q=q.filter_by(estado=estado_f)
        return render_template('produccion/granel.html', items=q.order_by(CotizacionGranel.creado_en.desc()).all(),
                               estado_f=estado_f)
    

    # ── granel_nuevo (/produccion/granel/nueva)
    @app.route('/produccion/granel/nueva', methods=['GET','POST'])
    @login_required
    def granel_nuevo():
        if request.method == 'POST':
            fc = request.form.get('fecha_cotizacion')
            fv = request.form.get('vigencia')
            pid = request.form.get('producto_id') or None
            estado = request.form.get('estado','vigente')
            precio_u = float(request.form.get('precio_unitario',0) or 0)
            g = CotizacionGranel(
                producto_id=int(pid) if pid else None,
                nombre_producto=request.form['nombre_producto'],
                sku=request.form.get('sku',''), nso=request.form.get('nso',''),
                proveedor=request.form.get('proveedor',''),
                precio_unitario=precio_u,
                unidades_minimas=int(request.form.get('unidades_minimas',1) or 1),
                fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else None,
                vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
                estado=estado, notas=request.form.get('notas',''), creado_por=current_user.id)
            db.session.add(g)
            if pid and estado == 'vigente':
                prod = db.session.get(Producto, int(pid))
                if prod: prod.costo = precio_u
            db.session.commit()
            flash('Cotización guardada.','success')
            return redirect(url_for('granel'))
        return render_template('produccion/granel_form.html', obj=None, titulo='Nueva Cotización Granel',
                               productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── granel_editar (/produccion/granel/<int:id>/editar)
    @app.route('/produccion/granel/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def granel_editar(id):
        obj=CotizacionGranel.query.get_or_404(id)
        if request.method == 'POST':
            fc = request.form.get('fecha_cotizacion')
            fv = request.form.get('vigencia')
            pid = request.form.get('producto_id') or None
            estado = request.form.get('estado','vigente')
            precio_u = float(request.form.get('precio_unitario',0) or 0)
            obj.producto_id=int(pid) if pid else None
            obj.nombre_producto=request.form['nombre_producto']
            obj.sku=request.form.get('sku',''); obj.nso=request.form.get('nso','')
            obj.proveedor=request.form.get('proveedor',''); obj.precio_unitario=precio_u
            obj.unidades_minimas=int(request.form.get('unidades_minimas',1) or 1)
            obj.fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else None
            obj.vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None
            obj.estado=estado; obj.notas=request.form.get('notas','')
            if pid and estado == 'vigente':
                prod = db.session.get(Producto, int(pid))
                if prod: prod.costo = precio_u
            db.session.commit()
            flash('Cotización actualizada.','success')
            return redirect(url_for('granel'))
        return render_template('produccion/granel_form.html', obj=obj, titulo='Editar Cotización Granel',
                               productos=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
                               today=datetime.utcnow().strftime('%Y-%m-%d'))
    

    # ── granel_eliminar (/produccion/granel/<int:id>/eliminar)
    @app.route('/produccion/granel/<int:id>/eliminar', methods=['POST'])
    @login_required
    def granel_eliminar(id):
        obj=CotizacionGranel.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Cotización eliminada.','info'); return redirect(url_for('granel'))
    

    # ── materias (/produccion/materias)
    @app.route('/produccion/materias')
    @login_required
    @requiere_modulo('produccion')
    def materias():
        from datetime import date
        items = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        return render_template('produccion/materias.html', materias=items, today=date.today())
    

    def _save_materia_m2m(m, form):
        """Guarda relación M2M MateriaPrima ↔ Productos."""
        prod_ids = [int(x) for x in form.getlist('producto_ids[]') if x]
        # Eliminar relaciones existentes
        MateriaPrimaProducto.query.filter_by(materia_prima_id=m.id).delete()
        # Primer producto = campo legacy producto_id
        m.producto_id = prod_ids[0] if prod_ids else None
        # Insertar nuevas relaciones M2M
        for pid in prod_ids:
            db.session.add(MateriaPrimaProducto(materia_prima_id=m.id, producto_id=pid))

    # ── materia_nueva (/produccion/materias/nueva)
    @app.route('/produccion/materias/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def materia_nueva():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            m = MateriaPrima(
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion','') or None,
                unidad=request.form.get('unidad','unidades'),
                stock_disponible=0,  # El stock solo entra por compras
                stock_minimo=float(request.form.get('stock_minimo',0)),
                costo_unitario=float(request.form.get('costo_unitario',0)),
                categoria=request.form.get('categoria','') or None,
                proveedor=request.form.get('proveedor','') or None,
                proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None,
            )
            db.session.add(m); db.session.flush()
            _save_materia_m2m(m, request.form)
            db.session.commit()
            flash('Materia prima creada. Registra entradas de stock mediante Compras.','success')
            return redirect(url_for('materias'))
        return render_template('produccion/materia_form.html', obj=None, titulo='Nueva Materia Prima',
                               productos=productos, prod_ids_sel=[],
                               proveedores_list=Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all())
    

    # ── materia_editar (/produccion/materias/<int:id>/editar)
    @app.route('/produccion/materias/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def materia_editar(id):
        obj = MateriaPrima.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        # IDs actuales de productos asociados para pre-seleccionar checkboxes
        prod_ids_sel = [mp.producto_id for mp in MateriaPrimaProducto.query.filter_by(materia_prima_id=obj.id).all()]
        if not prod_ids_sel and obj.producto_id:
            prod_ids_sel = [obj.producto_id]
        if request.method == 'POST':
            obj.nombre=request.form['nombre']
            obj.descripcion=request.form.get('descripcion','') or None
            obj.unidad=request.form.get('unidad','unidades')
            obj.stock_minimo=float(request.form.get('stock_minimo',0))
            obj.costo_unitario=float(request.form.get('costo_unitario',0))
            obj.categoria=request.form.get('categoria','') or None
            obj.proveedor=request.form.get('proveedor','') or None
            obj.proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None
            _save_materia_m2m(obj, request.form)
            db.session.commit()
            flash('Materia prima actualizada.','success'); return redirect(url_for('materias'))
        return render_template('produccion/materia_form.html', obj=obj, titulo='Editar Materia Prima',
                               productos=productos, prod_ids_sel=prod_ids_sel,
                               proveedores_list=Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all())
    

    # ── materia_eliminar (/produccion/materias/<int:id>/eliminar)
    @app.route('/produccion/materias/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def materia_eliminar(id):
        obj = MateriaPrima.query.get_or_404(id); obj.activo=False; db.session.commit()
        flash('Materia prima desactivada.','info'); return redirect(url_for('materias'))
    

    # ── recetas (/produccion/recetas)
    @app.route('/produccion/recetas')
    @login_required
    @requiere_modulo('produccion')
    def recetas():
        items = RecetaProducto.query.filter_by(activo=True).all()
        return render_template('produccion/recetas.html', recetas=items)
    

    def _registrar_ingredientes_en_cero(ids_ingredientes, producto_id):
        """
        Asegura que todos los ingredientes de una receta estén registrados
        como MateriaPrima (con stock=0 si no tienen compras aún).
        También vincula cada ingrediente al producto si no estaba vinculado.
        """
        for mid in ids_ingredientes:
            if not mid:
                continue
            m = db.session.get(MateriaPrima, int(mid))
            if not m:
                continue
            # Vincular al producto si no hay relación M2M aún
            if producto_id:
                existe = MateriaPrimaProducto.query.filter_by(
                    materia_prima_id=m.id, producto_id=producto_id
                ).first()
                if not existe:
                    db.session.add(MateriaPrimaProducto(
                        materia_prima_id=m.id, producto_id=producto_id
                    ))
                    # Mantener campo legacy
                    if not m.producto_id:
                        m.producto_id = producto_id

    # ── receta_nueva (/produccion/recetas/nueva)
    @app.route('/produccion/recetas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_nueva():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        materias_json = [{'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad} for m in materias]
        if request.method == 'POST':
            prod_id = int(request.form['producto_id'])
            r = RecetaProducto(
                producto_id=prod_id,
                unidades_produce=int(request.form.get('unidades_produce',1)),
                descripcion=request.form.get('descripcion','') or None
            )
            db.session.add(r); db.session.flush()
            ids   = request.form.getlist('materia_id[]')
            cants = request.form.getlist('cantidad[]')
            for mid, cant in zip(ids, cants):
                if mid and cant:
                    db.session.add(RecetaItem(
                        receta_id=r.id,
                        materia_prima_id=int(mid),
                        cantidad_por_unidad=float(cant)
                    ))
            # Registrar ingredientes al producto y asegurarse que existen en el catálogo
            _registrar_ingredientes_en_cero(ids, prod_id)
            db.session.commit()
            flash('Receta creada. Los ingredientes quedan registrados (stock=0 hasta primera compra).','success')
            return redirect(url_for('recetas'))
        return render_template('produccion/receta_form.html', obj=None, productos=productos,
                               materias=materias, materias_json=materias_json, titulo='Nueva Receta')
    

    # ── receta_editar (/produccion/recetas/<int:id>/editar)
    @app.route('/produccion/recetas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_editar(id):
        obj = RecetaProducto.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        materias_json = [{'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad} for m in materias]
        if request.method == 'POST':
            prod_id = int(request.form['producto_id'])
            obj.producto_id=prod_id
            obj.unidades_produce=int(request.form.get('unidades_produce',1))
            obj.descripcion=request.form.get('descripcion','') or None
            for item in obj.items: db.session.delete(item)
            db.session.flush()
            ids   = request.form.getlist('materia_id[]')
            cants = request.form.getlist('cantidad[]')
            for mid, cant in zip(ids, cants):
                if mid and cant:
                    db.session.add(RecetaItem(
                        receta_id=obj.id,
                        materia_prima_id=int(mid),
                        cantidad_por_unidad=float(cant)
                    ))
            _registrar_ingredientes_en_cero(ids, prod_id)
            db.session.commit()
            flash('Receta actualizada.','success'); return redirect(url_for('recetas'))
        return render_template('produccion/receta_form.html', obj=obj, productos=productos,
                               materias=materias, materias_json=materias_json, titulo='Editar Receta')
    

    # ── receta_eliminar (/produccion/recetas/<int:id>/eliminar)
    @app.route('/produccion/recetas/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_eliminar(id):
        obj = RecetaProducto.query.get_or_404(id); obj.activo=False; db.session.commit()
        flash('Receta eliminada.','info'); return redirect(url_for('recetas'))
    

    # ── reservas (/produccion/reservas)
    @app.route('/produccion/reservas')
    @login_required
    @requiere_modulo('produccion')
    def reservas():
        from datetime import date as _date
        from services.inventario import InventarioService
        items = ReservaProduccion.query.order_by(ReservaProduccion.creado_en.desc()).all()
        usuarios = User.query.filter_by(activo=True).order_by(User.nombre).all()

        # Pre-calcular validación por venta para el template
        venta_ids = list({r.venta_id for r in items if r.venta_id})
        validaciones = {}
        for vid in venta_ids:
            validaciones[vid] = InventarioService.validar_materias_produccion(vid)

        ESTADOS_VALIDOS_PROD = {'anticipo_pagado', 'completado', 'pagado'}
        return render_template('produccion/reservas.html',
                               reservas=items, usuarios=usuarios,
                               today=_date.today(),
                               validaciones=validaciones,
                               ESTADOS_VALIDOS_PROD=ESTADOS_VALIDOS_PROD)
    

    # ── reserva_solicitar_compra (/produccion/reservas/solicitar_compra)
    @app.route('/produccion/reservas/solicitar_compra', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def reserva_solicitar_compra():
        reserva_id = request.form.get('reserva_id')
        usuario_id = int(request.form.get('usuario_id'))
        descripcion = request.form.get('descripcion','')
        cantidad_faltante = request.form.get('cantidad_faltante','')
        r = ReservaProduccion.query.get_or_404(int(reserva_id))
        mp = r.materia
        from datetime import timedelta
        venc = (datetime.utcnow() + timedelta(days=3)).date()
    
        # Format the title with the missing quantity
        try:
            cant_fmt = f'{float(cantidad_faltante):.3f} {mp.unidad}' if cantidad_faltante else ''
        except (ValueError, TypeError):
            cant_fmt = ''
        titulo_compra = f'Comprar {cant_fmt} de {mp.nombre}' if cant_fmt else f'Comprar materia: {mp.nombre}'
    
        t_compra = Tarea(
            titulo=titulo_compra,
            descripcion=(f'Falta material en reserva de producción.\n'
                         f'Materia: {mp.nombre}\n'
                         f'Cantidad faltante: {cant_fmt or "ver descripción"}\n'
                         f'Producto: {r.producto.nombre if r.producto else "N/A"}\n\n{descripcion}'),
            estado='pendiente', prioridad='alta',
            asignado_a=usuario_id,
            creado_por=current_user.id,
            fecha_vencimiento=venc,
            tarea_tipo='comprar_materias'
        )
        db.session.add(t_compra); db.session.flush()
    
        t_abono = Tarea(
            titulo=f'Verificar abono — {titulo_compra}',
            descripcion=(f'Confirmar anticipo antes de comprar {mp.nombre}.\n'
                         f'Cantidad requerida: {cant_fmt or "ver descripción"}\n\n{descripcion}'),
            estado='pendiente', prioridad='alta',
            asignado_a=usuario_id,
            creado_por=current_user.id,
            fecha_vencimiento=venc,
            tarea_tipo='verificar_abono',
            tarea_pareja_id=t_compra.id
        )
        db.session.add(t_abono); db.session.flush()
        t_compra.tarea_pareja_id = t_abono.id
        db.session.commit()
    
        _crear_notificacion(
            usuario_id, 'tarea_asignada',
            f'Nueva tarea asignada: {t_compra.titulo}',
            f'Tienes 2 nuevas tareas de compra/abono para {mp.nombre}.',
            url_for('tareas')
        )
        flash(f'Tareas de compra y abono creadas y asignadas.', 'success')
        return redirect(url_for('reservas'))
    

    # ── reserva_nueva (/produccion/reservas/nueva)
    @app.route('/produccion/reservas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def reserva_nueva():
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            mid = int(request.form['materia_prima_id'])
            cantidad = float(request.form['cantidad'])
            m = MateriaPrima.query.get_or_404(mid)
            if cantidad > m.stock_disponible:
                flash(f'Stock insuficiente. Disponible: {m.stock_disponible} {m.unidad}','danger')
            else:
                pid_raw = request.form.get('producto_id','')
                r = ReservaProduccion(
                    materia_prima_id=mid, cantidad=cantidad,
                    producto_id=int(pid_raw) if pid_raw else None,
                    estado='reservado', notas=request.form.get('notas','') or None,
                    creado_por=current_user.id
                )
                m.stock_disponible -= cantidad
                m.stock_reservado += cantidad
                db.session.add(r); db.session.commit()
                flash('Reserva creada. Stock actualizado.','success')
                return redirect(url_for('reservas'))
        return render_template('produccion/reserva_form.html', materias=materias, productos=productos)
    

    # ── reserva_cancelar (/produccion/reservas/<int:id>/cancelar)
    @app.route('/produccion/reservas/<int:id>/cancelar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def reserva_cancelar(id):
        r = ReservaProduccion.query.get_or_404(id)
        if r.estado == 'reservado':
            m = db.session.get(MateriaPrima, r.materia_prima_id)
            if m:
                m.stock_disponible += r.cantidad
                m.stock_reservado = max(0, m.stock_reservado - r.cantidad)
            r.estado = 'cancelado'
            db.session.commit()
            flash('Reserva cancelada y stock devuelto.','info')
        return redirect(url_for('reservas'))
    

    # ── reserva_iniciar_produccion (/produccion/reservas/venta/<int:venta_id>/iniciar)
    @app.route('/produccion/reservas/venta/<int:venta_id>/iniciar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def reserva_iniciar_produccion(venta_id):
        """
        Inicia producción para una venta:
        1. Valida que la venta esté en estado anticipo_pagado o pagado/completado.
        2. Valida que TODOS los materiales estén disponibles (sin FALTANTE).
        3. Descuenta stock a través de InventarioService.
        4. Cambia órdenes a en_produccion.
        """
        from services.inventario import InventarioService

        venta = Venta.query.get_or_404(venta_id)

        # 1. Validar estado de la venta
        ESTADOS_VALIDOS = {'anticipo_pagado', 'completado', 'pagado'}
        if venta.estado not in ESTADOS_VALIDOS:
            flash(
                f'No se puede iniciar producción. La venta debe tener anticipo recibido o estar pagada '
                f'(estado actual: {venta.estado}).',
                'danger'
            )
            return redirect(url_for('reservas'))

        # 2. Validar materiales via InventarioService
        validacion = InventarioService.validar_materias_produccion(venta_id)
        if not validacion['ok']:
            msgs = [
                f'{f["nombre"]}: necesario {f["necesario"]:.3f} {f["unidad"]}, '
                f'disponible {f["disponible"]:.3f}, falta {f["falta"]:.3f}'
                for f in validacion['faltantes']
            ]
            flash(
                f'No se puede iniciar producción — materiales faltantes: ' + ' | '.join(msgs),
                'danger'
            )
            return redirect(url_for('reservas'))

        # 3. Descontar stock via InventarioService
        ok, msg = InventarioService.descontar_materias_produccion(venta_id)
        if not ok:
            flash(f'Error al descontar stock: {msg}', 'danger')
            return redirect(url_for('reservas'))

        # 4. Cambiar órdenes a en_produccion
        ordenes = OrdenProduccion.query.filter(
            OrdenProduccion.venta_id == venta_id,
            OrdenProduccion.estado.in_(['pendiente_materiales', 'en_produccion'])
        ).all()
        for o in ordenes:
            o.estado = 'en_produccion'
            if not o.fecha_inicio_real:
                o.fecha_inicio_real = datetime.utcnow().date()

        db.session.commit()
        flash('¡Producción iniciada! Stock de materias primas descontado correctamente.', 'success')
        return redirect(url_for('reservas'))
    

    # ── ordenes_produccion (/produccion/ordenes)
    @app.route('/produccion/ordenes')
    @login_required
    @requiere_modulo('produccion')
    def ordenes_produccion():
        pendientes = OrdenProduccion.query.filter(
            OrdenProduccion.estado.in_(['pendiente_materiales','en_produccion'])
        ).order_by(OrdenProduccion.creado_en.desc()).all()
        completados = OrdenProduccion.query.filter_by(estado='completado')\
            .order_by(OrdenProduccion.completado_en.desc()).limit(30).all()
        return render_template('produccion/ordenes.html',
                               pendientes=pendientes, completados=completados)
    

    # ── orden_completar (/produccion/ordenes/completar)
    @app.route('/produccion/ordenes/completar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def orden_completar():
        orden_id    = int(request.form.get('orden_id'))
        numero_lote = request.form.get('numero_lote','').strip()
        notas       = request.form.get('notas','')
        fv          = request.form.get('fecha_vencimiento')

        orden = OrdenProduccion.query.get_or_404(orden_id)
        prod  = orden.producto

        # Liberar materias primas reservadas para esta venta+producto
        # (marcar como 'usado' y descontar de stock_reservado)
        if orden.venta_id:
            reservas_mat = ReservaProduccion.query.filter(
                ReservaProduccion.venta_id == orden.venta_id,
                ReservaProduccion.producto_id == orden.producto_id,
                ReservaProduccion.estado == 'reservado'
            ).all()
            for r in reservas_mat:
                mp = r.materia
                # Reducir stock_reservado — el material fue consumido
                mp.stock_reservado = max(0.0, (mp.stock_reservado or 0) - r.cantidad)
                r.estado = 'usado'

        # Añadir producto terminado al stock
        prod.stock = (prod.stock or 0) + int(orden.cantidad_producir)

        # Registrar lote de producción
        lote_num = numero_lote or f'OP-{orden.id}'
        lote = LoteProducto(
            producto_id=prod.id,
            numero_lote=lote_num,
            fecha_produccion=datetime.utcnow().date(),
            fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
            unidades_producidas=orden.cantidad_producir,
            unidades_restantes=orden.cantidad_producir,
            notas=notas or f'Orden producción #{orden.id}',
            creado_por=current_user.id
        )
        db.session.add(lote)

        orden.estado       = 'completado'
        orden.numero_lote  = lote_num
        orden.completado_en = datetime.utcnow()
        db.session.commit()

        # Notificar admins
        admins = User.query.filter_by(rol='admin', activo=True).all()
        for adm in admins:
            _crear_notificacion(
                adm.id, 'info',
                f'✅ Producción completada: {prod.nombre}',
                f'{orden.cantidad_producir:.0f} unidades al inventario. Lote: {lote_num}',
                url_for('inventario')
            )
        flash(f'Producción completada. {orden.cantidad_producir:.0f} uds de {prod.nombre} añadidas al inventario. Lote: {lote_num}', 'success')
        return redirect(url_for('ordenes_produccion'))
    

    # ── gantt (/produccion/gantt)
    @app.route('/produccion/gantt')
    @login_required
    @requiere_modulo('produccion')
    def gantt():
        # Agrupa órdenes de producción por pedido (venta)
        ordenes = OrdenProduccion.query.order_by(OrdenProduccion.venta_id, OrdenProduccion.creado_en).all()
    
        # Construir grupos por venta
        grupos = {}   # venta_id -> {'venta': obj|None, 'ordenes': [...]}
        sin_venta = {'venta_id': None, 'titulo': 'Sin pedido asociado', 'ordenes': [],
                     'cliente': None, 'venta_numero': None, 'fecha_entrega': None}
    
        for o in ordenes:
            inicio = (o.fecha_inicio_real or o.creado_en.date())
            if o.fecha_fin_estimada:
                fin = o.fecha_fin_estimada
            elif o.completado_en:
                fin = o.completado_en.date()
            elif o.venta and o.venta.fecha_entrega_est:
                fin = o.venta.fecha_entrega_est
            elif o.cotizacion and o.cotizacion.fecha_entrega_est:
                fin = o.cotizacion.fecha_entrega_est
            else:
                fin = inicio + timedelta(days=30)
    
            # Buscar OC de materiales vinculada (mejor estimación de entrega de materiales)
            mat_inicio = mat_fin = None
            if o.venta_id:
                oc_mat = OrdenCompra.query.filter(
                    OrdenCompra.estado.in_(['borrador','enviada','recibida'])
                ).order_by(OrdenCompra.creado_en.desc()).first()
                if oc_mat:
                    mat_inicio = oc_mat.fecha_emision
                    mat_fin    = oc_mat.fecha_esperada or (oc_mat.fecha_emision + timedelta(days=15) if oc_mat.fecha_emision else None)
    
            ord_data = {
                'id':         o.id,
                'producto':   o.producto.nombre,
                'cantidad':   int(o.cantidad_producir),
                'estado':     o.estado,
                'lote':       o.numero_lote or '',
                'inicio':     inicio.strftime('%Y-%m-%d'),
                'fin':        fin.strftime('%Y-%m-%d'),
                'mat_inicio': mat_inicio.strftime('%Y-%m-%d') if mat_inicio else None,
                'mat_fin':    mat_fin.strftime('%Y-%m-%d')    if mat_fin    else None,
            }
    
            if o.venta_id:
                if o.venta_id not in grupos:
                    v = o.venta
                    grupos[o.venta_id] = {
                        'venta_id':     o.venta_id,
                        'titulo':       v.titulo if v else f'Venta #{o.venta_id}',
                        'venta_numero': v.numero if v else None,
                        'cliente':      (v.cliente.empresa or v.cliente.nombre) if v and v.cliente else None,
                        'fecha_entrega': v.fecha_entrega_est.strftime('%d/%m/%Y') if v and v.fecha_entrega_est else None,
                        'ordenes':      []
                    }
                grupos[o.venta_id]['ordenes'].append(ord_data)
            else:
                sin_venta['ordenes'].append(ord_data)
    
        pedidos_json = list(grupos.values())
        if sin_venta['ordenes']:
            pedidos_json.append(sin_venta)
    
        return render_template('produccion/gantt.html', pedidos_json=pedidos_json)
    
