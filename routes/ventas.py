# routes/ventas.py — reconstruido desde v27 con CRUD completo
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
    def _prods_json():
        # Debe ser lista (array) — el template usa PRODS.map(...)
        return [
            {
                'id':     p.id,
                'nombre': p.nombre,
                'sku':    p.sku or '',
                'precio': float(p.precio or 0),
                'stock':  float(p.stock or 0)
            }
            for p in Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        ]

    def _servicios_json():
        """Retorna servicios activos como JSON para el formulario de cotizaciones."""
        return [
            {
                'id': s.id,
                'nombre': s.nombre,
                'descripcion': s.descripcion or '',
                'precio_venta': float(s.precio_venta or 0),
                'unidad': s.unidad or 'unidades'
            }
            for s in Servicio.query.filter_by(activo=True).order_by(Servicio.nombre).all()
        ]

    def _save_items(venta_obj):
        VentaProducto.query.filter_by(venta_id=venta_obj.id).delete()
        pids    = request.form.getlist('prod_id[]')
        cants   = request.form.getlist('prod_cant[]')
        precios = request.form.getlist('prod_precio[]')
        for i, pid in enumerate(pids):
            if not pid: continue
            cant   = float(cants[i])   if i < len(cants)   else 1
            precio = float(precios[i]) if i < len(precios) else 0
            prod   = db.session.get(Producto, int(pid))
            db.session.add(VentaProducto(
                venta_id=venta_obj.id, producto_id=int(pid),
                nombre_prod=prod.nombre if prod else '',
                cantidad=cant, precio_unit=precio, subtotal=cant*precio))

    def _descontar_stock_venta(venta):
        from services.inventario import InventarioService
        InventarioService.descontar_stock_venta(venta)

    def _get_lotes_fifo(materia_prima_id):
        """
        Retorna los lotes disponibles de una materia prima, ordenados FIFO:
        1) Primero los que tienen fecha de vencimiento (más próximo a vencer primero)
        2) Luego los sin fecha de vencimiento
        Excluye lotes ya vencidos.
        """
        from models import LoteMateriaPrima
        from datetime import date
        hoy = date.today()
        lotes_con_fecha = LoteMateriaPrima.query.filter(
            LoteMateriaPrima.materia_prima_id == materia_prima_id,
            LoteMateriaPrima.cantidad_disponible > 0,
            LoteMateriaPrima.fecha_vencimiento.isnot(None),
            LoteMateriaPrima.fecha_vencimiento > hoy
        ).order_by(LoteMateriaPrima.fecha_vencimiento.asc()).all()
        lotes_sin_fecha = LoteMateriaPrima.query.filter(
            LoteMateriaPrima.materia_prima_id == materia_prima_id,
            LoteMateriaPrima.cantidad_disponible > 0,
            LoteMateriaPrima.fecha_vencimiento.is_(None)
        ).order_by(LoteMateriaPrima.creado_en.asc()).all()
        return lotes_con_fecha + lotes_sin_fecha

    def _procesar_venta_produccion(venta):
        """
        Crea órdenes de producción y reservas de materias primas por lote (FIFO por vencimiento).
        - Reservas se crean SIN deducir stock todavía (la deducción ocurre al 'Iniciar producción').
        - Estado de la orden: pendiente_materiales si falta algún insumo, en_produccion si todo está.
        - Detecta lotes próximos a vencer (< 90 días) y los marca en las notas de la reserva.
        """
        from datetime import date, timedelta
        UMBRAL_CADUCIDAD_DIAS = 90
        hoy = date.today()
        try:
            for item in venta.items:
                if not item.producto_id:
                    continue
                prod = db.session.get(Producto, item.producto_id)
                if not prod:
                    continue
                cant_requerida = int(round(float(item.cantidad or 0)))
                cant_en_stock  = min(int(prod.stock or 0), cant_requerida)
                cant_producir  = max(0, cant_requerida - cant_en_stock)
                if cant_producir <= 0:
                    continue
                existente = OrdenProduccion.query.filter(
                    OrdenProduccion.venta_id == venta.id,
                    OrdenProduccion.producto_id == prod.id,
                    OrdenProduccion.estado != 'completado'
                ).first()
                if existente:
                    continue

                receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
                hay_faltante = False

                if receta and receta.items:
                    unidades_por_batch = float(receta.unidades_produce or 1)
                    factor = cant_producir / unidades_por_batch

                    for ri in receta.items:
                        mp = ri.materia
                        cant_reservar_total = round(ri.cantidad_por_unidad * factor, 4)
                        if cant_reservar_total <= 0:
                            continue

                        # Verificar si ya existe reserva para este insumo/venta/producto
                        reserva_exist = ReservaProduccion.query.filter(
                            ReservaProduccion.venta_id == venta.id,
                            ReservaProduccion.materia_prima_id == mp.id,
                            ReservaProduccion.producto_id == prod.id,
                            ReservaProduccion.estado == 'reservado'
                        ).first()
                        if reserva_exist:
                            continue

                        # Asignar lotes FIFO
                        lotes = _get_lotes_fifo(mp.id)
                        stock_real = float(mp.stock_disponible or 0)
                        # Faltante se basa en el stock real (no solo en lotes registrados)
                        if stock_real < cant_reservar_total:
                            hay_faltante = True

                        # Crear una reserva por lote (o una sin lote si hay stock sin lote registrado)
                        restante = cant_reservar_total
                        if lotes:
                            for lote in lotes:
                                if restante <= 0:
                                    break
                                desde_este = min(lote.cantidad_disponible, restante)
                                prox_venc = (lote.fecha_vencimiento and
                                             lote.fecha_vencimiento <= hoy + timedelta(days=UMBRAL_CADUCIDAD_DIAS))
                                nota_lote = f'Lote {lote.numero_lote or lote.id}'
                                if lote.nro_factura:
                                    nota_lote += f' Fac:{lote.nro_factura}'
                                if lote.fecha_vencimiento:
                                    nota_lote += f' Vence:{lote.fecha_vencimiento.strftime("%d/%m/%Y")}'
                                if prox_venc:
                                    nota_lote += ' ⚠️PRÓX.VENCER'
                                db.session.add(ReservaProduccion(
                                    materia_prima_id=mp.id,
                                    cantidad=round(desde_este, 4),
                                    estado='reservado',
                                    producto_id=prod.id,
                                    venta_id=venta.id,
                                    lote_materia_prima_id=lote.id,
                                    notas=nota_lote,
                                    creado_por=current_user.id
                                ))
                                restante -= desde_este
                            # Si queda restante: verificar si hay stock sin lote
                            if restante > 0.001:
                                total_en_lotes = sum(l.cantidad_disponible for l in lotes)
                                stock_sin_lote = stock_real - total_en_lotes
                                if stock_sin_lote >= restante:
                                    # Hay stock real no asociado a lotes — reservar igual
                                    db.session.add(ReservaProduccion(
                                        materia_prima_id=mp.id,
                                        cantidad=round(restante, 4),
                                        estado='reservado',
                                        producto_id=prod.id,
                                        venta_id=venta.id,
                                        lote_materia_prima_id=None,
                                        notas='Sin lote registrado — verificar stock físico',
                                        creado_por=current_user.id
                                    ))
                                else:
                                    db.session.add(ReservaProduccion(
                                        materia_prima_id=mp.id,
                                        cantidad=round(restante, 4),
                                        estado='reservado',
                                        producto_id=prod.id,
                                        venta_id=venta.id,
                                        lote_materia_prima_id=None,
                                        notas='⚠️ FALTANTE — requiere compra',
                                        creado_por=current_user.id
                                    ))
                        else:
                            # Sin lotes registrados — usar stock_disponible directamente
                            if stock_real >= cant_reservar_total:
                                db.session.add(ReservaProduccion(
                                    materia_prima_id=mp.id,
                                    cantidad=cant_reservar_total,
                                    estado='reservado',
                                    producto_id=prod.id,
                                    venta_id=venta.id,
                                    lote_materia_prima_id=None,
                                    notas='Sin lote registrado — verificar stock físico',
                                    creado_por=current_user.id
                                ))
                            else:
                                db.session.add(ReservaProduccion(
                                    materia_prima_id=mp.id,
                                    cantidad=cant_reservar_total,
                                    estado='reservado',
                                    producto_id=prod.id,
                                    venta_id=venta.id,
                                    lote_materia_prima_id=None,
                                    notas='⚠️ Sin stock — requiere compra',
                                    creado_por=current_user.id
                                ))

                estado_orden = 'pendiente_materiales' if hay_faltante else 'en_produccion'
                db.session.add(OrdenProduccion(
                    venta_id=venta.id, producto_id=prod.id,
                    cantidad_total=cant_requerida, cantidad_stock=cant_en_stock,
                    cantidad_producir=cant_producir, estado=estado_orden,
                    notas=f'Venta: {venta.titulo or venta.numero} — {prod.nombre} x{cant_requerida:.0f}',
                    creado_por=current_user.id
                ))
        except Exception as ex:
            logging.warning(f'_procesar_venta_produccion error: {ex}')

    def _marcar_vencidas():
        """Marca cotizaciones vencidas automáticamente al listar."""
        hoy = date_type.today()
        vencidas = Cotizacion.query.filter(
            Cotizacion.fecha_validez < hoy,
            Cotizacion.estado.in_(['borrador', 'enviada'])
        ).all()
        for c in vencidas:
            c.estado = 'vencida'
        if vencidas:
            db.session.commit()

    # ── ventas (/ventas)
    @app.route('/ventas')
    @login_required
    def ventas():
        from datetime import date, timedelta
        estado_f = request.args.get('estado','')
        q = Venta.query
        if estado_f:
            q = q.filter_by(estado=estado_f)
        items = q.order_by(Venta.creado_en.desc()).all()

        # Alertas internas: materias primas próximas a vencer (< 90 días) con stock > 0
        hoy = date.today()
        try:
            from models import LoteMateriaPrima
            proximas_vencer = LoteMateriaPrima.query.filter(
                LoteMateriaPrima.fecha_vencimiento.isnot(None),
                LoteMateriaPrima.fecha_vencimiento <= hoy + timedelta(days=90),
                LoteMateriaPrima.fecha_vencimiento >= hoy,
                LoteMateriaPrima.cantidad_disponible > 0
            ).order_by(LoteMateriaPrima.fecha_vencimiento.asc()).all()
        except Exception:
            proximas_vencer = []

        return render_template('ventas/index.html', items=items, estado_f=estado_f,
                               proximas_vencer=proximas_vencer, today_date=hoy)


    # helper: get configured IVA rate (%)
    def _iva_rate():
        try:
            regla = ReglaTributaria.query.filter_by(aplica_a='ventas', activo=True).first()
            return float(regla.porcentaje) if regla else 19.0
        except Exception:
            return 19.0

    # ── venta_nueva (/ventas/nueva)
    @app.route('/ventas/nueva', methods=['GET','POST'])
    @login_required
    def venta_nueva():
        cl = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        iva_pct = _iva_rate()
        if request.method == 'POST':
            fa = request.form.get('fecha_anticipo')
            fe = request.form.get('fecha_entrega_est')
            subtotal = float(request.form.get('subtotal_calc') or 0)
            iva_monto = round(subtotal * iva_pct / 100.0, 2)
            total = subtotal + iva_monto
            v = Venta(titulo=request.form['titulo'],
                cliente_id=request.form.get('cliente_id') or None,
                subtotal=subtotal,
                iva=iva_monto,
                total=total,
                porcentaje_anticipo=float(request.form.get('porcentaje_anticipo') or 0),
                monto_anticipo=float(request.form.get('monto_anticipo') or 0),
                saldo=float(request.form.get('saldo') or 0),
                estado=request.form.get('estado','prospecto'),
                fecha_anticipo=datetime.strptime(fa,'%Y-%m-%d').date() if fa else None,
                dias_entrega=int(request.form.get('dias_entrega') or 30),
                fecha_entrega_est=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None,
                notas=request.form.get('notas',''), creado_por=current_user.id)
            db.session.add(v); db.session.flush()
            # Generar numero único VNT-YYYY-NNN
            hoy = datetime.utcnow().date()
            ultimo_vnt = Venta.query.filter(
                Venta.numero.like(f'VNT-{hoy.year}-%')
            ).order_by(Venta.id.desc()).first()
            if ultimo_vnt and ultimo_vnt.numero:
                try: seq = int(ultimo_vnt.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            v.numero = f'VNT-{hoy.year}-{seq:03d}'
            try:
                _save_items(v); db.session.flush()
                _procesar_venta_produccion(v)
                db.session.commit()
                flash('Venta creada.', 'success')
                return redirect(url_for('ventas'))
            except Exception as e:
                db.session.rollback()
                logging.error(f'venta_nueva error: {e}')
                flash('Error al crear la venta. Verifica los datos e intenta de nuevo.', 'danger')
        return render_template('ventas/form.html', obj=None, clientes_list=cl,
                               titulo='Nueva Venta', productos_json=_prods_json(), items_json=[],
                               iva_default=iva_pct)


    # ── venta_editar (/ventas/<int:id>/editar)
    @app.route('/ventas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def venta_editar(id):
        obj = Venta.query.get_or_404(id)
        cl  = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        iva_pct = _iva_rate()
        if request.method == 'POST':
            fa = request.form.get('fecha_anticipo')
            fe = request.form.get('fecha_entrega_est')
            subtotal = float(request.form.get('subtotal_calc') or 0)
            iva_monto = round(subtotal * iva_pct / 100.0, 2)
            total = subtotal + iva_monto
            obj.titulo=request.form['titulo']; obj.cliente_id=request.form.get('cliente_id') or None
            obj.subtotal=subtotal
            obj.iva=iva_monto
            obj.total=total
            obj.porcentaje_anticipo=float(request.form.get('porcentaje_anticipo') or 0)
            obj.monto_anticipo=float(request.form.get('monto_anticipo') or 0)
            obj.saldo=float(request.form.get('saldo') or 0)
            obj.estado=request.form.get('estado','prospecto')
            obj.fecha_anticipo=datetime.strptime(fa,'%Y-%m-%d').date() if fa else None
            obj.dias_entrega=int(request.form.get('dias_entrega') or 30)
            obj.fecha_entrega_est=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None
            obj.notas=request.form.get('notas','')
            try:
                db.session.flush()
                _save_items(obj)
                db.session.flush()
                _procesar_venta_produccion(obj)
                db.session.commit()
                flash('Venta actualizada.', 'success')
                return redirect(url_for('ventas'))
            except Exception as e:
                db.session.rollback()
                logging.error(f'venta_editar error: {e}')
                flash('Error al guardar la venta. Verifica los datos e intenta de nuevo.', 'danger')
        items_j = [{'pid':it.producto_id or '','nombre':it.nombre_prod,
                    'cant':it.cantidad,'precio':it.precio_unit} for it in obj.items]
        return render_template('ventas/form.html', obj=obj, clientes_list=cl,
                               titulo='Editar Venta', productos_json=_prods_json(), items_json=items_j,
                               iva_default=iva_pct)


    # ── venta_eliminar (/ventas/<int:id>/eliminar)
    @app.route('/ventas/<int:id>/eliminar', methods=['POST'])
    @login_required
    def venta_eliminar(id):
        from services.inventario import InventarioService
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar ventas.', 'danger')
            return redirect(url_for('ventas'))
        obj = Venta.query.get_or_404(id)
        try:
            # Devolver stock de materias primas antes de borrar
            InventarioService.devolver_materias_venta(obj.id)
            ReservaProduccion.query.filter_by(venta_id=obj.id).delete()
            OrdenProduccion.query.filter_by(venta_id=obj.id).delete()
            db.session.flush()
        except Exception as e:
            logging.warning(f'venta_eliminar: cleanup error: {e}')
            db.session.rollback()
        db.session.delete(obj)
        db.session.commit()
        _noop('eliminar','venta',id,'Venta eliminada'); db.session.commit()
        flash('Venta eliminada y stock de materias primas devuelto.', 'info')
        return redirect(url_for('ventas'))


    # ── venta_cambiar_estado (/ventas/<int:id>/estado)
    @app.route('/ventas/<int:id>/estado', methods=['POST'])
    @login_required
    def venta_cambiar_estado(id):
        from services.inventario import InventarioService
        venta = Venta.query.get_or_404(id)
        estado_anterior = venta.estado
        nuevo = request.form.get('estado', '')
        estados_validos = ['prospecto','negociacion','anticipo_pagado','pagado','cancelado',
                           'completado','perdido']  # completado/perdido kept for backward compat
        if nuevo not in estados_validos:
            return redirect(url_for('ventas'))

        venta.estado = nuevo
        _noop('editar','venta',venta.id,f'Estado → {nuevo}')

        # ── Bloque 3: sincronizar producción cuando venta se cancela/pierde ──
        ESTADOS_CANCEL = {'cancelado', 'perdido'}
        ESTADOS_ACTIVOS_PROD = {'anticipo_pagado', 'pagado', 'completado'}
        if nuevo in ESTADOS_CANCEL and estado_anterior in ESTADOS_ACTIVOS_PROD:
            # Devolver materias primas reservadas
            try:
                InventarioService.devolver_materias_venta(venta.id)
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: devolver_materias_venta error: {ex}')
            # Cancelar órdenes de producción activas
            ordenes_activas = OrdenProduccion.query.filter(
                OrdenProduccion.venta_id == venta.id,
                OrdenProduccion.estado.in_(['pendiente_materiales', 'en_produccion'])
            ).all()
            for o in ordenes_activas:
                o.estado = 'cancelado'
            # Crear tarea automática si hay órdenes que se detuvieron (evitar duplicados)
            if ordenes_activas:
                productos_afectados = ', '.join(
                    o.producto.nombre for o in ordenes_activas if o.producto
                )
                titulo_cancel = f'Producción detenida — {venta.titulo or venta.numero}'
                tarea_dup = Tarea.query.filter_by(
                    titulo=titulo_cancel, estado='pendiente'
                ).first()
                try:
                    responsable = current_user.id
                    if not tarea_dup:
                        t = Tarea(
                            titulo=titulo_cancel,
                            descripcion=(
                                f'La venta {venta.numero or "#"+str(venta.id)} fue marcada como '
                                f'"{nuevo}". Se detuvo la producción de: {productos_afectados}.\n'
                                f'Revisar materiales reservados y reordenar si aplica.'
                            ),
                            estado='pendiente', prioridad='alta',
                            asignado_a=responsable,
                            creado_por=responsable,
                            fecha_vencimiento=(datetime.utcnow() + timedelta(days=1)).date()
                        )
                        db.session.add(t)
                except Exception as ex:
                    logging.warning(f'venta_cambiar_estado: tarea automatica error: {ex}')
            flash(
                f'Venta cancelada. {len(ordenes_activas)} orden(es) de producción detenida(s) '
                f'y stock de materias primas devuelto.',
                'warning'
            )

        # ── BLOQUE 5: Crear asiento contable automático cuando venta se marca como "pagado" ──
        if nuevo == 'pagado' and estado_anterior != 'pagado':
            try:
                # Verificar si ya existe un asiento para esta venta
                asiento_existente = AsientoContable.query.filter_by(venta_id=venta.id).first()
                if not asiento_existente:
                    # Generar número automático
                    ultimo_asiento = AsientoContable.query.order_by(AsientoContable.id.desc()).first()
                    n_ac = (ultimo_asiento.id + 1) if ultimo_asiento else 1
                    numero_ac = f'AC-{datetime.utcnow().year}-{n_ac:04d}'

                    asiento = AsientoContable(
                        numero=numero_ac,
                        fecha=datetime.utcnow().date(),
                        descripcion=f'Ingreso por venta {venta.numero or venta.id}',
                        tipo='venta',
                        subtipo='ingreso_venta',
                        referencia=venta.numero or str(venta.id),
                        debe=float(venta.total or 0),
                        haber=float(venta.total or 0),
                        cuenta_debe='Cuentas por cobrar clientes',
                        cuenta_haber='Ingresos por ventas',
                        venta_id=venta.id,
                        creado_por=current_user.id
                    )
                    db.session.add(asiento)
                    logging.info(f'Asiento contable creado automáticamente: {numero_ac} para venta {venta.id}')
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: crear asiento contable error: {ex}')

        db.session.commit()
        return redirect(url_for('ventas'))


    # ── venta_remision (/ventas/<int:id>/remision)
    @app.route('/ventas/<int:id>/remision')
    @login_required
    def venta_remision(id):
        venta = Venta.query.get_or_404(id)
        upp   = request.args.get('upp', type=int, default=0)
        empresa = ConfigEmpresa.query.first()
        # Calcular totales de unidades por ítem
        items_data = []
        total_unidades = 0
        for it in venta.items:
            qty = it.cantidad if it.cantidad else 0
            items_data.append({'nombre': it.nombre_prod, 'cantidad': qty,
                               'precio_unit': it.precio_unit, 'subtotal': it.subtotal})
            total_unidades += qty
        # Cálculo de cajas
        cajas_info = None
        if upp and upp > 0:
            import math
            cajas_completas = math.floor(total_unidades / upp)
            sobrante       = total_unidades % upp
            cajas_parciales = 1 if sobrante > 0 else 0
            cajas_info = {'upp': upp, 'total_unidades': total_unidades,
                          'cajas_completas': cajas_completas, 'sobrante': sobrante,
                          'cajas_parciales': cajas_parciales}
        return render_template('ventas/remision.html', venta=venta, empresa=empresa,
                               items_data=items_data, total_unidades=total_unidades,
                               cajas_info=cajas_info, upp=upp)


    # ── venta_informar_cliente (/ventas/<int:id>/informar_cliente)
    @app.route('/ventas/<int:id>/informar_cliente', methods=['POST'])
    @login_required
    def venta_informar_cliente(id):
        venta = Venta.query.get_or_404(id)
        venta.cliente_informado_en = datetime.utcnow()
        db.session.commit()
        # Enviar email al cliente si tiene email
        email = venta.cliente.contactos[0].email if venta.cliente and venta.cliente.contactos else None
        if email:
            prod_nombres = ', '.join(
                it.nombre_prod for it in venta.items if it.nombre_prod
            ) or 'los productos'
            _send_email(
                email,
                f'Tu pedido está listo — {venta.titulo}',
                f'Hola {venta.cliente.nombre},\n\n'
                f'Nos complace informarte que {prod_nombres} de tu pedido "{venta.titulo}" '
                f'están listos para entrega.\n\n'
                f'Coordinaremos contigo la fecha y horario de entrega.\n\n'
                f'¡Gracias por tu compra!'
            )
            flash(f'Cliente {venta.cliente.nombre} notificado por email. Pedido listo para entrega.','success')
        else:
            flash('Venta marcada como "cliente informado". (Sin email del cliente para enviar notificación.)','info')
        return redirect(url_for('ventas'))


    # ── venta_entregar (/ventas/<int:id>/entregar)
    @app.route('/ventas/<int:id>/entregar', methods=['POST'])
    @login_required
    def venta_entregar(id):
        venta = Venta.query.get_or_404(id)
        try:
            venta.entregado_en = datetime.utcnow()
            # Mark as fully paid when delivered (unless already cancelled/lost)
            if venta.estado not in ('cancelado', 'perdido'):
                venta.estado = 'pagado'
            _descontar_stock_venta(venta)
            db.session.commit()
            flash('Venta entregada y marcada como pagada. Stock descontado del inventario.', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'venta_entregar error: {e}')
            flash('Error al entregar la venta. Por favor intenta de nuevo.', 'danger')
        return redirect(url_for('ventas'))


    # ── api_venta_material_status (/api/ventas/<id>/material_status)
    @app.route('/api/ventas/<int:id>/material_status')
    @login_required
    def api_venta_material_status(id):
        """Devuelve estado de materiales para una venta (para mostrar en tiempo real)."""
        venta = Venta.query.get_or_404(id)
        result = []
        todas_ok = True
        for item in venta.items:
            if not item.producto_id:
                continue
            prod = db.session.get(Producto, item.producto_id)
            if not prod:
                continue
            cant_req = float(item.cantidad or 0)
            cant_stock = float(prod.stock or 0)
            cant_producir = max(0.0, cant_req - cant_stock)
            if cant_producir <= 0:
                result.append({'producto': prod.nombre, 'ok': True,
                                'mensaje': f'En stock ({int(cant_stock)} uds)'})
                continue
            receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
            if not receta or not receta.items:
                result.append({'producto': prod.nombre, 'ok': False,
                                'mensaje': f'Necesita producir {cant_producir:.0f} uds — sin receta'})
                todas_ok = False
                continue
            materiales_ok = True
            faltantes = []
            factor = cant_producir / float(receta.unidades_produce or 1)
            for ri in receta.items:
                mp = ri.materia
                necesita = ri.cantidad_por_unidad * factor
                if mp.stock_disponible < necesita:
                    faltan = necesita - mp.stock_disponible
                    faltantes.append(f'{mp.nombre}: faltan {faltan:.2f} {mp.unidad}')
                    materiales_ok = False
            if not materiales_ok:
                todas_ok = False
                result.append({'producto': prod.nombre, 'ok': False,
                                'mensaje': f'Materiales faltantes: {"; ".join(faltantes)}'})
            else:
                result.append({'producto': prod.nombre, 'ok': True,
                                'mensaje': f'Materiales disponibles (a producir: {cant_producir:.0f} uds)'})
        return jsonify({'todas_ok': todas_ok, 'items': result})


    # ── venta_factura (/ventas/<int:id>/factura)
    @app.route('/ventas/<int:id>/factura')
    @login_required
    def venta_factura(id):
        obj = Venta.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        if not empresa:
            empresa = ConfigEmpresa(nombre='Evore')
        doc_tipo = 'COTIZACIÓN' if obj.estado in ('prospecto','negociacion') else 'FACTURA'
        doc_numero = f'EV-{obj.creado_en.year}-{obj.id:04d}'
        fecha_doc = obj.creado_en.strftime('%d/%m/%Y')
        return render_template('ventas/factura.html',
            obj=obj, empresa=empresa, doc_tipo=doc_tipo,
            doc_numero=doc_numero, fecha_doc=fecha_doc)


    # ── cotizaciones (/cotizaciones)
    @app.route('/cotizaciones')
    @login_required
    def cotizaciones():
        _marcar_vencidas()
        servicios = Servicio.query.filter_by(activo=True).all()
        items = Cotizacion.query.order_by(Cotizacion.fecha_emision.desc()).all()
        return render_template('cotizaciones/index.html', items=items, servicios=servicios)


    # ── cotizacion_nueva (/cotizaciones/nueva)
    @app.route('/cotizaciones/nueva', methods=['GET','POST'])
    @login_required
    def cotizacion_nueva():
        from datetime import date as date_t
        clientes_list = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        regla_iva = ReglaTributaria.query.filter_by(aplica_a='ventas', activo=True).first()
        iva_default = regla_iva.porcentaje if regla_iva else 19.0
        if request.method == 'POST':
            hoy = date_t.today()
            # Generar número secuencial
            ultimo = Cotizacion.query.filter(
                Cotizacion.numero.like(f'COT-{hoy.year}-%')
            ).order_by(Cotizacion.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            numero = f'COT-{hoy.year}-{seq:03d}'
            fd_em = request.form.get('fecha_emision')
            fd_val = request.form.get('fecha_validez')
            dias_tipo = request.form.get('dias_tipo', 'calendario')
            tiempo_desde = request.form.get('tiempo_desde', 'anticipo')

            nombres = request.form.getlist('item_nombre[]')
            tipos = request.form.getlist('item_tipo[]')
            cantidades = request.form.getlist('item_cantidad[]')
            precios = request.form.getlist('item_precio[]')
            unidades = request.form.getlist('item_unidad[]')
            aplica_ivas = request.form.getlist('item_aplica_iva[]')
            iva_pcts = request.form.getlist('item_iva_pct[]')
            servicio_ids = request.form.getlist('item_servicio_id[]')

            items_data = []
            subtotal = 0.0
            iva_total = 0.0
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = float(cantidades[i]) if i < len(cantidades) else 1.0
                precio = float(precios[i]) if i < len(precios) else 0.0
                unidad = unidades[i] if i < len(unidades) else 'unidades'
                tipo = tipos[i] if i < len(tipos) else 'producto'
                srv_id = int(servicio_ids[i]) if i < len(servicio_ids) and servicio_ids[i].strip() else None
                aplica_iva = aplica_ivas[i] if i < len(aplica_ivas) else 'on'
                aplica_iva = aplica_iva == 'on'
                iva_pct = float(iva_pcts[i]) if i < len(iva_pcts) else 0.0
                if not aplica_iva:
                    iva_pct = 0.0

                sub = cant * precio
                iva_monto = sub * iva_pct / 100.0 if aplica_iva else 0.0
                subtotal += sub
                iva_total += iva_monto

                items_data.append({
                    'nombre': nm, 'cantidad': cant, 'precio': precio, 'subtotal': sub,
                    'unidad': unidad, 'tipo': tipo, 'servicio_id': srv_id,
                    'aplica_iva': aplica_iva, 'iva_pct': iva_pct, 'iva_monto': iva_monto
                })

            total = subtotal + iva_total
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)
            monto_anticipo = total * pct_anticipo / 100.0
            saldo = total - monto_anticipo

            # Calcular fecha_entrega_est considerando dias_tipo
            fecha_emision = datetime.strptime(fd_em,'%Y-%m-%d').date() if fd_em else date_t.today()
            dias_ent = int(request.form.get('dias_entrega', 30) or 30)
            fecha_ent_est = self._calc_fecha_entrega(fecha_emision, dias_ent, dias_tipo)

            cot = Cotizacion(
                numero=numero,
                titulo=request.form['titulo'],
                cliente_id=request.form.get('cliente_id') or None,
                subtotal=subtotal, iva=iva_total, total=total,
                porcentaje_anticipo=pct_anticipo,
                monto_anticipo=monto_anticipo, saldo=saldo,
                fecha_emision=fecha_emision,
                fecha_validez=datetime.strptime(fd_val,'%Y-%m-%d').date() if fd_val else None,
                dias_entrega=dias_ent,
                dias_tipo=dias_tipo,
                tiempo_desde=tiempo_desde,
                fecha_entrega_est=fecha_ent_est,
                condiciones_pago=request.form.get('condiciones_pago',''),
                notas=request.form.get('notas',''),
                estado='borrador', creado_por=current_user.id)
            db.session.add(cot); db.session.flush()
            for it in items_data:
                db.session.add(CotizacionItem(
                    cotizacion_id=cot.id, nombre_prod=it['nombre'],
                    cantidad=it['cantidad'], precio_unit=it['precio'], subtotal=it['subtotal'],
                    unidad=it['unidad'], tipo_item=it['tipo'], servicio_id=it['servicio_id'],
                    aplica_iva=it['aplica_iva'], iva_pct=it['iva_pct'], iva_monto=it['iva_monto']))
            _noop('crear','cotizacion',cot.id,f'Cotización {numero}: {cot.titulo}'); db.session.commit()
            flash(f'Cotización {numero} creada.','success')
            return redirect(url_for('cotizacion_ver', id=cot.id))

        return render_template('cotizaciones/form.html', obj=None, titulo='Nueva Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default, servicios_json=_servicios_json())


    # ── Helper: calcular fecha de entrega según dias_tipo
    def _calc_fecha_entrega(fecha_emision, dias, dias_tipo):
        """Calcula fecha entrega considerando tipo de días (calendario o hábiles)."""
        from datetime import date, timedelta
        if dias_tipo == 'calendario':
            return fecha_emision + timedelta(days=dias)
        elif dias_tipo == 'habiles':
            # Omitir sábados (5) y domingos (6)
            current = fecha_emision
            dias_contados = 0
            while dias_contados < dias:
                current += timedelta(days=1)
                if current.weekday() < 5:  # Lunes-Viernes
                    dias_contados += 1
            return current
        else:
            return fecha_emision + timedelta(days=dias)

    # ── cotizacion_ver (/cotizaciones/<int:id>)
    @app.route('/cotizaciones/<int:id>')
    @login_required
    def cotizacion_ver(id):
        obj = Cotizacion.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first() or ConfigEmpresa(nombre='Evore')
        return render_template('cotizaciones/ver.html', obj=obj, empresa=empresa)


    # ── cotizacion_editar (/cotizaciones/<int:id>/editar)
    @app.route('/cotizaciones/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def cotizacion_editar(id):
        from datetime import date as date_t
        obj = Cotizacion.query.get_or_404(id)
        clientes_list = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        regla_iva = ReglaTributaria.query.filter_by(aplica_a='ventas', activo=True).first()
        iva_default = regla_iva.porcentaje if regla_iva else 19.0
        if request.method == 'POST':
            fd_em = request.form.get('fecha_emision')
            fd_val = request.form.get('fecha_validez')
            dias_tipo = request.form.get('dias_tipo', obj.dias_tipo or 'calendario')
            tiempo_desde = request.form.get('tiempo_desde', obj.tiempo_desde or 'anticipo')

            nombres = request.form.getlist('item_nombre[]')
            tipos = request.form.getlist('item_tipo[]')
            cantidades = request.form.getlist('item_cantidad[]')
            precios = request.form.getlist('item_precio[]')
            unidades = request.form.getlist('item_unidad[]')
            aplica_ivas = request.form.getlist('item_aplica_iva[]')
            iva_pcts = request.form.getlist('item_iva_pct[]')
            servicio_ids = request.form.getlist('item_servicio_id[]')

            # Borrar items existentes
            for it in obj.items: db.session.delete(it)
            db.session.flush()

            subtotal = 0.0
            iva_total = 0.0
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = float(cantidades[i]) if i < len(cantidades) else 1.0
                precio = float(precios[i]) if i < len(precios) else 0.0
                unidad = unidades[i] if i < len(unidades) else 'unidades'
                tipo = tipos[i] if i < len(tipos) else 'producto'
                srv_id = int(servicio_ids[i]) if i < len(servicio_ids) and servicio_ids[i].strip() else None
                aplica_iva = aplica_ivas[i] if i < len(aplica_ivas) else 'on'
                aplica_iva = aplica_iva == 'on'
                iva_pct = float(iva_pcts[i]) if i < len(iva_pcts) else 0.0
                if not aplica_iva:
                    iva_pct = 0.0

                sub = cant * precio
                iva_monto = sub * iva_pct / 100.0 if aplica_iva else 0.0
                subtotal += sub
                iva_total += iva_monto

                db.session.add(CotizacionItem(
                    cotizacion_id=obj.id, nombre_prod=nm,
                    cantidad=cant, precio_unit=precio, subtotal=sub,
                    unidad=unidad, tipo_item=tipo, servicio_id=srv_id,
                    aplica_iva=aplica_iva, iva_pct=iva_pct, iva_monto=iva_monto))

            total = subtotal + iva_total
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)

            fecha_emision = datetime.strptime(fd_em,'%Y-%m-%d').date() if fd_em else obj.fecha_emision
            dias_ent = int(request.form.get('dias_entrega', 30) or 30)
            fecha_ent_est = self._calc_fecha_entrega(fecha_emision, dias_ent, dias_tipo)

            obj.titulo = request.form['titulo']
            obj.cliente_id = request.form.get('cliente_id') or None
            obj.subtotal = subtotal; obj.iva = iva_total; obj.total = total
            obj.porcentaje_anticipo = pct_anticipo
            obj.monto_anticipo = total * pct_anticipo / 100.0
            obj.saldo = total - obj.monto_anticipo
            obj.fecha_emision = fecha_emision
            obj.fecha_validez = datetime.strptime(fd_val,'%Y-%m-%d').date() if fd_val else None
            obj.dias_entrega = dias_ent
            obj.dias_tipo = dias_tipo
            obj.tiempo_desde = tiempo_desde
            obj.fecha_entrega_est = fecha_ent_est
            obj.condiciones_pago = request.form.get('condiciones_pago','')
            obj.notas = request.form.get('notas','')
            db.session.commit()
            flash('Cotización actualizada.','success')
            return redirect(url_for('cotizacion_ver', id=obj.id))

        return render_template('cotizaciones/form.html', obj=obj, titulo='Editar Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default, servicios_json=_servicios_json())


    # ── cotizacion_cambiar_estado (/cotizaciones/<int:id>/estado)
    @app.route('/cotizaciones/<int:id>/estado', methods=['POST'])
    @login_required
    def cotizacion_cambiar_estado(id):
        obj = Cotizacion.query.get_or_404(id)
        nuevo = request.form.get('estado','borrador')
        if nuevo in ('borrador','enviada','aprobada','confirmacion_orden','vencida'):
            obj.estado = nuevo
            db.session.commit()
            if nuevo == 'confirmacion_orden':
                try:
                    _procesar_orden_produccion(obj)
                    db.session.commit()
                except Exception as ep:
                    db.session.rollback()
                    print(f'_procesar_orden_produccion error: {ep}')
            flash(f'Estado actualizado a: {nuevo}.','success')
        return redirect(url_for('cotizacion_ver', id=id))


    # ── cotizacion_eliminar (/cotizaciones/<int:id>/eliminar)
    @app.route('/cotizaciones/<int:id>/eliminar', methods=['POST'])
    @login_required
    def cotizacion_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj = Cotizacion.query.get_or_404(id)
        db.session.delete(obj); db.session.commit()
        flash('Cotización eliminada.','info')
        return redirect(url_for('cotizaciones'))


    # ── cotizacion_pdf (/cotizaciones/<int:id>/pdf)
    @app.route('/cotizaciones/<int:id>/pdf')
    @login_required
    def cotizacion_pdf(id):
        obj = Cotizacion.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first() or ConfigEmpresa(nombre='Evore')
        return render_template('cotizaciones/pdf.html', obj=obj, empresa=empresa)
