# routes/ventas.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db, tenant_query
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging
from models import HistorialPrecio, HistorialCotizacion

def register(app):

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
            for p in tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
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
            for s in tenant_query(Servicio).filter_by(activo=True).order_by(Servicio.nombre).all()
        ]

    def _save_items(venta_obj):
        VentaProducto.query.filter_by(venta_id=venta_obj.id).delete()
        pids    = request.form.getlist('prod_id[]')
        cants   = request.form.getlist('prod_cant[]')
        precios = request.form.getlist('prod_precio[]')
        for i, pid in enumerate(pids):
            if not pid: continue
            cant   = _parse_decimal(cants[i])   if i < len(cants)   else 1
            precio = _parse_decimal(precios[i]) if i < len(precios) else 0
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
                existente = tenant_query(OrdenProduccion).filter(
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
                    company_id=getattr(g, 'company_id', None),
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
        vencidas = tenant_query(Cotizacion).filter(
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
    @requiere_modulo('ventas')
    def ventas():
        from datetime import date, timedelta
        estado_f = request.args.get('estado','')
        buscar = request.args.get('buscar','').strip()
        page = request.args.get('page', 1, type=int)
        per_page = 25
        q = tenant_query(Venta)
        if buscar:
            q = q.filter(db.or_(Venta.titulo.ilike(f'%{buscar}%'), Venta.numero.ilike(f'%{buscar}%')))
        if estado_f:
            q = q.filter_by(estado=estado_f)
        pagination = q.order_by(Venta.creado_en.desc()).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
        total_pages = pagination.pages
        total_items = pagination.total

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

        transportistas_list = tenant_query(Proveedor).filter(
            Proveedor.activo == True,
            Proveedor.tipo.in_(['transportista', 'ambos'])
        ).order_by(Proveedor.empresa).all()
        # Contratos existentes por cliente para mostrar "Ver contrato" vs "Generar"
        docs_por_cliente = {}
        try:
            contratos = tenant_query(DocumentoLegal).filter(
                DocumentoLegal.tipo.in_(['contrato']),
                DocumentoLegal.activo == True,
                DocumentoLegal.cliente_id.isnot(None)
            ).all()
            for doc in contratos:
                docs_por_cliente[doc.cliente_id] = doc
        except Exception:
            pass
        return render_template('ventas/index.html', items=items, estado_f=estado_f,
                               buscar=buscar,
                               proximas_vencer=proximas_vencer, today_date=hoy,
                               transportistas_list=transportistas_list,
                               docs_por_cliente=docs_por_cliente,
                               page=page, total_pages=total_pages,
                               total_items=total_items)


    # ── ventas_export_csv (/ventas/export-csv)
    @app.route('/ventas/export-csv')
    @login_required
    @requiere_modulo('ventas')
    def ventas_export_csv():
        ventas = tenant_query(Venta).order_by(Venta.creado_en.desc()).all()
        rows = []
        for v in ventas:
            cliente = v.cliente
            if cliente:
                nombre_cliente = cliente.empresa or cliente.nombre or ''
            else:
                nombre_cliente = ''
            fecha = v.creado_en.strftime('%d/%m/%Y') if v.creado_en else ''
            rows.append([
                v.numero or '',
                v.titulo or '',
                nombre_cliente,
                v.total or 0,
                v.estado or '',
                fecha,
                v.monto_pagado_total or 0,
            ])
        return generar_csv_response(
            rows,
            ['Numero', 'Titulo', 'Cliente', 'Total', 'Estado', 'Fecha', 'Pagado'],
            filename='ventas.csv'
        )

    # helper: get configured IVA rate (%)
    def _iva_rate():
        try:
            regla = tenant_query(ReglaTributaria).filter_by(aplica_a='ventas', activo=True).first()
            return float(regla.porcentaje) if regla else 19.0
        except Exception:
            return 19.0

    # ── venta_nueva (/ventas/nueva)
    @app.route('/ventas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_nueva():
        cl = tenant_query(Cliente).order_by(Cliente.empresa, Cliente.nombre).all()
        iva_pct = _iva_rate()
        # Cotizaciones disponibles para vincular (solo enviadas o aprobadas — no borradores)
        cots_disponibles = tenant_query(Cotizacion).filter(
            Cotizacion.estado.in_(['enviada','aprobada'])
        ).order_by(Cotizacion.fecha_emision.desc()).all()
        # Pre-selección de cliente via query param (desde cotizacion)
        pre_cliente_id = request.args.get('cliente_id', type=int)
        pre_cotizacion_id = request.args.get('cotizacion_id', type=int)
        if request.method == 'POST':
            fa = request.form.get('fecha_anticipo')
            fe = request.form.get('fecha_entrega_est')
            subtotal = float(request.form.get('subtotal_calc') or 0)
            if subtotal <= 0:
                flash('El valor de la venta debe ser mayor a cero.', 'danger')
                return redirect(url_for('venta_nueva'))
            iva_monto = round(subtotal * iva_pct / 100.0, 2)
            total = round(subtotal + iva_monto, 2)
            cot_id = request.form.get('cotizacion_id') or None
            if cot_id:
                venta_dup = tenant_query(Venta).filter_by(cotizacion_id=int(cot_id)).first()
                if venta_dup:
                    flash(f'Ya existe una venta ({venta_dup.numero}) para esa cotización.', 'warning')
                    return redirect(url_for('ventas'))
            cliente_id = request.form.get('cliente_id') or None
            if not cliente_id:
                flash('Debes seleccionar un cliente.', 'danger')
                return redirect(url_for('venta_nueva'))
            v = Venta(company_id=getattr(g, 'company_id', None),
                titulo=request.form['titulo'],
                cliente_id=cliente_id,
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
                notas=request.form.get('notas',''), creado_por=current_user.id,
                cotizacion_id=int(cot_id) if cot_id else None)
            db.session.add(v); db.session.flush()
            # Marcar cotización como aprobada si fue vinculada
            if cot_id:
                try:
                    cot_obj = Cotizacion.query.get(int(cot_id))
                    if cot_obj and cot_obj.estado not in ('aprobada','vencida'):
                        cot_obj.estado = 'aprobada'
                except Exception as ce:
                    logging.warning(f'No se pudo marcar cotizacion {cot_id} como aprobada: {ce}')
            # Generar numero único VNT-YYYY-NNN
            hoy = datetime.utcnow().date()
            ultimo_vnt = tenant_query(Venta).filter(
                Venta.numero.like(f'VNT-{hoy.year}-%')
            ).order_by(Venta.id.desc()).first()
            if ultimo_vnt and ultimo_vnt.numero:
                try: seq = int(ultimo_vnt.numero.split('-')[-1]) + 1
                except Exception: seq = 1
            else: seq = 1
            v.numero = f'VNT-{hoy.year}-{seq:03d}'
            try:
                _save_items(v); db.session.flush()
                _procesar_venta_produccion(v)
                # Auto-crear asiento contable de ingreso en borrador
                try:
                    asiento_venta = AsientoContable(
                        company_id=getattr(g, 'company_id', None),
                        numero='AC-TEMP',
                        fecha=hoy,
                        descripcion=f'Ingreso pendiente — Venta {v.numero}',
                        tipo='venta',
                        subtipo='ingreso_venta',
                        referencia=v.numero,
                        debe=float(v.total or 0),
                        haber=float(v.total or 0),
                        cuenta_debe='130505 Nacionales',
                        cuenta_haber='4135 Comercio al por mayor y menor',
                        clasificacion='ingreso',
                        estado_asiento='borrador',
                        estado_pago='pendiente',
                        venta_id=v.id,
                        creado_por=current_user.id
                    )
                    db.session.add(asiento_venta)
                    db.session.flush()
                    asiento_venta.numero = f'AC-{hoy.year}-{asiento_venta.id:04d}'
                except Exception as ex_ac:
                    logging.warning(f'venta_nueva: auto-asiento ingreso error: {ex_ac}')
                db.session.commit()
                flash('Venta creada con asiento contable de ingreso pendiente.', 'success')
                return redirect(url_for('ventas'))
            except Exception as e:
                db.session.rollback()
                logging.error(f'venta_nueva error: {e}')
                flash('Error al crear la venta. Verifica los datos e intenta de nuevo.', 'danger')
        return render_template('ventas/form.html', obj=None, clientes_list=cl,
                               titulo='Nueva Venta', productos_json=_prods_json(), items_json=[],
                               servicios_json=_servicios_json(),
                               iva_default=iva_pct, cots_disponibles=cots_disponibles,
                               pre_cliente_id=pre_cliente_id, pre_cotizacion_id=pre_cotizacion_id)


    # ── venta_ver (/ventas/<int:id>)
    @app.route('/ventas/<int:id>')
    @login_required
    @requiere_modulo('ventas')
    def venta_ver(id):
        obj = Venta.query.get_or_404(id)
        ordenes = tenant_query(OrdenProduccion).filter_by(venta_id=obj.id).all()
        reservas = ReservaProduccion.query.filter_by(venta_id=obj.id).all()
        pagos = PagoVenta.query.filter_by(venta_id=obj.id).order_by(PagoVenta.fecha.desc()).all()
        return render_template('ventas/ver.html', obj=obj, ordenes=ordenes,
                               reservas=reservas, pagos=pagos)

    # ── venta_editar (/ventas/<int:id>/editar)
    @app.route('/ventas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_editar(id):
        obj = Venta.query.get_or_404(id)
        cl  = tenant_query(Cliente).order_by(Cliente.empresa, Cliente.nombre).all()
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
                               servicios_json=_servicios_json(),
                               iva_default=iva_pct)


    # ── venta_eliminar (/ventas/<int:id>/eliminar)
    @app.route('/ventas/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_eliminar(id):
        from services.inventario import InventarioService
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar ventas.', 'danger')
            return redirect(url_for('ventas'))
        obj = Venta.query.get_or_404(id)
        try:
            # Liberar stock reservado de productos terminados (ATP)
            InventarioService.liberar_reserva_venta(obj)
            # Devolver stock de materias primas antes de borrar
            InventarioService.devolver_materias_venta(obj.id)
            ReservaProduccion.query.filter_by(venta_id=obj.id).delete()
            tenant_query(OrdenProduccion).filter_by(venta_id=obj.id).delete()
            db.session.flush()
        except Exception as e:
            logging.warning(f'venta_eliminar: cleanup error: {e}')
            db.session.rollback()
        db.session.delete(obj)
        db.session.commit()
        _log('eliminar','venta',id,'Venta eliminada'); db.session.commit()
        flash('Venta eliminada y stock de materias primas devuelto.', 'info')
        return redirect(url_for('ventas'))


    # ── venta_cambiar_estado (/ventas/<int:id>/estado)
    @app.route('/ventas/<int:id>/estado', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_cambiar_estado(id):
        from services.inventario import InventarioService
        venta = db.session.get(Venta, id, with_for_update=True)
        if not venta:
            flash('Venta no encontrada.', 'danger')
            return redirect(url_for('ventas'))
        estado_anterior = venta.estado
        nuevo = request.form.get('estado', '')
        estados_validos = ['prospecto','negociacion','anticipo_pagado','pagado','entregado',
                           'completado','cancelado','perdido']
        if nuevo not in estados_validos:
            return redirect(url_for('ventas'))

        # State machine: validar transiciones permitidas
        TRANSICIONES = {
            'prospecto': ['negociacion', 'cancelado', 'perdido'],
            'negociacion': ['prospecto', 'anticipo_pagado', 'cancelado', 'perdido'],
            'anticipo_pagado': ['negociacion', 'pagado', 'cancelado', 'perdido'],
            'pagado': ['entregado', 'completado', 'cancelado'],
            'entregado': ['completado'],
            'completado': [],
            'cancelado': ['prospecto'],
            'perdido': ['prospecto'],
        }
        permitidos = TRANSICIONES.get(estado_anterior, [])
        if nuevo not in permitidos and current_user.rol != 'admin':
            flash(f'No se puede cambiar de "{estado_anterior}" a "{nuevo}". Transiciones validas: {", ".join(permitidos)}', 'warning')
            return redirect(url_for('ventas'))

        # Restringir: anticipo_pagado solo se puede marcar desde asientos contables
        # (a menos que venga con flag _from_contable en el form)
        if nuevo == 'anticipo_pagado' and estado_anterior in ('prospecto', 'negociacion'):
            if not request.form.get('_from_contable'):
                flash('El pago de anticipo solo se puede confirmar desde Asientos Contables (seccion Ingresos).', 'warning')
                return redirect(url_for('ventas'))

        venta.estado = nuevo
        _log('editar','venta',venta.id,f'Estado → {nuevo}')

        # ── Bloque 2b: Reservar stock de producto al confirmar anticipo ──
        if nuevo == 'anticipo_pagado' and estado_anterior not in {'anticipo_pagado', 'pagado', 'completado'}:
            InventarioService.reservar_stock_venta(venta)

            # ── Bloque 2b2: Auto-crear contrato legal para el cliente ──
            try:
                if venta.cliente_id:
                    existing_doc = tenant_query(DocumentoLegal).filter_by(
                        cliente_id=venta.cliente_id, tipo='contrato', activo=True,
                        requiere_firma_portal=True
                    ).filter(DocumentoLegal.firma_portal_data == None).first()
                    if not existing_doc:
                        empresa = ConfigEmpresa.query.first()
                        cli = db.session.get(Cliente, venta.cliente_id)
                        doc = DocumentoLegal(
                            tipo='contrato',
                            titulo=f'Contrato de fabricacion — {venta.numero or venta.titulo}',
                            numero=f'CTR-{venta.numero or venta.id}',
                            entidad=empresa.nombre if empresa else 'Empresa',
                            descripcion=f'Contrato de fabricacion para terceros vinculado a la venta {venta.numero}. Incluye especificaciones de producto, plazos de entrega y condiciones de pago.',
                            estado='en_tramite',
                            fecha_emision=datetime.utcnow().date(),
                            cliente_id=venta.cliente_id,
                            tipo_entidad='cliente',
                            requiere_firma_portal=True,
                            activo=True,
                            creado_por=current_user.id
                        )
                        # Auto-firma empresa si hay representante legal configurado
                        if empresa and getattr(empresa, 'representante_legal', ''):
                            doc.firma_empresa_por = empresa.representante_legal
                        db.session.add(doc)
                        db.session.flush()
                        # Notificar al cliente si tiene usuario portal
                        from models import User as UserModel
                        user_cli = UserModel.query.filter_by(cliente_id=venta.cliente_id, rol='cliente', activo=True).first()
                        if user_cli:
                            _crear_notificacion(user_cli.id, 'info',
                                'Nuevo contrato para firmar',
                                f'Tienes un contrato pendiente de firma en tu portal: {doc.titulo}',
                                url_for('portal_cliente_docs'))
                        flash('Contrato generado y enviado al portal del cliente para firma.', 'info')
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: auto-doc error: {ex}')

            # ── Bloque 2c: Generar OC automáticas para MP faltante ──
            try:
                from datetime import date as _d
                ocs_creadas = 0
                for item in venta.items:
                    if not item.producto_id: continue
                    receta = RecetaProducto.query.filter_by(producto_id=item.producto_id, activo=True).first()
                    if not receta or receta.unidades_produce <= 0: continue
                    cant_producir = max(0, (item.cantidad or 0) - (Producto.query.get(item.producto_id).stock or 0))
                    if cant_producir <= 0: continue
                    factor = cant_producir / receta.unidades_produce
                    for ri in receta.items:
                        mp = db.session.get(MateriaPrima, ri.materia_prima_id)
                        if not mp: continue
                        necesaria = ri.cantidad_por_unidad * factor
                        disponible = mp.stock_disponible or 0
                        if disponible >= necesaria: continue
                        faltante = necesaria - disponible
                        # Buscar cotización vigente de proveedor para esta MP
                        cot_prov = CotizacionProveedor.query.filter(
                            CotizacionProveedor.materia_prima_id == mp.id,
                            CotizacionProveedor.estado == 'vigente',
                            CotizacionProveedor.vigencia >= _d.today()
                        ).order_by(CotizacionProveedor.precio_unitario.asc()).first()
                        if not cot_prov:
                            # Alerta: no hay cotización vigente
                            _crear_notificacion(
                                current_user.id, 'alerta',
                                f'MP sin cotizacion: {mp.nombre}',
                                f'Se necesitan {faltante:.2f} {mp.unidad} de {mp.nombre} para la venta {venta.numero} pero no hay cotizacion vigente.',
                                url_for('cotizaciones_proveedor'))
                            continue
                        # Crear OC automática
                        proveedor_id = cot_prov.proveedor_id
                        hoy_oc = _d.today()
                        ult_oc = tenant_query(OrdenCompra).filter(
                            OrdenCompra.numero.like(f'OC-{hoy_oc.year}-%')
                        ).order_by(OrdenCompra.id.desc()).first()
                        seq_oc = (int(ult_oc.numero.split('-')[-1]) + 1) if ult_oc and ult_oc.numero else 1
                        precio_unit = cot_prov.precio_unitario or 0
                        subtotal_oc = round(faltante * precio_unit, 2)
                        iva_oc = round(subtotal_oc * 0.19, 2)
                        oc = OrdenCompra(
                            company_id=getattr(g, 'company_id', None),
                            numero=f'OC-{hoy_oc.year}-{seq_oc:03d}',
                            proveedor_id=proveedor_id,
                            cotizacion_id=cot_prov.id,
                            estado='borrador',
                            fecha_emision=hoy_oc,
                            fecha_esperada=hoy_oc + timedelta(days=cot_prov.plazo_entrega_dias or 15),
                            subtotal=subtotal_oc, iva=iva_oc, total=subtotal_oc + iva_oc,
                            notas=f'OC automatica — Venta {venta.numero}, faltante {mp.nombre}',
                            creado_por=current_user.id,
                            venta_origen_id=venta.id
                        )
                        db.session.add(oc); db.session.flush()
                        db.session.add(OrdenCompraItem(
                            orden_id=oc.id, cotizacion_id=cot_prov.id,
                            nombre_item=mp.nombre,
                            descripcion=f'Para producción venta {venta.numero}',
                            cantidad=round(faltante, 3), unidad=mp.unidad,
                            precio_unit=precio_unit, subtotal=subtotal_oc
                        ))
                        ocs_creadas += 1
                if ocs_creadas > 0:
                    flash(f'{ocs_creadas} orden(es) de compra creadas automáticamente para MP faltante.', 'info')
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: OC auto error: {ex}')

        # ── Bloque 3: sincronizar producción cuando venta se cancela/pierde ──
        ESTADOS_CANCEL = {'cancelado', 'perdido'}
        ESTADOS_ACTIVOS_PROD = {'anticipo_pagado', 'pagado', 'completado'}
        if nuevo in ESTADOS_CANCEL and estado_anterior in ESTADOS_ACTIVOS_PROD:
            # Liberar stock reservado de productos terminados
            InventarioService.liberar_reserva_venta(venta)
            # Devolver materias primas reservadas
            try:
                InventarioService.devolver_materias_venta(venta.id)
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: devolver_materias_venta error: {ex}')
            # Cancelar órdenes de producción activas
            ordenes_activas = tenant_query(OrdenProduccion).filter(
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
                tarea_dup = tenant_query(Tarea).filter_by(
                    titulo=titulo_cancel, estado='pendiente'
                ).first()
                try:
                    responsable = current_user.id
                    if not tarea_dup:
                        t = Tarea(
                            company_id=getattr(g, 'company_id', None),
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

        # ── BLOQUE 4b: Pausar producción si la venta retrocede desde anticipo_pagado ──
        ESTADOS_ACTIVOS = {'anticipo_pagado', 'pagado', 'completado'}
        ESTADOS_PAUSAN  = {'prospecto', 'negociacion'}
        if estado_anterior == 'anticipo_pagado' and nuevo in ESTADOS_PAUSAN:
            ordenes_a_pausar = tenant_query(OrdenProduccion).filter(
                OrdenProduccion.venta_id == venta.id,
                OrdenProduccion.estado.in_(['pendiente_materiales','en_produccion'])
            ).all()
            for o in ordenes_a_pausar:
                o.estado = 'pausada'
            if ordenes_a_pausar:
                # Notificar al creador de la venta
                try:
                    creador_id = venta.creado_por or current_user.id
                    t_pausa = Tarea(
                        company_id=getattr(g, 'company_id', None),
                        titulo=f'Producción pausada — {venta.titulo or venta.numero}',
                        descripcion=(
                            f'La venta {venta.numero or "#"+str(venta.id)} cambió de '
                            f'"Anticipo Pagado" a "{nuevo}". '
                            f'Se pausaron {len(ordenes_a_pausar)} orden(es) de producción. '
                            f'Verificar con el cliente antes de reanudar.'
                        ),
                        estado='pendiente', prioridad='alta',
                        asignado_a=creador_id,
                        creado_por=current_user.id,
                        fecha_vencimiento=(datetime.utcnow() + timedelta(days=1)).date()
                    )
                    db.session.add(t_pausa)
                except Exception as ep:
                    logging.warning(f'venta_cambiar_estado: tarea pausa error: {ep}')
            flash(f'Estado actualizado. {len(ordenes_a_pausar)} orden(es) de producción pausada(s).', 'warning')

        # ── BLOQUE 4b.2: Liberar reserva de producto si venta retrocede desde anticipo_pagado ──
        if estado_anterior in ESTADOS_ACTIVOS_PROD and nuevo in ESTADOS_PAUSAN:
            InventarioService.liberar_reserva_venta(venta)

        # ── BLOQUE 4c: Reanudar producción si venta vuelve a anticipo_pagado ──
        if nuevo == 'anticipo_pagado' and estado_anterior in ESTADOS_PAUSAN:
            ordenes_pausadas = tenant_query(OrdenProduccion).filter(
                OrdenProduccion.venta_id == venta.id,
                OrdenProduccion.estado == 'pausada'
            ).all()
            for o in ordenes_pausadas:
                o.estado = 'en_produccion'
            if ordenes_pausadas:
                flash(f'{len(ordenes_pausadas)} orden(es) de producción reanudadas.', 'success')
            # Re-reservar stock de producto
            InventarioService.reservar_stock_venta(venta)

        # ── BLOQUE 5: Crear asiento contable automático cuando venta se marca como "pagado" ──
        if nuevo == 'pagado' and estado_anterior != 'pagado':
            try:
                # Verificar si ya existe un asiento para esta venta
                asiento_existente = tenant_query(AsientoContable).filter_by(venta_id=venta.id).first()
                if not asiento_existente:
                    # Generar número automático
                    ultimo_asiento = tenant_query(AsientoContable).order_by(AsientoContable.id.desc()).first()
                    n_ac = (ultimo_asiento.id + 1) if ultimo_asiento else 1
                    numero_ac = f'AC-{datetime.utcnow().year}-{n_ac:04d}'

                    asiento = AsientoContable(
                        company_id=getattr(g, 'company_id', None),
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

        # ── BLOQUE 6: Auto-crear comision cuando venta se marca como "completado" ──
        if nuevo == 'completado' and estado_anterior != 'completado':
            try:
                comision_existente = tenant_query(Comision).filter_by(venta_id=venta.id).first()
                if not comision_existente and venta.creado_por:
                    monto_com = round(float(venta.total or 0) * 0.05, 2)
                    db.session.add(Comision(
                        venta_id=venta.id,
                        vendedor_id=venta.creado_por,
                        porcentaje=5.0,
                        monto=monto_com,
                        estado='pendiente'
                    ))
                    logging.info(f'Comision creada automaticamente para venta {venta.id}')
            except Exception as ex:
                logging.warning(f'venta_cambiar_estado: auto-comision error: {ex}')

        db.session.commit()

        # ── Undo: guardar estado anterior en sesión y mostrar toast con enlace ──
        flask_session['undo_venta'] = {
            'id': venta.id,
            'estado_anterior': estado_anterior,
            'ts': datetime.utcnow().isoformat()
        }
        flash(
            f'Estado actualizado a "{nuevo}". '
            f'<a href="#" onclick="event.preventDefault();var f=document.createElement(\'form\');'
            f'f.method=\'POST\';f.action=\'/ventas/{venta.id}/deshacer-estado\';'
            f'var c=document.createElement(\'input\');c.type=\'hidden\';c.name=\'_csrf_token\';'
            f'c.value=document.querySelector(\'meta[name=csrf-token]\').content;'
            f'f.appendChild(c);document.body.appendChild(f);f.submit();" '
            f'style="color:#fff;text-decoration:underline;font-weight:700">Deshacer</a>',
            'success'
        )
        return redirect(url_for('ventas'))


    # ── venta_deshacer_estado (/ventas/<int:id>/deshacer-estado)
    @app.route('/ventas/<int:id>/deshacer-estado', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_deshacer_estado(id):
        undo = flask_session.pop('undo_venta', None)
        if not undo or undo['id'] != id:
            flash('No hay acción para deshacer.', 'warning')
            return redirect(url_for('ventas'))
        # Expirar undo despues de 30 segundos
        from datetime import datetime as _dt
        try:
            ts = _dt.fromisoformat(undo['ts'])
            if (_dt.utcnow() - ts).total_seconds() > 30:
                flash('El tiempo para deshacer ha expirado.', 'warning')
                return redirect(url_for('ventas'))
        except Exception:
            pass
        venta = Venta.query.get_or_404(id)
        venta.estado = undo['estado_anterior']
        _log('editar', 'venta', id, f'Estado revertido a {undo["estado_anterior"]} (undo)')
        db.session.commit()
        flash(f'Estado revertido a "{undo["estado_anterior"]}".', 'info')
        return redirect(url_for('ventas'))

    # ── venta_remision (/ventas/<int:id>/remision)
    @app.route('/ventas/<int:id>/remision')
    @login_required
    @requiere_modulo('ventas')
    def venta_remision(id):
        venta = Venta.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        import math
        # Calcular totales de unidades por ítem con empaque asignado
        items_data = []
        total_unidades = 0
        empaques_detalle = []
        for it in venta.items:
            qty = it.cantidad if it.cantidad else 0
            item_d = {'nombre': it.nombre_prod, 'cantidad': qty,
                      'precio_unit': it.precio_unit, 'subtotal': it.subtotal,
                      'marca': it.marca.nombre_marca if hasattr(it, 'marca') and it.marca else None}
            # Buscar empaque asignado al producto
            if it.producto_id:
                empaque = tenant_query(EmpaqueSecundario).filter_by(
                    producto_id=it.producto_id, aprobado=True
                ).first()
                if empaque and empaque.unidades_por_caja > 0:
                    upp = empaque.unidades_por_caja
                    cajas = math.ceil(qty / upp)
                    cajas_completas = math.floor(qty / upp)
                    sobrante = int(qty) % upp
                    item_d['empaque'] = {
                        'upp': upp,
                        'cajas': cajas,
                        'cajas_completas': cajas_completas,
                        'sobrante': sobrante,
                        'dim': f'{empaque.ancho}x{empaque.largo}x{empaque.alto} cm',
                        'peso_caja': round(empaque.peso_unitario * upp, 2)
                    }
                    empaques_detalle.append({
                        'producto': it.nombre_prod,
                        'cajas': cajas,
                        'upp': upp,
                        'sobrante': sobrante
                    })
            items_data.append(item_d)
            total_unidades += qty
        # Fallback manual de UPP
        upp_manual = request.args.get('upp', type=int, default=0)
        cajas_info = None
        if upp_manual and upp_manual > 0:
            cajas_completas = math.floor(total_unidades / upp_manual)
            sobrante = int(total_unidades) % upp_manual
            cajas_info = {'upp': upp_manual, 'total_unidades': total_unidades,
                          'cajas_completas': cajas_completas, 'sobrante': sobrante,
                          'cajas_parciales': 1 if sobrante > 0 else 0}
        # Info transportista
        transportista = None
        if venta.cliente and hasattr(venta.cliente, 'envio_responsable') and venta.cliente.envio_responsable == 'empresa':
            if hasattr(venta.cliente, 'transportista_preferido') and venta.cliente.transportista_preferido:
                transportista = venta.cliente.transportista_preferido
        return render_template('ventas/remision.html', venta=venta, empresa=empresa,
                               items_data=items_data, total_unidades=total_unidades,
                               cajas_info=cajas_info, upp=upp_manual,
                               empaques_detalle=empaques_detalle, transportista=transportista)


    # ── venta_informar_cliente (/ventas/<int:id>/informar_cliente)
    @app.route('/ventas/<int:id>/informar_cliente', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
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


    # ── venta_enviar (/ventas/<int:id>/enviar) — asignar transportista y notificar
    @app.route('/ventas/<int:id>/enviar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_enviar(id):
        venta = Venta.query.get_or_404(id)
        transportista_id = request.form.get('transportista_id', type=int)
        if transportista_id:
            venta.transportista_id = transportista_id
        venta.enviado_en = datetime.utcnow()
        venta.guia_transporte = request.form.get('guia_transporte', '').strip() or None
        venta.estado_envio = 'en_transito'
        db.session.commit()

        # Notificar al cliente
        if venta.cliente_id:
            try:
                cli = db.session.get(Cliente, venta.cliente_id)
                if cli:
                    transportista = db.session.get(Proveedor, transportista_id) if transportista_id else None
                    trans_nombre = (transportista.empresa or transportista.nombre) if transportista else 'por definir'
                    _crear_notificacion(
                        venta.creado_por or current_user.id, 'info',
                        f'Venta {venta.numero} enviada',
                        f'Transportista: {trans_nombre}',
                        url_for('venta_ver', id=venta.id)
                    )
                    # Email al cliente
                    email_dest = None
                    if hasattr(cli, 'contactos') and cli.contactos:
                        for c in cli.contactos:
                            if c.email:
                                email_dest = c.email
                                break
                    if email_dest:
                        empresa = ConfigEmpresa.query.first()
                        _send_email(
                            email_dest,
                            f'Tu pedido ha sido enviado — {venta.numero}',
                            f'Hola,\n\nTu pedido {venta.numero} ha sido enviado.\n'
                            f'Transportista: {trans_nombre}\n\n'
                            f'Saludos,\n{empresa.nombre if empresa else "Evore"}'
                        )
            except Exception as ex:
                logging.warning(f'venta_enviar notificacion error: {ex}')

        flash(f'Venta {venta.numero} marcada como enviada. Cliente notificado.', 'success')
        return redirect(url_for('venta_remision', id=venta.id))


    # ── venta_entregar (/ventas/<int:id>/entregar)
    @app.route('/ventas/<int:id>/entregar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_entregar(id):
        venta = Venta.query.get_or_404(id)
        try:
            venta.entregado_en = datetime.utcnow()
            venta.estado_envio = 'entregado'
            if venta.estado not in ('cancelado', 'perdido'):
                venta.estado = 'entregado'
            from services.inventario import InventarioService
            InventarioService.descontar_stock_venta(venta)
            db.session.commit()
            flash('Venta entregada y marcada como pagada. Stock descontado del inventario.', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f'venta_entregar error: {e}')
            flash('Error al entregar la venta. Por favor intenta de nuevo.', 'danger')
            return redirect(url_for('ventas'))
        # Redirigir a la remisión para que el usuario pueda imprimirla/descargarla
        return redirect(url_for('venta_remision', id=venta.id))


    # ── api_venta_material_status (/api/ventas/<id>/material_status)
    @app.route('/api/cotizacion/<int:id>/items')
    @login_required
    def api_cotizacion_items(id):
        """API: items de una cotización para pre-llenar formulario de venta."""
        cot = Cotizacion.query.get_or_404(id)
        items = []
        for it in cot.items:
            items.append({
                'nombre': it.nombre_prod,
                'producto_id': it.producto_id,
                'servicio_id': it.servicio_id,
                'cantidad': it.cantidad,
                'precio_unit': it.precio_unit,
                'subtotal': it.subtotal,
                'unidad': getattr(it, 'unidad', 'unidades'),
                'tipo': getattr(it, 'tipo_item', 'producto'),
                'sku': it.producto.sku if it.producto_id and it.producto else None,
                'aplica_iva': getattr(it, 'aplica_iva', True),
                'iva_pct': getattr(it, 'iva_pct', 19)
            })
        return jsonify({
            'cliente_id': cot.cliente_id,
            'titulo': cot.titulo,
            'porcentaje_anticipo': cot.porcentaje_anticipo,
            'dias_entrega': cot.dias_entrega,
            'notas': cot.notas or '',
            'items': items
        })

    @app.route('/api/ventas/<int:id>/material_status')
    @login_required
    @requiere_modulo('ventas')
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
    @requiere_modulo('ventas')
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


    # ── ventas_kanban (/ventas/kanban)
    @app.route('/ventas/kanban')
    @login_required
    @requiere_modulo('ventas')
    def ventas_kanban():
        from datetime import datetime as _dt
        ventas_todas = tenant_query(Venta).order_by(Venta.creado_en.asc()).all()
        hoy = _dt.utcnow()
        COLUMNAS = ['prospecto', 'negociacion', 'anticipo_pagado', 'pagado', 'entregado', 'completado']
        pipeline = {col: [] for col in COLUMNAS}
        for v in ventas_todas:
            if v.estado not in pipeline:
                continue
            cli = v.cliente
            dias_en_etapa = (hoy - v.creado_en).days if v.creado_en else 0
            creador = db.session.get(User, v.creado_por) if v.creado_por else None
            pipeline[v.estado].append({
                'id': v.id,
                'numero': v.numero or f'#{v.id}',
                'titulo': v.titulo,
                'cliente_nombre': (cli.empresa or cli.nombre) if cli else '—',
                'total': v.total or 0,
                'dias_en_etapa': dias_en_etapa,
                'creado_por_nombre': creador.nombre if creador else '—',
                'estado': v.estado,
            })
        return render_template('ventas/kanban.html', pipeline=pipeline, columnas=COLUMNAS)


    # ── ventas_comisiones (/ventas/comisiones)
    @app.route('/ventas/comisiones')
    @login_required
    @requiere_modulo('ventas')
    def ventas_comisiones():
        from datetime import datetime as _dt
        buscar     = request.args.get('buscar', '').strip()
        vendedor_f = request.args.get('vendedor_id', type=int)
        estado_f   = request.args.get('estado', '')
        periodo_f  = request.args.get('periodo', '')

        q = tenant_query(Comision)
        if buscar:
            q = q.outerjoin(User, Comision.vendedor_id == User.id).outerjoin(Venta, Comision.venta_id == Venta.id).filter(
                db.or_(User.nombre.ilike(f'%{buscar}%'),
                        Venta.titulo.ilike(f'%{buscar}%')))
        if vendedor_f:
            q = q.filter(Comision.vendedor_id == vendedor_f)
        if estado_f:
            q = q.filter_by(estado=estado_f)
        if periodo_f:
            try:
                anio, mes = int(periodo_f[:4]), int(periodo_f[5:7])
                from datetime import date as _d
                inicio = _dt(anio, mes, 1)
                if mes == 12:
                    fin = _dt(anio + 1, 1, 1)
                else:
                    fin = _dt(anio, mes + 1, 1)
                q = q.filter(Comision.creado_en >= inicio, Comision.creado_en < fin)
            except Exception:
                pass

        comisiones = q.order_by(Comision.creado_en.desc()).all()
        total_pendiente = sum(c.monto for c in comisiones if c.estado == 'pendiente')
        total_pagada    = sum(c.monto for c in comisiones if c.estado == 'pagada')
        vendedores = User.query.filter(User.activo == True).order_by(User.nombre).all()
        return render_template('ventas/comisiones.html',
                               comisiones=comisiones,
                               total_pendiente=total_pendiente,
                               total_pagada=total_pagada,
                               vendedores=vendedores,
                               buscar=buscar,
                               vendedor_f=vendedor_f,
                               estado_f=estado_f,
                               periodo_f=periodo_f)


    # ── ventas_comision_pagar (/ventas/comisiones/<id>/pagar)
    @app.route('/ventas/comisiones/<int:id>/pagar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def ventas_comision_pagar(id):
        com = Comision.query.get_or_404(id)
        if com.estado != 'pagada':
            com.estado = 'pagada'
            db.session.commit()
            flash('Comisión marcada como pagada.', 'success')
        else:
            flash('La comisión ya estaba pagada.', 'info')
        return redirect(url_for('ventas_comisiones'))


    # ── cotizaciones (/cotizaciones)
    @app.route('/cotizaciones')
    @login_required
    @requiere_modulo('ventas')
    def cotizaciones():
        _marcar_vencidas()
        servicios = tenant_query(Servicio).filter_by(activo=True).all()
        buscar = request.args.get('buscar','').strip()
        estado_f = request.args.get('estado','')
        q = tenant_query(Cotizacion)
        if buscar:
            q = q.filter(db.or_(Cotizacion.titulo.ilike(f'%{buscar}%'), Cotizacion.numero.ilike(f'%{buscar}%')))
        if estado_f:
            q = q.filter_by(estado=estado_f)
        items = q.order_by(Cotizacion.fecha_emision.desc()).all()
        return render_template('cotizaciones/index.html', items=items, servicios=servicios,
                               buscar=buscar, estado_f=estado_f)


    # ── cotizacion_nueva (/cotizaciones/nueva)
    @app.route('/cotizaciones/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ventas')
    def cotizacion_nueva():
        from datetime import date as date_t
        clientes_list = tenant_query(Cliente).order_by(Cliente.empresa, Cliente.nombre).all()
        regla_iva = tenant_query(ReglaTributaria).filter_by(aplica_a='ventas', activo=True).first()
        iva_default = regla_iva.porcentaje if regla_iva else 19.0
        if request.method == 'POST':
            hoy = date_t.today()
            # Generar número secuencial
            ultimo = tenant_query(Cotizacion).filter(
                Cotizacion.numero.like(f'COT-{hoy.year}-%')
            ).order_by(Cotizacion.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except Exception: seq = 1
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

            iva_incluido = bool(request.form.get('iva_incluido'))
            producto_ids = request.form.getlist('item_producto_id[]')

            items_data = []
            subtotal = 0.0
            iva_total = 0.0
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = _parse_decimal(cantidades[i]) if i < len(cantidades) else 1.0
                precio = _parse_decimal(precios[i]) if i < len(precios) else 0.0
                unidad = unidades[i] if i < len(unidades) else 'unidades'
                tipo = tipos[i] if i < len(tipos) else 'producto'
                srv_id = int(servicio_ids[i]) if i < len(servicio_ids) and servicio_ids[i].strip() else None
                prod_id = int(producto_ids[i]) if i < len(producto_ids) and producto_ids[i].strip() else None
                aplica_iva = aplica_ivas[i] if i < len(aplica_ivas) else 'on'
                aplica_iva = aplica_iva == 'on'
                iva_pct = float(iva_pcts[i]) if i < len(iva_pcts) else 0.0
                if not aplica_iva:
                    iva_pct = 0.0

                # Frontend always sends base price (without IVA)
                sub = cant * precio
                iva_monto = sub * iva_pct / 100.0 if aplica_iva else 0.0
                subtotal += sub
                iva_total += iva_monto

                items_data.append({
                    'nombre': nm, 'cantidad': cant, 'precio': precio, 'subtotal': sub,
                    'unidad': unidad, 'tipo': tipo, 'servicio_id': srv_id,
                    'aplica_iva': aplica_iva, 'iva_pct': iva_pct, 'iva_monto': iva_monto,
                    'producto_id': prod_id
                })

            total = subtotal + iva_total
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)
            monto_anticipo = total * pct_anticipo / 100.0
            saldo = total - monto_anticipo

            # Calcular fecha_entrega_est considerando dias_tipo
            fecha_emision = datetime.strptime(fd_em,'%Y-%m-%d').date() if fd_em else date_t.today()
            dias_ent = int(request.form.get('dias_entrega', 30) or 30)
            fecha_ent_est = _calc_fecha_entrega(fecha_emision, dias_ent, dias_tipo)

            cot = Cotizacion(
                company_id=getattr(g, 'company_id', None),
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
                iva_incluido=iva_incluido,
                estado='borrador', creado_por=current_user.id)
            db.session.add(cot); db.session.flush()
            for it in items_data:
                db.session.add(CotizacionItem(
                    cotizacion_id=cot.id, nombre_prod=it['nombre'],
                    producto_id=it.get('producto_id'),
                    cantidad=it['cantidad'], precio_unit=it['precio'], subtotal=it['subtotal'],
                    unidad=it['unidad'], tipo_item=it['tipo'], servicio_id=it['servicio_id'],
                    aplica_iva=it['aplica_iva'], iva_pct=it['iva_pct'], iva_monto=it['iva_monto']))
            # Actualizar precio del producto con precio total (IVA incluido)
            for it in items_data:
                if it.get('producto_id') and it['tipo'] == 'producto':
                    prod = db.session.get(Producto, it['producto_id'])
                    if not prod:
                        continue
                    # Calcular precio con IVA para guardar en producto
                    # Frontend sends base price — add IVA for storage in Producto.precio
                    precio_con_iva = round(it['precio'] * (1 + it['iva_pct'] / 100), 2) if it['iva_pct'] > 0 else round(it['precio'], 2)
                    if prod.precio != precio_con_iva:
                        db.session.add(HistorialPrecio(
                            producto_id=prod.id,
                            precio_anterior=prod.precio or 0,
                            precio_nuevo=precio_con_iva,
                            origen=f'cotizacion {numero}',
                            usuario_id=current_user.id
                        ))
                        prod.precio = precio_con_iva
                        receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
                        if receta:
                            receta.precio_venta_sugerido = precio_con_iva
            _log('crear','cotizacion',cot.id,f'Cotización {numero}: {cot.titulo}'); db.session.commit()
            flash(f'Cotización {numero} creada.','success')
            return redirect(url_for('cotizacion_ver', id=cot.id))

        # Construir lista de productos con precio correcto desde receta
        prods_cot = []
        for p in tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all():
            receta = RecetaProducto.query.filter_by(producto_id=p.id, activo=True).first()
            precio_venta = receta.precio_venta_sugerido if receta and receta.precio_venta_sugerido else p.precio or 0
            costo = receta.costo_calculado if receta and receta.costo_calculado else p.costo_receta or p.costo or 0
            prods_cot.append({
                'id': p.id, 'nombre': p.nombre, 'sku': p.sku or '',
                'precio': p.precio or 0,
                'precio_venta_sugerido': precio_venta,
                'costo_receta': costo
            })
        # NSOs y documentos legales vinculados a productos
        docs_legales = [{'id':d.id, 'titulo':d.titulo, 'tipo':d.tipo,
                         'numero':d.numero or '', 'entidad':d.entidad or '',
                         'producto_id':d.producto_id or 0,
                         'producto_nombre': d.producto.nombre if d.producto_id and d.producto else ''}
                        for d in tenant_query(DocumentoLegal).filter_by(activo=True).all()
                        if d.producto_id]
        nsos = [dl for dl in docs_legales if dl['tipo'] == 'nso']
        # Pre-fill de envío si viene del simulador de logística
        envio_prefill = None
        if request.args.get('servicio_envio'):
            envio_prefill = {
                'titulo': request.args.get('titulo', ''),
                'vehiculo': request.args.get('envio_vehiculo', ''),
                'modo': request.args.get('envio_modo', ''),
                'costo': int(request.args.get('envio_costo', 0)),
                'dist': request.args.get('envio_dist', ''),
                'cajas': request.args.get('envio_cajas', ''),
                'uds': request.args.get('envio_uds', ''),
            }
        return render_template('cotizaciones/form.html', obj=None, titulo='Nueva Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default, servicios_json=_servicios_json(), prods_json=prods_cot,
            nsos_json=nsos, docs_legales_json=docs_legales, envio_prefill=envio_prefill)


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
    @requiere_modulo('ventas')
    def cotizacion_ver(id):
        obj = Cotizacion.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first() or ConfigEmpresa(nombre='Evore')
        historial = HistorialCotizacion.query.filter_by(cotizacion_id=id).order_by(HistorialCotizacion.creado_en.desc()).all()
        return render_template('cotizaciones/ver.html', obj=obj, empresa=empresa, historial=historial)


    # ── cotizacion_editar (/cotizaciones/<int:id>/editar)
    @app.route('/cotizaciones/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ventas')
    def cotizacion_editar(id):
        from datetime import date as date_t
        obj = Cotizacion.query.get_or_404(id)
        clientes_list = tenant_query(Cliente).order_by(Cliente.empresa, Cliente.nombre).all()
        regla_iva = tenant_query(ReglaTributaria).filter_by(aplica_a='ventas', activo=True).first()
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

            iva_incluido = bool(request.form.get('iva_incluido'))
            producto_ids = request.form.getlist('item_producto_id[]')

            subtotal = 0.0
            iva_total = 0.0
            items_editados = []
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = _parse_decimal(cantidades[i]) if i < len(cantidades) else 1.0
                precio = _parse_decimal(precios[i]) if i < len(precios) else 0.0
                unidad = unidades[i] if i < len(unidades) else 'unidades'
                tipo = tipos[i] if i < len(tipos) else 'producto'
                srv_id = int(servicio_ids[i]) if i < len(servicio_ids) and servicio_ids[i].strip() else None
                prod_id = int(producto_ids[i]) if i < len(producto_ids) and producto_ids[i].strip() else None
                aplica_iva = aplica_ivas[i] if i < len(aplica_ivas) else 'on'
                aplica_iva = aplica_iva == 'on'
                iva_pct = float(iva_pcts[i]) if i < len(iva_pcts) else 0.0
                if not aplica_iva:
                    iva_pct = 0.0

                # Frontend always sends base price (without IVA)
                sub = cant * precio
                iva_monto = sub * iva_pct / 100.0 if aplica_iva else 0.0
                subtotal += sub
                iva_total += iva_monto

                db.session.add(CotizacionItem(
                    cotizacion_id=obj.id, nombre_prod=nm,
                    producto_id=prod_id,
                    cantidad=cant, precio_unit=precio, subtotal=sub,
                    unidad=unidad, tipo_item=tipo, servicio_id=srv_id,
                    aplica_iva=aplica_iva, iva_pct=iva_pct, iva_monto=iva_monto))
                items_editados.append({'producto_id': prod_id, 'precio': precio, 'tipo': tipo, 'iva_pct': iva_pct})

            total = subtotal + iva_total
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)

            fecha_emision = datetime.strptime(fd_em,'%Y-%m-%d').date() if fd_em else obj.fecha_emision
            dias_ent = int(request.form.get('dias_entrega', 30) or 30)
            fecha_ent_est = _calc_fecha_entrega(fecha_emision, dias_ent, dias_tipo)

            # Registrar cambios y actualizar precios
            cambios = []
            if obj.total != total:
                cambios.append(f'Total: ${obj.total:,.0f} → ${total:,.0f}')
            if obj.titulo != request.form['titulo']:
                cambios.append(f'Título: "{obj.titulo}" → "{request.form["titulo"]}"')
            for it in items_editados:
                if it.get('producto_id') and it['tipo'] == 'producto':
                    prod = db.session.get(Producto, it['producto_id'])
                    if not prod:
                        continue
                    # Frontend sends base price — add IVA for storage in Producto.precio
                    iva_pct_item = float(it.get('iva_pct', 0) or 0)
                    precio_con_iva = it['precio'] * (1 + iva_pct_item / 100) if iva_pct_item > 0 else it['precio']
                    precio_con_iva = round(precio_con_iva, 2)
                    if prod.precio != precio_con_iva:
                        cambios.append(f'Precio {prod.nombre}: ${prod.precio:,.0f} → ${precio_con_iva:,.0f}')
                        db.session.add(HistorialPrecio(
                            producto_id=prod.id,
                            precio_anterior=prod.precio or 0,
                            precio_nuevo=precio_con_iva,
                            origen=f'cotizacion {obj.numero}',
                            usuario_id=current_user.id
                        ))
                        prod.precio = precio_con_iva
                        receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
                        if receta:
                            receta.precio_venta_sugerido = precio_con_iva
            if cambios:
                db.session.add(HistorialCotizacion(
                    cotizacion_id=obj.id,
                    cambios=' | '.join(cambios),
                    usuario_id=current_user.id
                ))

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
            obj.iva_incluido = iva_incluido
            db.session.commit()
            flash('Cotización actualizada.','success')
            return redirect(url_for('cotizacion_ver', id=obj.id))

        prods_cot = []
        for p in tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all():
            receta = RecetaProducto.query.filter_by(producto_id=p.id, activo=True).first()
            precio_venta = receta.precio_venta_sugerido if receta and receta.precio_venta_sugerido else p.precio or 0
            costo = receta.costo_calculado if receta and receta.costo_calculado else p.costo_receta or p.costo or 0
            prods_cot.append({
                'id': p.id, 'nombre': p.nombre, 'sku': p.sku or '',
                'precio': p.precio or 0,
                'precio_venta_sugerido': precio_venta,
                'costo_receta': costo
            })
        docs_legales = [{'id':d.id, 'titulo':d.titulo, 'tipo':d.tipo,
                         'numero':d.numero or '', 'entidad':d.entidad or '',
                         'producto_id':d.producto_id or 0,
                         'producto_nombre': d.producto.nombre if d.producto_id and d.producto else ''}
                        for d in tenant_query(DocumentoLegal).filter_by(activo=True).all()
                        if d.producto_id]
        nsos = [dl for dl in docs_legales if dl['tipo'] == 'nso']
        return render_template('cotizaciones/form.html', obj=obj, titulo='Editar Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default, servicios_json=_servicios_json(), prods_json=prods_cot,
            nsos_json=nsos, docs_legales_json=docs_legales)


    # ── cotizacion_cambiar_estado (/cotizaciones/<int:id>/estado)
    @app.route('/cotizaciones/<int:id>/estado', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
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
                    logging.warning(f'_procesar_orden_produccion error: {ep}')
            flash(f'Estado actualizado a: {nuevo}.','success')
        return redirect(url_for('cotizacion_ver', id=id))


    # ── cotizacion_eliminar (/cotizaciones/<int:id>/eliminar)
    @app.route('/cotizaciones/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
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
    @requiere_modulo('ventas')
    def cotizacion_pdf(id):
        obj = Cotizacion.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first() or ConfigEmpresa(nombre='Evore')
        return render_template('cotizaciones/pdf.html', obj=obj, empresa=empresa)


    # ── cotizacion_enviar_email (/cotizaciones/<int:id>/enviar-email)
    @app.route('/cotizaciones/<int:id>/enviar-email', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def cotizacion_enviar_email(id):
        obj = Cotizacion.query.get_or_404(id)
        cliente = obj.cliente
        email_destino = None
        if cliente and cliente.contactos:
            for c in cliente.contactos:
                if c.email:
                    email_destino = c.email
                    break
        if not email_destino and cliente:
            email_destino = getattr(cliente, 'email', None)
        if not email_destino:
            flash('El cliente no tiene email registrado en sus contactos.', 'danger')
            return redirect(url_for('cotizacion_ver', id=id))
        try:
            empresa = ConfigEmpresa.query.first() or ConfigEmpresa(nombre='Evore')
            cuerpo = render_template('cotizaciones/email_body.html', obj=obj, empresa=empresa)
            asunto = f'Cotizacion {obj.numero} — {empresa.nombre}'
            _send_email(email_destino, asunto, cuerpo)
            obj.estado = 'enviada'
            db.session.commit()
            flash(f'Cotizacion enviada a {email_destino}.', 'success')
        except Exception as ex:
            logging.warning(f'cotizacion_enviar_email: {ex}')
            flash(f'Error al enviar email: {ex}', 'danger')
        return redirect(url_for('cotizacion_ver', id=id))


    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE v33 — Conversión Cotización → Venta
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/cotizaciones/<int:id>/convertir', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def cotizacion_convertir_a_venta(id):
        """Convierte una cotización en venta copiando todos los datos e items."""
        cot = Cotizacion.query.get_or_404(id)

        # Validar que no esté ya vinculada a una venta
        venta_existente = tenant_query(Venta).filter_by(cotizacion_id=cot.id).first()
        if venta_existente:
            flash(f'Esta cotización ya está vinculada a la venta {venta_existente.numero}.', 'warning')
            return redirect(url_for('cotizacion_ver', id=id))

        # Generar número VNT-YYYY-NNN
        hoy = datetime.utcnow().date()
        ultimo_vnt = tenant_query(Venta).filter(
            Venta.numero.like(f'VNT-{hoy.year}-%')
        ).order_by(Venta.id.desc()).first()
        if ultimo_vnt and ultimo_vnt.numero:
            try: seq = int(ultimo_vnt.numero.split('-')[-1]) + 1
            except Exception: seq = 1
        else: seq = 1
        numero_venta = f'VNT-{hoy.year}-{seq:03d}'

        # Crear venta desde cotización
        v = Venta(
            company_id=getattr(g, 'company_id', None),
            titulo=cot.titulo,
            numero=numero_venta,
            cliente_id=cot.cliente_id,
            subtotal=cot.subtotal,
            iva=cot.iva,
            total=cot.total,
            porcentaje_anticipo=cot.porcentaje_anticipo,
            monto_anticipo=cot.monto_anticipo,
            saldo=cot.saldo,
            estado='negociacion',
            dias_entrega=cot.dias_entrega,
            fecha_entrega_est=cot.fecha_entrega_est,
            notas=cot.notas or '',
            cotizacion_id=cot.id,
            creado_por=current_user.id
        )
        db.session.add(v); db.session.flush()

        # Copiar items
        for item in cot.items:
            db.session.add(VentaProducto(
                venta_id=v.id,
                producto_id=item.producto_id,
                servicio_id=item.servicio_id if hasattr(item, 'servicio_id') else None,
                nombre_prod=item.nombre_prod,
                cantidad=item.cantidad,
                precio_unit=item.precio_unit,
                subtotal=item.subtotal,
                unidad=getattr(item, 'unidad', 'unidades'),
                es_servicio=(getattr(item, 'tipo_item', 'producto') == 'servicio')
            ))

        # Marcar cotización como aprobada
        if cot.estado not in ('aprobada', 'vencida'):
            cot.estado = 'aprobada'

        # Procesar producción automáticamente
        try:
            db.session.flush()
            _procesar_venta_produccion(v)
        except Exception as ep:
            logging.warning(f'cotizacion_convertir: produccion error: {ep}')

        _log('crear', 'venta', v.id, f'Venta {numero_venta} creada desde cotización {cot.numero}')
        db.session.commit()
        flash(f'Venta {numero_venta} creada desde cotización {cot.numero}.', 'success')
        return redirect(url_for('venta_editar', id=v.id))


    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE v33 — Registro de pagos y reconciliación
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/ventas/<int:id>/pago', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def venta_registrar_pago(id):
        """Registra un pago parcial o total para una venta."""
        venta = Venta.query.get_or_404(id)
        monto = float(request.form.get('monto', 0) or 0)
        if monto <= 0:
            flash('El monto del pago debe ser mayor a 0.', 'danger')
            return redirect(url_for('venta_editar', id=id))

        tipo_pago = request.form.get('tipo_pago', 'parcial')
        metodo = request.form.get('metodo_pago', 'transferencia')
        referencia = request.form.get('referencia', '').strip() or None
        fecha_str = request.form.get('fecha_pago')
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date() if fecha_str else datetime.utcnow().date()
        notas = request.form.get('notas_pago', '').strip()

        pago = PagoVenta(
            venta_id=venta.id,
            monto=monto,
            tipo=tipo_pago,
            metodo_pago=metodo,
            referencia=referencia,
            fecha=fecha,
            notas=notas,
            creado_por=current_user.id
        )
        db.session.add(pago)

        # Actualizar totales de la venta (con cap — no puede pagar más del total)
        venta.monto_pagado_total = min((venta.monto_pagado_total or 0) + monto, float(venta.total or 0))
        venta.saldo = max(0, float(venta.total or 0) - (venta.monto_pagado_total or 0))

        # Auto-transicionar estado si corresponde
        if venta.monto_pagado_total >= (venta.monto_anticipo or 0) and venta.estado == 'negociacion':
            venta.estado = 'anticipo_pagado'
            venta.fecha_anticipo = fecha
            from services.inventario import InventarioService
            InventarioService.reservar_stock_venta(venta)
            flash('Anticipo confirmado. Estado actualizado a "Anticipo Pagado".', 'info')
        if venta.monto_pagado_total >= (venta.total or 0) and venta.estado in ('anticipo_pagado', 'negociacion'):
            venta.estado = 'pagado'
            flash('Pago total confirmado. Estado actualizado a "Pagado".', 'info')

        # Crear asiento contable automático
        _crear_asiento_auto(
            tipo='venta', subtipo=f'pago_{tipo_pago}',
            descripcion=f'Pago {tipo_pago} venta {venta.numero or venta.id}: ${monto:,.0f}',
            monto=monto,
            cuenta_debe='Bancos / Caja',
            cuenta_haber='Cuentas por cobrar clientes',
            clasificacion='ingreso',
            referencia=referencia or venta.numero,
            venta_id=venta.id
        )

        _log('crear', 'pago', pago.id, f'Pago ${monto:,.0f} registrado en venta {venta.numero}')
        db.session.commit()
        flash(f'Pago de ${monto:,.0f} registrado. Saldo pendiente: ${venta.saldo:,.0f}', 'success')
        return redirect(url_for('venta_editar', id=id))
