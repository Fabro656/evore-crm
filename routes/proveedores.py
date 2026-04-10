# routes/proveedores.py — reconstruido desde v27 con CRUD completo
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

    # ── proveedores (/proveedores)
    @app.route('/proveedores')
    @login_required
    def proveedores():
        busqueda = request.args.get('buscar','')
        tipo_f   = request.args.get('tipo_f','')
        q = Proveedor.query.filter_by(activo=True)
        if busqueda:
            q = q.filter(db.or_(Proveedor.nombre.ilike(f'%{busqueda}%'),
                                 Proveedor.empresa.ilike(f'%{busqueda}%'),
                                 Proveedor.nit.ilike(f'%{busqueda}%')))
        if tipo_f:
            q = q.filter_by(tipo=tipo_f)
        return render_template('proveedores/index.html', items=q.order_by(Proveedor.empresa, Proveedor.nombre).all(),
                               busqueda=busqueda)
    

    # ── proveedor_nuevo (/proveedores/nuevo)
    @app.route('/proveedores/nuevo', methods=['GET','POST'])
    @login_required
    def proveedor_nuevo():
        if request.method == 'POST':
            p = Proveedor(
                nombre=request.form.get('nombre','') or request.form.get('empresa',''),
                empresa=request.form.get('empresa',''),
                nit=request.form.get('nit',''),
                email=request.form.get('email',''),
                telefono=request.form.get('telefono',''),
                direccion=request.form.get('direccion',''),
                categoria=request.form.get('categoria',''),
                tipo=request.form.get('tipo','proveedor'),
                notas=request.form.get('notas',''), activo=True)
            db.session.add(p); db.session.commit()
            flash('Registro creado.','success'); return redirect(url_for('proveedores'))
        return render_template('proveedores/form.html', obj=None, titulo='Nuevo Proveedor / Transportista')
    

    # ── proveedor_editar (/proveedores/<int:id>/editar)
    @app.route('/proveedores/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def proveedor_editar(id):
        obj = Proveedor.query.get_or_404(id)
        if request.method == 'POST':
            obj.nombre=request.form.get('nombre','') or request.form.get('empresa','') or obj.nombre
            obj.empresa=request.form.get('empresa','')
            obj.nit=request.form.get('nit','')
            obj.email=request.form.get('email','')
            obj.telefono=request.form.get('telefono','')
            obj.direccion=request.form.get('direccion','')
            obj.categoria=request.form.get('categoria','')
            obj.tipo=request.form.get('tipo','proveedor')
            obj.notas=request.form.get('notas','')
            db.session.commit()
            flash('Registro actualizado.','success'); return redirect(url_for('proveedores'))
        return render_template('proveedores/form.html', obj=obj, titulo='Editar Proveedor / Transportista')
    

    # ── proveedor_eliminar (/proveedores/<int:id>/eliminar)
    @app.route('/proveedores/<int:id>/eliminar', methods=['POST'])
    @login_required
    def proveedor_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj = Proveedor.query.get_or_404(id)
        obj.activo = False
        db.session.commit()
        flash('Registro eliminado.','info'); return redirect(url_for('proveedores'))
    
