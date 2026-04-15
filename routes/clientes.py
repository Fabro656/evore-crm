# routes/clientes.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app, g
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
from sqlalchemy import func
import json, os, re, io, logging

def register(app):

    # ── Helpers ─────────────────────────────────────────────────────
    def _save_contactos(cliente_obj):
        ContactoCliente.query.filter_by(cliente_id=cliente_obj.id).delete()
        nombres = request.form.getlist('c_nombre[]')
        cargos  = request.form.getlist('c_cargo[]')
        emails  = request.form.getlist('c_email[]')
        tels    = request.form.getlist('c_telefono[]')
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
        tier_f = request.args.get('tier','')
        if tier_f: q = q.filter_by(tier=tier_f)

        page = request.args.get('page', 1, type=int)
        per_page = 25
        pagination = q.order_by(Cliente.empresa, Cliente.nombre).paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items

        # Auto-update client tiers based on total revenue
        try:
            tier_data = db.session.query(
                Venta.cliente_id,
                func.sum(Venta.total).label('total_rev')
            ).filter(Venta.estado.in_(['completado','pagado','entregado'])
            ).group_by(Venta.cliente_id).all()

            tier_map = {r.cliente_id: r.total_rev for r in tier_data}
            changed = False
            for c in items:
                rev = tier_map.get(c.id, 0)
                new_tier = 'gold' if rev >= 50_000_000 else 'silver' if rev >= 20_000_000 else 'bronze' if rev >= 5_000_000 else 'standard'
                if c.tier != new_tier:
                    c.tier = new_tier
                    changed = True
            if changed:
                db.session.commit()
        except Exception:
            pass

        return render_template('clientes/index.html', items=items,
                               busqueda=busqueda, estado_rel_f=estado_rel_f,
                               page=page, total_pages=pagination.pages,
                               total_items=pagination.total)
    

    # ── clientes_export_csv (/clientes/export-csv)
    @app.route('/clientes/export-csv')
    @login_required
    @requiere_modulo('clientes')
    def clientes_export_csv():
        clientes_list = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        rows = []
        for c in clientes_list:
            rows.append([
                c.nombre or '',
                c.empresa or '',
                c.nit or '',
                c.email or '',
                c.telefono or '',
                c.estado_relacion or '',
                c.ciudad or '',
            ])
        return generar_csv_response(
            rows,
            ['Nombre', 'Empresa', 'NIT', 'Email', 'Telefono', 'Estado', 'Ciudad'],
            filename='clientes.csv'
        )

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
            c = Cliente(company_id=getattr(g, 'company_id', None),
                nombre=request.form.get('empresa','') or request.form.get('nombre',''),
                empresa=request.form.get('empresa',''),
                tipo_documento=request.form.get('tipo_documento','NIT'),
                nit=request.form.get('nit',''),
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
            _log('crear','cliente',c.id,f'Cliente creado: {c.empresa or c.nombre}')

            # ── Counter-party detection / auto-provision
            my_company_id = getattr(g, 'company_id', None)
            nit_cliente = (c.nit or '').strip()
            nombre_empresa = (c.empresa or c.nombre or '').strip()
            if nit_cliente and my_company_id and nombre_empresa:
                # Check if already exists by NIT
                matched = Company.query.filter(
                    Company.nit == nit_cliente,
                    Company.id != my_company_id,
                    Company.activo == True
                ).first()
                if matched:
                    # Link if no relationship yet
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
                            tipo='cliente', cliente_id=c.id, activo=True)
                        db.session.add(rel); db.session.flush()
                        chat_room = ChatRoom(company_id=my_company_id, tipo='cliente',
                            nombre=f'Cliente: {matched.nombre}',
                            company_relationship_id=rel.id, creado_por=current_user.id)
                        db.session.add(chat_room); db.session.flush()
                        db.session.add(ChatParticipant(room_id=chat_room.id,
                            user_id=current_user.id, rol='admin', agregado_por=current_user.id))
                        flash(f'{matched.nombre} ya está en Evore — conexión creada.', 'info')
                    else:
                        flash(f'Ya existe una relación con {matched.nombre}.', 'info')
                else:
                    # Auto-provision free company + admin user
                    tipo_doc = request.form.get('tipo_documento', 'NIT')
                    emp, admin_user, rel = _auto_provision_company(
                        nombre_empresa, nit_cliente, 'cliente', my_company_id,
                        cliente_id=c.id, tipo_documento=tipo_doc)
                    if emp and admin_user:
                        flash(f'Se creo cuenta Evore para {emp.nombre}. '
                              f'Acceso: {admin_user.email} / contrasena: {nit_cliente}', 'success')

            db.session.commit()
            flash('Cliente creado.','success'); return redirect(url_for('clientes'))
        sales_managers = User.query.filter(User.rol.in_(['sales_manager','admin']), User.activo==True).order_by(User.nombre).all()
        return render_template('clientes/form.html', obj=None, titulo='Nuevo Cliente', sales_managers=sales_managers)
    

    # ── cliente_ver (/clientes/<int:id>)
    @app.route('/clientes/<int:id>')
    @login_required
    @requiere_modulo('clientes')
    def cliente_ver(id):
        obj = Cliente.query.get_or_404(id)
        # Check if this client is linked to an Evore company
        my_company_id = getattr(g, 'company_id', None)
        linked_company = None
        if my_company_id:
            rel = CompanyRelationship.query.filter(
                CompanyRelationship.company_from_id == my_company_id,
                CompanyRelationship.cliente_id == obj.id,
                CompanyRelationship.activo == True
            ).first()
            if rel:
                linked_company = Company.query.get(rel.company_to_id)
        return render_template('clientes/ver.html', obj=obj, linked_company=linked_company)

    # ── cliente_editar (/clientes/<int:id>/editar)
    @app.route('/clientes/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('clientes')
    def cliente_editar(id):
        obj = Cliente.query.get_or_404(id)
        if request.method == 'POST':
            obj.empresa=request.form.get('empresa','')
            obj.tipo_documento=request.form.get('tipo_documento','NIT'); obj.nit=request.form.get('nit','')
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
        obj = Cliente.query.get_or_404(id)
        nombre = obj.empresa or obj.nombre
        try:
            # Desvincular entidades que referencian este cliente (nullificar FK)
            Venta.query.filter_by(cliente_id=id).update({'cliente_id': None})
            Cotizacion.query.filter_by(cliente_id=id).update({'cliente_id': None})
            Nota.query.filter_by(cliente_id=id).update({'cliente_id': None})
            DocumentoLegal.query.filter_by(cliente_id=id).update({'cliente_id': None})
            User.query.filter_by(cliente_id=id).update({'cliente_id': None})
            PreCotizacion.query.filter_by(cliente_id=id).delete()
            Comision.query.filter(Comision.venta_id.in_(
                db.session.query(Venta.id).filter_by(cliente_id=id)
            )).delete(synchronize_session=False)
            # Contactos se borran por cascade (delete-orphan)
            db.session.delete(obj)
            _log('eliminar', 'cliente', id, f'Cliente eliminado: {nombre}')
            db.session.commit()
            flash(f'Cliente "{nombre}" eliminado.', 'info')
        except Exception as e:
            db.session.rollback()
            logging.error(f'Error eliminando cliente {id}: {e}')
            flash(f'Error al eliminar: {e}', 'danger')
        return redirect(url_for('clientes'))
    
