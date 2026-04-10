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
        return {str(p.id): {'nombre': p.nombre, 'precio': float(p.precio or 0), 'stock': float(p.stock or 0)}
                for p in Producto.query.filter_by(activo=True).all()}

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


    # ── ventas (/ventas)
    @app.route('/ventas')
    @login_required
    def ventas():
        estado_f=request.args.get('estado','')
        q=Venta.query
        if estado_f: q=q.filter_by(estado=estado_f)
        return render_template('ventas/index.html', items=q.order_by(Venta.creado_en.desc()).all(), estado_f=estado_f)
    

    # ── venta_nueva (/ventas/nueva)
    @app.route('/ventas/nueva', methods=['GET','POST'])
    @login_required
    def venta_nueva():
        cl = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        if request.method == 'POST':
            fa = request.form.get('fecha_anticipo')
            fe = request.form.get('fecha_entrega_est')
            v = Venta(titulo=request.form['titulo'],
                cliente_id=request.form.get('cliente_id') or None,
                subtotal=float(request.form.get('subtotal_calc') or 0),
                iva=float(request.form.get('iva_calc') or 0),
                total=float(request.form.get('total_calc') or 0),
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
            _save_items(v); db.session.flush()
            _procesar_venta_produccion(v)
            _noop('crear','venta',v.id,f'Venta creada: {v.titulo} ({v.numero})'); db.session.commit()
            flash('Venta creada.','success'); return redirect(url_for('ventas'))
        return render_template('ventas/form.html', obj=None, clientes_list=cl,
                               titulo='Nueva Venta', productos_json=_prods_json(), items_json=[])
    

    # ── venta_editar (/ventas/<int:id>/editar)
    @app.route('/ventas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def venta_editar(id):
        obj = Venta.query.get_or_404(id)
        cl  = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        if request.method == 'POST':
            fa = request.form.get('fecha_anticipo')
            fe = request.form.get('fecha_entrega_est')
            obj.titulo=request.form['titulo']; obj.cliente_id=request.form.get('cliente_id') or None
            obj.subtotal=float(request.form.get('subtotal_calc') or 0)
            obj.iva=float(request.form.get('iva_calc') or 0)
            obj.total=float(request.form.get('total_calc') or 0)
            obj.porcentaje_anticipo=float(request.form.get('porcentaje_anticipo') or 0)
            obj.monto_anticipo=float(request.form.get('monto_anticipo') or 0)
            obj.saldo=float(request.form.get('saldo') or 0)
            obj.estado=request.form.get('estado','prospecto')
            obj.fecha_anticipo=datetime.strptime(fa,'%Y-%m-%d').date() if fa else None
            obj.dias_entrega=int(request.form.get('dias_entrega') or 30)
            obj.fecha_entrega_est=datetime.strptime(fe,'%Y-%m-%d').date() if fe else None
            obj.notas=request.form.get('notas','')
            db.session.flush(); _save_items(obj); db.session.flush()
            _procesar_venta_produccion(obj)
            _noop('editar','venta',obj.id,f'Venta editada: {obj.titulo}'); db.session.commit()
            flash('Venta actualizada.','success'); return redirect(url_for('ventas'))
        items_j = [{'pid':it.producto_id or '','nombre':it.nombre_prod,
                    'cant':it.cantidad,'precio':it.precio_unit} for it in obj.items]
        return render_template('ventas/form.html', obj=obj, clientes_list=cl,
                               titulo='Editar Venta', productos_json=_prods_json(), items_json=items_j)
    

    # ── venta_eliminar (/ventas/<int:id>/eliminar)
    @app.route('/ventas/<int:id>/eliminar', methods=['POST'])
    @login_required
    def venta_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar ventas.', 'danger')
            return redirect(url_for('ventas'))
        obj = Venta.query.get_or_404(id)
        try:
            ReservaProduccion.query.filter_by(venta_id=obj.id).delete()
            OrdenProduccion.query.filter_by(venta_id=obj.id).delete()
            db.session.flush()
        except Exception as e:
            db.session.rollback()
        db.session.delete(obj)
        db.session.commit()
        _noop('eliminar','venta',id,'Venta eliminada'); db.session.commit()
        flash('Venta eliminada.', 'info')
        return redirect(url_for('ventas'))
    

    # ── venta_cambiar_estado (/ventas/<int:id>/estado)
    @app.route('/ventas/<int:id>/estado', methods=['POST'])
    @login_required
    def venta_cambiar_estado(id):
        venta = Venta.query.get_or_404(id)
        nuevo = request.form.get('estado', '')
        estados_validos = ['prospecto','negociacion','anticipo_pagado','completado','perdido']
        if nuevo in estados_validos:
            venta.estado = nuevo
            _noop('editar','venta',venta.id,f'Estado → {nuevo}'); db.session.commit()
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
        venta.entregado_en = datetime.utcnow()
        # Descontar stock de productos entregados
        _descontar_stock_venta(venta)
        # Marcar órdenes de producción vinculadas como listas
        db.session.commit()
        flash(f'Venta marcada como entregada. Stock descontado del inventario.','success')
        return redirect(url_for('ventas'))
    

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
        items = Cotizacion.query.order_by(Cotizacion.fecha_emision.desc()).all()
        return render_template('cotizaciones/index.html', items=items)
    

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
            iva_pct = float(request.form.get('iva_pct', iva_default) or iva_default)
            nombres = request.form.getlist('item_nombre[]')
            cantidades = request.form.getlist('item_cantidad[]')
            precios = request.form.getlist('item_precio[]')
            items_data = []
            subtotal = 0.0
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = float(cantidades[i]) if i < len(cantidades) else 1.0
                precio = float(precios[i]) if i < len(precios) else 0.0
                sub = cant * precio
                subtotal += sub
                items_data.append({'nombre': nm, 'cantidad': cant, 'precio': precio, 'subtotal': sub})
            iva_monto = subtotal * iva_pct / 100.0
            total = subtotal + iva_monto
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)
            monto_anticipo = total * pct_anticipo / 100.0
            saldo = total - monto_anticipo
            cot = Cotizacion(
                numero=numero,
                titulo=request.form['titulo'],
                cliente_id=request.form.get('cliente_id') or None,
                subtotal=subtotal, iva=iva_monto, total=total,
                porcentaje_anticipo=pct_anticipo,
                monto_anticipo=monto_anticipo, saldo=saldo,
                fecha_emision=datetime.strptime(fd_em,'%Y-%m-%d').date() if fd_em else date_t.today(),
                fecha_validez=datetime.strptime(fd_val,'%Y-%m-%d').date() if fd_val else None,
                dias_entrega=int(request.form.get('dias_entrega',30) or 30),
                condiciones_pago=request.form.get('condiciones_pago',''),
                notas=request.form.get('notas',''),
                estado='borrador', creado_por=current_user.id)
            db.session.add(cot); db.session.flush()
            for it in items_data:
                db.session.add(CotizacionItem(
                    cotizacion_id=cot.id, nombre_prod=it['nombre'],
                    cantidad=it['cantidad'], precio_unit=it['precio'], subtotal=it['subtotal']))
            _noop('crear','cotizacion',cot.id,f'Cotización {numero}: {cot.titulo}'); db.session.commit()
            flash(f'Cotización {numero} creada.','success')
            return redirect(url_for('cotizacion_ver', id=cot.id))
        return render_template('cotizaciones/form.html', obj=None, titulo='Nueva Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default)
    

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
            iva_pct = float(request.form.get('iva_pct', iva_default) or iva_default)
            nombres = request.form.getlist('item_nombre[]')
            cantidades = request.form.getlist('item_cantidad[]')
            precios = request.form.getlist('item_precio[]')
            # Borrar items existentes
            for it in obj.items: db.session.delete(it)
            db.session.flush()
            subtotal = 0.0
            for i in range(len(nombres)):
                nm = nombres[i].strip() if i < len(nombres) else ''
                if not nm: continue
                cant = float(cantidades[i]) if i < len(cantidades) else 1.0
                precio = float(precios[i]) if i < len(precios) else 0.0
                sub = cant * precio
                subtotal += sub
                db.session.add(CotizacionItem(
                    cotizacion_id=obj.id, nombre_prod=nm,
                    cantidad=cant, precio_unit=precio, subtotal=sub))
            iva_monto = subtotal * iva_pct / 100.0
            total = subtotal + iva_monto
            pct_anticipo = float(request.form.get('porcentaje_anticipo', 50) or 50)
            obj.titulo = request.form['titulo']
            obj.cliente_id = request.form.get('cliente_id') or None
            obj.subtotal = subtotal; obj.iva = iva_monto; obj.total = total
            obj.porcentaje_anticipo = pct_anticipo
            obj.monto_anticipo = total * pct_anticipo / 100.0
            obj.saldo = total - obj.monto_anticipo
            if fd_em: obj.fecha_emision = datetime.strptime(fd_em,'%Y-%m-%d').date()
            obj.fecha_validez = datetime.strptime(fd_val,'%Y-%m-%d').date() if fd_val else None
            obj.dias_entrega = int(request.form.get('dias_entrega',30) or 30)
            obj.condiciones_pago = request.form.get('condiciones_pago','')
            obj.notas = request.form.get('notas','')
            db.session.commit()
            flash('Cotización actualizada.','success')
            return redirect(url_for('cotizacion_ver', id=obj.id))
        return render_template('cotizaciones/form.html', obj=obj, titulo='Editar Cotización',
            clientes_list=clientes_list, today=datetime.utcnow().strftime('%Y-%m-%d'),
            iva_default=iva_default)
    

    # ── cotizacion_cambiar_estado (/cotizaciones/<int:id>/estado)
    @app.route('/cotizaciones/<int:id>/estado', methods=['POST'])
    @login_required
    def cotizacion_cambiar_estado(id):
        obj = Cotizacion.query.get_or_404(id)
        nuevo = request.form.get('estado','borrador')
        if nuevo in ('borrador','enviada','aprobada','confirmacion_orden'):
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
    
