# routes/compras.py
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
    @app.route('/ordenes-compra')
    @login_required
    def ordenes_compra():
        estado_f = request.args.get('estado','')
        q = OrdenCompra.query
        if estado_f: q = q.filter_by(estado=estado_f)
        return render_template('ordenes_compra/index.html',
                               items=q.order_by(OrdenCompra.creado_en.desc()).all(),
                               estado_f=estado_f)

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

    @app.route('/ordenes-compra/<int:id>/estado', methods=['POST'])
    @login_required
    def orden_compra_estado(id):
        obj = OrdenCompra.query.get_or_404(id)
        estado_anterior = obj.estado
        obj.estado = request.form.get('estado', obj.estado)
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

    @app.route('/ordenes_compra/<int:id>/pdf')
    @login_required
    def oc_pdf(id):
        oc = OrdenCompra.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('ordenes_compra/pdf.html', oc=oc, empresa=empresa)
