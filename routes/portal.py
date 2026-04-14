# routes/portal.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging

def register(app):

    # ── portal_cliente (/portal)
    @app.route('/portal')
    @login_required
    def portal_cliente():
        if _get_rol_activo(current_user) != 'cliente':
            return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente:
            flash('Tu cuenta no está vinculada a una empresa. Contacta al administrador.', 'warning')
            return render_template('portal/sin_empresa.html')

        # -- Search, filter & pagination for ventas --
        buscar = request.args.get('buscar', '').strip()
        estado_filtro = request.args.get('estado', '')
        page = request.args.get('page', 1, type=int)
        per_page = 20

        q_ventas = Venta.query.filter_by(cliente_id=cliente.id)
        if buscar:
            like_term = f'%{buscar}%'
            q_ventas = q_ventas.filter(db.or_(
                Venta.numero.ilike(like_term),
                Venta.titulo.ilike(like_term)
            ))
        if estado_filtro:
            q_ventas = q_ventas.filter(Venta.estado == estado_filtro)

        total_ventas = q_ventas.count()
        total_pages = max(1, (total_ventas + per_page - 1) // per_page)
        page = max(1, min(page, total_pages))
        ventas = q_ventas.order_by(Venta.creado_en.desc()).offset((page - 1) * per_page).limit(per_page).all()

        # Distinct estados for filter dropdown
        estados_ventas = [r[0] for r in db.session.query(Venta.estado).filter_by(cliente_id=cliente.id).distinct().order_by(Venta.estado).all()]

        cotizaciones = Cotizacion.query.filter_by(cliente_id=cliente.id).order_by(Cotizacion.creado_en.desc()).limit(20).all()
        pre_cots = PreCotizacion.query.filter_by(cliente_id=cliente.id).order_by(PreCotizacion.creado_en.desc()).limit(10).all()
        mensajes = Tarea.query.filter(Tarea.titulo.like('[Mensaje]%'),
                                      db.or_(Tarea.creado_por==current_user.id,
                                             Tarea.asignado_a==cliente.sales_manager_id)).order_by(Tarea.creado_en.desc()).limit(50).all()
        sales_manager_user = db.session.get(User, cliente.sales_manager_id) if cliente.sales_manager_id else User.query.filter_by(rol='admin', activo=True).first()
        return render_template('portal/index.html', cliente=cliente, ventas=ventas,
                               cotizaciones=cotizaciones, pre_cots=pre_cots, mensajes=mensajes,
                               sales_manager_user=sales_manager_user,
                               buscar=buscar, estado_filtro=estado_filtro,
                               page=page, total_pages=total_pages, total_ventas=total_ventas,
                               estados_ventas=estados_ventas)
    

    # ── portal_cliente_factura (/portal/venta/<id>/factura)
    @app.route('/portal/venta/<int:id>/factura')
    @login_required
    def portal_cliente_factura(id):
        if _get_rol_activo(current_user) != 'cliente': return redirect(url_for('dashboard'))
        venta = Venta.query.get_or_404(id)
        if venta.cliente_id != current_user.cliente_id:
            flash('No tienes acceso a esta venta.', 'danger')
            return redirect(url_for('portal_cliente'))
        empresa = ConfigEmpresa.query.first()
        return render_template('ventas/factura.html', venta=venta, empresa=empresa)


    # ── portal_cliente_remision (/portal/venta/<id>/remision)
    @app.route('/portal/venta/<int:id>/remision')
    @login_required
    def portal_cliente_remision(id):
        if _get_rol_activo(current_user) != 'cliente': return redirect(url_for('dashboard'))
        venta = Venta.query.get_or_404(id)
        if venta.cliente_id != current_user.cliente_id:
            flash('No tienes acceso a esta venta.', 'danger')
            return redirect(url_for('portal_cliente'))
        empresa = ConfigEmpresa.query.first()
        empaques_detalle = []
        transportista = venta.transportista if hasattr(venta, 'transportista') else None
        return render_template('ventas/remision.html', venta=venta, empresa=empresa,
                               empaques_detalle=empaques_detalle, transportista=transportista)


    # ── portal_cliente_docs (/portal/documentos)
    @app.route('/portal/documentos')
    @login_required
    def portal_cliente_docs():
        if _get_rol_activo(current_user) != 'cliente': return redirect(url_for('dashboard'))
        cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
        if not cliente: return redirect(url_for('portal_cliente'))
        docs = DocumentoLegal.query.filter(
            DocumentoLegal.activo == True,
            db.or_(DocumentoLegal.cliente_id == cliente.id, DocumentoLegal.tipo_entidad == 'empresa')
        ).order_by(DocumentoLegal.creado_en.desc()).all()
        return render_template('portal/documentos.html', docs=docs, entidad=cliente, tipo='cliente')


    # ── portal_cliente_marcar_pago (/portal/venta/<id>/marcar-pago)
    @app.route('/portal/venta/<int:id>/marcar-pago', methods=['POST'])
    @login_required
    def portal_cliente_marcar_pago(id):
        """Cliente marca que ya envió el pago/anticipo de una venta."""
        if _get_rol_activo(current_user) != 'cliente':
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('dashboard'))
        if not current_user.cliente_id:
            flash('Tu cuenta no esta vinculada a una empresa.', 'danger')
            return redirect(url_for('portal_cliente'))
        venta = Venta.query.get_or_404(id)
        if venta.cliente_id != current_user.cliente_id:
            flash('Sin permisos.', 'danger')
            return redirect(url_for('portal_cliente'))
        try:
            monto = float(request.form.get('monto_pago') or 0)
            metodo = request.form.get('metodo_pago', 'transferencia')
            referencia = request.form.get('referencia_pago', '')
            total_venta = float(venta.total or 0)
            ya_pagado = float(venta.monto_pagado_total or 0)
            max_permitido = max(0, total_venta - ya_pagado)
            if monto <= 0:
                flash('Indica el monto del pago.', 'warning')
                return redirect(url_for('portal_cliente'))
            if monto > max_permitido:
                monto = max_permitido
                if monto <= 0:
                    flash('Esta venta ya esta completamente pagada.', 'info')
                    return redirect(url_for('portal_cliente'))
            venta.estado_cliente_pago = 'enviado'
            # Registrar pago pendiente de confirmación
            pago = PagoVenta(
                venta_id=venta.id,
                monto=monto,
                tipo='anticipo' if monto < float(venta.total or 0) else 'saldo',
                metodo_pago=metodo,
                referencia=referencia,
                fecha=datetime.utcnow().date(),
                notas=f'Reportado por cliente via portal. Pendiente confirmación.',
                creado_por=current_user.id
            )
            db.session.add(pago)
            # Notificar al equipo contable/ventas
            cliente = db.session.get(Cliente, current_user.cliente_id)
            nombre_cli = cliente.empresa or cliente.nombre if cliente else 'Cliente'
            destinatarios = User.query.filter(
                User.rol.in_(['admin', 'contador', 'vendedor']), User.activo == True
            ).all()
            for u in destinatarios[:3]:
                _crear_notificacion(u.id, 'info',
                    f'{nombre_cli} reportó pago de {moneda(monto)}',
                    f'Venta {venta.numero or venta.id} — {metodo} ref: {referencia}. Confirmar recepción en Asientos Contables.',
                    url=url_for('contable_asientos', vista='generados'))
            db.session.commit()
            flash(f'Pago de {moneda(monto)} reportado. Será confirmado por el equipo.', 'success')
        except Exception as e:
            logging.warning(f'portal_cliente_marcar_pago error: {e}')
            db.session.rollback()
            flash('Error al reportar el pago.', 'danger')
        return redirect(url_for('portal_cliente'))


    # ── portal_mensaje_nuevo (/portal/mensaje/nuevo)
    @app.route('/portal/mensaje/nuevo', methods=['POST'])
    @login_required
    def portal_mensaje_nuevo():
        if _get_rol_activo(current_user) != 'cliente':
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
        if _get_rol_activo(current_user) != 'cliente':
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
        if _get_rol_activo(current_user) != 'cliente':
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
        if _get_rol_activo(current_user) not in ['admin','sales_manager','vendedor']:
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
        if _get_rol_activo(current_user) != 'cliente':
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
    

    # ── portal_precot_convertir (/portal/manager/pre-cotizacion/<int:id>/convertir)
    @app.route('/portal/manager/pre-cotizacion/<int:id>/convertir', methods=['POST'])
    @login_required
    def portal_precot_convertir(id):
        """Convierte una pre-cotización aceptada en cotización formal."""
        if _get_rol_activo(current_user) not in ['admin', 'sales_manager', 'vendedor']:
            flash('Sin permisos.', 'danger')
            return redirect(url_for('dashboard'))
        pc = PreCotizacion.query.get_or_404(id)
        if pc.estado not in ('aprobada', 'aceptada_cliente'):
            flash('Solo se pueden convertir pre-cotizaciones aprobadas o aceptadas.', 'warning')
            return redirect(url_for('portal_manager_revisar', id=id))

        # Verificar que no exista ya una cotización para esta pre-cot
        cot_existente = Cotizacion.query.filter_by(
            cliente_id=pc.cliente_id,
            titulo=f'Pre-cotización {pc.numero}'
        ).first()
        if cot_existente:
            flash(f'Ya existe la cotización {cot_existente.numero} para esta pre-cotización.', 'warning')
            return redirect(url_for('cotizacion_ver', id=cot_existente.id))

        # Generar número COT-YYYY-NNN
        from datetime import date as date_t
        hoy = date_t.today()
        ultimo = Cotizacion.query.filter(
            Cotizacion.numero.like(f'COT-{hoy.year}-%')
        ).order_by(Cotizacion.id.desc()).first()
        if ultimo and ultimo.numero:
            try: seq = int(ultimo.numero.split('-')[-1]) + 1
            except Exception: seq = 1
        else: seq = 1
        numero = f'COT-{hoy.year}-{seq:03d}'

        cot = Cotizacion(
            numero=numero,
            titulo=f'Pre-cotización {pc.numero}',
            cliente_id=pc.cliente_id,
            subtotal=pc.subtotal,
            iva=pc.iva,
            total=pc.total,
            porcentaje_anticipo=50,
            monto_anticipo=pc.total * 0.5,
            saldo=pc.total * 0.5,
            fecha_emision=hoy,
            dias_entrega=30,
            notas=pc.notas_cliente or '',
            estado='borrador',
            creado_por=current_user.id
        )
        db.session.add(cot); db.session.flush()

        # Copiar items
        for item in pc.items:
            db.session.add(CotizacionItem(
                cotizacion_id=cot.id,
                nombre_prod=item.nombre_prod,
                cantidad=item.cantidad,
                precio_unit=item.precio_unit,
                subtotal=item.subtotal,
                unidad=getattr(item, 'unidad', 'unidades'),
                aplica_iva=True,
                iva_pct=19.0,
                iva_monto=round(item.subtotal * 0.19, 2)
            ))

        pc.estado = 'convertida'
        pc.actualizado_en = datetime.utcnow()
        db.session.commit()

        flash(f'Cotización {numero} creada desde pre-cotización {pc.numero}.', 'success')
        return redirect(url_for('cotizacion_ver', id=cot.id))


    # ── portal_proveedor (/portal-proveedor)
    @app.route('/portal-proveedor')
    @login_required
    def portal_proveedor():
        if _get_rol_activo(current_user) != 'proveedor':
            return redirect(url_for('dashboard'))
        prov = db.session.get(Proveedor, current_user.proveedor_id) if current_user.proveedor_id else None
        if not prov:
            flash('Tu cuenta no está vinculada a una empresa proveedora.', 'warning')
            return render_template('portal/proveedor_sin_empresa.html')
        ordenes = OrdenCompra.query.filter_by(proveedor_id=prov.id).order_by(OrdenCompra.creado_en.desc()).limit(30).all()
        cotizaciones = CotizacionProveedor.query.filter_by(proveedor_id=prov.id).order_by(CotizacionProveedor.creado_en.desc()).limit(20).all()
        return render_template('portal/proveedor_index.html', prov=prov,
                               ordenes=ordenes, cotizaciones=cotizaciones)
    

    # ── portal_firmar_documento (/portal/documentos/<id>/firmar)
    @app.route('/portal/documentos/<int:id>/firmar', methods=['POST'])
    @login_required
    def portal_firmar_documento(id):
        """Cliente o proveedor firma digitalmente un documento legal."""
        doc = DocumentoLegal.query.get_or_404(id)
        # Verificar permisos
        if _get_rol_activo(current_user) == 'cliente':
            cliente = db.session.get(Cliente, current_user.cliente_id) if current_user.cliente_id else None
            if not cliente or (doc.cliente_id != cliente.id and doc.tipo_entidad != 'empresa'):
                flash('Sin permisos para firmar.', 'danger')
                return redirect(url_for('portal_cliente_docs'))
        elif _get_rol_activo(current_user) == 'proveedor':
            prov = db.session.get(Proveedor, current_user.proveedor_id) if current_user.proveedor_id else None
            if not prov or (doc.proveedor_id != prov.id and doc.tipo_entidad != 'empresa'):
                flash('Sin permisos para firmar.', 'danger')
                return redirect(url_for('portal_prov_docs'))
        else:
            return redirect(url_for('dashboard'))

        firma_data = request.form.get('firma_data', '')
        if not firma_data or len(firma_data) < 100:
            flash('Firma inválida. Dibuja tu firma en el recuadro.', 'warning')
            if _get_rol_activo(current_user) == 'cliente':
                return redirect(url_for('portal_cliente_docs'))
            return redirect(url_for('portal_prov_docs'))

        doc.firma_portal_data = firma_data
        doc.firma_portal_por = current_user.nombre
        doc.firma_portal_en = datetime.utcnow()
        # Selfie de verificacion
        selfie_data = request.form.get('selfie_data', '')
        if selfie_data and len(selfie_data) > 100:
            doc.selfie_portal_data = selfie_data
        if doc.firma_empresa_data:
            doc.estado = 'vigente'  # Ambas partes firmaron
        db.session.commit()

        # Notificar al admin
        admins = User.query.filter(User.rol.in_(['admin', 'vendedor']), User.activo == True).all()
        for a in admins[:2]:
            _crear_notificacion(a.id, 'info',
                f'Documento firmado por {current_user.nombre}',
                f'"{doc.titulo}" fue firmado digitalmente.',
                url=url_for('legal_index'))
        db.session.commit()

        flash('Documento firmado exitosamente.', 'success')
        if _get_rol_activo(current_user) == 'cliente':
            return redirect(url_for('portal_cliente_docs'))
        return redirect(url_for('portal_prov_docs'))


    # ── portal_prov_oc_pdf (/portal-proveedor/oc/<int:id>/pdf)
    @app.route('/portal-proveedor/oc/<int:id>/pdf')
    @login_required
    def portal_prov_oc_pdf(id):
        """Proveedor descarga PDF de su OC."""
        if _get_rol_activo(current_user) != 'proveedor': return redirect(url_for('dashboard'))
        oc = OrdenCompra.query.get_or_404(id)
        if oc.proveedor_id != current_user.proveedor_id:
            flash('No tienes acceso a esta OC.', 'danger')
            return redirect(url_for('portal_proveedor'))
        empresa = ConfigEmpresa.query.first()
        return render_template('ordenes_compra/pdf.html', oc=oc, empresa=empresa)


    # ── portal_prov_docs (/portal-proveedor/documentos)
    @app.route('/portal-proveedor/documentos')
    @login_required
    def portal_prov_docs():
        if _get_rol_activo(current_user) != 'proveedor': return redirect(url_for('dashboard'))
        prov = db.session.get(Proveedor, current_user.proveedor_id) if current_user.proveedor_id else None
        if not prov: return redirect(url_for('portal_proveedor'))
        docs = DocumentoLegal.query.filter(
            DocumentoLegal.activo == True,
            db.or_(DocumentoLegal.proveedor_id == prov.id, DocumentoLegal.tipo_entidad == 'empresa')
        ).order_by(DocumentoLegal.creado_en.desc()).all()
        return render_template('portal/documentos.html', docs=docs, entidad=prov, tipo='proveedor')


    # ── portal_prov_confirmar_oc (/portal-proveedor/confirmar-oc/<int:id>)
    @app.route('/portal-proveedor/confirmar-oc/<int:id>', methods=['POST'])
    @login_required
    def portal_prov_confirmar_oc(id):
        if _get_rol_activo(current_user) != 'proveedor':
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
        if _get_rol_activo(current_user) != 'proveedor':
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


    # ── BLOQUE 4: portal_prov_anticipo_oc (/portal-proveedor/oc/<int:id>/anticipo)
    @app.route('/portal-proveedor/oc/<int:id>/anticipo', methods=['POST'])
    @login_required
    def portal_prov_anticipo_oc(id):
        """Portal del proveedor: confirma que el anticipo fue recibido — sincroniza con AsientoContable."""
        if _get_rol_activo(current_user) != 'proveedor':
            return redirect(url_for('dashboard'))
        oc = OrdenCompra.query.get_or_404(id)
        prov = db.session.get(Proveedor, current_user.proveedor_id)
        if not prov or oc.proveedor_id != prov.id:
            flash('Sin permisos.', 'danger')
            return redirect(url_for('portal_proveedor'))

        try:
            oc.fecha_anticipo_real = datetime.utcnow().date()
            oc.estado_proveedor = 'anticipo_recibido'
            # Recalcular fecha esperada si existe cotización
            if oc.cotizacion_id:
                cotprov = CotizacionProveedor.query.get(oc.cotizacion_id)
                if cotprov and cotprov.plazo_entrega_dias:
                    oc.fecha_esperada = oc.fecha_anticipo_real + timedelta(days=cotprov.plazo_entrega_dias)
            # Sincronizar con AsientoContable vinculado
            asiento = AsientoContable.query.filter_by(orden_compra_id=oc.id).first()
            if asiento and asiento.estado_pago in ('parcial', 'completo'):
                asiento.notas = (asiento.notas or '') + f'\nProveedor confirmó recepción de anticipo el {datetime.utcnow().strftime("%d/%m/%Y %H:%M")}.'
            # Notificar al equipo
            admins = User.query.filter(User.rol.in_(['admin', 'vendedor', 'contador']), User.activo == True).all()
            for a in admins[:3]:
                _crear_notificacion(a.id, 'info',
                    f'{prov.nombre} confirmó anticipo recibido',
                    f'OC {oc.numero or oc.id} — anticipo de {moneda(oc.monto_pagado or 0)} confirmado por proveedor.',
                    url=url_for('orden_compra_editar', id=oc.id))
            db.session.commit()
            flash('Anticipo confirmado como recibido. Fecha de entrega actualizada.', 'success')
        except Exception as e:
            logging.warning(f'portal_prov_anticipo_oc error: {e}')
            db.session.rollback()
            flash('Error al confirmar el anticipo.', 'danger')
        return redirect(url_for('portal_proveedor'))

    # ══════════════════════════════════════════════════════════════
    # PORTAL INTER-EMPRESA: ver mis datos en otra empresa
    # ══════════════════════════════════════════════════════════════

    @app.route('/portal/empresa/<int:company_id>')
    @login_required
    def portal_interempresa(company_id):
        """Ver mis pedidos/OC en otra empresa con la que tengo relacion."""
        from flask import g
        my_company_id = g.company_id
        if not my_company_id:
            return redirect(url_for('seleccionar_empresa'))
        rel = CompanyRelationship.query.filter(
            db.or_(
                db.and_(CompanyRelationship.company_from_id == company_id,
                        CompanyRelationship.company_to_id == my_company_id),
                db.and_(CompanyRelationship.company_from_id == my_company_id,
                        CompanyRelationship.company_to_id == company_id)
            ),
            CompanyRelationship.activo == True
        ).first()
        if not rel:
            flash('No tienes relacion con esa empresa.', 'danger')
            return redirect(url_for('dashboard'))
        other_company = db.session.get(Company, company_id)
        if not other_company:
            return redirect(url_for('dashboard'))
        my_nit = ''
        try:
            my_co = db.session.get(Company, my_company_id)
            my_nit = my_co.nit or ''
        except Exception: pass
        if rel.company_from_id == my_company_id:
            my_type = rel.tipo
        else:
            my_type = 'proveedor' if rel.tipo == 'cliente' else ('cliente' if rel.tipo == 'proveedor' else 'ambos')
        ventas_conmigo = []
        oc_conmigo = []
        try:
            if my_type in ('cliente', 'ambos') and my_nit:
                ventas_conmigo = db.session.execute(
                    db.text("SELECT v.id, v.numero, v.titulo, v.total, v.estado, v.creado_en FROM ventas v JOIN clientes c ON v.cliente_id = c.id WHERE v.company_id = :cid AND c.nit = :nit ORDER BY v.creado_en DESC LIMIT 50"),
                    {'cid': company_id, 'nit': my_nit}
                ).fetchall()
            if my_type in ('proveedor', 'ambos') and my_nit:
                oc_conmigo = db.session.execute(
                    db.text("SELECT oc.id, oc.numero, oc.total, oc.estado, oc.fecha_emision FROM ordenes_compra oc JOIN proveedores p ON oc.proveedor_id = p.id WHERE oc.company_id = :cid AND p.nit = :nit ORDER BY oc.fecha_emision DESC LIMIT 50"),
                    {'cid': company_id, 'nit': my_nit}
                ).fetchall()
        except Exception as e:
            logging.warning(f'portal_interempresa error: {e}')
        return render_template('portal/interempresa.html',
                               other_company=other_company, my_type=my_type,
                               ventas=ventas_conmigo, ordenes=oc_conmigo)

    @app.route('/portal/mis-relaciones')
    @login_required
    def portal_mis_relaciones():
        """Lista de empresas con las que tengo relacion comercial."""
        from flask import g
        my_cid = g.company_id
        if not my_cid:
            return redirect(url_for('seleccionar_empresa'))
        rels = CompanyRelationship.query.filter(
            db.or_(CompanyRelationship.company_from_id == my_cid,
                   CompanyRelationship.company_to_id == my_cid),
            CompanyRelationship.activo == True
        ).all()
        empresas_rel = []
        for r in rels:
            if r.company_from_id == my_cid:
                other = db.session.get(Company, r.company_to_id)
                tipo_display = r.tipo
            else:
                other = db.session.get(Company, r.company_from_id)
                tipo_display = 'proveedor' if r.tipo == 'cliente' else ('cliente' if r.tipo == 'proveedor' else 'ambos')
            if other and other.activo:
                empresas_rel.append({'company': other, 'tipo': tipo_display})
        return render_template('portal/mis_relaciones.html', empresas=empresas_rel)

    # ── Planes y precios (/planes)
    @app.route('/planes')
    @login_required
    def planes():
        my_company_id = getattr(g, 'company_id', None)
        company = db.session.get(Company, my_company_id) if my_company_id else None
        # Get Evore bank details
        evore_company = Company.query.filter_by(es_principal=True).first()
        evore_config = ConfigEmpresa.query.filter_by(company_id=evore_company.id).first() if evore_company else None
        # Active subscription
        sub_activa = Suscripcion.query.filter_by(
            company_id=my_company_id, estado='activa'
        ).first() if my_company_id else None
        return render_template('portal/planes.html', company=company,
                               evore_config=evore_config, sub_activa=sub_activa)

    # ── Suscribir plan (/planes/suscribir)
    @app.route('/planes/suscribir', methods=['POST'])
    @login_required
    def planes_suscribir():
        my_company_id = getattr(g, 'company_id', None)
        if not my_company_id:
            flash('No se pudo identificar tu empresa.', 'danger')
            return redirect(url_for('planes'))
        company = db.session.get(Company, my_company_id)
        plan = request.form.get('plan', 'starter')
        periodo = request.form.get('periodo', 'mensual')
        usuarios_extra = int(request.form.get('usuarios_extra', 0) or 0)
        if plan not in ('starter', 'pro'):
            flash('Plan no valido.', 'danger')
            return redirect(url_for('planes'))
        if plan == 'starter':
            usuarios_extra = 0

        # Calculate amount
        base = 39900
        extra = usuarios_extra * 5900 if plan == 'pro' else 0
        mensual = base + extra
        if periodo == 'anual':
            monto_cobrado = round(mensual * 12 * 0.9)  # 10% discount
        else:
            monto_cobrado = mensual

        today = date_type.today()
        if periodo == 'anual':
            next_pay = today + timedelta(days=365)
        else:
            next_pay = today + timedelta(days=30)

        # Create subscription (pending until payment confirmed)
        sub = Suscripcion(
            company_id=my_company_id, plan=plan, periodo=periodo,
            usuarios_extra=usuarios_extra, monto_mensual=mensual,
            monto_cobrado=monto_cobrado, estado='pendiente',
            fecha_inicio=today, fecha_proximo_pago=next_pay,
            fecha_vencimiento=next_pay,
            creado_por=current_user.id)
        db.session.add(sub)
        db.session.flush()

        # Create asiento contable (pending income for Evore)
        evore = Company.query.filter_by(es_principal=True).first()
        if evore:
            periodo_label = '12 meses' if periodo == 'anual' else '1 mes'
            extras_label = f' + {usuarios_extra} usuarios extra' if usuarios_extra else ''
            asiento = AsientoContable(
                company_id=evore.id,
                descripcion=f'Suscripcion {plan.capitalize()} ({periodo_label}{extras_label}) — {company.nombre}',
                haber=monto_cobrado, debe=0,
                estado_pago='pendiente', estado_asiento='borrador',
                fecha=today, tipo_documento='factura_venta',
                tercero_nit=company.nit or '',
                banco_nombre='Pendiente transferencia',
                beneficiario=company.nombre)
            db.session.add(asiento)
            db.session.flush()
            sub.asiento_id = asiento.id

        db.session.commit()

        # Send chat message from MyEvore
        _send_myevore_message(my_company_id,
            f'Has solicitado el plan {plan.capitalize()} ({periodo}). '
            f'Monto: ${monto_cobrado:,.0f} COP. '
            f'Realiza la transferencia y envia el comprobante por este chat. '
            f'Tu plan se activara cuando finanzas confirme el pago.')

        flash(f'Solicitud de plan {plan.capitalize()} creada. Realiza la transferencia y envia el comprobante por el chat con Evore.', 'success')
        return redirect(url_for('planes'))

    def _get_or_create_myevore_user():
        """Get or create the MyEvore system notification account."""
        myevore = User.query.filter_by(email='myevore@evore.system').first()
        if not myevore:
            evore = Company.query.filter_by(es_principal=True).first()
            myevore = User(nombre='MyEvore', email='myevore@evore.system',
                           rol='admin', activo=True,
                           company_id=evore.id if evore else None)
            myevore.set_password('SYSTEM_ACCOUNT_NO_LOGIN_' + str(datetime.utcnow().timestamp()))
            db.session.add(myevore)
            db.session.flush()
            if evore:
                existing_uc = UserCompany.query.filter_by(user_id=myevore.id, company_id=evore.id).first()
                if not existing_uc:
                    db.session.add(UserCompany(user_id=myevore.id, company_id=evore.id, rol='admin'))
        return myevore

    def _send_myevore_message(target_company_id, text):
        """Send a message from MyEvore to the target company's chat with Evore."""
        try:
            myevore = _get_or_create_myevore_user()
            evore = Company.query.filter_by(es_principal=True).first()
            if not evore:
                return
            # Find the chat room between Evore and target company
            rel = CompanyRelationship.query.filter(
                db.or_(
                    db.and_(CompanyRelationship.company_from_id == evore.id,
                            CompanyRelationship.company_to_id == target_company_id),
                    db.and_(CompanyRelationship.company_from_id == target_company_id,
                            CompanyRelationship.company_to_id == evore.id)
                )).first()
            if not rel:
                return
            room = ChatRoom.query.filter_by(company_relationship_id=rel.id, activo=True).first()
            if not room:
                return
            # Ensure MyEvore is participant
            part = ChatParticipant.query.filter_by(room_id=room.id, user_id=myevore.id).first()
            if not part:
                db.session.add(ChatParticipant(room_id=room.id, user_id=myevore.id,
                               rol='admin', agregado_por=myevore.id))
            db.session.add(ChatMessage(room_id=room.id, user_id=myevore.id,
                           contenido=text, tipo='texto'))
            db.session.commit()
        except Exception as e:
            logging.warning(f'MyEvore message error: {e}')
            try: db.session.rollback()
            except Exception: pass

    # ── Subscription lifecycle: reminders, grace period, soft-block
    @app.before_request
    def _check_subscription_lifecycle():
        """7-day reminder, 3-day grace, soft-block after expiry. Runs once per session."""
        if not hasattr(g, 'company_id') or not g.company_id:
            return
        try:
            if flask_session.get('_sub_lifecycle_checked'):
                return
            flask_session['_sub_lifecycle_checked'] = True
            today = date_type.today()
            changed = False

            # 1) Reminder: 7 days before due date (current company only)
            reminder_date = today + timedelta(days=7)
            for sub in Suscripcion.query.filter(
                Suscripcion.company_id == g.company_id,
                Suscripcion.estado == 'activa',
                Suscripcion.recordatorio_enviado == False,
                Suscripcion.fecha_proximo_pago <= reminder_date,
                Suscripcion.fecha_proximo_pago >= today
            ).all():
                _send_myevore_message(sub.company_id,
                    f'Recordatorio: tu suscripcion {sub.plan.capitalize()} vence el '
                    f'{sub.fecha_proximo_pago.strftime("%d/%m/%Y")}. '
                    f'Monto a pagar: ${sub.monto_cobrado:,.0f} COP. '
                    f'Realiza la transferencia y envia el comprobante por este chat.')
                sub.recordatorio_enviado = True
                db.session.add(Notificacion(
                    usuario_id=sub.creado_por or current_user.id,
                    tipo='pago',
                    mensaje=f'Tu suscripcion {sub.plan.capitalize()} vence el {sub.fecha_proximo_pago.strftime("%d/%m/%Y")}. Realiza el pago.',
                    url='/planes'))
                changed = True

            # 2) Grace period expired (3 days after due) → soft-block
            grace_limit = today - timedelta(days=3)
            for sub in Suscripcion.query.filter(
                Suscripcion.estado == 'activa',
                Suscripcion.fecha_proximo_pago < grace_limit
            ).all():
                sub.estado = 'vencida'
                comp = db.session.get(Company, sub.company_id)
                if comp and comp.plan not in ('free',):
                    comp.plan = 'bloqueado'
                    _send_myevore_message(sub.company_id,
                        f'Tu suscripcion ha vencido. Tu acceso al CRM esta temporalmente suspendido. '
                        f'Tus datos se mantienen seguros. Realiza el pago para reactivar tu plan. '
                        f'Monto: ${sub.monto_cobrado:,.0f} COP.')
                changed = True

            if changed:
                db.session.commit()
        except Exception:
            try: db.session.rollback()
            except Exception: pass
