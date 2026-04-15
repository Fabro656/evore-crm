# routes/notas.py — v36 notas mejoradas con vinculos a entidades
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

    # ── notas (/notas)
    @app.route('/notas')
    @login_required
    @requiere_modulo('notas')
    def notas():
        cliente_f = request.args.get('cliente_id','')
        tipo_f = request.args.get('tipo_nota','')
        estado_f = request.args.get('estado_nota','')
        oc_f = request.args.get('orden_compra_id','')
        venta_f = request.args.get('venta_id','')
        try:
            q = Nota.query
            if cliente_f: q = q.filter_by(cliente_id=int(cliente_f))
            # Filtros v36 — proteger contra columnas faltantes en DB legacy
            try:
                if tipo_f: q = q.filter_by(tipo_nota=tipo_f)
                if estado_f: q = q.filter_by(estado_nota=estado_f)
                if oc_f: q = q.filter_by(orden_compra_id=int(oc_f))
                if venta_f: q = q.filter_by(venta_id=int(venta_f))
            except Exception:
                pass
            items = q.order_by(Nota.actualizado_en.desc()).all()
        except Exception as e:
            logging.warning(f'notas: query error (posible columna faltante): {e}')
            items = Nota.query.order_by(Nota.creado_en.desc()).all()
        return render_template('notas/index.html',
            items=items,
            clientes_list=Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all(),
            productos_list=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
            cliente_f=cliente_f, tipo_f=tipo_f, estado_f=estado_f)


    # ── nota_nueva (/notas/nueva)
    @app.route('/notas/nueva', methods=['GET','POST'])
    @login_required
    @requiere_modulo('notas')
    def nota_nueva():
        cl = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        pl = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        provs = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all()
        try:
            ocs = OrdenCompra.query.filter(OrdenCompra.estado != 'cancelada').order_by(OrdenCompra.creado_en.desc()).limit(20).all()
        except Exception:
            ocs = []
        try:
            ventas = Venta.query.filter(Venta.estado != 'cancelado').order_by(Venta.creado_en.desc()).limit(20).all()
        except Exception:
            ventas = []
        if request.method == 'POST':
            fd_rev = request.form.get('fecha_revision')
            kwargs = dict(
                titulo=request.form.get('titulo','').strip() or None,
                contenido=request.form['contenido'],
                cliente_id=request.form.get('cliente_id') or None,
                producto_id=request.form.get('producto_id') or None,
                modulo=request.form.get('modulo','') or None,
                fecha_revision=datetime.strptime(fd_rev,'%Y-%m-%d').date() if fd_rev else None,
                creado_por=current_user.id)
            # Campos v36 — solo agregar si la columna existe
            for field in ['orden_compra_id','venta_id','proveedor_id']:
                val = request.form.get(field) or None
                if val and hasattr(Nota, field): kwargs[field] = val
            if hasattr(Nota, 'tipo_nota'): kwargs['tipo_nota'] = request.form.get('tipo_nota','nota')
            if hasattr(Nota, 'estado_nota'): kwargs['estado_nota'] = request.form.get('estado_nota','abierta')
            if hasattr(Nota, 'prioridad'): kwargs['prioridad'] = request.form.get('prioridad','normal')
            kwargs['company_id'] = getattr(g, 'company_id', None)
            n = Nota(**kwargs)
            db.session.add(n)
            db.session.commit()
            flash('Nota guardada.','success'); return redirect(url_for('notas'))
        # Pre-fill from query params (para crear desde OC/venta)
        pre_oc = request.args.get('orden_compra_id', type=int)
        pre_venta = request.args.get('venta_id', type=int)
        return render_template('notas/form.html', obj=None, titulo='Nueva Nota',
            clientes_list=cl, productos_list=pl, proveedores_list=provs,
            ocs_list=ocs, ventas_list=ventas,
            pre_oc=pre_oc, pre_venta=pre_venta)


    # ── nota_editar (/notas/<int:id>/editar)
    @app.route('/notas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('notas')
    def nota_editar(id):
        obj = Nota.query.get_or_404(id)
        cl  = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        pl  = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        provs = Proveedor.query.filter_by(activo=True).order_by(Proveedor.empresa).all()
        try:
            ocs = OrdenCompra.query.filter(OrdenCompra.estado != 'cancelada').order_by(OrdenCompra.creado_en.desc()).limit(20).all()
        except Exception:
            ocs = []
        try:
            ventas = Venta.query.filter(Venta.estado != 'cancelado').order_by(Venta.creado_en.desc()).limit(20).all()
        except Exception:
            ventas = []
        if request.method == 'POST':
            fd_rev = request.form.get('fecha_revision')
            obj.titulo=request.form.get('titulo','').strip() or None
            obj.contenido=request.form['contenido']
            obj.cliente_id=request.form.get('cliente_id') or None
            obj.producto_id=request.form.get('producto_id') or None
            obj.modulo=request.form.get('modulo','') or None
            obj.fecha_revision=datetime.strptime(fd_rev,'%Y-%m-%d').date() if fd_rev else None
            obj.actualizado_en=datetime.utcnow()
            obj.orden_compra_id=request.form.get('orden_compra_id') or None
            obj.venta_id=request.form.get('venta_id') or None
            obj.proveedor_id=request.form.get('proveedor_id') or None
            obj.tipo_nota=request.form.get('tipo_nota','nota')
            obj.estado_nota=request.form.get('estado_nota','abierta')
            obj.prioridad=request.form.get('prioridad','normal')
            db.session.commit()
            flash('Nota actualizada.','success'); return redirect(url_for('notas'))
        return render_template('notas/form.html', obj=obj, titulo='Editar Nota',
            clientes_list=cl, productos_list=pl, proveedores_list=provs,
            ocs_list=ocs, ventas_list=ventas, pre_oc=None, pre_venta=None)


    # ── nota_resolver (/notas/<int:id>/resolver)
    @app.route('/notas/<int:id>/resolver', methods=['POST'])
    @login_required
    @requiere_modulo('notas')
    def nota_resolver(id):
        obj = Nota.query.get_or_404(id)
        obj.estado_nota = 'resuelta'
        obj.actualizado_en = datetime.utcnow()
        db.session.commit()
        flash('Nota marcada como resuelta.', 'success')
        return redirect(url_for('notas'))


    # ── nota_eliminar (/notas/<int:id>/eliminar)
    @app.route('/notas/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('notas')
    def nota_eliminar(id):
        if _get_rol_activo(current_user) != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=Nota.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Nota eliminada.','info'); return redirect(url_for('notas'))

