# routes/produccion.py
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

    @app.route('/produccion/recetas')
    @login_required
    @requiere_modulo('produccion')
    def recetas():
        items = RecetaProducto.query.filter_by(activo=True).all()
        return render_template('produccion/recetas.html', recetas=items)

    @app.route('/produccion/recetas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_nueva():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        materias_json = [{'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad} for m in materias]
        if request.method == 'POST':
            r = RecetaProducto(
                producto_id=int(request.form['producto_id']),
                unidades_produce=int(request.form.get('unidades_produce',1)),
                descripcion=request.form.get('descripcion','') or None
            )
            db.session.add(r); db.session.flush()
            ids = request.form.getlist('materia_id[]')
            cants = request.form.getlist('cantidad[]')
            for mid, cant in zip(ids, cants):
                if mid and cant:
                    db.session.add(RecetaItem(
                        receta_id=r.id,
                        materia_prima_id=int(mid),
                        cantidad_por_unidad=float(cant)
                    ))
            db.session.commit()
            flash('Receta creada.','success'); return redirect(url_for('recetas'))
        return render_template('produccion/receta_form.html', obj=None, productos=productos,
                               materias=materias, materias_json=materias_json, titulo='Nueva Receta')

    @app.route('/produccion/recetas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_editar(id):
        obj = RecetaProducto.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
        materias_json = [{'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad} for m in materias]
        if request.method == 'POST':
            obj.producto_id=int(request.form['producto_id'])
            obj.unidades_produce=int(request.form.get('unidades_produce',1))
            obj.descripcion=request.form.get('descripcion','') or None
            # Rebuild items
            for item in obj.items: db.session.delete(item)
            db.session.flush()
            ids = request.form.getlist('materia_id[]')
            cants = request.form.getlist('cantidad[]')
            for mid, cant in zip(ids, cants):
                if mid and cant:
                    db.session.add(RecetaItem(
                        receta_id=obj.id,
                        materia_prima_id=int(mid),
                        cantidad_por_unidad=float(cant)
                    ))
            db.session.commit()
            flash('Receta actualizada.','success'); return redirect(url_for('recetas'))
        return render_template('produccion/receta_form.html', obj=obj, productos=productos,
                               materias=materias, materias_json=materias_json, titulo='Editar Receta')

    @app.route('/produccion/recetas/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def receta_eliminar(id):
        obj = RecetaProducto.query.get_or_404(id); obj.activo=False; db.session.commit()
        flash('Receta eliminada.','info'); return redirect(url_for('recetas'))

    @app.route('/produccion/reservas')
    @login_required
    @requiere_modulo('produccion')
    def reservas():
        items = ReservaProduccion.query.order_by(ReservaProduccion.creado_en.desc()).all()
        usuarios = User.query.filter_by(activo=True).order_by(User.nombre).all()
        return render_template('produccion/reservas.html', reservas=items, usuarios=usuarios)

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

    @app.route('/produccion/reservas/venta/<int:venta_id>/iniciar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def reserva_iniciar_produccion(venta_id):
        """Marca todas las órdenes de producción de una venta como en_produccion."""
        ordenes = OrdenProduccion.query.filter(
            OrdenProduccion.venta_id == venta_id,
            OrdenProduccion.estado.in_(['pendiente_materiales','en_produccion'])
        ).all()
        for o in ordenes:
            o.estado = 'en_produccion'
        db.session.commit()
        flash('Producción iniciada. Las órdenes están en progreso.','success')
        return redirect(url_for('reservas'))

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

    @app.route('/produccion/ordenes/completar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def orden_completar():
        orden_id  = int(request.form.get('orden_id'))
        numero_lote = request.form.get('numero_lote','').strip()
        notas       = request.form.get('notas','')
        fv          = request.form.get('fecha_vencimiento')

        orden = OrdenProduccion.query.get_or_404(orden_id)
        prod  = orden.producto

        # Añadir al stock
        prod.stock += int(orden.cantidad_producir)

        # Registrar lote
        lote = LoteProducto(
            producto_id=prod.id,
            numero_lote=numero_lote or f'OP-{orden.id}',
            fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
            unidades_producidas=orden.cantidad_producir,
            unidades_restantes=orden.cantidad_producir,
            notas=notas or f'Orden producción #{orden.id}',
            creado_por=current_user.id
        )
        db.session.add(lote)

        orden.estado = 'completado'
        orden.numero_lote = numero_lote or f'OP-{orden.id}'
        orden.completado_en = datetime.utcnow()
        db.session.commit()

        # Notificar admins
        admins = User.query.filter_by(rol='admin', activo=True).all()
        for adm in admins:
            _crear_notificacion(
                adm.id, 'info',
                f'✅ Producción completada: {prod.nombre}',
                f'{orden.cantidad_producir:.0f} unidades movidas al inventario. Lote: {orden.numero_lote}',
                url_for('inventario')
            )
        flash(f'Producción completada. {orden.cantidad_producir:.0f} unidades agregadas al inventario.','success')
        return redirect(url_for('ordenes_produccion'))

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

    @app.route('/produccion/granel')
    @login_required
    def granel():
        estado_f=request.args.get('estado','')
        q=CotizacionGranel.query
        if estado_f: q=q.filter_by(estado=estado_f)
        return render_template('produccion/granel.html', items=q.order_by(CotizacionGranel.creado_en.desc()).all(),
                               estado_f=estado_f)

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

    @app.route('/produccion/granel/<int:id>/eliminar', methods=['POST'])
    @login_required
    def granel_eliminar(id):
        obj=CotizacionGranel.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Cotización eliminada.','info'); return redirect(url_for('granel'))

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
        return render_template('produccion/compras.html', items=q.order_by(CompraMateria.fecha.desc()).all(),
                               busqueda=busqueda, total_general=total_general, total_mes=total_mes)

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

    @app.route('/produccion/compras/<int:id>/eliminar', methods=['POST'])
    @login_required
    def compra_eliminar(id):
        obj=CompraMateria.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Compra eliminada.','info'); return redirect(url_for('compras'))
