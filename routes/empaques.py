# routes/empaques.py — Módulo Empaques Secundarios v30
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, session as flask_session, g
from flask_login import login_required, current_user
from extensions import db, tenant_query
from models import *
from utils import *
from datetime import datetime
import math, json

def register(app):

    # ── calculadora_envio (/logistica/calculadora)
    @app.route('/logistica/calculadora')
    @login_required
    def calculadora_envio():
        """Calculadora de costo de envio independiente."""
        transportistas = tenant_query(Proveedor).filter(
            Proveedor.activo == True,
            Proveedor.tipo.in_(['transportista', 'ambos'])
        ).order_by(Proveedor.empresa).all()
        trans_json = [{'id': t.id, 'nombre': t.empresa or t.nombre,
                       'kg': t.capacidad_vehiculo_kg or 0,
                       'm3': t.capacidad_vehiculo_m3 or 0,
                       'tipo': t.tipo_vehiculo or ''}
                      for t in transportistas]
        try:
            cotizaciones_envio = []
            for c in tenant_query(Cotizacion).filter(Cotizacion.estado.in_(['enviada','aprobada'])).order_by(Cotizacion.fecha_emision.desc()).limit(20).all():
                total_qty = sum(i.cantidad or 0 for i in c.items) if c.items else 0
                if total_qty > 0:
                    cotizaciones_envio.append({'id': c.id, 'numero': c.numero, 'titulo': c.titulo or '', 'total_qty': int(total_qty)})
        except Exception:
            cotizaciones_envio = []
        try:
            ventas_envio = []
            for v in tenant_query(Venta).filter(Venta.estado.in_(['anticipo_pagado','pagado'])).order_by(Venta.creado_en.desc()).limit(20).all():
                total_qty = sum(i.cantidad or 0 for i in v.items) if v.items else 0
                if total_qty > 0:
                    ventas_envio.append({'id': v.id, 'numero': v.numero, 'titulo': v.titulo or '', 'total_qty': int(total_qty)})
        except Exception:
            ventas_envio = []
        empaques = tenant_query(EmpaqueSecundario).join(Producto).order_by(Producto.nombre).all()
        return render_template('empaques/calculadora.html',
                               transportistas_json=trans_json,
                               cotizaciones_envio=cotizaciones_envio,
                               ventas_envio=ventas_envio,
                               empaques=empaques)


    # ── calculadora_guardar (/logistica/calculadora/guardar)
    @app.route('/logistica/calculadora/guardar', methods=['POST'])
    @login_required
    def calculadora_guardar():
        """Guarda el resultado de la calculadora de envio en la sesion del usuario."""
        try:
            data = request.get_json(force=True) or {}
            # Guardar lista de cotizaciones en sesion (max 20)
            historial = flask_session.get('cotizaciones_envio_guardadas', [])
            nuevo_id = (max((c.get('id', 0) for c in historial), default=0) + 1)
            data['id'] = nuevo_id
            data['usuario'] = current_user.nombre if hasattr(current_user, 'nombre') else str(current_user.id)
            historial.insert(0, data)
            # Mantener solo las ultimas 20
            flask_session['cotizaciones_envio_guardadas'] = historial[:20]
            flask_session.modified = True
            return jsonify({'ok': True, 'id': nuevo_id})
        except Exception as e:
            logging.warning(f'producto_rapido error: {e}')
            return jsonify({'ok': False, 'error': 'Error interno'}), 500


    # ── empaques (/empaques)
    @app.route('/empaques')
    @login_required
    @requiere_modulo('produccion')
    def empaques():
        """Lista todos los empaques secundarios con calculadora inline."""
        items = tenant_query(EmpaqueSecundario).join(Producto).order_by(Producto.nombre).all()
        productos = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()
        # Transportistas para simulador logístico
        transportistas = tenant_query(Proveedor).filter(
            Proveedor.activo == True,
            Proveedor.tipo.in_(['transportista', 'ambos'])
        ).order_by(Proveedor.empresa).all()
        trans_json = [{'id': t.id, 'nombre': t.empresa or t.nombre,
                       'kg': t.capacidad_vehiculo_kg or 0,
                       'm3': t.capacidad_vehiculo_m3 or 0,
                       'tipo': t.tipo_vehiculo or ''}
                      for t in transportistas]
        # Cotizaciones y ventas para vincular al simulador de envio
        try:
            cotizaciones_envio = []
            for c in tenant_query(Cotizacion).filter(Cotizacion.estado.in_(['enviada','aprobada'])).order_by(Cotizacion.fecha_emision.desc()).limit(20).all():
                total_qty = sum(i.cantidad or 0 for i in c.items) if c.items else 0
                if total_qty > 0:
                    cotizaciones_envio.append({'id': c.id, 'numero': c.numero, 'titulo': c.titulo or '', 'total_qty': int(total_qty)})
        except Exception:
            cotizaciones_envio = []
        try:
            ventas_envio = []
            for v in tenant_query(Venta).filter(Venta.estado.in_(['anticipo_pagado','pagado'])).order_by(Venta.creado_en.desc()).limit(20).all():
                total_qty = sum(i.cantidad or 0 for i in v.items) if v.items else 0
                if total_qty > 0:
                    ventas_envio.append({'id': v.id, 'numero': v.numero, 'titulo': v.titulo or '', 'total_qty': int(total_qty)})
        except Exception:
            ventas_envio = []
        return render_template('empaques/index.html', items=items, productos=productos,
                               transportistas_json=trans_json,
                               cotizaciones_envio=cotizaciones_envio,
                               ventas_envio=ventas_envio)


    # ── empaques_nuevo (/empaques/nuevo)
    @app.route('/empaques/nuevo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_nuevo():
        """Crear nuevo empaque (con producto_id requerido)."""
        productos = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()

        if request.method == 'POST':
            producto_id = request.form.get('producto_id')

            if not producto_id:
                flash('Debe seleccionar un producto.', 'warning')
                return render_template('empaques/form.html', productos=productos, obj=None)

            producto = Producto.query.get_or_404(int(producto_id))

            try:
                alto = float(request.form.get('alto', 0))
                ancho = float(request.form.get('ancho', 0))
                largo = float(request.form.get('largo', 0))
                peso_unitario = float(request.form.get('peso_unitario', 0))
                peso_max_caja = float(request.form.get('peso_max_caja', 0))
                unidades_por_caja = int(request.form.get('unidades_por_caja', 1))
                notas = request.form.get('notas', '')

                ancho_caja = float(request.form.get('ancho_caja', 0))
                largo_caja = float(request.form.get('largo_caja', 0))
                alto_caja = float(request.form.get('alto_caja', 0))
                empaque = EmpaqueSecundario(
                    company_id=getattr(g, 'company_id', None),
                    producto_id=int(producto_id),
                    alto=alto,
                    ancho=ancho,
                    largo=largo,
                    peso_unitario=peso_unitario,
                    peso_max_caja=peso_max_caja,
                    unidades_por_caja=unidades_por_caja,
                    ancho_caja=ancho_caja,
                    largo_caja=largo_caja,
                    alto_caja=alto_caja,
                    notas=notas,
                    creado_por=current_user.id,
                    aprobado=False
                )
                db.session.add(empaque)
                db.session.commit()
                flash(f'Empaque para "{producto.nombre}" creado como borrador.', 'success')
                return redirect(url_for('empaques'))
            except (ValueError, TypeError) as e:
                flash('Error al procesar los valores del formulario.', 'danger')
                return render_template('empaques/form.html', productos=productos, obj=None)

        return render_template('empaques/form.html', productos=productos, obj=None)


    # ── empaques_editar (/empaques/<int:id>/editar)
    @app.route('/empaques/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_editar(id):
        """Editar un empaque existente (solo si no está aprobado, o admin)."""
        empaque = EmpaqueSecundario.query.get_or_404(id)
        productos = tenant_query(Producto).filter_by(activo=True).order_by(Producto.nombre).all()

        if empaque.aprobado and _get_rol_activo(current_user) != 'admin':
            flash('No se pueden editar empaques aprobados. Contacta al administrador.', 'warning')
            return redirect(url_for('empaques'))

        if request.method == 'POST':
            try:
                empaque.producto_id = int(request.form.get('producto_id', empaque.producto_id))
                empaque.alto = float(request.form.get('alto', 0))
                empaque.ancho = float(request.form.get('ancho', 0))
                empaque.largo = float(request.form.get('largo', 0))
                empaque.peso_unitario = float(request.form.get('peso_unitario', 0))
                empaque.peso_max_caja = float(request.form.get('peso_max_caja', 0))
                empaque.unidades_por_caja = int(request.form.get('unidades_por_caja', 1))
                empaque.notas = request.form.get('notas', '')
                db.session.commit()
                flash(f'Empaque actualizado.', 'success')
                return redirect(url_for('empaques'))
            except (ValueError, TypeError) as e:
                flash('Error al procesar los valores del formulario.', 'danger')

        return render_template('empaques/form.html', productos=productos, obj=empaque)


    # ── empaques_calcular (/empaques/calcular) — API para la calculadora
    @app.route('/empaques/calcular', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_calcular():
        """Genera TODAS las variantes de distribución (filas×columnas×capas)
        cuyo único límite real es el peso máximo por caja."""
        try:
            alto_prod    = float(request.json.get('alto_prod', 0))
            ancho_prod   = float(request.json.get('ancho_prod', 0))
            largo_prod   = float(request.json.get('largo_prod', 0))
            peso_unit    = float(request.json.get('peso_unitario', 0))
            peso_max     = float(request.json.get('peso_max_caja', 0))
            margen       = float(request.json.get('margen', 2))   # cm de holgura por lado

            if peso_unit <= 0 or peso_max <= 0:
                return jsonify({'error': 'Peso unitario y peso máximo deben ser mayores a 0'}), 400
            if alto_prod <= 0 or ancho_prod <= 0 or largo_prod <= 0:
                return jsonify({'error': 'Las dimensiones del producto deben ser mayores a 0'}), 400

            # ── Límite absoluto por peso ───────────────────────────────────────
            max_por_peso = math.floor(peso_max / peso_unit)
            if max_por_peso < 1:
                return jsonify({'error': f'Con ese peso máximo ({peso_max} kg) no cabe ni 1 unidad '
                                         f'({peso_unit} kg c/u)'}), 400

            # Exploramos hasta 2× el límite por peso para encontrar cajas de proporciones
            # adecuadas aunque geométricamente soporten más unidades que el peso permite.
            # Si la caja es más grande de lo que dicta el peso, la mostramos igualmente
            # (el empaque puede transportar hasta max_por_peso aunque la caja quepa más).
            tope = min(int(max_por_peso * 2), 1200)

            # ── Generar todas las factorizaciones con TODAS las orientaciones ──
            # Probar las 3 orientaciones únicas del producto (rotaciones XYZ)
            from itertools import permutations
            orientaciones = list(set(permutations([ancho_prod, largo_prod, alto_prod])))

            variantes = []
            seen = set()
            for total in range(1, tope + 1):
                for r in range(1, total + 1):
                    if total % r != 0:
                        continue
                    resto = total // r
                    for c in range(r, resto + 1):   # c >= r para evitar duplicados
                        if resto % c != 0:
                            continue
                        l = resto // c              # l >= c por construcción

                        # Probar cada orientación del producto
                        for (dim_x, dim_z, dim_y) in orientaciones:
                            w = round(r * dim_x + margen, 1)
                            d = round(c * dim_z + margen, 1)
                            h = round(l * dim_y + margen, 1)

                            key = (r, c, l, round(w,0), round(d,0), round(h,0))
                            if key in seen:
                                continue
                            seen.add(key)

                            volumen = round(w * d * h, 1)

                            # ── Filtro de proporciones para transporte/almacenaje ──
                            dims_u = sorted([r, c, l])
                            if dims_u[2] / max(dims_u[0], 1) > 6:
                                continue
                            dims_cm = sorted([w, d, h])
                            if dims_cm[2] / max(dims_cm[0], 0.01) > 4.5:
                                continue

                            actual_units = min(total, max_por_peso)
                            peso_total   = round(actual_units * peso_unit, 3)
                            pct_peso     = round((peso_total / peso_max) * 100, 1)

                            # Cálculo de cinta: perímetro cara superior + inferior + 30%
                            perimetro_superior = 2 * (w + d)
                            perimetro_inferior = 2 * (w + d)
                            cinta_cm = round((perimetro_superior + perimetro_inferior) * 1.3, 1)
                            cinta_m = round(cinta_cm / 100, 3)

                            variantes.append({
                                'total'      : actual_units,
                                'filas'      : r,
                                'columnas'   : c,
                                'capas'      : l,
                                'distribucion': f'{r}×{c}×{l}',
                                'ancho_caja' : w,
                                'largo_caja' : d,
                                'alto_caja'  : h,
                                'volumen_cm3': volumen,
                                'peso_total' : peso_total,
                                'pct_peso'   : pct_peso,
                                'cinta_cm'   : cinta_cm,
                                'cinta_m'    : cinta_m,
                                'orientacion': f'{dim_x}×{dim_z}×{dim_y}',
                            })

            # Ordenar: por total unidades, luego por volumen (más compacto primero)
            variantes.sort(key=lambda v: (v['total'], v['volumen_cm3']))

            return jsonify({
                'variantes'    : variantes,
                'max_por_peso' : max_por_peso,
                'total_variantes': len(variantes),
            }), 200

        except (ValueError, TypeError) as e:
            return jsonify({'error': 'Valores invalidos en el formulario'}), 400


    # ── empaques_aprobar (/empaques/<int:id>/aprobar)
    @app.route('/empaques/<int:id>/aprobar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_aprobar(id):
        """Aprueba un empaque y crea automáticamente MateriaPrima tipo 'caja'."""
        empaque = EmpaqueSecundario.query.get_or_404(id)

        if empaque.aprobado:
            flash('Este empaque ya está aprobado.', 'info')
            return redirect(url_for('empaques'))

        try:
            # Crear MateriaPrima tipo 'caja'
            nombre_mp = f'Caja {empaque.producto.nombre} x{empaque.unidades_por_caja}'

            mp = MateriaPrima(
                company_id=getattr(g, 'company_id', None),
                nombre=nombre_mp,
                categoria='empaques',
                unidad='unidades',
                stock_disponible=0,
                stock_reservado=0,
                stock_minimo=0,
                costo_unitario=0,
                producto_id=empaque.producto_id,
                activo=True
            )
            db.session.add(mp)
            db.session.flush()
            # Vincular al producto en M2M
            existe_m2m = MateriaPrimatenant_query(Producto).filter_by(
                materia_prima_id=mp.id, producto_id=empaque.producto_id).first()
            if not existe_m2m:
                db.session.add(MateriaPrimaProducto(
                    materia_prima_id=mp.id, producto_id=empaque.producto_id))

            # Vincular empaque a materia prima
            empaque.materia_prima_id = mp.id
            empaque.aprobado = True

            # ── Crear/buscar MateriaPrima de cinta de embalaje ──
            cinta_mp = tenant_query(MateriaPrima).filter(
                db.func.lower(MateriaPrima.nombre).like('%cinta%embalaje%'),
                MateriaPrima.activo == True
            ).first()
            if not cinta_mp:
                cinta_mp = MateriaPrima(
                    company_id=getattr(g, 'company_id', None),
                    nombre='Cinta de embalaje (rollo 100m)',
                    categoria='empaques',
                    unidad='metros',
                    stock_disponible=0,
                    stock_reservado=0,
                    stock_minimo=0,
                    costo_unitario=0,
                    activo=True
                )
                db.session.add(cinta_mp)
                db.session.flush()

            # Calcular cinta necesaria: perímetro superior + inferior + 30%
            ancho_caja = getattr(empaque, 'ancho_caja', 0) or 0
            largo_caja = getattr(empaque, 'largo_caja', 0) or 0
            if ancho_caja and largo_caja:
                perimetro = 2 * (ancho_caja + largo_caja)
                cinta_por_caja_cm = perimetro * 2 * 1.3  # sup + inf + 30%
                cinta_por_caja_m = round(cinta_por_caja_cm / 100, 4)
            else:
                cinta_por_caja_m = 0.5  # fallback 50cm si no hay dims

            # Agregar caja como ingrediente de la receta del producto (si existe)
            receta = Recetatenant_query(Producto).filter_by(producto_id=empaque.producto_id, activo=True).first()
            receta_msg = ''
            if receta:
                # Agregar caja si no existe
                ya_existe = RecetaItem.query.filter_by(receta_id=receta.id, materia_prima_id=mp.id).first()
                if not ya_existe:
                    cajas_por_lote = receta.unidades_produce / empaque.unidades_por_caja
                    db.session.add(RecetaItem(
                        receta_id=receta.id,
                        materia_prima_id=mp.id,
                        cantidad_por_unidad=round(1.0 / empaque.unidades_por_caja, 6),
                        es_empaque=True,
                        clasificacion='empaque_secundario'
                    ))
                    receta_msg = f' Caja agregada ({cajas_por_lote:.1f}/lote).'

                # Agregar cinta si no existe
                cinta_existe = RecetaItem.query.filter_by(receta_id=receta.id, materia_prima_id=cinta_mp.id).first()
                if not cinta_existe:
                    # Cinta por unidad = cinta_por_caja / unidades_por_caja
                    cinta_por_unidad = round(cinta_por_caja_m / empaque.unidades_por_caja, 6)
                    db.session.add(RecetaItem(
                        receta_id=receta.id,
                        materia_prima_id=cinta_mp.id,
                        cantidad_por_unidad=cinta_por_unidad,
                        es_empaque=True,
                        clasificacion='empaque_secundario'
                    ))
                    receta_msg += f' Cinta: {cinta_por_caja_m:.2f}m/caja.'
            else:
                receta_msg = ' Sin receta activa — agregar manualmente.'

            # ── Auto-crear cotización para la CAJA (específica por producto) ──
            prod_nombre = empaque.producto.nombre if empaque.producto else ''
            tiene_cot_caja = Cotizaciontenant_query(Proveedor).filter(
                db.or_(
                    CotizacionProveedor.materia_prima_id == mp.id,
                    db.func.lower(CotizacionProveedor.nombre_producto) == mp.nombre.lower()
                )
            ).first()
            if not tiene_cot_caja:
                db.session.add(CotizacionProveedor(
                    company_id=getattr(g, 'company_id', None),
                    nombre_producto=f'{mp.nombre} — {prod_nombre}',
                    tipo_cotizacion='maquila',
                    tipo_producto_servicio='empaque secundario',
                    unidad='unidades',
                    estado='en_revision',
                    materia_prima_id=mp.id,
                    precio_unitario=0,
                    notas=f'Cotizar caja para {prod_nombre}. Incluir cantidad mínima y transporte.',
                    creado_por=current_user.id
                ))

            # ── Cotización de CINTA: una sola global (rollo 100m, compartida) ──
            tiene_cot_cinta = Cotizaciontenant_query(Proveedor).filter(
                db.or_(
                    CotizacionProveedor.materia_prima_id == cinta_mp.id,
                    db.func.lower(CotizacionProveedor.nombre_producto).like('%cinta%embalaje%')
                )
            ).first()
            if not tiene_cot_cinta:
                db.session.add(CotizacionProveedor(
                    company_id=getattr(g, 'company_id', None),
                    nombre_producto='Cinta de embalaje — Rollo 100m',
                    tipo_cotizacion='maquila',
                    tipo_producto_servicio='empaque secundario',
                    unidad='metros',
                    unidades_minimas=100,
                    estado='en_revision',
                    materia_prima_id=cinta_mp.id,
                    precio_unitario=0,
                    notas='Cotizar rollo de 100 metros. Incluir cantidad mínima de rollos y costo de transporte.',
                    creado_por=current_user.id
                ))

            # Vincular cinta al producto (M2M, sin producto_id fijo porque es compartida)
            if cinta_mp and empaque.producto_id:
                cinta_m2m = MateriaPrimatenant_query(Producto).filter_by(
                    materia_prima_id=cinta_mp.id, producto_id=empaque.producto_id).first()
                if not cinta_m2m:
                    db.session.add(MateriaPrimaProducto(
                        materia_prima_id=cinta_mp.id, producto_id=empaque.producto_id))

            db.session.commit()
            # Recalcular costo de la receta
            try:
                _calcular_costo_receta(empaque.producto_id)
                db.session.commit()
            except Exception:
                pass
            flash(f'Empaque aprobado. MP "{nombre_mp}" creada.{receta_msg}', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error al aprobar el empaque.', 'danger')

        return redirect(url_for('empaques'))


    # ── empaques_eliminar (/empaques/<int:id>/eliminar)
    @app.route('/empaques/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_eliminar(id):
        """Elimina un empaque (solo si no está aprobado o si es admin)."""
        empaque = EmpaqueSecundario.query.get_or_404(id)

        # Solo admin puede eliminar empaques aprobados
        if empaque.aprobado and _get_rol_activo(current_user) != 'admin':
            flash('Solo administradores pueden eliminar empaques aprobados.', 'danger')
            return redirect(url_for('empaques'))

        try:
            nombre_producto = empaque.producto.nombre if empaque.producto else 'Desconocido'
            producto_id = empaque.producto_id

            # Si estaba aprobado, quitar de la receta y marcar cotización como no actual
            if empaque.aprobado and empaque.materia_prima_id:
                mp_id = empaque.materia_prima_id

                # Quitar de la receta activa (el item sigue disponible para futuras recetas)
                receta = Recetatenant_query(Producto).filter_by(producto_id=producto_id, activo=True).first()
                if receta:
                    RecetaItem.query.filter_by(receta_id=receta.id, materia_prima_id=mp_id).delete()

                    # Si no quedan otros empaques aprobados, quitar cinta de esta receta
                    otros_empaques = tenant_query(EmpaqueSecundario).filter(
                        EmpaqueSecundario.producto_id == producto_id,
                        EmpaqueSecundario.id != empaque.id,
                        EmpaqueSecundario.aprobado == True
                    ).count()
                    if otros_empaques == 0:
                        cinta_mp = tenant_query(MateriaPrima).filter(
                            db.func.lower(MateriaPrima.nombre).like('%cinta%embalaje%'),
                            MateriaPrima.activo == True
                        ).first()
                        if cinta_mp:
                            RecetaItem.query.filter_by(receta_id=receta.id, materia_prima_id=cinta_mp.id).delete()

                # Marcar cotización de la caja como "vencida" (no actual), NO eliminar
                cots_caja = Cotizaciontenant_query(Proveedor).filter_by(materia_prima_id=mp_id).all()
                for cot in cots_caja:
                    if cot.estado in ('vigente', 'en_revision'):
                        cot.estado = 'vencida'

            db.session.delete(empaque)
            db.session.commit()

            # Recalcular costo si hay receta
            if producto_id:
                try:
                    _calcular_costo_receta(producto_id)
                    db.session.commit()
                except Exception:
                    pass

            flash(f'Empaque de "{nombre_producto}" eliminado de receta. Cotización marcada como no actual. Stock y materias primas conservados.', 'info')
        except Exception as e:
            db.session.rollback()
            flash('Error al eliminar el empaque.', 'danger')

        return redirect(url_for('empaques'))
