# routes/produccion.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
from sqlalchemy import func, case
import logging

def register(app):

    # ── produccion_index (/produccion)
    @app.route('/produccion')
    @login_required
    @requiere_modulo('produccion')
    def produccion_index():
        from datetime import date
        mes_ini = date.today().replace(day=1)
        total_compras  = db.session.query(db.func.sum(CompraMateria.costo_total)).scalar() or 0
        compras_mes    = db.session.query(db.func.sum(CompraMateria.costo_total)).filter(CompraMateria.fecha >= mes_ini).scalar() or 0
        cotizaciones_vigentes = CotizacionGranel.query.filter_by(estado='vigente').count()
        ordenes_activas = OrdenCompra.query.filter(OrdenCompra.estado.in_(['borrador','enviada','en_transito'])).count()
        compras_recientes = CompraMateria.query.order_by(CompraMateria.fecha.desc()).limit(5).all()
        granel_recientes  = CotizacionGranel.query.order_by(CotizacionGranel.creado_en.desc()).limit(5).all()
        # Supplier quality scorecard
        try:
            proveedores_score = db.session.query(
                Proveedor.id, Proveedor.empresa, Proveedor.nombre,
                func.count(OrdenCompra.id).label('total_oc'),
                func.sum(case((OrdenCompra.tiene_problema_calidad == True, 1), else_=0)).label('problemas'),
                func.sum(case((OrdenCompra.estado == 'recibida', 1), else_=0)).label('recibidas'),
            ).join(OrdenCompra, OrdenCompra.proveedor_id == Proveedor.id
            ).group_by(Proveedor.id, Proveedor.empresa, Proveedor.nombre
            ).having(func.count(OrdenCompra.id) >= 1
            ).order_by(func.count(OrdenCompra.id).desc()).limit(10).all()
        except Exception:
            proveedores_score = []
        # Capacity planning: operator workload
        try:
            operarios_carga = db.session.query(
                Empleado.id, Empleado.nombre, Empleado.apellido,
                func.count(OrdenProduccion.id).label('ordenes_activas'),
                func.sum(OrdenProduccion.cantidad_producir).label('unidades_total')
            ).outerjoin(OrdenProduccion, db.and_(
                OrdenProduccion.operario_id == Empleado.id,
                OrdenProduccion.estado.in_(['pendiente', 'en_produccion'])
            )).filter(
                Empleado.estado == 'activo',
                db.or_(
                    Empleado.cargo.ilike('%producci%'),
                    Empleado.cargo.ilike('%operari%'),
                    Empleado.cargo.ilike('%planta%'),
                    OrdenProduccion.operario_id != None
                )
            ).group_by(Empleado.id, Empleado.nombre, Empleado.apellido
            ).order_by(func.count(OrdenProduccion.id).desc()
            ).limit(15).all()
        except Exception:
            operarios_carga = []
        return render_template('produccion/index.html',
            total_compras=total_compras, compras_mes=compras_mes,
            cotizaciones_vigentes=cotizaciones_vigentes, ordenes_activas=ordenes_activas,
            compras_recientes=compras_recientes, granel_recientes=granel_recientes,
            proveedores_score=proveedores_score, operarios_carga=operarios_carga)
    

    # ── compras (/produccion/compras)
    @app.route('/produccion/compras')
    @login_required
    @requiere_modulo('produccion')
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
    @requiere_modulo('produccion')
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
    @requiere_modulo('produccion')
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
    

    # ── compra_recibir (/produccion/compras/<int:id>/recibir)
    @app.route('/produccion/compras/<int:id>/recibir', methods=['POST'])
    @login_required
    def compra_recibir(id):
        """Registrar recepcion total o parcial de material."""
        obj = CompraMateria.query.get_or_404(id)
        tipo = request.form.get('tipo_recepcion', 'total')
        cant_total_item = float(obj.cantidad or 0)
        if tipo == 'total':
            obj.estado_recepcion = 'recibido'
            obj.cantidad_recibida = cant_total_item
        else:
            cant = float(request.form.get('cantidad_recibida') or 0)
            if cant <= 0:
                flash('La cantidad debe ser mayor a cero.', 'warning')
                return redirect(url_for('compras'))
            obj.cantidad_recibida = float(obj.cantidad_recibida or 0) + cant
            # Cap: no puede recibir mas de lo pedido
            if cant_total_item > 0:
                obj.cantidad_recibida = min(obj.cantidad_recibida, cant_total_item)
            # Determinar estado: recibido si cantidad_recibida >= cantidad pedida
            if cant_total_item > 0 and obj.cantidad_recibida >= cant_total_item:
                obj.estado_recepcion = 'recibido'
            else:
                obj.estado_recepcion = 'parcial'
        # Actualizar OC vinculada si aplica
        if obj.orden_compra_id:
            oc = db.session.get(OrdenCompra, obj.orden_compra_id)
            if oc:
                compras_oc = CompraMateria.query.filter_by(orden_compra_id=oc.id).all()
                # Re-evaluar cada item: si cantidad_recibida >= cantidad, es recibido
                for c in compras_oc:
                    cant_c = float(c.cantidad or 0)
                    rec_c = float(c.cantidad_recibida or 0)
                    if cant_c > 0 and rec_c >= cant_c and c.estado_recepcion != 'recibido':
                        c.estado_recepcion = 'recibido'
                todos_recibidos = all(
                    c.estado_recepcion == 'recibido'
                    for c in compras_oc
                    if c.estado_recepcion != 'solicitado' or float(c.cantidad or 0) > 0
                )
                alguno_recibido = any(c.estado_recepcion in ('parcial', 'recibido') for c in compras_oc)
                if todos_recibidos and alguno_recibido:
                    oc.estado_recepcion = 'recibida'
                    oc.estado = 'recibida'
                elif alguno_recibido:
                    oc.estado_recepcion = 'parcial'
                    if oc.estado in ('en_espera_producto', 'pagado', 'anticipo_pagado'):
                        oc.estado = 'recibida_parcial'
        # Auto-incrementar stock de materia prima si aplica
        cant_recibida = obj.cantidad if tipo == 'total' else float(request.form.get('cantidad_recibida') or 0)
        if cant_recibida > 0 and obj.materia_id:
            try:
                mp = db.session.get(MateriaPrima, obj.materia_id)
                if mp:
                    stock_antes = float(mp.stock_disponible or 0)
                    mp.stock_disponible = stock_antes + cant_recibida
                    _registrar_movimiento(
                        materia_prima_id=mp.id, tipo='ingreso', cantidad=cant_recibida,
                        stock_anterior=stock_antes, stock_posterior=mp.stock_disponible,
                        referencia=f'Recepcion OC {obj.orden_compra.numero if obj.orden_compra else "manual"}',
                        usuario_id=current_user.id)
                    # Crear lote de trazabilidad
                    lote = LoteMateriaPrima(
                        materia_prima_id=mp.id,
                        compra_id=obj.id,
                        nro_factura=obj.nro_factura,
                        proveedor=obj.proveedor or '',
                        fecha_compra=obj.fecha,
                        cantidad_inicial=cant_recibida,
                        cantidad_disponible=cant_recibida,
                        costo_unitario=obj.precio_unitario or 0
                    )
                    db.session.add(lote)
            except Exception as ex:
                logging.warning(f'compra_recibir: auto-stock error: {ex}')

        # Actualizar score del proveedor
        if obj.proveedor_id:
            _actualizar_score_proveedor(obj.proveedor_id)

        db.session.commit()
        flash(f'Recepcion de "{obj.nombre_item}" registrada. Stock actualizado.', 'success')
        return redirect(url_for('compras'))


    # ── compra_problema_calidad (/produccion/compras/<int:id>/problema-calidad)
    @app.route('/produccion/compras/<int:id>/problema-calidad', methods=['POST'])
    @login_required
    def compra_problema_calidad(id):
        """Reportar problema de calidad en material recibido."""
        obj = CompraMateria.query.get_or_404(id)
        descripcion = request.form.get('descripcion_problema', '')
        requiere_cambio = request.form.get('requiere_cambio') == '1'

        obj.estado_recepcion = 'parcial'

        # Marcar problema en OC
        oc = None
        if obj.orden_compra_id:
            oc = db.session.get(OrdenCompra, obj.orden_compra_id)
            if oc:
                oc.tiene_problema_calidad = True
                if oc.estado in ('en_espera_producto', 'pagado', 'anticipo_pagado'):
                    oc.estado = 'recibida_parcial'
                oc.estado_recepcion = 'parcial'

        # Crear ticket para el creador de la OC (contactar proveedor)
        # Evitar duplicados si el boton se presiona varias veces
        if oc:
            titulo_t1 = f'Problema de calidad MP — {obj.nombre_item} (OC {oc.numero})'
            existente_t1 = Tarea.query.filter(
                Tarea.titulo == titulo_t1,
                Tarea.tarea_tipo == 'problema_calidad',
                Tarea.estado == 'pendiente'
            ).first()
            if not existente_t1:
                t1 = Tarea(
                    titulo=titulo_t1,
                    descripcion=f'Se reporto un problema de calidad con "{obj.nombre_item}" de la OC {oc.numero}.\n\n'
                                f'Problema: {descripcion}\n\n'
                                f'Accion requerida: Contactar al proveedor para resolver el problema.',
                    estado='pendiente', prioridad='alta',
                    asignado_a=oc.creado_por or current_user.id,
                    creado_por=current_user.id,
                    orden_compra_id=oc.id,
                    categoria='calidad',
                    tarea_tipo='problema_calidad',
                    fecha_vencimiento=(datetime.utcnow() + timedelta(days=2)).date()
                )
                db.session.add(t1)

            # Si hay venta vinculada, crear ticket para el vendedor
            if oc.venta_origen_id:
                venta = db.session.get(Venta, oc.venta_origen_id)
                if venta:
                    titulo_t2 = f'Retraso por calidad MP — Venta {venta.numero}'
                    existente_t2 = Tarea.query.filter(
                        Tarea.titulo == titulo_t2,
                        Tarea.tarea_tipo == 'retraso_calidad',
                        Tarea.estado == 'pendiente'
                    ).first()
                    if not existente_t2:
                        t2 = Tarea(
                            titulo=titulo_t2,
                            descripcion=f'La materia prima "{obj.nombre_item}" de la OC {oc.numero} tiene un problema de calidad.\n\n'
                                        f'Problema: {descripcion}\n\n'
                                        f'Esto puede afectar la fecha de entrega de la venta {venta.numero}. '
                                        f'Contactar al cliente para informar del posible retraso.',
                            estado='pendiente', prioridad='alta',
                            asignado_a=venta.creado_por or current_user.id,
                            creado_por=current_user.id,
                            venta_id=venta.id,
                            orden_compra_id=oc.id,
                            categoria='calidad',
                            tarea_tipo='retraso_calidad',
                            fecha_vencimiento=(datetime.utcnow() + timedelta(days=1)).date()
                        )
                        db.session.add(t2)

                    if requiere_cambio:
                        # Marcar en la venta que hay un problema
                        # Reabrir la OC para que se solicite reemplazo
                        oc.estado = 'en_espera_producto'  # reabrir

        # Actualizar score proveedor (penalizar calidad)
        if oc and oc.proveedor_id:
            _actualizar_score_proveedor(oc.proveedor_id)

        db.session.commit()
        msg = f'Problema de calidad reportado para "{obj.nombre_item}". Tickets creados.'
        if requiere_cambio:
            msg += ' La OC fue reabierta para solicitar reemplazo.'
        flash(msg, 'warning')
        return redirect(url_for('compras'))


    # ── compra_eliminar (/produccion/compras/<int:id>/eliminar)
    @app.route('/produccion/compras/<int:id>/eliminar', methods=['POST'])
    @login_required
    def compra_eliminar(id):
        obj=CompraMateria.query.get_or_404(id)
        # Buscar y eliminar GastoOperativo y AsientoContable vinculados
        gastos_vinc = GastoOperativo.query.filter_by(
            tipo='compra_produccion', fecha=obj.fecha
        ).filter(GastoOperativo.descripcion.contains(obj.nombre_item[:30])).all()
        for g in gastos_vinc:
            AsientoContable.query.filter_by(gasto_id=g.id).delete()
            db.session.delete(g)
        db.session.delete(obj); db.session.commit()
        flash('Compra, gasto y asiento contable eliminados.','info'); return redirect(url_for('compras'))


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
        page = request.args.get('page', 1, type=int)
        per_page = 25
        pagination = RecetaProducto.query.filter_by(activo=True).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
        # Recalcular costos y precios para cada receta (siempre actualizado)
        costos = {}
        for r in items:
            costos[r.id] = _calcular_costo_receta(r.producto_id)
        try:
            db.session.commit()  # Persistir precios actualizados
        except Exception:
            db.session.rollback()
        return render_template('produccion/recetas.html', recetas=items, costos=costos,
                              page=page, total_pages=pagination.pages, total_items=pagination.total)

    @app.route('/api/receta/<int:producto_id>/costo')
    @login_required
    def api_receta_costo(producto_id):
        """API: calcula costo de producción y precio mínimo de venta."""
        costo = _calcular_costo_receta(producto_id)
        precio = _precio_minimo_venta(producto_id, 1)
        return jsonify({**costo, 'precio': precio})

    @app.route('/api/producto/<int:producto_id>/historial-precios')
    @login_required
    def api_historial_precios(producto_id):
        """API: historial de cambios de precio de un producto."""
        from models import HistorialPrecio
        items = HistorialPrecio.query.filter_by(producto_id=producto_id)\
            .order_by(HistorialPrecio.creado_en.desc()).limit(50).all()
        return jsonify([{
            'fecha': h.creado_en.strftime('%Y-%m-%d %H:%M') if h.creado_en else '',
            'precio_anterior': h.precio_anterior,
            'precio_nuevo': h.precio_nuevo,
            'origen': h.origen or '',
            'usuario': h.usuario.nombre if h.usuario else ''
        } for h in items])

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

    # ── materia_nueva_rapida (/produccion/materias/nueva-rapida) — AJAX
    @app.route('/produccion/materias/nueva-rapida', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def materia_nueva_rapida():
        """Crea una MateriaPrima con stock=0 y la devuelve como JSON."""
        nombre = (request.json or {}).get('nombre','').strip()
        unidad = (request.json or {}).get('unidad','unidades').strip() or 'unidades'
        if not nombre:
            return jsonify({'error': 'Nombre requerido'}), 400
        exist = MateriaPrima.query.filter(
            db.func.lower(MateriaPrima.nombre) == nombre.lower(),
            MateriaPrima.activo == True
        ).first()
        if exist:
            return jsonify({'id': exist.id, 'nombre': exist.nombre,
                            'unidad': exist.unidad, 'existente': True})
        mp = MateriaPrima(
            nombre=nombre, unidad=unidad,
            stock_disponible=0, stock_reservado=0,
            stock_minimo=0, costo_unitario=0,
            activo=True
        )
        db.session.add(mp); db.session.flush()
        # Auto-crear cotización pendiente en módulo Compras
        db.session.add(CotizacionProveedor(
            nombre_producto=nombre,
            tipo_cotizacion='granel',
            tipo_producto_servicio='materia prima',
            unidad=unidad,
            estado='en_revision',
            materia_prima_id=mp.id,
            precio_unitario=0,
            notas='Requiere cotización de proveedor.',
            creado_por=current_user.id
        ))
        db.session.commit()
        return jsonify({'id': mp.id, 'nombre': mp.nombre,
                        'unidad': mp.unidad, 'existente': False})


    # ── receta_nueva (/produccion/recetas/nueva)
    @app.route('/produccion/recetas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_nueva():
      try:
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        nombres_con_cot = {
            cp.nombre_producto.lower()
            for cp in CotizacionProveedor.query.filter(
                CotizacionProveedor.estado.in_(['vigente','en_revision'])
            ).all() if cp.nombre_producto
        }
        sin_cot_ids = {m.id for m in materias if m.nombre.lower() not in nombres_con_cot}
        materias_json = [
            {'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad,
             'sin_cot': m.id in sin_cot_ids}
            for m in materias
        ]
        if request.method == 'POST':
            prod_id_raw = request.form.get('producto_id','').strip()
            # Soporte free-text: si se seleccionó "__nuevo__", crear el producto
            if prod_id_raw == '__nuevo__':
                nuevo_nombre = request.form.get('nuevo_producto_nombre','').strip()
                if not nuevo_nombre:
                    flash('Escribe el nombre del nuevo producto.','danger')
                    return render_template('produccion/receta_form.html', obj=None, productos=productos,
                                           materias=materias, materias_json=materias_json, titulo='Nueva Receta')
                # Buscar si ya existe con ese nombre (case insensitive)
                prod_exist = Producto.query.filter(
                    db.func.lower(Producto.nombre) == nuevo_nombre.lower()
                ).first()
                if prod_exist:
                    prod_id = prod_exist.id
                else:
                    nuevo_prod = Producto(nombre=nuevo_nombre, activo=True,
                                          precio=0, stock=0)
                    db.session.add(nuevo_prod); db.session.flush()
                    prod_id = nuevo_prod.id
                    flash(f'Producto "{nuevo_nombre}" creado automáticamente.','info')
            else:
                try:
                    prod_id = int(prod_id_raw)
                except (ValueError, TypeError):
                    flash('Selecciona un producto válido.','danger')
                    return render_template('produccion/receta_form.html', obj=None, productos=productos,
                                           materias=materias, materias_json=materias_json, titulo='Nueva Receta')
            # ── Crear la receta (aplica tanto para producto nuevo como existente) ──
            r = RecetaProducto(
                producto_id=prod_id,
                unidades_produce=int(request.form.get('unidades_produce',1)),
                descripcion=request.form.get('descripcion','') or None
            )
            db.session.add(r); db.session.flush()
            ids   = request.form.getlist('materia_id[]')
            cants = request.form.getlist('cantidad[]')
            clasifs = request.form.getlist('clasificacion[]')
            rendimientos = request.form.getlist('rendimiento[]')
            for i, (mid, cant) in enumerate(zip(ids, cants)):
                if mid and cant:
                    clasif = clasifs[i] if i < len(clasifs) else 'materia_prima'
                    rend = float(rendimientos[i]) if i < len(rendimientos) and rendimientos[i] else 1
                    es_emp = clasif in ('empaque_primario', 'empaque_secundario')
                    db.session.add(RecetaItem(
                        receta_id=r.id,
                        materia_prima_id=int(mid),
                        cantidad_por_unidad=float(cant),
                        clasificacion=clasif,
                        es_empaque=es_emp,
                        rendimiento=rend if es_emp else 1
                    ))
            # Registrar ingredientes al producto y asegurarse que existen en el catálogo
            _registrar_ingredientes_en_cero(ids, prod_id)
            # Auto-generar SKU si el producto no tiene uno
            prod_obj = db.session.get(Producto, prod_id)
            if prod_obj and (not prod_obj.sku or prod_obj.sku in ('None', '')):
                from models import _generar_sku
                prod_obj.sku = _generar_sku(prod_obj.nombre)
            # Calcular costo y precio desde receta
            costo = _calcular_costo_receta(prod_id)
            r.costo_calculado = costo['costo_unitario']
            margen = float(request.form.get('margen_pct', 30) or 30)
            r.margen_pct = margen
            try:
                regla_iva = ReglaTributaria.query.filter_by(aplica_a='ventas', activo=True).first()
                iva_pct = float(regla_iva.porcentaje) if regla_iva else 19.0
            except Exception:
                iva_pct = 19.0
            precio_sin_iva = costo['costo_unitario'] * (1 + margen / 100)
            r.precio_venta_sugerido = round(precio_sin_iva * (1 + iva_pct / 100), 2)
            if prod_obj and prod_obj.precio != r.precio_venta_sugerido:
                from models import HistorialPrecio
                db.session.add(HistorialPrecio(
                    producto_id=prod_obj.id,
                    precio_anterior=prod_obj.precio or 0,
                    precio_nuevo=r.precio_venta_sugerido,
                    origen='receta',
                    usuario_id=current_user.id
                ))
                prod_obj.precio = r.precio_venta_sugerido
            # ── Auto-crear cotizaciones para TODOS los ingredientes que no tengan una ──
            cots_creadas = 0
            for mid in ids:
                if not mid:
                    continue
                mp = db.session.get(MateriaPrima, int(mid))
                if not mp:
                    continue
                # Verificar si ya tiene CUALQUIER cotización (vigente, en_revision, o vencida)
                tiene_cot = CotizacionProveedor.query.filter(
                    db.or_(
                        CotizacionProveedor.materia_prima_id == mp.id,
                        db.func.lower(CotizacionProveedor.nombre_producto) == mp.nombre.lower()
                    )
                ).first()
                if not tiene_cot:
                    # Nombre: ingrediente — producto
                    nombre_cot = f'{mp.nombre} — {prod_obj.nombre}' if prod_obj else mp.nombre
                    db.session.add(CotizacionProveedor(
                        nombre_producto=nombre_cot,
                        tipo_cotizacion='granel',
                        tipo_producto_servicio='materia prima',
                        unidad=mp.unidad,
                        estado='en_revision',
                        materia_prima_id=mp.id,
                        precio_unitario=mp.costo_unitario or 0,
                        notas=f'Requiere cotización de proveedor.',
                        creado_por=current_user.id
                    ))
                    cots_creadas += 1
            db.session.commit()
            msg = f'Receta creada. SKU: {prod_obj.sku if prod_obj else "—"}. Costo: ${costo["costo_unitario"]:,.0f}/und. Precio sugerido: ${r.precio_venta_sugerido:,.0f}'
            if cots_creadas:
                msg += f' · {cots_creadas} cotización(es) pendiente(s) creada(s) en Compras.'
            flash(msg, 'success')
            return redirect(url_for('recetas'))
        return render_template('produccion/receta_form.html', obj=None, productos=productos,
                               materias=materias, materias_json=materias_json,
                               sin_cot_ids=sin_cot_ids, titulo='Nueva Receta')
      except Exception as e:
        db.session.rollback()
        logging.exception(f'Error en receta_nueva: {e}')
        flash(f'Error: {type(e).__name__}: {e}', 'danger')
        return redirect(url_for('recetas'))
    

    # ── receta_editar (/produccion/recetas/<int:id>/editar)
    @app.route('/produccion/recetas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_editar(id):
        obj = RecetaProducto.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        nombres_con_cot = {
            cp.nombre_producto.lower()
            for cp in CotizacionProveedor.query.filter(
                CotizacionProveedor.estado.in_(['vigente','en_revision'])
            ).all() if cp.nombre_producto
        }
        sin_cot_ids = {m.id for m in materias if m.nombre.lower() not in nombres_con_cot}
        materias_json = [
            {'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad,
             'sin_cot': m.id in sin_cot_ids}
            for m in materias
        ]
        if request.method == 'POST':
            try:
                prod_id = int(request.form['producto_id'])
                obj.producto_id=prod_id
                obj.unidades_produce=int(request.form.get('unidades_produce',1))
                obj.descripcion=request.form.get('descripcion','') or None
                # Guardar items de empaque que podrían no estar en el form
                empaques_preservados = []
                for item in obj.items:
                    if item.es_empaque or item.clasificacion == 'empaque_secundario':
                        empaques_preservados.append({
                            'materia_prima_id': item.materia_prima_id,
                            'cantidad_por_unidad': item.cantidad_por_unidad,
                            'es_empaque': item.es_empaque,
                            'clasificacion': item.clasificacion
                        })
                for item in obj.items: db.session.delete(item)
                db.session.flush()
                ids   = request.form.getlist('materia_id[]')
                cants = request.form.getlist('cantidad[]')
                clasifs = request.form.getlist('clasificacion[]')
                # Restaurar empaques que no vinieron en el form
                ids_enviados = set(int(x) for x in ids if x)
                for emp in empaques_preservados:
                    if emp['materia_prima_id'] not in ids_enviados:
                        db.session.add(RecetaItem(
                            receta_id=obj.id,
                            materia_prima_id=emp['materia_prima_id'],
                            cantidad_por_unidad=emp['cantidad_por_unidad'],
                            es_empaque=emp['es_empaque'],
                            clasificacion=emp['clasificacion']
                        ))
                rendimientos = request.form.getlist('rendimiento[]')
                for i, (mid, cant) in enumerate(zip(ids, cants)):
                    if mid and cant:
                        clasif = clasifs[i] if i < len(clasifs) else 'materia_prima'
                        rend = float(rendimientos[i]) if i < len(rendimientos) and rendimientos[i] else 1
                        es_emp = clasif in ('empaque_primario', 'empaque_secundario')
                        db.session.add(RecetaItem(
                            receta_id=obj.id,
                            materia_prima_id=int(mid),
                            cantidad_por_unidad=float(cant),
                            clasificacion=clasif,
                            es_empaque=es_emp,
                            rendimiento=rend if es_emp else 1
                        ))
                _registrar_ingredientes_en_cero(ids, prod_id)
                # Auto-generar SKU si falta
                prod_obj = db.session.get(Producto, prod_id)
                if prod_obj and not prod_obj.sku:
                    from models import _generar_sku
                    prod_obj.sku = _generar_sku(prod_obj.nombre)
                # Recalcular costo y precio
                costo = _calcular_costo_receta(prod_id)
                obj.costo_calculado = costo['costo_unitario']
                margen = float(request.form.get('margen_pct', obj.margen_pct or 30) or 30)
                obj.margen_pct = margen
                try:
                    regla_iva = ReglaTributaria.query.filter_by(aplica_a='ventas', activo=True).first()
                    iva_pct = float(regla_iva.porcentaje) if regla_iva else 19.0
                except Exception:
                    iva_pct = 19.0
                precio_sin_iva = costo['costo_unitario'] * (1 + margen / 100)
                obj.precio_venta_sugerido = round(precio_sin_iva * (1 + iva_pct / 100), 2)
                if prod_obj:
                    prod_obj.precio = obj.precio_venta_sugerido
                db.session.commit()
                flash(f'Receta actualizada. Costo: ${costo["costo_unitario"]:,.0f}. Precio: ${obj.precio_venta_sugerido:,.0f}','success')
                return redirect(url_for('recetas'))
            except Exception as e:
                db.session.rollback()
                logging.exception(f'Error editando receta: {e}')
                flash(f'Error al actualizar receta: {type(e).__name__}: {e}', 'danger')
                return render_template('produccion/receta_form.html', obj=obj, productos=productos,
                                       materias=materias, materias_json=materias_json,
                                       sin_cot_ids=sin_cot_ids, titulo='Editar Receta')
        # Pasar costo actual
        costo_actual = _calcular_costo_receta(obj.producto_id) if obj.producto_id else None
        return render_template('produccion/receta_form.html', obj=obj, productos=productos,
                               materias=materias, materias_json=materias_json,
                               sin_cot_ids=sin_cot_ids, titulo='Editar Receta',
                               costo_actual=costo_actual)
    

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
            try:
                validaciones[vid] = InventarioService.validar_materias_produccion(vid)
            except Exception as _ve:
                logging.warning(f'reservas: validar_materias_produccion({vid}) error: {_ve}')
                validaciones[vid] = {'ok': True, 'faltantes': [], 'proximos_vencer': []}

        ESTADOS_VALIDOS_PROD = {'anticipo_pagado', 'completado', 'pagado'}  # completado = legado
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

        # Bloque 7: prevent duplicate pending purchase tasks for the same materia prima
        titulo_buscar = f'Comprar%de {mp.nombre}'
        tarea_existente = Tarea.query.filter(
            Tarea.titulo.like(titulo_buscar),
            Tarea.tarea_tipo == 'comprar_materias',
            Tarea.estado == 'pendiente'
        ).first()
        if tarea_existente:
            flash(
                f'Ya existe una tarea pendiente de compra para {mp.nombre} (#{tarea_existente.id}). '
                f'Complétala antes de crear otra.',
                'warning'
            )
            return redirect(url_for('reservas'))

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
    
        db.session.commit()

        _crear_notificacion(
            usuario_id, 'tarea_asignada',
            f'Nueva tarea asignada: {t_compra.titulo}',
            f'Requiere comprar {cant_fmt or mp.nombre} para continuar producción.',
            url_for('tareas')
        )
        flash(f'Tarea de compra creada y asignada.', 'success')
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
                # Verificar stock mínimo
                from services.inventario import verificar_stock_minimo
                verificar_stock_minimo(m.id)
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

        # 1. Validar estado de la venta (completado = legado de nombre anterior)
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
        empleados = Empleado.query.filter_by(estado='activo').order_by(Empleado.apellido, Empleado.nombre).all()
        return render_template('produccion/ordenes.html',
                               pendientes=pendientes, completados=completados,
                               empleados=empleados)
    

    # ── ordenes_produccion_export_csv (/produccion/ordenes/export-csv)
    @app.route('/produccion/ordenes/export-csv')
    @login_required
    @requiere_modulo('produccion')
    def ordenes_produccion_export_csv():
        ordenes = OrdenProduccion.query.order_by(OrdenProduccion.creado_en.desc()).all()
        rows = []
        for o in ordenes:
            producto_nombre = o.producto.nombre if o.producto else ''
            venta_numero = o.venta.numero if o.venta else ''
            if o.fecha_inicio_real:
                fecha = o.fecha_inicio_real.strftime('%d/%m/%Y')
            elif o.creado_en:
                fecha = o.creado_en.strftime('%d/%m/%Y')
            else:
                fecha = ''
            rows.append([
                o.id,
                producto_nombre,
                o.cantidad_producir or 0,
                o.estado or '',
                venta_numero,
                fecha,
                o.numero_lote or '',
            ])
        return generar_csv_response(
            rows,
            ['ID', 'Producto', 'Cantidad', 'Estado', 'Venta', 'Fecha_Inicio', 'Lote'],
            filename='ordenes_produccion.csv'
        )

    # ── orden_completar (/produccion/ordenes/completar)
    @app.route('/produccion/ordenes/completar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def orden_completar():
        orden_id    = int(request.form.get('orden_id'))
        numero_lote = request.form.get('numero_lote','').strip()
        notas       = request.form.get('notas','')
        fv          = request.form.get('fecha_vencimiento')
        merma_val   = float(request.form.get('merma') or 0)
        merma_motivo = request.form.get('merma_motivo','').strip() or None

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
        orden.merma        = merma_val
        orden.merma_motivo = merma_motivo
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
                    OrdenCompra.venta_origen_id == o.venta_id,
                    OrdenCompra.estado.notin_(['cancelada'])
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


    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 7 — Automatización: Detención de órdenes de producción
    # ══════════════════════════════════════════════════════════════════════════

    # ── orden_detener (/produccion/ordenes/<int:id>/detener)
    @app.route('/produccion/ordenes/<int:id>/detener', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def orden_detener(id):
        """
        Detiene una orden de producción:
        1. Cambia estado a 'detenida'
        2. Crea un evento automático (si no existe)
        3. Crea una tarea única de reactivación (si no existe)
        4. Notifica al usuario actual
        """
        orden = OrdenProduccion.query.get_or_404(id)
        motivo = request.form.get('motivo', 'Sin especificar').strip()

        if not motivo:
            motivo = 'Sin especificar'

        orden.estado = 'detenida'

        # Devolver materias primas reservadas para esta orden (venta+producto)
        if orden.venta_id:
            reservas = ReservaProduccion.query.filter(
                ReservaProduccion.venta_id == orden.venta_id,
                ReservaProduccion.producto_id == orden.producto_id,
                ReservaProduccion.estado == 'reservado'
            ).all()
            for r in reservas:
                mp = r.materia
                if not mp:
                    continue
                notas_r = r.notas or ''
                if 'FALTANTE' in notas_r or 'Sin stock' in notas_r:
                    r.estado = 'cancelado'
                    continue
                mp.stock_disponible = float(mp.stock_disponible or 0) + r.cantidad
                mp.stock_reservado  = max(0.0, float(mp.stock_reservado or 0) - r.cantidad)
                r.estado = 'cancelado'

        # Crear evento automático con detalles
        from routes.tareas import _crear_evento_automatico
        _crear_evento_automatico(
            titulo=f'Producción detenida — {orden.producto.nombre}',
            descripcion=f'Motivo: {motivo}\nVenta: #{orden.venta_id}\nOrden: #{orden.id}',
            tipo='alerta',
            fecha=date_type.today(),
            creado_por=current_user.id
        )

        # Crear tarea única de reactivación si no existe
        from routes.tareas import _crear_tarea_unica
        titulo_tarea = f'Reactivar producción {orden.producto.nombre}'
        t, creada = _crear_tarea_unica(
            titulo_patron=titulo_tarea,
            tarea_tipo='produccion_detenida',
            descripcion=(
                f'Orden de producción detenida y requiere reactivación.\n'
                f'Producto: {orden.producto.nombre}\n'
                f'Cantidad: {orden.cantidad_producir:.0f} unidades\n'
                f'Motivo: {motivo}\n'
                f'Venta: #{orden.venta_id}'
            ),
            prioridad='alta',
            creado_por=current_user.id,
            entidad_id=orden.id,
            entidad_tipo='orden_produccion'
        )

        if creada and t:
            # Asignar tarea al usuario actual
            db.session.add(TareaAsignado(tarea_id=t.id, usuario_id=current_user.id))
            # Notificar
            _crear_notificacion(
                current_user.id, 'alerta',
                f'Tarea creada: Reactivar producción {orden.producto.nombre}',
                f'Orden #{orden.id} fue detenida. Motivo: {motivo}',
                url_for('tareas')
            )

        db.session.commit()
        flash(f'Orden #{orden.id} detenida. Evento y tarea de reactivación creados.', 'warning')
        return redirect(url_for('ordenes_produccion'))


    # ── orden_asignar_operario (/produccion/ordenes/<id>/operario)
    @app.route('/produccion/ordenes/<int:id>/operario', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def orden_asignar_operario(id):
        orden = OrdenProduccion.query.get_or_404(id)
        operario_id_raw = request.form.get('operario_id')
        orden.operario_id = int(operario_id_raw) if operario_id_raw else None
        db.session.commit()
        flash('Operario asignado.', 'success')
        return redirect(url_for('ordenes_produccion'))

