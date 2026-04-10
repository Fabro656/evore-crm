# routes/empaques.py — Módulo Empaques Secundarios v30
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime
import math

def register(app):
    def _noop(*a, **kw): pass

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


    # ── empaques_calcular (/empaques/calcular) — API para la calculadora
    @app.route('/empaques/calcular', methods=['POST'])
    @login_required
    @requiere_modulo('produccion')
    def empaques_calcular():
        """Calcula opciones de empaque basado en dimensiones y peso."""
        try:
            alto_prod = float(request.json.get('alto_prod', 0))
            ancho_prod = float(request.json.get('ancho_prod', 0))
            largo_prod = float(request.json.get('largo_prod', 0))
            peso_unitario = float(request.json.get('peso_unitario', 0))
            peso_max_caja = float(request.json.get('peso_max_caja', 0))

            if peso_unitario <= 0 or peso_max_caja <= 0:
                return jsonify({'error': 'Peso unitario y peso máximo de caja deben ser mayores a 0'}), 400

            # Calcular cuántas unidades caben por peso
            max_unidades_por_peso = math.floor(peso_max_caja / peso_unitario)

            # Opciones de unidades a sugerir: [6, 12, 24, 48] filtradas
            opciones_sugeridas = [6, 12, 24, 48]
            opciones = [o for o in opciones_sugeridas if o <= max_unidades_por_peso]

            if not opciones:
                opciones = [max_unidades_por_peso] if max_unidades_por_peso > 0 else [1]

            # Limitar a máximo 3 opciones
            opciones = opciones[:3]

            # Calcular dimensiones y peso para cada opción
            resultados = []
            for unidades in opciones:
                # Dimensiones mínimas de caja (simple: asumimos disposición lineal)
                # Para simplificar: altura = altura_prod, ancho = ancho_prod,
                # largo = largo_prod * unidades (apiladas)
                alto_caja = alto_prod + 2  # +2cm para margen
                ancho_caja = ancho_prod + 2
                largo_caja = (largo_prod * unidades) + 2

                peso_total_caja = unidades * peso_unitario

                resultados.append({
                    'unidades': unidades,
                    'alto_caja': round(alto_caja, 2),
                    'ancho_caja': round(ancho_caja, 2),
                    'largo_caja': round(largo_caja, 2),
                    'peso_total': round(peso_total_caja, 2)
                })

            return jsonify({'opciones': resultados}), 200
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
