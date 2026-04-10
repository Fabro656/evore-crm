# routes/compras.py — reconstruido desde v27 con CRUD completo
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
    def _oc_save_items(oc_id):
        nombres = request.form.getlist('item_nombre[]')
        descs   = request.form.getlist('item_desc[]')
        cants   = request.form.getlist('item_cant[]')
        units   = request.form.getlist('item_unidad[]')
        precios = request.form.getlist('item_precio[]')
        cot_ids = request.form.getlist('item_cot_id[]')
        items = []
        for i, nom in enumerate(nombres):
            if not nom.strip(): continue
            cant   = float(cants[i])   if i < len(cants)   else 1
            precio = float(precios[i]) if i < len(precios) else 0
            cot_id = int(cot_ids[i]) if i < len(cot_ids) and cot_ids[i].strip() else None
            items.append(OrdenCompraItem(
                orden_id=oc_id, nombre_item=nom.strip(),
                descripcion=descs[i] if i < len(descs) else '',
                cantidad=cant, unidad=units[i] if i < len(units) else 'unidades',
                precio_unit=precio, subtotal=cant*precio, cotizacion_id=cot_id))
        return items


    # ── cotizaciones_proveedor (/cotizaciones-proveedor)
    @app.route('/cotizaciones-proveedor')
    @login_required
    def cotizaciones_proveedor():
        estado_f = request.args.get('estado','')
        tipo_f   = request.args.get('tipo','')   # granel / general
        q = CotizacionProveedor.query
        if estado_f: q = q.filter_by(estado=estado_f)
        if tipo_f:   q = q.filter_by(tipo_cotizacion=tipo_f)
        items = q.order_by(CotizacionProveedor.creado_en.desc()).all()
        totales = {
            'granel':  CotizacionProveedor.query.filter_by(tipo_cotizacion='granel').count(),
            'general': CotizacionProveedor.query.filter_by(tipo_cotizacion='general').count(),
        }
        return render_template('proveedores/cotizaciones.html',
                               items=items, estado_f=estado_f, tipo_f=tipo_f, totales=totales)


    # ── cotizacion_proveedor_json (/cotizaciones-proveedor/<int:id>/json)
    @app.route('/cotizaciones-proveedor/<int:id>/json')
    @login_required
    def cotizacion_proveedor_json(id):
        """API para traer datos de cotización al formulario de OC"""
        cp = CotizacionProveedor.query.get_or_404(id)
        return jsonify({
            'id': cp.id,
            'numero': cp.numero,
            'nombre_producto': cp.nombre_producto,
            'descripcion': cp.descripcion or '',
            'sku': cp.sku or '',
            'precio_unitario': cp.precio_unitario,
            'unidades_minimas': cp.unidades_minimas,
            'unidad': cp.unidad,
            'plazo_entrega_dias': cp.plazo_entrega_dias or 0,
            'condicion_pago_tipo': cp.condicion_pago_tipo or 'contado',
            'condicion_pago_dias': cp.condicion_pago_dias or 0,
            'anticipo_porcentaje': cp.anticipo_porcentaje or 0,
            'proveedor_id': cp.proveedor_id,
        })


    # ── cotizacion_proveedor_nueva (/cotizaciones-proveedor/nueva)
    @app.route('/cotizaciones-proveedor/nueva', methods=['GET','POST'])
    @login_required
    def cotizacion_proveedor_nueva():
        provs = Proveedor.query.filter(Proveedor.activo==True,
            Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        tipo_default = request.args.get('tipo','general')
        if request.method == 'POST':
            fc = request.form.get('fecha_cotizacion')
            fv = request.form.get('vigencia')
            cp = CotizacionProveedor(
                proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None,
                tipo_cotizacion=request.form.get('tipo_cotizacion','general'),
                tipo_producto_servicio=request.form.get('tipo_producto_servicio',''),
                nombre_producto=request.form['nombre_producto'],
                descripcion=request.form.get('descripcion',''),
                sku=request.form.get('sku',''),
                precio_unitario=float(request.form.get('precio_unitario') or 0),
                unidades_minimas=int(request.form.get('unidades_minimas') or 1),
                unidad=request.form.get('unidad','unidades'),
                plazo_entrega=request.form.get('plazo_entrega',''),
                plazo_entrega_dias=int(request.form.get('plazo_entrega_dias') or 0),
                condiciones_pago=request.form.get('condiciones_pago',''),
                condicion_pago_tipo=request.form.get('condicion_pago_tipo','contado'),
                condicion_pago_dias=int(request.form.get('condicion_pago_dias') or 0),
                anticipo_porcentaje=float(request.form.get('anticipo_porcentaje') or 0),
                fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else datetime.utcnow().date(),
                vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
                estado=request.form.get('estado','vigente'),
                notas=request.form.get('notas',''),
                creado_por=current_user.id
            )
            db.session.add(cp); db.session.flush()
            hoy = datetime.utcnow().date()
            ultimo = CotizacionProveedor.query.filter(
                CotizacionProveedor.numero.like(f'CP-{hoy.year}-%')
            ).order_by(CotizacionProveedor.id.desc()).first()
            if ultimo and ultimo.numero:
                try: seq = int(ultimo.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            cp.numero = f'CP-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Cotización {cp.numero} creada.','success')
            return redirect(url_for('cotizaciones_proveedor', tipo=cp.tipo_cotizacion))
        return render_template('proveedores/cotizacion_form.html', obj=None,
                               proveedores_list=provs, titulo='Nueva Cotización Proveedor',
                               tipo_default=tipo_default)


    # ── cotizacion_proveedor_editar (/cotizaciones-proveedor/<int:id>/editar)
    @app.route('/cotizaciones-proveedor/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def cotizacion_proveedor_editar(id):
        obj = CotizacionProveedor.query.get_or_404(id)
        provs = Proveedor.query.filter(Proveedor.activo==True,
            Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        if request.method == 'POST':
            fc = request.form.get('fecha_cotizacion')
            fv = request.form.get('vigencia')
            obj.proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None
            obj.tipo_cotizacion=request.form.get('tipo_cotizacion','general')
            obj.tipo_producto_servicio=request.form.get('tipo_producto_servicio','')
            obj.nombre_producto=request.form.get('nombre_producto','')
            obj.descripcion=request.form.get('descripcion','')
            obj.sku=request.form.get('sku','')
            obj.precio_unitario=float(request.form.get('precio_unitario') or 0)
            obj.unidades_minimas=int(request.form.get('unidades_minimas') or 1)
            obj.unidad=request.form.get('unidad','unidades')
            obj.plazo_entrega=request.form.get('plazo_entrega','')
            obj.plazo_entrega_dias=int(request.form.get('plazo_entrega_dias') or 0)
            obj.condiciones_pago=request.form.get('condiciones_pago','')
            obj.condicion_pago_tipo=request.form.get('condicion_pago_tipo','contado')
            obj.condicion_pago_dias=int(request.form.get('condicion_pago_dias') or 0)
            obj.anticipo_porcentaje=float(request.form.get('anticipo_porcentaje') or 0)
            obj.fecha_cotizacion=datetime.strptime(fc,'%Y-%m-%d').date() if fc else obj.fecha_cotizacion
            obj.vigencia=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None
            obj.estado=request.form.get('estado','vigente')
            obj.notas=request.form.get('notas','')
            db.session.commit()
            flash('Cotización actualizada.','success')
            return redirect(url_for('cotizaciones_proveedor', tipo=obj.tipo_cotizacion))
        return render_template('proveedores/cotizacion_form.html', obj=obj,
                               proveedores_list=provs, titulo='Editar Cotización Proveedor',
                               tipo_default=obj.tipo_cotizacion)


    # ── cotizacion_proveedor_eliminar (/cotizaciones-proveedor/<int:id>/eliminar)
    @app.route('/cotizaciones-proveedor/<int:id>/eliminar', methods=['POST'])
    @login_required
    def cotizacion_proveedor_eliminar(id):
        obj = CotizacionProveedor.query.get_or_404(id)
        tipo = obj.tipo_cotizacion
        db.session.delete(obj); db.session.commit()
        flash('Cotización eliminada.','info')
        return redirect(url_for('cotizaciones_proveedor', tipo=tipo))


    # ── ordenes_compra (/ordenes-compra)
    @app.route('/ordenes-compra')
    @login_required
    def ordenes_compra():
        estado_f = request.args.get('estado','')
        q = OrdenCompra.query
        if estado_f: q = q.filter_by(estado=estado_f)
        return render_template('ordenes_compra/index.html',
                               items=q.order_by(OrdenCompra.creado_en.desc()).all(),
                               estado_f=estado_f)


    # ── oc_pdf (/ordenes_compra/<int:id>/pdf)
    @app.route('/ordenes_compra/<int:id>/pdf')
    @login_required
    def oc_pdf(id):
        oc = OrdenCompra.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('ordenes_compra/pdf.html', oc=oc, empresa=empresa)


    # ── orden_compra_nueva (/ordenes-compra/nueva)
    @app.route('/ordenes-compra/nueva', methods=['GET','POST'])
    @login_required
    def orden_compra_nueva():
        provs       = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        transportistas = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['transportista','ambos'])).order_by(Proveedor.nombre).all()
        cotizaciones_disponibles = CotizacionProveedor.query.filter_by(estado='vigente').order_by(CotizacionProveedor.nombre_producto).all()
        if request.method == 'POST':
            fe  = request.form.get('fecha_emision')
            fes = request.form.get('fecha_esperada')
            fep = request.form.get('fecha_estimada_pago')
            fer = request.form.get('fecha_estimada_recogida')
            frc = request.form.get('fecha_anticipo_real')
            cot_id = int(request.form.get('cotizacion_id')) if request.form.get('cotizacion_id') else None
            tra_id = int(request.form.get('transportista_id')) if request.form.get('transportista_id') else None
            fecha_emision = datetime.strptime(fe,'%Y-%m-%d').date() if fe else datetime.utcnow().date()
            # Calcular fecha_esperada desde cotización si no se ingresó manualmente
            fecha_esp = None
            if fes:
                fecha_esp = datetime.strptime(fes,'%Y-%m-%d').date()
            elif cot_id:
                cot_obj = db.session.get(CotizacionProveedor, cot_id)
                if cot_obj and cot_obj.plazo_entrega_dias:
                    fecha_esp = fecha_emision + timedelta(days=cot_obj.plazo_entrega_dias)
            oc = OrdenCompra(
                proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None,
                cotizacion_id=cot_id,
                transportista_id=tra_id,
                estado=request.form.get('estado','borrador'),
                fecha_emision=fecha_emision,
                fecha_esperada=fecha_esp,
                fecha_estimada_pago=datetime.strptime(fep,'%Y-%m-%d').date() if fep else None,
                fecha_estimada_recogida=datetime.strptime(fer,'%Y-%m-%d').date() if fer else None,
                fecha_anticipo_real=datetime.strptime(frc,'%Y-%m-%d').date() if frc else None,
                subtotal=float(request.form.get('subtotal_calc') or 0),
                iva=float(request.form.get('iva_calc') or 0),
                total=float(request.form.get('total_calc') or 0),
                notas=request.form.get('notas',''),
                creado_por=current_user.id
            )
            db.session.add(oc); db.session.flush()
            hoy = datetime.utcnow().date()
            ultimo_oc = OrdenCompra.query.filter(OrdenCompra.numero.like(f'OC-{hoy.year}-%')).order_by(OrdenCompra.id.desc()).first()
            if ultimo_oc and ultimo_oc.numero:
                try: seq = int(ultimo_oc.numero.split('-')[-1]) + 1
                except: seq = 1
            else: seq = 1
            oc.numero = f'OC-{hoy.year}-{seq:03d}'
            for it in _oc_save_items(oc.id): db.session.add(it)
            # Auto-tarea para transportista
            if tra_id and fer:
                tra = db.session.get(Proveedor, tra_id)
                fecha_rec = datetime.strptime(fer,'%Y-%m-%d').date()
                t = Tarea(titulo=f'Contratar transporte para OC {oc.numero}',
                          descripcion=f'Contactar a {tra.nombre or tra.empresa} para coordinar recogida el {fecha_rec.strftime("%d/%m/%Y")}. OC: {oc.numero}',
                          estado='pendiente', prioridad='alta',
                          fecha_vencimiento=fecha_rec - timedelta(days=2),
                          creado_por=current_user.id, tarea_tipo='contratar_transporte')
                db.session.add(t)
            db.session.commit()
            flash(f'Orden de compra {oc.numero} creada.','success')
            return redirect(url_for('ordenes_compra'))
        return render_template('ordenes_compra/form.html', obj=None,
                               proveedores_list=provs, transportistas_list=transportistas,
                               cotizaciones_list=cotizaciones_disponibles,
                               titulo='Nueva Orden de Compra', items_json=[])


    # ── orden_compra_editar (/ordenes-compra/<int:id>/editar)
    @app.route('/ordenes-compra/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def orden_compra_editar(id):
        obj = OrdenCompra.query.get_or_404(id)
        provs       = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        transportistas = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['transportista','ambos'])).order_by(Proveedor.nombre).all()
        cotizaciones_disponibles = CotizacionProveedor.query.filter_by(estado='vigente').order_by(CotizacionProveedor.nombre_producto).all()
        if request.method == 'POST':
            fe  = request.form.get('fecha_emision')
            fes = request.form.get('fecha_esperada')
            fep = request.form.get('fecha_estimada_pago')
            fer = request.form.get('fecha_estimada_recogida')
            frc = request.form.get('fecha_anticipo_real')
            cot_id = int(request.form.get('cotizacion_id')) if request.form.get('cotizacion_id') else None
            tra_id = int(request.form.get('transportista_id')) if request.form.get('transportista_id') else None
            fecha_emision = datetime.strptime(fe,'%Y-%m-%d').date() if fe else obj.fecha_emision
            fecha_esp = None
            if fes:
                fecha_esp = datetime.strptime(fes,'%Y-%m-%d').date()
            elif cot_id:
                cot_obj = db.session.get(CotizacionProveedor, cot_id)
                if cot_obj and cot_obj.plazo_entrega_dias:
                    fecha_esp = fecha_emision + timedelta(days=cot_obj.plazo_entrega_dias)
            obj.proveedor_id        = int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None
            obj.cotizacion_id       = cot_id
            obj.transportista_id    = tra_id
            obj.estado              = request.form.get('estado', obj.estado)
            obj.fecha_emision       = fecha_emision
            obj.fecha_esperada      = fecha_esp
            obj.fecha_estimada_pago = datetime.strptime(fep,'%Y-%m-%d').date() if fep else None
            obj.fecha_estimada_recogida = datetime.strptime(fer,'%Y-%m-%d').date() if fer else None
            obj.fecha_anticipo_real = datetime.strptime(frc,'%Y-%m-%d').date() if frc else None
            obj.subtotal = float(request.form.get('subtotal_calc') or 0)
            obj.iva      = float(request.form.get('iva_calc') or 0)
            obj.total    = float(request.form.get('total_calc') or 0)
            obj.notas    = request.form.get('notas','')
            OrdenCompraItem.query.filter_by(orden_id=obj.id).delete()
            for it in _oc_save_items(obj.id): db.session.add(it)
            db.session.commit()
            flash('Orden de compra actualizada.','success')
            return redirect(url_for('ordenes_compra'))
        items_json = [{'nombre':it.nombre_item,'desc':it.descripcion or '','cant':it.cantidad,
                       'unidad':it.unidad,'precio':it.precio_unit,'cot_id':it.cotizacion_id or ''} for it in obj.items]
        return render_template('ordenes_compra/form.html', obj=obj,
                               proveedores_list=provs, transportistas_list=transportistas,
                               cotizaciones_list=cotizaciones_disponibles,
                               titulo='Editar Orden de Compra', items_json=items_json)


    # ── orden_compra_estado (/ordenes-compra/<int:id>/estado)
    @app.route('/ordenes-compra/<int:id>/estado', methods=['POST'])
    @login_required
    def orden_compra_estado(id):
        obj = OrdenCompra.query.get_or_404(id)
        estado_anterior = obj.estado
        obj.estado = request.form.get('estado', obj.estado)

        # Al pasar de borrador → enviada: crear CompraMateria por cada ítem de la orden
        if obj.estado == 'enviada' and estado_anterior == 'borrador':
            for item in (obj.items or []):
                cant  = float(item.cantidad or 1)
                precio = float(item.precio_unit or 0)
                total  = float(item.subtotal or cant * precio)
                c = CompraMateria(
                    nombre_item=item.nombre_item or f'Ítem OC {obj.numero}',
                    tipo_compra='insumo',
                    proveedor=obj.proveedor.empresa if obj.proveedor else (obj.proveedor_id and str(obj.proveedor_id)) or '',
                    proveedor_id=obj.proveedor_id,
                    fecha=obj.fecha_emision or datetime.utcnow().date(),
                    nro_factura=obj.numero,
                    cantidad=cant,
                    unidad=item.unidad or 'unidades',
                    costo_producto=total,
                    impuestos=0,
                    transporte=0,
                    costo_total=total,
                    precio_unitario=precio,
                    notas=f'Generado automáticamente desde OC {obj.numero}',
                    creado_por=current_user.id,
                )
                db.session.add(c)
            if obj.items:
                flash(f'{len(obj.items)} ítem(s) de la OC {obj.numero} registrados en Compras automáticamente.', 'info')

        # Al marcar como "recibida": calcular fecha de entrega con plazo de cotización y agendar en calendario
        if obj.estado == 'recibida' and estado_anterior != 'recibida':
            hoy_recv = datetime.utcnow().date()
            cot = obj.cotizacion_ref
            if cot and cot.plazo_entrega_dias and not cot.calendario_integrado:
                fecha_entrega = hoy_recv + timedelta(days=cot.plazo_entrega_dias)
                ev = Evento(
                    titulo=f'Entrega esperada: {cot.nombre_producto} ({obj.numero})',
                    tipo='recordatorio',
                    fecha=fecha_entrega,
                    descripcion=f'OC {obj.numero} recibida el {hoy_recv.strftime("%d/%m/%Y")}. Entrega esperada en {cot.plazo_entrega_dias} días desde recepción. Proveedor: {obj.proveedor.nombre if obj.proveedor else "—"}',
                    usuario_id=current_user.id
                )
                db.session.add(ev)
                cot.calendario_integrado = True
            elif obj.fecha_esperada:
                # Si no hay cotizacion pero hay fecha_esperada, agendar igual
                ev = Evento(
                    titulo=f'Entrega esperada OC {obj.numero}',
                    tipo='recordatorio',
                    fecha=obj.fecha_esperada,
                    descripcion=f'Orden de compra {obj.numero} marcada como recibida. Entrega esperada: {obj.fecha_esperada.strftime("%d/%m/%Y")}.',
                    usuario_id=current_user.id
                )
                db.session.add(ev)
        db.session.commit()
        flash(f'Estado actualizado a "{obj.estado}".','success')
        return redirect(url_for('ordenes_compra'))


    # ── BLOQUE 4: oc_anticipo_recibido (/ordenes-compra/<int:id>/anticipo-recibido)
    @app.route('/ordenes-compra/<int:id>/anticipo-recibido', methods=['POST'])
    @login_required
    def oc_anticipo_recibido(id):
        """Registra la recepción del anticipo y recalcula fecha de entrega."""
        oc = OrdenCompra.query.get_or_404(id)
        fecha_real = request.form.get('fecha_anticipo_real')
        if fecha_real:
            oc.fecha_anticipo_real = datetime.strptime(fecha_real, '%Y-%m-%d').date()
            # Recalcular fecha esperada desde anticipo real
            if oc.fecha_anticipo_real and oc.cotizacion_id:
                cotprov = CotizacionProveedor.query.get(oc.cotizacion_id)
                if cotprov and cotprov.plazo_entrega_dias:
                    oc.fecha_esperada = oc.fecha_anticipo_real + timedelta(days=cotprov.plazo_entrega_dias)
        db.session.commit()
        flash('Anticipo registrado. Fecha de entrega actualizada.', 'success')
        return redirect(url_for('ordenes_compra'))


    # ── orden_compra_eliminar (/ordenes-compra/<int:id>/eliminar)
    @app.route('/ordenes-compra/<int:id>/eliminar', methods=['POST'])
    @login_required
    def orden_compra_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj = OrdenCompra.query.get_or_404(id)
        db.session.delete(obj); db.session.commit()
        flash('Orden de compra eliminada.','info')
        return redirect(url_for('ordenes_compra'))
