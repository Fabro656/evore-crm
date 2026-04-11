# routes/clientes.py — reconstruido desde v27 con CRUD completo
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

    # ── Helpers ─────────────────────────────────────────────────────
    def _save_contactos(cliente_obj):
        ContactoCliente.query.filter_by(cliente_id=cliente_obj.id).delete()
        nombres = request.form.getlist('contacto_nombre[]')
        cargos  = request.form.getlist('contacto_cargo[]')
        emails  = request.form.getlist('contacto_email[]')
        tels    = request.form.getlist('contacto_tel[]')
        for i, nombre in enumerate(nombres):
            if not nombre.strip(): continue
            db.session.add(ContactoCliente(
                cliente_id=cliente_obj.id, nombre=nombre.strip(),
                cargo=cargos[i] if i < len(cargos) else '',
                email=emails[i] if i < len(emails) else '',
                telefono=tels[i] if i < len(tels) else ''))


    # ── clientes (/clientes)
    @app.route('/clientes')
    @login_required
    @requiere_modulo('clientes')
    def clientes():
        busqueda = request.args.get('buscar','')
        estado_rel_f = request.args.get('estado_rel','')
        q = Cliente.query
        if busqueda:
            q = q.filter(db.or_(Cliente.nombre.ilike(f'%{busqueda}%'),
                                 Cliente.empresa.ilike(f'%{busqueda}%'),
                                 Cliente.nit.ilike(f'%{busqueda}%')))
        if estado_rel_f: q = q.filter_by(estado_relacion=estado_rel_f)
        return render_template('clientes/index.html', items=q.order_by(Cliente.empresa, Cliente.nombre).all(),
                               busqueda=busqueda, estado_rel_f=estado_rel_f)
    

    # ── cliente_nuevo (/clientes/nuevo)
    @app.route('/clientes/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('clientes')
    def cliente_nuevo():
        if request.method == 'POST':
            sales_manager_id = request.form.get('sales_manager_id','').strip()
            try:
                sales_manager_id = int(sales_manager_id) if sales_manager_id else None
            except (ValueError, TypeError):
                sales_manager_id = None
            anticipo_pct = request.form.get('anticipo_pct','').strip()
            try:
                anticipo_pct = float(anticipo_pct) if anticipo_pct else None
            except (ValueError, TypeError):
                anticipo_pct = None
            minimo_pedido = request.form.get('minimo_pedido','').strip()
            try:
                minimo_pedido = float(minimo_pedido) if minimo_pedido else None
            except (ValueError, TypeError):
                minimo_pedido = None
            c = Cliente(nombre=request.form.get('empresa','') or request.form.get('nombre',''),
                empresa=request.form.get('empresa',''), nit=request.form.get('nit',''),
                estado_relacion=request.form.get('estado_relacion','prospecto'),
                dir_comercial=request.form.get('dir_comercial',''),
                dir_entrega=request.form.get('dir_entrega',''),
                notas=request.form.get('notas',''), estado='activo',
                banco_nombre=request.form.get('banco_nombre','').strip() or None,
                banco_cuenta=request.form.get('banco_cuenta','').strip() or None,
                banco_tipo=request.form.get('banco_tipo','').strip() or None,
                banco_titular=request.form.get('banco_titular','').strip() or None,
                info_legal=request.form.get('info_legal','').strip() or None,
                sales_manager_id=sales_manager_id,
                anticipo_pct=anticipo_pct,
                minimo_pedido=minimo_pedido)
            db.session.add(c); db.session.flush()
            _save_contactos(c)
            _log('crear','cliente',c.id,f'Cliente creado: {c.empresa or c.nombre}'); db.session.commit()
            flash('Cliente creado.','success'); return redirect(url_for('clientes'))
        sales_managers = User.query.filter(User.rol.in_(['sales_manager','admin']), User.activo==True).order_by(User.nombre).all()
        return render_template('clientes/form.html', obj=None, titulo='Nuevo Cliente', sales_managers=sales_managers)
    

    # ── cliente_ver (/clientes/<int:id>)
    @app.route('/clientes/<int:id>')
    @login_required
    @requiere_modulo('clientes')
    def cliente_ver(id):
        return render_template('clientes/ver.html', obj=Cliente.query.get_or_404(id))
    

    # ── cliente_editar (/clientes/<int:id>/editar)
    @app.route('/clientes/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('clientes')
    def cliente_editar(id):
        obj = Cliente.query.get_or_404(id)
        if request.method == 'POST':
            obj.empresa=request.form.get('empresa',''); obj.nit=request.form.get('nit','')
            obj.nombre=request.form.get('empresa','') or obj.nombre
            obj.estado_relacion=request.form.get('estado_relacion','prospecto')
            obj.dir_comercial=request.form.get('dir_comercial','')
            obj.dir_entrega=request.form.get('dir_entrega','')
            obj.notas=request.form.get('notas',''); obj.actualizado_en=datetime.utcnow()
            obj.banco_nombre=request.form.get('banco_nombre','').strip() or None
            obj.banco_cuenta=request.form.get('banco_cuenta','').strip() or None
            obj.banco_tipo=request.form.get('banco_tipo','').strip() or None
            obj.banco_titular=request.form.get('banco_titular','').strip() or None
            obj.info_legal=request.form.get('info_legal','').strip() or None
            sales_manager_id = request.form.get('sales_manager_id','').strip()
            try:
                obj.sales_manager_id = int(sales_manager_id) if sales_manager_id else None
            except (ValueError, TypeError):
                obj.sales_manager_id = None
            anticipo_pct = request.form.get('anticipo_pct','').strip()
            try:
                obj.anticipo_pct = float(anticipo_pct) if anticipo_pct else None
            except (ValueError, TypeError):
                obj.anticipo_pct = None
            minimo_pedido = request.form.get('minimo_pedido','').strip()
            try:
                obj.minimo_pedido = float(minimo_pedido) if minimo_pedido else None
            except (ValueError, TypeError):
                obj.minimo_pedido = None
            db.session.flush(); _save_contactos(obj)
            _log('editar','cliente',obj.id,f'Cliente editado: {obj.empresa or obj.nombre}'); db.session.commit()
            flash('Cliente actualizado.','success'); return redirect(url_for('cliente_ver', id=obj.id))
        sales_managers = User.query.filter(User.rol.in_(['sales_manager','admin']), User.activo==True).order_by(User.nombre).all()
        return render_template('clientes/form.html', obj=obj, titulo='Editar Cliente', sales_managers=sales_managers)
    

    # ── cliente_eliminar (/clientes/<int:id>/eliminar)
    @app.route('/clientes/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('clientes')
    def cliente_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=Cliente.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Cliente eliminado.','info'); return redirect(url_for('clientes'))
    
