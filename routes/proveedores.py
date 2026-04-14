# routes/proveedores.py — reconstruido desde v27 con CRUD completo
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

    # ── proveedores (/proveedores)
    @app.route('/proveedores')
    @login_required
    @requiere_modulo('clientes')
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
    @requiere_modulo('clientes')
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
                notas=request.form.get('notas',''), activo=True,
                tipo_vehiculo=request.form.get('tipo_vehiculo','') or None,
                capacidad_vehiculo_kg=float(request.form.get('capacidad_vehiculo_kg') or 0),
                capacidad_vehiculo_m3=float(request.form.get('capacidad_vehiculo_m3') or 0))
            db.session.add(p); db.session.flush()

            # ── Counter-party detection / auto-provision
            my_company_id = getattr(g, 'company_id', None)
            nit_prov = (p.nit or '').strip()
            nombre_empresa = (p.empresa or p.nombre or '').strip()
            if nit_prov and my_company_id and nombre_empresa:
                matched = Company.query.filter(
                    Company.nit == nit_prov,
                    Company.id != my_company_id,
                    Company.activo == True
                ).first()
                if matched:
                    existing_rel = CompanyRelationship.query.filter(
                        db.or_(
                            db.and_(CompanyRelationship.company_from_id == my_company_id,
                                    CompanyRelationship.company_to_id == matched.id),
                            db.and_(CompanyRelationship.company_from_id == matched.id,
                                    CompanyRelationship.company_to_id == my_company_id)
                        )).first()
                    if not existing_rel:
                        rel = CompanyRelationship(
                            company_from_id=my_company_id, company_to_id=matched.id,
                            tipo='proveedor', proveedor_id=p.id, activo=True)
                        db.session.add(rel); db.session.flush()
                        chat_room = ChatRoom(company_id=my_company_id, tipo='proveedor',
                            nombre=f'Proveedor: {matched.nombre}',
                            company_relationship_id=rel.id, creado_por=current_user.id)
                        db.session.add(chat_room); db.session.flush()
                        db.session.add(ChatParticipant(room_id=chat_room.id,
                            user_id=current_user.id, rol='admin', agregado_por=current_user.id))
                        flash(f'{matched.nombre} ya esta en Evore — conexion creada.', 'info')
                    else:
                        flash(f'Ya existe una relacion con {matched.nombre}.', 'info')
                else:
                    tipo_doc = request.form.get('tipo_documento', 'NIT')
                    emp, admin_user, rel = _auto_provision_company(
                        nombre_empresa, nit_prov, 'proveedor', my_company_id,
                        proveedor_id=p.id, tipo_documento=tipo_doc)
                    if emp and admin_user:
                        flash(f'Se creo cuenta Evore para {emp.nombre}. '
                              f'Acceso: {admin_user.email} / contrasena: {nit_prov}', 'success')

            db.session.commit()
            flash('Registro creado.','success'); return redirect(url_for('proveedores'))
        return render_template('proveedores/form.html', obj=None, titulo='Nuevo Proveedor / Transportista')
    

    # ── proveedor_editar (/proveedores/<int:id>/editar)
    @app.route('/proveedores/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('clientes')
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
            obj.tipo_vehiculo=request.form.get('tipo_vehiculo','') or None
            obj.capacidad_vehiculo_kg=float(request.form.get('capacidad_vehiculo_kg') or 0)
            obj.capacidad_vehiculo_m3=float(request.form.get('capacidad_vehiculo_m3') or 0)
            db.session.commit()
            flash('Registro actualizado.','success'); return redirect(url_for('proveedores'))
        return render_template('proveedores/form.html', obj=obj, titulo='Editar Proveedor / Transportista')
    

    # ── proveedor_eliminar (/proveedores/<int:id>/eliminar)
    @app.route('/proveedores/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('clientes')
    def proveedor_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj = Proveedor.query.get_or_404(id)
        obj.activo = False
        db.session.commit()
        flash('Registro eliminado.','info'); return redirect(url_for('proveedores'))
    
