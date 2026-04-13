# routes/servicios.py — Módulo Servicios v30
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from extensions import db
from models import *
from utils import *
from datetime import datetime

def register(app):

    # ── servicios (/servicios)
    @app.route('/servicios')
    @login_required
    @requiere_modulo('ventas')
    def servicios():
        """Lista todos los servicios con estadísticas."""
        items = Servicio.query.order_by(Servicio.nombre).all()

        # Estadísticas
        activos_count = len([s for s in items if s.activo])
        precios = [s.precio_venta for s in items if s.activo and s.precio_venta]
        precio_min = min(precios) if precios else 0
        precio_max = max(precios) if precios else 0

        return render_template('servicios/index.html',
                               items=items,
                               activos_count=activos_count,
                               precio_min=precio_min,
                               precio_max=precio_max)


    # ── servicios_nuevo (/servicios/nuevo)
    @app.route('/servicios/nuevo', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('ventas')
    def servicios_nuevo():
        """Crear nuevo servicio."""
        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()

            if not nombre:
                flash('El nombre del servicio es obligatorio.', 'warning')
                return render_template('servicios/form.html', obj=None)

            # Verificar duplicado
            if Servicio.query.filter_by(nombre=nombre).first():
                flash(f'Ya existe un servicio llamado "{nombre}".', 'warning')
                return render_template('servicios/form.html', obj=None)

            try:
                descripcion = request.form.get('descripcion', '')
                categoria = request.form.get('categoria', '')
                costo_interno = float(request.form.get('costo_interno', 0))
                precio_venta = float(request.form.get('precio_venta', 0))
                unidad = request.form.get('unidad', 'servicio')

                servicio = Servicio(
                    nombre=nombre,
                    descripcion=descripcion,
                    categoria=categoria,
                    costo_interno=costo_interno,
                    precio_venta=precio_venta,
                    unidad=unidad,
                    activo=True,
                    creado_por=current_user.id
                )
                db.session.add(servicio)
                db.session.commit()
                flash(f'Servicio "{nombre}" creado exitosamente.', 'success')
                return redirect(url_for('servicios'))
            except (ValueError, TypeError) as e:
                flash(f'Error al procesar valores: {str(e)}', 'danger')
                return render_template('servicios/form.html', obj=None)

        return render_template('servicios/form.html', obj=None)


    # ── servicios_editar (/servicios/<int:id>/editar)
    @app.route('/servicios/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    @requiere_modulo('ventas')
    def servicios_editar(id):
        """Editar un servicio existente."""
        obj = Servicio.query.get_or_404(id)

        if request.method == 'POST':
            nombre = request.form.get('nombre', '').strip()

            if not nombre:
                flash('El nombre del servicio es obligatorio.', 'warning')
                return render_template('servicios/form.html', obj=obj)

            # Verificar duplicado (excluyendo el mismo objeto)
            duplicado = Servicio.query.filter(
                Servicio.nombre == nombre,
                Servicio.id != id
            ).first()
            if duplicado:
                flash(f'Ya existe otro servicio llamado "{nombre}".', 'warning')
                return render_template('servicios/form.html', obj=obj)

            try:
                obj.nombre = nombre
                obj.descripcion = request.form.get('descripcion', '')
                obj.categoria = request.form.get('categoria', '')
                obj.costo_interno = float(request.form.get('costo_interno', 0))
                obj.precio_venta = float(request.form.get('precio_venta', 0))
                obj.unidad = request.form.get('unidad', 'servicio')

                db.session.commit()
                flash(f'Servicio "{nombre}" actualizado exitosamente.', 'success')
                return redirect(url_for('servicios'))
            except (ValueError, TypeError) as e:
                flash(f'Error al procesar valores: {str(e)}', 'danger')
                return render_template('servicios/form.html', obj=obj)

        return render_template('servicios/form.html', obj=obj)


    # ── servicios_toggle (/servicios/<int:id>/toggle)
    @app.route('/servicios/<int:id>/toggle', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def servicios_toggle(id):
        """Activar/desactivar un servicio."""
        obj = Servicio.query.get_or_404(id)

        try:
            obj.activo = not obj.activo
            db.session.commit()
            estado = 'activado' if obj.activo else 'desactivado'
            flash(f'Servicio "{obj.nombre}" {estado}.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al cambiar estado: {str(e)}', 'danger')

        return redirect(url_for('servicios'))


    # ── servicios_eliminar (/servicios/<int:id>/eliminar)
    @app.route('/servicios/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('ventas')
    def servicios_eliminar(id):
        """Eliminar un servicio (solo admin)."""
        if _get_rol_activo(current_user) != 'admin':
            flash('Solo administradores pueden eliminar servicios.', 'danger')
            return redirect(url_for('servicios'))

        obj = Servicio.query.get_or_404(id)
        nombre = obj.nombre

        try:
            db.session.delete(obj)
            db.session.commit()
            flash(f'Servicio "{nombre}" eliminado.', 'info')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al eliminar servicio: {str(e)}', 'danger')

        return redirect(url_for('servicios'))


    # ── API: servicios_json (/api/servicios/json)
    @app.route('/api/servicios/json')
    @login_required
    @requiere_modulo('ventas')
    def servicios_json():
        """Retorna JSON de todos los servicios activos (para usar en forms de ventas/cotizaciones)."""
        servicios = Servicio.query.filter_by(activo=True).order_by(Servicio.nombre).all()
        return jsonify([
            {
                'id': s.id,
                'nombre': s.nombre,
                'categoria': s.categoria or '',
                'precio_venta': float(s.precio_venta or 0),
                'costo_interno': float(s.costo_interno or 0),
                'unidad': s.unidad or 'servicio',
                'margen': s.margen
            }
            for s in servicios
        ])
