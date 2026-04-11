# routes/empaques.py — Módulo Empaques Secundarios v30
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime
import math

def register(app):

    # ── empaques (/empaques)
    @app.route('/empaques')
    @login_required
    @requiere_modulo('produccion')
    def empaques():
        """Lista todos los empaques secundarios con calculadora inline."""
        items = EmpaqueSecundario.query.join(Producto).order_by(Producto.nombre).all()
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        return render_template('empaques/index.html', items=items, productos=productos)


    # ── empaques_nuevo (/empaques/nuevo)
    @app.route('/empaques/nuevo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_nuevo():
        """Crear nuevo empaque (con producto_id requerido)."""
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()

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

                empaque = EmpaqueSecundario(
                    producto_id=int(producto_id),
                    alto=alto,
                    ancho=ancho,
                    largo=largo,
                    peso_unitario=peso_unitario,
                    peso_max_caja=peso_max_caja,
                    unidades_por_caja=unidades_por_caja,
                    notas=notas,
                    creado_por=current_user.id,
                    aprobado=False
                )
                db.session.add(empaque)
                db.session.commit()
                flash(f'Empaque para "{producto.nombre}" creado como borrador.', 'success')
                return redirect(url_for('empaques'))
            except (ValueError, TypeError) as e:
                flash(f'Error al procesar valores: {str(e)}', 'danger')
                return render_template('empaques/form.html', productos=productos, obj=None)

        return render_template('empaques/form.html', productos=productos, obj=None)


    # ── empaques_editar (/empaques/<int:id>/editar)
    @app.route('/empaques/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_editar(id):
        """Editar un empaque existente (solo si no está aprobado, o admin)."""
        empaque = EmpaqueSecundario.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()

        if empaque.aprobado and current_user.rol != 'admin':
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
                flash(f'Error al procesar valores: {str(e)}', 'danger')

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

            # ── Generar todas las factorizaciones únicas (r ≤ c ≤ l) ───────────
            # r = filas (ancho), c = columnas (largo), l = capas (alto)
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
                        key = (r, c, l)
                        if key in seen:
                            continue
                        seen.add(key)

                        # Dimensiones internas de la caja:
                        #   ancho_caja = r * ancho_prod + margen
                        #   largo_caja = c * largo_prod + margen
                        #   alto_caja  = l * alto_prod  + margen
                        w = round(r * ancho_prod + margen, 1)
                        d = round(c * largo_prod + margen, 1)
                        h = round(l * alto_prod  + margen, 1)
                        volumen    = round(w * d * h, 1)

                        # ── Filtro de proporciones para transporte/almacenaje ─────
                        # 1) En unidades: ningún lado puede ser más de 6× otro
                        dims_u = sorted([r, c, l])
                        if dims_u[2] / max(dims_u[0], 1) > 6:
                            continue
                        # 2) En centímetros: ratio máx/mín de la caja ≤ 4.5
                        #    (evita palillos; si total > max_por_peso la caja es válida
                        #    pero sólo se cargan max_por_peso unidades)
                        dims_cm = sorted([w, d, h])
                        if dims_cm[2] / max(dims_cm[0], 0.01) > 4.5:
                            continue

                        # Si la configuración geométrica supera el límite de peso,
                        # sólo cargamos max_por_peso unidades (caja "sobredimensionada").
                        # Esto permite encontrar cajas de buenas proporciones aunque
                        # el peso sea el factor limitante.
                        actual_units = min(total, max_por_peso)
                        peso_total   = round(actual_units * peso_unit, 3)
                        pct_peso     = round((peso_total / peso_max) * 100, 1)

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
                        })

            # Ordenar: por total unidades, luego por volumen (más compacto primero)
            variantes.sort(key=lambda v: (v['total'], v['volumen_cm3']))

            return jsonify({
                'variantes'    : variantes,
                'max_por_peso' : max_por_peso,
                'total_variantes': len(variantes),
            }), 200

        except (ValueError, TypeError) as e:
            return jsonify({'error': f'Valores inválidos: {str(e)}'}), 400


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
                nombre=nombre_mp,
                categoria='empaques',
                unidad='unidades',
                stock_disponible=0,
                stock_reservado=0,
                stock_minimo=0,
                costo_unitario=0,
                activo=True
            )
            db.session.add(mp)
            db.session.flush()  # Para obtener el ID generado

            # Vincular empaque a materia prima
            empaque.materia_prima_id = mp.id
            empaque.aprobado = True

            db.session.commit()
            flash(f'Empaque aprobado. Materia prima "{nombre_mp}" creada automáticamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al aprobar empaque: {str(e)}', 'danger')

        return redirect(url_for('empaques'))


    # ── empaques_eliminar (/empaques/<int:id>/eliminar)
    @app.route('/empaques/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_eliminar(id):
        """Elimina un empaque (solo si no está aprobado o si es admin)."""
        empaque = EmpaqueSecundario.query.get_or_404(id)

        # Solo admin puede eliminar empaques aprobados
        if empaque.aprobado and current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar empaques aprobados.', 'danger')
            return redirect(url_for('empaques'))

        try:
            nombre_producto = empaque.producto.nombre if empaque.producto else 'Desconocido'
            db.session.delete(empaque)
            db.session.commit()
            flash(f'Empaque de "{nombre_producto}" eliminado.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar empaque: {str(e)}', 'danger')

        return redirect(url_for('empaques'))
