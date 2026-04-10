# routes/portal.py — reconstruido desde v27 con CRUD completo
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

    # ── portal_cliente (/portal)
    @app.route('/portal')
    @login_required
    def portal_cliente():
        if current_user.rol != 'cliente':
            return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente:
            flash('Tu cuenta no está vinculada a una empresa. Contacta al administrador.', 'warning')
            return render_template('portal/sin_empresa.html')
        ventas = Venta.query.filter_by(cliente_id=cliente.id).order_by(Venta.creado_en.desc()).limit(20).all()
        cotizaciones = Cotizacion.query.filter_by(cliente_id=cliente.id).order_by(Cotizacion.creado_en.desc()).limit(20).all()
        pre_cots = PreCotizacion.query.filter_by(cliente_id=cliente.id).order_by(PreCotizacion.creado_en.desc()).limit(10).all()
        mensajes = Tarea.query.filter(Tarea.titulo.like('[Mensaje]%'),
                                      db.or_(Tarea.creado_por==current_user.id,
                                             Tarea.asignado_a==cliente.sales_manager_id)).order_by(Tarea.creado_en.desc()).limit(50).all()
        sales_manager_user = db.session.get(User, cliente.sales_manager_id) if cliente.sales_manager_id else User.query.filter_by(rol='admin', activo=True).first()
        return render_template('portal/index.html', cliente=cliente, ventas=ventas,
                               cotizaciones=cotizaciones, pre_cots=pre_cots, mensajes=mensajes,
                               sales_manager_user=sales_manager_user)
    

    # ── portal_mensaje_nuevo (/portal/mensaje/nuevo)
    @app.route('/portal/mensaje/nuevo', methods=['POST'])
    @login_required
    def portal_mensaje_nuevo():
        if current_user.rol != 'cliente':
            return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente:
            flash('Sin empresa vinculada.', 'danger')
            return redirect(url_for('portal_cliente'))
        texto = request.form.get('mensaje', '').strip()
        if not texto:
            flash('El mensaje no puede estar vacío.', 'warning')
            return redirect(url_for('portal_cliente'))
        recipient_id = cliente.sales_manager_id
        if not recipient_id:
            admin = User.query.filter_by(rol='admin', activo=True).first()
            recipient_id = admin.id if admin else None
        t = Tarea(
            titulo=f'[Mensaje] {cliente.empresa or cliente.nombre}: {texto[:60]}',
            descripcion=texto,
            estado='pendiente', prioridad='media',
            asignado_a=recipient_id, creado_por=current_user.id)
        db.session.add(t)
        if recipient_id:
            db.session.flush()
            db.session.add(TareaAsignado(tarea_id=t.id, user_id=recipient_id))
            _crear_notificacion(recipient_id, 'info',
                f'Mensaje de {cliente.empresa or cliente.nombre}',
                texto[:120], url_for('portal_cliente'))
        db.session.commit()
        flash('Mensaje enviado.', 'success')
        return redirect(url_for('portal_cliente'))
    

    # ── portal_pre_cotizacion_nueva (/portal/pre-cotizacion/nueva)
    @app.route('/portal/pre-cotizacion/nueva', methods=['GET','POST'])
    @login_required
    def portal_pre_cotizacion_nueva():
        if current_user.rol != 'cliente':
            return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente:
            flash('Sin empresa vinculada.','danger'); return redirect(url_for('portal_cliente'))
        if request.method == 'POST':
            items_raw = []
            nombres = request.form.getlist('item_nombre[]')
            cantidades = request.form.getlist('item_cantidad[]')
            precios = request.form.getlist('item_precio[]')
            subtotal_total = 0
            for i, nom in enumerate(nombres):
                if not nom.strip(): continue
                qty = float(cantidades[i] or 0)
                prc = float(precios[i] or 0)
                sub = round(qty * prc, 2)
                subtotal_total += sub
                items_raw.append({'nombre': nom, 'cantidad': qty, 'precio': prc, 'subtotal': sub})
            iva = round(subtotal_total * 0.19, 2)
            total = subtotal_total + iva
            # Count pre-cots for numero
            cnt = PreCotizacion.query.count() + 1
            pc = PreCotizacion(
                numero=f'PC-{cnt:04d}',
                cliente_id=cliente.id,
                cliente_user_id=current_user.id,
                sales_manager_id=cliente.sales_manager_id,
                notas_cliente=request.form.get('notas',''),
                subtotal=subtotal_total, iva=iva, total=total
            )
            db.session.add(pc); db.session.flush()
            for it in items_raw:
                db.session.add(PreCotizacionItem(
                    precot_id=pc.id, nombre_prod=it['nombre'],
                    cantidad=it['cantidad'], precio_unit=it['precio'], subtotal=it['subtotal']
                ))
            db.session.commit()
            # Notify sales manager
            if cliente.sales_manager_id:
                _crear_notificacion(
                    cliente.sales_manager_id, 'info',
                    f'Pre-cotización pendiente de revisión: {pc.numero}',
                    f'{cliente.empresa or cliente.nombre} envió una pre-cotización por ${total:,.0f}',
                    url_for('portal_manager_revisar', id=pc.id)
                ); db.session.commit()
            flash(f'Pre-cotización {pc.numero} enviada. Tu sales manager la revisará pronto.', 'success')
            return redirect(url_for('portal_cliente'))
        empresa = ConfigEmpresa.query.first()
        return render_template('portal/pre_cotizacion_form.html', cliente=cliente, empresa=empresa)
    

    # ── portal_ticket_nuevo (/portal/ticket/nuevo)
    @app.route('/portal/ticket/nuevo', methods=['GET','POST'])
    @login_required
    def portal_ticket_nuevo():
        if current_user.rol != 'cliente':
            return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente:
            flash('Sin empresa vinculada.','danger'); return redirect(url_for('portal_cliente'))
        if request.method == 'POST':
            asignado = cliente.sales_manager_id or current_user.id
            t = Tarea(
                titulo=f"[Ticket] {request.form.get('asunto','')}",
                descripcion=f"De: {cliente.empresa or cliente.nombre}\n\n{request.form.get('mensaje','')}",
                estado='pendiente', prioridad=request.form.get('prioridad','media'),
                asignado_a=asignado, creado_por=current_user.id
            )
            db.session.add(t); db.session.flush()
            db.session.add(TareaAsignado(tarea_id=t.id, user_id=asignado))
            db.session.commit()
            if asignado != current_user.id:
                _crear_notificacion(asignado,'tarea_asignada',
                    f'Nuevo ticket de {cliente.empresa or cliente.nombre}: {request.form.get("asunto","")}',
                    request.form.get('mensaje','')[:120],
                    url_for('tarea_ver', id=t.id)); db.session.commit()
            flash('Ticket enviado a tu sales manager.','success')
            return redirect(url_for('portal_cliente'))
        return render_template('portal/ticket_form.html', cliente=cliente)
    

    # ── portal_manager_revisar (/portal/manager/pre-cotizacion/<int:id>)
    @app.route('/portal/manager/pre-cotizacion/<int:id>', methods=['GET','POST'])
    @login_required
    def portal_manager_revisar(id):
        if current_user.rol not in ['admin','sales_manager','vendedor']:
            flash('Sin permisos.','danger'); return redirect(url_for('dashboard'))
        pc = PreCotizacion.query.get_or_404(id)
        if request.method == 'POST':
            accion = request.form.get('accion','')
            pc.notas_manager = request.form.get('notas_manager', pc.notas_manager or '')
            pc.actualizado_en = datetime.utcnow()
            if accion == 'aprobar':
                pc.estado = 'aprobada'
                msg = f'Tu pre-cotización {pc.numero} fue aprobada por tu sales manager.'
            elif accion == 'rechazar':
                pc.estado = 'rechazada'
                msg = f'Tu pre-cotización {pc.numero} fue rechazada. Nota: {pc.notas_manager}'
            elif accion == 'corregir':
                pc.estado = 'en_revision'
                # Update prices from form
                for item in pc.items:
                    new_price = request.form.get(f'precio_{item.id}', type=float)
                    if new_price is not None:
                        item.precio_unit = new_price
                        item.subtotal = round(item.cantidad * new_price, 2)
                pc.subtotal = sum(i.subtotal for i in pc.items)
                pc.iva = round(pc.subtotal * 0.19, 2)
                pc.total = pc.subtotal + pc.iva
                msg = f'Tu pre-cotización {pc.numero} fue revisada y tiene ajustes. Por favor revísala.'
            db.session.commit()
            # Notify client user
            if pc.cliente_user_id:
                _crear_notificacion(pc.cliente_user_id,'info', msg, pc.notas_manager or '',
                    url_for('portal_cliente')); db.session.commit()
            flash(f'Pre-cotización {accion}da.','success')
            return redirect(url_for('portal_manager_revisar', id=id))
        return render_template('portal/manager_revisar.html', pc=pc)
    

    # ── portal_precot_aceptar (/portal/pre-cotizacion/<int:id>/aceptar)
    @app.route('/portal/pre-cotizacion/<int:id>/aceptar', methods=['POST'])
    @login_required
    def portal_precot_aceptar(id):
        if current_user.rol != 'cliente':
            return redirect(url_for('dashboard'))
        pc = PreCotizacion.query.get_or_404(id)
        if pc.cliente_user_id != current_user.id:
            flash('Sin permisos.','danger'); return redirect(url_for('portal_cliente'))
        pc.estado = 'aceptada_cliente'
        pc.actualizado_en = datetime.utcnow()
        db.session.commit()
        if pc.sales_manager_id:
            _crear_notificacion(pc.sales_manager_id,'info',
                f'Cliente aceptó la pre-cotización {pc.numero}',
                f'{pc.cliente.empresa or pc.cliente.nombre} aceptó. Puedes convertirla en cotización formal.',
                url_for('portal_manager_revisar', id=pc.id)); db.session.commit()
        flash('Aceptaste la pre-cotización. Tu sales manager continuará el proceso.','success')
        return redirect(url_for('portal_cliente'))
    

    # ── portal_proveedor (/portal-proveedor)
    @app.route('/portal-proveedor')
    @login_required
    def portal_proveedor():
        if current_user.rol != 'proveedor':
            return redirect(url_for('dashboard'))
        prov = db.session.get(Proveedor, current_user.proveedor_id) if current_user.proveedor_id else None
        if not prov:
            flash('Tu cuenta no está vinculada a una empresa proveedora.', 'warning')
            return render_template('portal/proveedor_sin_empresa.html')
        ordenes = OrdenCompra.query.filter_by(proveedor_id=prov.id).order_by(OrdenCompra.creado_en.desc()).limit(30).all()
        cotizaciones = CotizacionProveedor.query.filter_by(proveedor_id=prov.id).order_by(CotizacionProveedor.creado_en.desc()).limit(20).all()
        return render_template('portal/proveedor_index.html', prov=prov,
                               ordenes=ordenes, cotizaciones=cotizaciones)
    

    # ── portal_prov_confirmar_oc (/portal-proveedor/confirmar-oc/<int:id>)
    @app.route('/portal-proveedor/confirmar-oc/<int:id>', methods=['POST'])
    @login_required
    def portal_prov_confirmar_oc(id):
        if current_user.rol != 'proveedor':
            return redirect(url_for('dashboard'))
        oc = OrdenCompra.query.get_or_404(id)
        prov = db.session.get(Proveedor, current_user.proveedor_id)
        if not prov or oc.proveedor_id != prov.id:
            flash('Sin permisos.','danger'); return redirect(url_for('portal_proveedor'))
        oc.estado = 'confirmada'
        oc.estado_proveedor = 'confirmada'
        oc.confirmado_en = datetime.utcnow()
        oc.confirmado_por = current_user.id
        db.session.commit()
        # Notify purchaser
        admins = User.query.filter(User.rol.in_(['admin','vendedor','sales_manager']), User.activo==True).all()
        fecha_est = oc.fecha_esperada.strftime('%d/%m/%Y') if oc.fecha_esperada else 'por confirmar'
        for a in admins[:2]:
            _crear_notificacion(a.id, 'info',
                f'OC confirmada por {prov.nombre}',
                f'Orden {oc.numero or oc.id} confirmada. Fecha estimada: {fecha_est}',
                url=url_for('orden_compra_editar', id=oc.id))
        db.session.commit()
        flash('Orden de compra confirmada exitosamente.','success')
        return redirect(url_for('portal_proveedor'))
    

    # ── portal_prov_ticket (/portal-proveedor/ticket/nuevo)
    @app.route('/portal-proveedor/ticket/nuevo', methods=['GET','POST'])
    @login_required
    def portal_prov_ticket():
        if current_user.rol != 'proveedor':
            return redirect(url_for('dashboard'))
        prov = db.session.get(Proveedor, current_user.proveedor_id) if current_user.proveedor_id else None
        if not prov:
            flash('Sin empresa vinculada.','danger'); return redirect(url_for('portal_proveedor'))
        if request.method == 'POST':
            admins = User.query.filter(User.rol.in_(['admin','vendedor']), User.activo==True).all()
            asignado = admins[0].id if admins else current_user.id
            t = Tarea(
                titulo=f"[Prov] {request.form.get('asunto','')}",
                descripcion=f"De proveedor: {prov.nombre}\n\n{request.form.get('mensaje','')}",
                estado='pendiente', prioridad=request.form.get('prioridad','media'),
                asignado_a=asignado, creado_por=current_user.id
            )
            db.session.add(t); db.session.flush()
            db.session.add(TareaAsignado(tarea_id=t.id, user_id=asignado))
            db.session.commit()
            if asignado != current_user.id:
                _crear_notificacion(asignado,'tarea_asignada',
                    f'Mensaje de proveedor {prov.nombre}: {request.form.get("asunto","")}',
                    request.form.get('mensaje','')[:120],
                    url=url_for('tarea_ver', id=t.id)); db.session.commit()
            flash('Mensaje enviado al equipo.','success')
            return redirect(url_for('portal_proveedor'))
        return render_template('portal/proveedor_ticket.html', prov=prov)
    
