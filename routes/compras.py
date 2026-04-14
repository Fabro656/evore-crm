# routes/compras.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import logging

def register(app):

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
            try:
                cant = float(cants[i]) if i < len(cants) else 1
            except (ValueError, IndexError):
                cant = 0
            try:
                precio = float(precios[i]) if i < len(precios) else 0
            except (ValueError, IndexError):
                precio = 0
            if cant <= 0: continue
            if precio < 0: precio = 0  # No permitir precios negativos
            cot_id = int(cot_ids[i]) if i < len(cot_ids) and cot_ids[i].strip() else None
            subtotal = round(cant * precio, 2)
            items.append(OrdenCompraItem(
                orden_id=oc_id, nombre_item=nom.strip(),
                descripcion=descs[i] if i < len(descs) else '',
                cantidad=cant, unidad=units[i] if i < len(units) else 'unidades',
                precio_unit=precio, subtotal=subtotal, cotizacion_id=cot_id))
        return items


    # ── comparativo_cotizaciones (/cotizaciones-proveedor/comparativo)
    @app.route('/cotizaciones-proveedor/comparativo')
    @login_required
    @requiere_modulo('ordenes_compra')
    def comparativo_cotizaciones():
        producto_q  = request.args.get('producto', '').strip()
        materia_id  = request.args.get('materia_id', type=int)

        q = CotizacionProveedor.query
        if producto_q:
            q = q.filter(CotizacionProveedor.nombre_producto.ilike(f'%{producto_q}%'))
        if materia_id:
            q = q.filter_by(materia_prima_id=materia_id)
        cotizaciones = q.order_by(CotizacionProveedor.nombre_producto,
                                  CotizacionProveedor.precio_unitario).all()

        # Agrupar por nombre_producto (case-insensitive, strip)
        grupos = {}
        for c in cotizaciones:
            key = c.nombre_producto.strip().lower()
            grupos.setdefault(key, {'nombre': c.nombre_producto.strip(), 'cotizaciones': []})
            prov_nombre = (c.proveedor.empresa or c.proveedor.nombre) if c.proveedor else '—'
            grupos[key]['cotizaciones'].append({
                'id':               c.id,
                'numero':           c.numero or '',
                'proveedor':        prov_nombre,
                'precio_unitario':  c.precio_unitario,
                'unidad':           c.unidad,
                'unidades_minimas': c.unidades_minimas,
                'plazo_entrega_dias': c.plazo_entrega_dias or 0,
                'vigencia':         c.vigencia,
                'estado':           c.estado,
                'condicion_pago_tipo': c.condicion_pago_tipo or 'contado',
                'condicion_pago_dias': c.condicion_pago_dias or 0,
                'anticipo_porcentaje': c.anticipo_porcentaje or 0,
            })

        # Para cada grupo calcular el precio mínimo y el plazo mínimo (>0)
        grupos_lista = []
        for key, g in grupos.items():
            cots = g['cotizaciones']
            precios = [c['precio_unitario'] for c in cots if c['precio_unitario'] > 0]
            plazos  = [c['plazo_entrega_dias'] for c in cots if c['plazo_entrega_dias'] > 0]
            g['precio_min']  = min(precios) if precios else None
            g['plazo_min']   = min(plazos)  if plazos  else None
            grupos_lista.append(g)

        grupos_lista.sort(key=lambda g: g['nombre'].lower())

        return render_template('proveedores/comparativo.html',
                               grupos=grupos_lista,
                               producto_q=producto_q,
                               materia_id=materia_id)


    # ── cotizaciones_proveedor (/cotizaciones-proveedor)
    @app.route('/cotizaciones-proveedor')
    @login_required
    @requiere_modulo('ordenes_compra')
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
    @requiere_modulo('ordenes_compra')
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


    # ── Helper: construir texto plazo_entrega desde form ──
    def _construir_plazo_entrega(form):
        dias = int(form.get('plazo_entrega_dias') or 0)
        tipo_dias = form.get('plazo_tipo_dias', 'habiles')
        desde_anticipo = form.get('plazo_desde_anticipo')
        if dias <= 0:
            return ''
        texto = f'{dias} días {tipo_dias}'
        if desde_anticipo:
            texto += ' desde pago del anticipo'
        return texto

    # ── cotizacion_proveedor_nueva (/cotizaciones-proveedor/nueva)
    @app.route('/cotizaciones-proveedor/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def cotizacion_proveedor_nueva():
        provs = Proveedor.query.filter(Proveedor.activo==True,
            Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        tipo_default   = request.args.get('tipo','general')
        nombre_default = request.args.get('nombre','')   # pre-fill desde receta
        unidad_default = request.args.get('unidad', '')
        if request.method == 'POST':
            fc = request.form.get('fecha_cotizacion')
            fv = request.form.get('vigencia')
            # Calcular precio unitario real
            precio_raw = float(request.form.get('precio_unitario') or 0)
            cantidad = float(request.form.get('unidades_minimas') or 1)
            precio_por_unidad = request.form.get('precio_por_unidad')  # checkbox
            iva_incluido = request.form.get('iva_incluido')  # checkbox
            # Si IVA incluido, extraer base (precio / 1.19)
            if iva_incluido and precio_raw > 0:
                precio_raw = round(precio_raw / 1.19, 2)
            if not precio_por_unidad and cantidad > 0:
                precio_unitario_real = round(precio_raw / cantidad, 2)
            else:
                precio_unitario_real = precio_raw
            cp = CotizacionProveedor(
                proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None,
                tipo_cotizacion=request.form.get('tipo_cotizacion','general'),
                tipo_producto_servicio=request.form.get('tipo_producto_servicio',''),
                nombre_producto=request.form['nombre_producto'],
                descripcion=request.form.get('descripcion',''),
                sku=request.form.get('sku',''),
                precio_unitario=precio_unitario_real,
                unidades_minimas=int(cantidad),
                unidad=request.form.get('unidad','unidades'),
                plazo_entrega=_construir_plazo_entrega(request.form),
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
                except Exception: seq = 1
            else: seq = 1
            cp.numero = f'CP-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Cotización {cp.numero} creada.','success')
            return redirect(url_for('cotizaciones_proveedor', tipo=cp.tipo_cotizacion))
        return render_template('proveedores/cotizacion_form.html', obj=None,
                               proveedores_list=provs, titulo='Nueva Cotización Proveedor',
                               tipo_default=tipo_default, nombre_default=nombre_default,
                               unidad_default=unidad_default)


    # ── cotizacion_proveedor_editar (/cotizaciones-proveedor/<int:id>/editar)
    @app.route('/cotizaciones-proveedor/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
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
            precio_raw = float(request.form.get('precio_unitario') or 0)
            cantidad = float(request.form.get('unidades_minimas') or 1)
            precio_por_unidad = request.form.get('precio_por_unidad')
            iva_incluido = request.form.get('iva_incluido')
            if iva_incluido and precio_raw > 0:
                precio_raw = round(precio_raw / 1.19, 2)
            if not precio_por_unidad and cantidad > 0:
                obj.precio_unitario = round(precio_raw / cantidad, 2)
            else:
                obj.precio_unitario = precio_raw
            obj.unidades_minimas=int(cantidad)
            obj.unidad=request.form.get('unidad','unidades')
            obj.plazo_entrega=_construir_plazo_entrega(request.form)
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
    @requiere_modulo('ordenes_compra')
    def cotizacion_proveedor_eliminar(id):
        obj = CotizacionProveedor.query.get_or_404(id)
        tipo = obj.tipo_cotizacion
        db.session.delete(obj); db.session.commit()
        flash('Cotización eliminada.','info')
        return redirect(url_for('cotizaciones_proveedor', tipo=tipo))


    # ── API: cotizaciones por proveedor (/api/cotizaciones-por-proveedor/<prov_id>)
    @app.route('/api/cotizaciones-por-proveedor/<int:prov_id>')
    @login_required
    @requiere_modulo('ordenes_compra')
    def api_cotizaciones_por_proveedor(prov_id):
        """Retorna cotizaciones vigentes de un proveedor para seleccion multiple en OC."""
        cots = CotizacionProveedor.query.filter(
            CotizacionProveedor.proveedor_id == prov_id,
            CotizacionProveedor.estado == 'vigente'
        ).order_by(CotizacionProveedor.nombre_producto).all()
        return jsonify([{
            'id': c.id,
            'numero': c.numero or '',
            'nombre_producto': c.nombre_producto,
            'descripcion': c.descripcion or '',
            'precio_unitario': c.precio_unitario,
            'unidades_minimas': c.unidades_minimas,
            'unidad': c.unidad,
            'plazo_entrega_dias': c.plazo_entrega_dias or 0,
            'condicion_pago_tipo': c.condicion_pago_tipo or 'contado',
        } for c in cots])


    # ── ordenes_compra (/ordenes-compra)
    @app.route('/ordenes-compra')
    @login_required
    @requiere_modulo('ordenes_compra')
    def ordenes_compra():
        estado_f = request.args.get('estado','')
        q = OrdenCompra.query
        if estado_f: q = q.filter_by(estado=estado_f)
        page = request.args.get('page', 1, type=int)
        per_page = 25
        pagination = q.order_by(OrdenCompra.creado_en.desc()).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
        return render_template('ordenes_compra/index.html',
                               items=items, estado_f=estado_f,
                               page=page, total_pages=pagination.pages,
                               total_items=pagination.total)


    # ── oc_pdf (/ordenes_compra/<int:id>/pdf)
    @app.route('/ordenes_compra/<int:id>/pdf')
    @login_required
    @requiere_modulo('ordenes_compra')
    def oc_pdf(id):
        oc = OrdenCompra.query.get_or_404(id)
        empresa = ConfigEmpresa.query.first()
        return render_template('ordenes_compra/pdf.html', oc=oc, empresa=empresa)


    # ── orden_compra_nueva (/ordenes-compra/nueva)
    @app.route('/ordenes-compra/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def orden_compra_nueva():
        provs       = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['proveedor','ambos'])).order_by(Proveedor.empresa).all()
        transportistas = Proveedor.query.filter(Proveedor.activo==True, Proveedor.tipo.in_(['transportista','ambos'])).order_by(Proveedor.nombre).all()
        cotizaciones_disponibles = CotizacionProveedor.query.filter_by(estado='vigente').order_by(CotizacionProveedor.nombre_producto).all()
        if request.method == 'POST':
            # Validar proveedor existe y esta activo
            prov_id_raw = request.form.get('proveedor_id', '').strip()
            if not prov_id_raw:
                flash('Debes seleccionar un proveedor.', 'danger')
                return redirect(url_for('orden_compra_nueva'))
            prov_check = db.session.get(Proveedor, int(prov_id_raw))
            if not prov_check or not prov_check.activo:
                flash('El proveedor seleccionado no existe o no esta activo.', 'danger')
                return redirect(url_for('orden_compra_nueva'))
            total_oc = float(request.form.get('total_calc') or 0)
            if total_oc <= 0:
                flash('No se puede crear una orden de compra con valor cero.', 'danger')
                return redirect(url_for('orden_compra_nueva'))
            fe  = request.form.get('fecha_emision')
            fes = request.form.get('fecha_esperada')
            fep = request.form.get('fecha_estimada_pago')
            fer = request.form.get('fecha_estimada_recogida')
            cot_id = int(request.form.get('cotizacion_id')) if request.form.get('cotizacion_id') else None
            tra_id = int(request.form.get('transportista_id')) if request.form.get('transportista_id') else None
            fecha_emision = datetime.strptime(fe,'%Y-%m-%d').date() if fe else datetime.utcnow().date()
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
                estado='borrador',  # siempre inicia borrador, cambia via asientos contables
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
                except Exception: seq = 1
            else: seq = 1
            oc.numero = f'OC-{hoy.year}-{seq:03d}'
            saved_items = _oc_save_items(oc.id)
            if not saved_items:
                db.session.rollback()
                flash('La OC debe tener al menos un item con cantidad y precio validos.', 'danger')
                return redirect(url_for('orden_compra_nueva'))
            for it in saved_items: db.session.add(it)
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
            # Auto-crear asiento contable de egreso en borrador
            try:
                asiento = AsientoContable(
                    numero='AC-TEMP',
                    fecha=oc.fecha_emision or datetime.utcnow().date(),
                    descripcion=f'Egreso pendiente — OC {oc.numero}',
                    tipo='compra',
                    subtipo='orden_compra',
                    referencia=oc.numero,
                    debe=float(oc.total or 0),
                    haber=float(oc.total or 0),
                    cuenta_debe='1405 Materias primas',
                    cuenta_haber='220505 Nacionales',
                    clasificacion='egreso',
                    estado_asiento='borrador',
                    estado_pago='pendiente',
                    orden_compra_id=oc.id,
                    proveedor_id=oc.proveedor_id,
                    tercero_nombre=oc.proveedor.empresa if oc.proveedor else None,
                    creado_por=current_user.id
                )
                db.session.add(asiento)
                db.session.flush()
                asiento.numero = f'AC-{datetime.utcnow().year}-{asiento.id:04d}'
            except Exception as ex:
                logging.warning(f'orden_compra_nueva: auto-asiento error: {ex}')
            # Auto-crear contrato proveedor para firma en portal
            try:
                if oc.proveedor_id:
                    empresa = ConfigEmpresa.query.first()
                    prov = db.session.get(Proveedor, oc.proveedor_id)
                    doc = DocumentoLegal(
                        tipo='contrato',
                        titulo=f'Contrato de suministro — {oc.numero}',
                        numero=f'CTP-{oc.numero or oc.id}',
                        entidad=empresa.nombre if empresa else 'Empresa',
                        descripcion=f'Contrato de suministro vinculado a la OC {oc.numero}. Incluye condiciones de entrega, calidad y forma de pago.',
                        estado='en_tramite',
                        fecha_emision=datetime.utcnow().date(),
                        proveedor_id=oc.proveedor_id,
                        tipo_entidad='proveedor',
                        requiere_firma_portal=True,
                        activo=True,
                        creado_por=current_user.id
                    )
                    if empresa and getattr(empresa, 'representante_legal', ''):
                        doc.firma_empresa_por = empresa.representante_legal
                    db.session.add(doc)
                    # Notificar proveedor
                    from models import User as UserModel
                    user_prov = UserModel.query.filter_by(proveedor_id=oc.proveedor_id, rol='proveedor', activo=True).first()
                    if user_prov:
                        _crear_notificacion(user_prov.id, 'info',
                            'Nuevo contrato para firmar',
                            f'Tienes un contrato pendiente de firma: Contrato de suministro — {oc.numero}',
                            url_for('portal_prov_docs'))
            except Exception as ex:
                logging.warning(f'orden_compra_nueva: auto-doc error: {ex}')
            db.session.commit()
            flash(f'Orden de compra {oc.numero} creada con asiento contable de egreso pendiente.','success')
            return redirect(url_for('ordenes_compra'))
        return render_template('ordenes_compra/form.html', obj=None,
                               proveedores_list=provs, transportistas_list=transportistas,
                               cotizaciones_list=cotizaciones_disponibles,
                               titulo='Nueva Orden de Compra', items_json=[],
                               today=datetime.utcnow().strftime('%Y-%m-%d'))


    # ── orden_compra_editar (/ordenes-compra/<int:id>/editar)
    @app.route('/ordenes-compra/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
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
            # estado no se cambia desde edicion — solo via asientos contables
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
                               titulo='Editar Orden de Compra', items_json=items_json,
                               today=datetime.utcnow().strftime('%Y-%m-%d'))


    # ── orden_compra_estado (/ordenes-compra/<int:id>/estado)
    @app.route('/ordenes-compra/<int:id>/estado', methods=['POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def orden_compra_estado(id):
        obj = db.session.get(OrdenCompra, id, with_for_update=True)
        if not obj:
            flash('Orden de compra no encontrada.', 'danger')
            return redirect(url_for('ordenes_compra'))
        estado_anterior = obj.estado
        nuevo = request.form.get('estado', obj.estado)

        # Validar transiciones permitidas
        OC_TRANSICIONES = {
            'borrador': ['enviada', 'cancelada'],
            'enviada': ['anticipo_pagado', 'cancelada'],
            'anticipo_pagado': ['en_espera_producto', 'cancelada'],
            'en_espera_producto': ['recibida', 'cancelada'],
            'recibida': [],
            'cancelada': ['borrador'],
        }
        permitidos = OC_TRANSICIONES.get(estado_anterior, [])
        if nuevo not in permitidos and current_user.rol != 'admin':
            flash(f'No se puede cambiar de "{estado_anterior}" a "{nuevo}". Transiciones validas: {", ".join(permitidos)}', 'warning')
            return redirect(url_for('ordenes_compra'))
        obj.estado = nuevo

        # Al pasar de borrador → enviada: crear CompraMateria por cada ítem de la orden
        if obj.estado == 'enviada' and estado_anterior == 'borrador':
            for item in (obj.items or []):
                cant  = float(item.cantidad or 1)
                precio = float(item.precio_unit or 0)
                total  = float(item.subtotal or cant * precio)
                c = CompraMateria(
                    nombre_item=item.nombre_item or f'Item OC {obj.numero}',
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
                    notas=f'Generado automaticamente desde OC {obj.numero}',
                    creado_por=current_user.id,
                    orden_compra_id=obj.id,
                    orden_compra_item_id=item.id,
                    estado_recepcion='solicitado',
                )
                db.session.add(c)
            if obj.items:
                flash(f'{len(obj.items)} ítem(s) de la OC {obj.numero} registrados en Compras automáticamente.', 'info')

        db.session.commit()
        flash(f'Estado actualizado a "{obj.estado}".','success')
        return redirect(url_for('ordenes_compra'))


    # ── BLOQUE 4: oc_anticipo_recibido (/ordenes-compra/<int:id>/anticipo-recibido)
    @app.route('/ordenes-compra/<int:id>/anticipo-recibido', methods=['POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
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
    @requiere_modulo('ordenes_compra')
    def orden_compra_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj = OrdenCompra.query.get_or_404(id)
        db.session.delete(obj); db.session.commit()
        flash('Orden de compra eliminada.','info')
        return redirect(url_for('ordenes_compra'))


    # ── requisiciones (/requisiciones)
    @app.route('/requisiciones', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def requisiciones():
        if request.method == 'POST':
            req = Requisicion(
                solicitante_id=current_user.id,
                descripcion=request.form.get('descripcion', '').strip(),
                motivo=request.form.get('motivo', '').strip() or None,
                prioridad=request.form.get('prioridad', 'media'),
                estado='pendiente'
            )
            db.session.add(req)
            db.session.flush()
            hoy = datetime.utcnow().date()
            ultimo = Requisicion.query.filter(
                Requisicion.numero.like(f'REQ-{hoy.year}-%')
            ).order_by(Requisicion.id.desc()).first()
            if ultimo and ultimo.numero and ultimo.id != req.id:
                try:
                    seq = int(ultimo.numero.split('-')[-1]) + 1
                except Exception:
                    seq = req.id
            else:
                seq = req.id
            req.numero = f'REQ-{hoy.year}-{seq:03d}'
            db.session.commit()
            flash(f'Requisicion {req.numero} creada.', 'success')
            return redirect(url_for('requisiciones'))
        items = Requisicion.query.order_by(Requisicion.creado_en.desc()).all()
        return render_template('ordenes_compra/requisiciones.html', items=items)


    # ── requisicion_aprobar (/requisiciones/<id>/aprobar)
    @app.route('/requisiciones/<int:id>/aprobar', methods=['POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def requisicion_aprobar(id):
        req = Requisicion.query.get_or_404(id)
        req.estado = 'aprobada'
        db.session.commit()
        flash(f'Requisicion {req.numero} aprobada.', 'success')
        return redirect(url_for('requisiciones'))


    # ── requisicion_rechazar (/requisiciones/<id>/rechazar)
    @app.route('/requisiciones/<int:id>/rechazar', methods=['POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def requisicion_rechazar(id):
        req = Requisicion.query.get_or_404(id)
        req.estado = 'rechazada'
        db.session.commit()
        flash(f'Requisicion {req.numero} rechazada.', 'warning')
        return redirect(url_for('requisiciones'))


    # ── requisicion_convertir (/requisiciones/<id>/convertir)
    @app.route('/requisiciones/<int:id>/convertir', methods=['POST'])
    @login_required
    @requiere_modulo('ordenes_compra')
    def requisicion_convertir(id):
        req = Requisicion.query.get_or_404(id)
        if req.estado != 'aprobada':
            flash('Solo se pueden convertir requisiciones aprobadas.', 'warning')
            return redirect(url_for('requisiciones'))
        hoy = datetime.utcnow().date()
        ultimo_oc = OrdenCompra.query.filter(
            OrdenCompra.numero.like(f'OC-{hoy.year}-%')
        ).order_by(OrdenCompra.id.desc()).first()
        if ultimo_oc and ultimo_oc.numero:
            try:
                seq = int(ultimo_oc.numero.split('-')[-1]) + 1
            except Exception:
                seq = 1
        else:
            seq = 1
        oc = OrdenCompra(
            estado='borrador',
            fecha_emision=hoy,
            subtotal=0,
            iva=0,
            total=0,
            notas=f'Generada desde requisicion {req.numero}. {req.descripcion}',
            creado_por=current_user.id
        )
        db.session.add(oc)
        db.session.flush()
        oc.numero = f'OC-{hoy.year}-{seq:03d}'
        req.orden_compra_id = oc.id
        req.estado = 'convertida'
        db.session.commit()
        flash(f'OC {oc.numero} creada desde requisicion {req.numero}. Complete los datos de la orden.', 'success')
        return redirect(url_for('orden_compra_editar', id=oc.id))
