# routes/barcode.py — Codigos de barras: generacion, scanner, stock in/out
from flask import render_template, redirect, url_for, flash, request, jsonify, g, send_file
from flask_login import login_required, current_user
from extensions import db, tenant_query
from models import *
from utils import *
from datetime import datetime
import io, logging, json

def register(app):

    # ══════════════════════════════════════════════════════════════
    # BARCODE GENERATION
    # ══════════════════════════════════════════════════════════════

    def _generate_barcode_image(code, barcode_format='code128'):
        """Generate barcode as PNG bytes."""
        import barcode
        from barcode.writer import ImageWriter
        bc_class = barcode.get_barcode_class(barcode_format)
        bc = bc_class(str(code), writer=ImageWriter())
        buffer = io.BytesIO()
        bc.write(buffer, options={'module_width': 0.4, 'module_height': 15,
                                   'font_size': 10, 'text_distance': 5,
                                   'quiet_zone': 6})
        buffer.seek(0)
        return buffer

    def _auto_generate_code(product_id):
        """Generate a unique barcode number for a product."""
        # Format: 200 (internal) + company_id (3 digits) + product_id (5 digits) + check digit
        cid = getattr(g, 'company_id', None) or 1
        base = f'200{cid:03d}{product_id:05d}'
        # EAN-13 check digit
        total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(base[:12]))
        check = (10 - total % 10) % 10
        return base[:12] + str(check)

    @app.route('/barcode/generar/<int:producto_id>')
    @login_required
    def barcode_generar(producto_id):
        """Generate or retrieve barcode for a product."""
        p = Producto.query.get_or_404(producto_id)
        if not p.codigo_barras:
            p.codigo_barras = _auto_generate_code(p.id)
            db.session.commit()
        buffer = _generate_barcode_image(p.codigo_barras)
        return send_file(buffer, mimetype='image/png',
                         download_name=f'barcode_{p.sku or p.id}.png')

    @app.route('/barcode/descargar/<int:producto_id>')
    @login_required
    def barcode_descargar(producto_id):
        """Download barcode as PNG."""
        p = Producto.query.get_or_404(producto_id)
        if not p.codigo_barras:
            p.codigo_barras = _auto_generate_code(p.id)
            db.session.commit()
        buffer = _generate_barcode_image(p.codigo_barras)
        return send_file(buffer, mimetype='image/png', as_attachment=True,
                         download_name=f'barcode_{p.nombre.replace(" ","_")}_{p.codigo_barras}.png')

    @app.route('/api/barcode/auto-generar/<int:producto_id>', methods=['POST'])
    @login_required
    def api_barcode_autogenerar(producto_id):
        """Auto-generate barcode for a product."""
        p = Producto.query.get_or_404(producto_id)
        if not p.codigo_barras:
            p.codigo_barras = _auto_generate_code(p.id)
        db.session.commit()
        return jsonify({'ok': True, 'codigo': p.codigo_barras})

    @app.route('/api/barcode/verificar/<int:producto_id>', methods=['POST'])
    @login_required
    def api_barcode_verificar(producto_id):
        """Mark barcode as verified."""
        p = Producto.query.get_or_404(producto_id)
        p.barcode_verificado = True
        nuevo = request.json.get('codigo_barras')
        if nuevo and nuevo != p.codigo_barras:
            p.codigo_barras = nuevo
        db.session.commit()
        return jsonify({'ok': True, 'codigo': p.codigo_barras})

    # ══════════════════════════════════════════════════════════════
    # SCANNER — scan barcode with phone camera
    # ══════════════════════════════════════════════════════════════

    @app.route('/scanner')
    @login_required
    def scanner():
        """Barcode scanner page — works on mobile with camera."""
        return render_template('scanner.html')

    @app.route('/api/scanner/buscar', methods=['POST'])
    @login_required
    def api_scanner_buscar():
        """Look up a product by barcode."""
        codigo = request.json.get('codigo', '').strip()
        if not codigo:
            return jsonify({'error': 'Codigo vacio'}), 400

        # Search in products
        p = tenant_query(Producto).filter_by(codigo_barras=codigo, activo=True).first()
        if p:
            return jsonify({
                'tipo': 'producto',
                'id': p.id,
                'nombre': p.nombre,
                'sku': p.sku or '',
                'precio': p.precio or 0,
                'costo': p.costo_compra or p.costo or 0,
                'stock': p.stock or 0,
                'stock_minimo': p.stock_minimo or 0,
                'tipo_producto': p.tipo_producto or 'produccion',
                'codigo_barras': p.codigo_barras,
                'verificado': p.barcode_verificado,
                'categoria': p.categoria or '',
            })

        # Search in materias primas (if they have barcode field in future)
        mp = tenant_query(MateriaPrima).filter_by(activo=True).filter(
            MateriaPrima.nombre.ilike(f'%{codigo}%')
        ).first()
        if mp:
            return jsonify({
                'tipo': 'materia_prima',
                'id': mp.id,
                'nombre': mp.nombre,
                'unidad': mp.unidad,
                'stock': mp.stock_disponible or 0,
                'costo': mp.costo_unitario or 0,
            })

        return jsonify({'error': f'Producto no encontrado para codigo: {codigo}'}), 404

    @app.route('/api/scanner/stock', methods=['POST'])
    @login_required
    def api_scanner_stock():
        """Add or remove stock via scanner."""
        data = request.json
        producto_id = data.get('producto_id')
        cantidad = int(data.get('cantidad', 0))
        operacion = data.get('operacion', 'ingreso')  # ingreso | salida
        notas = data.get('notas', '')

        if not producto_id or cantidad <= 0:
            return jsonify({'error': 'Producto y cantidad requeridos'}), 400

        p = Producto.query.get_or_404(producto_id)
        cid = getattr(g, 'company_id', None)

        if operacion == 'ingreso':
            p.stock = (p.stock or 0) + cantidad
            # Verify barcode on first entry
            if not p.barcode_verificado:
                p.barcode_verificado = True
        elif operacion == 'salida':
            if (p.stock or 0) < cantidad:
                return jsonify({'error': f'Stock insuficiente. Disponible: {p.stock}'}), 400
            p.stock = (p.stock or 0) - cantidad

        # Log movement
        try:
            db.session.add(MovimientoInventario(
                company_id=cid,
                producto_id=p.id,
                tipo=operacion,
                cantidad=cantidad if operacion == 'ingreso' else -cantidad,
                stock_despues=p.stock,
                notas=f'Scanner: {notas}' if notas else f'Scanner {operacion}',
                usuario_id=current_user.id
            ))
        except Exception:
            pass

        db.session.commit()
        return jsonify({
            'ok': True,
            'stock_nuevo': p.stock,
            'operacion': operacion,
            'cantidad': cantidad
        })

    # ══════════════════════════════════════════════════════════════
    # PRODUCTO COMERCIAL — simplified flow
    # ══════════════════════════════════════════════════════════════

    @app.route('/inventario/producto-comercial/nuevo', methods=['GET', 'POST'])
    @login_required
    def producto_comercial_nuevo():
        """Create a commercial product (buy & resell, no manufacturing)."""
        proveedores = tenant_query(Proveedor).filter_by(activo=True).order_by(Proveedor.empresa).all()
        if request.method == 'POST':
            cid = getattr(g, 'company_id', None)
            costo = float(request.form.get('costo_compra') or 0)
            margen = float(request.form.get('margen_comercial') or 30)
            precio_venta = round(costo * (1 + margen / 100), 2)
            codigo_barras = request.form.get('codigo_barras', '').strip() or None

            p = Producto(
                company_id=cid,
                nombre=request.form['nombre'],
                descripcion=request.form.get('descripcion', ''),
                tipo_producto='comercial',
                costo_compra=costo,
                costo=costo,
                margen_comercial=margen,
                precio=precio_venta,
                stock=0,
                stock_minimo=int(request.form.get('stock_minimo') or 5),
                categoria=request.form.get('categoria', ''),
                proveedor_id=int(request.form.get('proveedor_id')) if request.form.get('proveedor_id') else None,
                codigo_barras=codigo_barras,
                activo=True
            )
            db.session.add(p)
            db.session.flush()

            # Auto-generate barcode if not provided
            if not p.codigo_barras:
                p.codigo_barras = _auto_generate_code(p.id)

            _log('crear', 'producto', p.id, f'Producto comercial creado: {p.nombre}')
            db.session.commit()
            flash(f'Producto comercial "{p.nombre}" creado. Precio venta: ${precio_venta:,.0f}', 'success')
            return redirect(url_for('inventario_index'))

        return render_template('inventario/producto_comercial_form.html',
                               proveedores=proveedores, obj=None)

    # ══════════════════════════════════════════════════════════════
    # PORTAL SCANNER (cliente: entregas, proveedor: recepciones)
    # ══════════════════════════════════════════════════════════════

    @app.route('/portal/scanner')
    @login_required
    def portal_scanner():
        """Scanner for portal users — clients confirm deliveries, suppliers confirm receipts."""
        modo = request.args.get('modo', 'entrega')
        return render_template('portal/scanner.html', modo=modo)

    @app.route('/api/portal/scanner/registrar', methods=['POST'])
    @login_required
    def api_portal_scanner_registrar():
        """Register a delivery/receipt scan from portal."""
        data = request.json
        codigo = data.get('codigo', '').strip()
        cantidad = int(data.get('cantidad', 0))
        modo = data.get('modo', 'entrega')
        notas = data.get('notas', '')

        if not codigo or cantidad <= 0:
            return jsonify({'error': 'Codigo y cantidad requeridos'}), 400

        # Find product across companies (portal users may scan products from the company they trade with)
        p = Producto.query.filter_by(codigo_barras=codigo, activo=True).first()
        if not p:
            return jsonify({'error': f'Producto no encontrado: {codigo}'}), 404

        rol = current_user.rol
        if modo == 'entrega' and rol == 'cliente':
            # Client confirms they received the delivery
            descripcion = f'Entrega confirmada por cliente {current_user.nombre}: {cantidad} uds'
        elif modo == 'recepcion' and rol == 'proveedor':
            # Supplier confirms they sent/delivered product
            descripcion = f'Envio registrado por proveedor {current_user.nombre}: {cantidad} uds'
        else:
            descripcion = f'Scan portal ({modo}) por {current_user.nombre}: {cantidad} uds'

        # Log the scan (don't modify stock — that's the company admin's job)
        try:
            db.session.add(Actividad(
                company_id=p.company_id,
                tipo='scanner',
                entidad='producto',
                entidad_id=p.id,
                descripcion=f'{descripcion}. {notas}'.strip(),
                usuario_id=current_user.id
            ))
            # Notify company admin
            admin = User.query.filter_by(company_id=p.company_id, rol='admin', activo=True).first()
            if admin:
                db.session.add(Notificacion(
                    company_id=p.company_id,
                    user_id=admin.id,
                    tipo='scanner',
                    titulo=f'Scan {modo}: {p.nombre}',
                    mensaje=f'{current_user.nombre} registro {modo} de {cantidad} uds de "{p.nombre}" via scanner',
                    creado_en=__import__("datetime").datetime.utcnow()
                ))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logging.warning(f'portal_scanner_registrar: {e}')

        return jsonify({
            'ok': True,
            'producto': p.nombre,
            'cantidad': cantidad,
            'modo': modo,
            'mensaje': descripcion
        })
