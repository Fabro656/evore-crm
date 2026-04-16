# routes/foro.py — Somos Evore: foro de productos y servicios
from flask import render_template, redirect, url_for, flash, request, g, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db, tenant_query
from models import *
import os
from utils import *
from datetime import datetime
from sqlalchemy import func, case
import logging

INDUSTRIAS = [
    'Alimentos y bebidas', 'Textil y confeccion', 'Cosmeticos y cuidado personal',
    'Farmaceutico', 'Construccion y materiales', 'Tecnologia y software',
    'Agricultura y agroindustria', 'Mineria y energia', 'Logistica y transporte',
    'Plasticos y polimeros', 'Metalmecanica', 'Quimicos e insumos industriales',
    'Papel, carton y empaques', 'Madera y muebles', 'Cuero y calzado',
    'Joyeria y accesorios', 'Automotriz y autopartes', 'Electronica y electricidad',
    'Empaques y etiquetas', 'Servicios profesionales', 'Publicidad y marketing',
    'Educacion y capacitacion', 'Salud y bienestar', 'Limpieza e higiene',
    'Seguridad industrial', 'Impresion y artes graficas', 'Reciclaje y medio ambiente',
    'Ferreteria y herramientas', 'Telecomunicaciones', 'Otro',
]

def register(app):

    # ── Foro principal (/foro)
    @app.route('/foro')
    @login_required
    def foro():
        buscar = request.args.get('buscar', '').strip()
        industria_f = request.args.get('industria', '')
        tipo_f = request.args.get('tipo', '')
        modalidad_f = request.args.get('modalidad', '')
        orden = request.args.get('orden', 'reciente')  # reciente, valoracion

        q = ForoPublicacion.query.options(db.joinedload(ForoPublicacion.company)).filter_by(activo=True)
        if buscar:
            q = q.filter(db.or_(
                ForoPublicacion.titulo.ilike(f'%{buscar}%'),
                ForoPublicacion.descripcion.ilike(f'%{buscar}%')))
        if industria_f:
            q = q.filter_by(industria=industria_f)
        if tipo_f:
            q = q.filter_by(tipo=tipo_f)
        if modalidad_f:
            q = q.filter_by(modalidad=modalidad_f)

        if orden == 'valoracion':
            # Subquery: avg rating per company
            avg_rating = db.session.query(
                ForoValoracion.proveedor_company_id,
                func.avg(ForoValoracion.estrellas).label('avg_stars')
            ).filter(ForoValoracion.estado == 'activa'
            ).group_by(ForoValoracion.proveedor_company_id).subquery()

            q = q.outerjoin(avg_rating, ForoPublicacion.company_id == avg_rating.c.proveedor_company_id
            ).order_by(db.desc(db.func.coalesce(avg_rating.c.avg_stars, 0)), ForoPublicacion.creado_en.desc())
        else:
            q = q.order_by(ForoPublicacion.creado_en.desc())

        page = request.args.get('page', 1, type=int)
        pagination = q.paginate(page=page, per_page=20, error_out=False)

        # Company ratings cache
        company_ids = list(set(p.company_id for p in pagination.items))
        ratings = {}
        ventas_count = {}
        if company_ids:
            for cid, avg_s, cnt in db.session.query(
                ForoValoracion.proveedor_company_id,
                func.avg(ForoValoracion.estrellas),
                func.count(ForoValoracion.id)
            ).filter(
                ForoValoracion.proveedor_company_id.in_(company_ids),
                ForoValoracion.estado == 'activa'
            ).group_by(ForoValoracion.proveedor_company_id).all():
                ratings[cid] = {'avg': round(avg_s, 1), 'count': cnt}

            # Count confirmed sales as supplier — single grouped query
            for cid, cnt in db.session.query(
                CompanyRelationship.company_to_id, func.count(CompanyRelationship.id)
            ).filter(
                CompanyRelationship.company_to_id.in_(company_ids),
                CompanyRelationship.tipo.in_(['proveedor', 'ambos']),
                CompanyRelationship.activo == True
            ).group_by(CompanyRelationship.company_to_id).all():
                ventas_count[cid] = cnt

        # ── Marketplace banners ──
        banner_q = ForoBanner.query.filter_by(activo=True)
        if industria_f:
            banner_q = banner_q.filter(db.or_(ForoBanner.industria == industria_f, ForoBanner.industria == None))
        else:
            banner_q = banner_q  # show all active banners
        banners = banner_q.order_by(ForoBanner.orden, ForoBanner.creado_en.desc()).all()

        return render_template('foro/index.html',
            items=pagination.items, pagination=pagination,
            buscar=buscar, industria_f=industria_f, tipo_f=tipo_f, modalidad_f=modalidad_f, orden=orden,
            ratings=ratings, ventas_count=ventas_count,
            industrias=INDUSTRIAS, banners=banners)

    # ── Nueva publicacion (/foro/nueva)
    @app.route('/foro/nueva', methods=['GET', 'POST'])
    @login_required
    def foro_nueva():
        my_company_id = getattr(g, 'company_id', None)
        company = db.session.get(Company, my_company_id) if my_company_id else None
        if not company:
            flash('No se pudo identificar tu empresa.', 'danger')
            return redirect(url_for('foro'))
        # Portal users (cliente/proveedor) cannot publish
        if current_user.rol in ('cliente', 'proveedor'):
            flash('Los usuarios de portal no pueden publicar en el foro.', 'warning')
            return redirect(url_for('foro'))

        if request.method == 'POST':
            titulo = request.form.get('titulo', '').strip()
            descripcion = request.form.get('descripcion', '').strip()
            if not titulo or not descripcion:
                flash('Titulo y descripcion son obligatorios.', 'danger')
                return render_template('foro/form.html', obj=None, company=company, industrias=INDUSTRIAS)

            industria = request.form.get('industria', '').strip()
            # Update company industry if set
            if industria and not company.industria:
                company.industria = industria

            imagen_url = None
            img_file = request.files.get('imagen')
            if img_file and img_file.filename:
                ext = img_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp') and img_file.content_length < 2 * 1024 * 1024:
                    img_dir = os.path.join(current_app.root_path, 'static', 'foro')
                    os.makedirs(img_dir, exist_ok=True)
                    fname = secure_filename(f'pub_{my_company_id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.{ext}')
                    img_file.save(os.path.join(img_dir, fname))
                    imagen_url = f'static/foro/{fname}'

            pub = ForoPublicacion(
                company_id=my_company_id, user_id=current_user.id,
                tipo=request.form.get('tipo', 'producto'),
                modalidad=request.form.get('modalidad', 'vendo'),
                titulo=titulo, descripcion=descripcion,
                industria=industria or company.industria,
                precio_referencia=float(request.form.get('precio_referencia') or 0) or None,
                unidad=request.form.get('unidad', '').strip() or None,
                imagen_url=imagen_url,
                activo=True)
            db.session.add(pub)
            db.session.commit()
            flash('Publicacion creada en Somos Evore.', 'success')
            return redirect(url_for('foro'))

        return render_template('foro/form.html', obj=None, company=company, industrias=INDUSTRIAS)

    # ── Editar publicacion (/foro/<id>/editar)
    @app.route('/foro/<int:id>/editar', methods=['GET', 'POST'])
    @login_required
    def foro_editar(id):
        pub = ForoPublicacion.query.get_or_404(id)
        my_company_id = getattr(g, 'company_id', None)
        if pub.company_id != my_company_id:
            flash('No puedes editar publicaciones de otra empresa.', 'danger')
            return redirect(url_for('foro'))

        if request.method == 'POST':
            pub.titulo = request.form.get('titulo', pub.titulo).strip()
            pub.descripcion = request.form.get('descripcion', pub.descripcion).strip()
            pub.tipo = request.form.get('tipo', pub.tipo)
            pub.modalidad = request.form.get('modalidad', pub.modalidad)
            pub.industria = request.form.get('industria', pub.industria)
            pub.precio_referencia = float(request.form.get('precio_referencia') or 0) or None
            pub.unidad = request.form.get('unidad', '').strip() or None
            pub.actualizado_en = datetime.utcnow()
            img_file = request.files.get('imagen')
            if img_file and img_file.filename:
                ext = img_file.filename.rsplit('.', 1)[-1].lower()
                if ext in ('png', 'jpg', 'jpeg', 'webp'):
                    img_dir = os.path.join(current_app.root_path, 'static', 'foro')
                    os.makedirs(img_dir, exist_ok=True)
                    fname = secure_filename(f'pub_{pub.company_id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.{ext}')
                    img_file.save(os.path.join(img_dir, fname))
                    pub.imagen_url = f'static/foro/{fname}'
            db.session.commit()
            flash('Publicacion actualizada.', 'success')
            return redirect(url_for('foro_ver', id=pub.id))

        company = db.session.get(Company, my_company_id)
        return render_template('foro/form.html', obj=pub, company=company, industrias=INDUSTRIAS)

    # ── Ver publicacion (/foro/<id>)
    @app.route('/foro/<int:id>')
    @login_required
    def foro_ver(id):
        pub = ForoPublicacion.query.get_or_404(id)
        company = pub.company
        my_company_id = getattr(g, 'company_id', None)
        es_mio = (pub.company_id == my_company_id)

        # Ratings for this company (joinedload to avoid N+1 on v.cliente.nombre)
        valoraciones = ForoValoracion.query.options(
            db.joinedload(ForoValoracion.cliente)
        ).filter_by(
            proveedor_company_id=pub.company_id, estado='activa'
        ).order_by(ForoValoracion.creado_en.desc()).all()
        avg_rating = 0
        if valoraciones:
            avg_rating = round(sum(v.estrellas for v in valoraciones) / len(valoraciones), 1)

        # Check if already related
        ya_relacionado = False
        if my_company_id and my_company_id != pub.company_id:
            ya_relacionado = CompanyRelationship.query.filter(
                db.or_(
                    db.and_(CompanyRelationship.company_from_id == my_company_id,
                            CompanyRelationship.company_to_id == pub.company_id),
                    db.and_(CompanyRelationship.company_from_id == pub.company_id,
                            CompanyRelationship.company_to_id == my_company_id)
                )).first() is not None

        # Check if I already rated this company
        ya_valorado = False
        if my_company_id:
            ya_valorado = ForoValoracion.query.filter_by(
                proveedor_company_id=pub.company_id,
                cliente_company_id=my_company_id,
                estado='activa'
            ).first() is not None

        # Ventas confirmadas count
        ventas_conf = ForoValoracion.query.filter_by(
            proveedor_company_id=pub.company_id, estado='activa').count()

        return render_template('foro/ver.html', pub=pub, company=company,
            es_mio=es_mio, valoraciones=valoraciones, avg_rating=avg_rating,
            ya_relacionado=ya_relacionado, ya_valorado=ya_valorado,
            ventas_conf=ventas_conf)

    # ── Conectar (crea relacion mutua bimodal) (/foro/<id>/conectar-foro)
    @app.route('/foro/<int:id>/conectar-foro', methods=['POST'])
    @login_required
    def foro_conectar(id):
        pub = ForoPublicacion.query.get_or_404(id)
        my_company_id = getattr(g, 'company_id', None)
        if not my_company_id or my_company_id == pub.company_id:
            flash('No puedes conectar con tu propia empresa.', 'warning')
            return redirect(url_for('foro_ver', id=id))

        # Check existing relationship
        existing = CompanyRelationship.query.filter(
            db.or_(
                db.and_(CompanyRelationship.company_from_id == my_company_id,
                        CompanyRelationship.company_to_id == pub.company_id),
                db.and_(CompanyRelationship.company_from_id == pub.company_id,
                        CompanyRelationship.company_to_id == my_company_id)
            )).first()
        if existing:
            flash(f'Ya tienes una relación con {pub.company.nombre}.', 'info')
            return redirect(url_for('foro_ver', id=id))

        my_company = db.session.get(Company, my_company_id)
        modalidad = getattr(pub, 'modalidad', 'vendo') or 'vendo'

        # Bimodal logic:
        # "vendo" → publisher sells, I buy → they're my supplier, I'm their client
        # "compro" → publisher buys, I sell → I'm their supplier, they're my client
        if modalidad == 'vendo':
            rel_tipo = 'proveedor'
            chat_label = f'Proveedor: {pub.company.nombre}'
            # I register them as supplier, they register me as client
            if not (pub.company.nit and tenant_query(Proveedor).filter_by(company_id=my_company_id, nit=pub.company.nit).first()):
                db.session.add(Proveedor(nombre=pub.company.nombre, empresa=pub.company.nombre,
                                         nit=pub.company.nit or '', activo=True, company_id=my_company_id))
            if not (my_company.nit and tenant_query(Cliente).filter_by(company_id=pub.company_id, nit=my_company.nit).first()):
                db.session.add(Cliente(nombre=my_company.nombre, empresa=my_company.nombre,
                                       nit=my_company.nit or '', estado_relacion='cliente_activo',
                                       estado='activo', company_id=pub.company_id))
        else:  # compro
            rel_tipo = 'cliente'
            chat_label = f'Cliente: {pub.company.nombre}'
            # I register them as client, they register me as supplier
            if not (pub.company.nit and tenant_query(Cliente).filter_by(company_id=my_company_id, nit=pub.company.nit).first()):
                db.session.add(Cliente(nombre=pub.company.nombre, empresa=pub.company.nombre,
                                       nit=pub.company.nit or '', estado_relacion='cliente_activo',
                                       estado='activo', company_id=my_company_id))
            if not (my_company.nit and tenant_query(Proveedor).filter_by(company_id=pub.company_id, nit=my_company.nit).first()):
                db.session.add(Proveedor(nombre=my_company.nombre, empresa=my_company.nombre,
                                         nit=my_company.nit or '', activo=True, company_id=pub.company_id))

        rel = CompanyRelationship(
            company_from_id=my_company_id, company_to_id=pub.company_id,
            tipo=rel_tipo, activo=True)
        db.session.add(rel)
        db.session.flush()

        # Create chat room
        chat_room = ChatRoom(
            company_id=my_company_id, tipo=rel_tipo,
            nombre=chat_label,
            company_relationship_id=rel.id,
            creado_por=current_user.id)
        db.session.add(chat_room)
        db.session.flush()
        db.session.add(ChatParticipant(
            room_id=chat_room.id, user_id=current_user.id,
            rol='admin', agregado_por=current_user.id))
        db.session.add(ChatParticipant(
            room_id=chat_room.id, user_id=pub.user_id,
            rol='admin', agregado_por=current_user.id))

        db.session.commit()
        flash(f'Conexion creada con {pub.company.nombre}. Ya pueden comunicarse por chat.', 'success')
        return redirect(url_for('foro_ver', id=id))

    # ── Contactar por chat (/foro/<id>/contactar)
    @app.route('/foro/<int:id>/contactar')
    @login_required
    def foro_contactar(id):
        pub = ForoPublicacion.query.get_or_404(id)
        my_company_id = getattr(g, 'company_id', None)
        # Find existing chat room
        rel = CompanyRelationship.query.filter(
            db.or_(
                db.and_(CompanyRelationship.company_from_id == my_company_id,
                        CompanyRelationship.company_to_id == pub.company_id),
                db.and_(CompanyRelationship.company_from_id == pub.company_id,
                        CompanyRelationship.company_to_id == my_company_id)
            )).first()
        if rel:
            room = ChatRoom.query.filter_by(company_relationship_id=rel.id, activo=True).first()
            if room:
                return redirect(url_for('chat_room', room_id=room.id))
        flash('Primero debes conectarte con esta empresa usando "Hacerme cliente".', 'info')
        return redirect(url_for('foro_ver', id=id))

    # ── Valorar proveedor (/foro/valorar/<int:company_id>)
    @app.route('/foro/valorar/<int:company_id>', methods=['POST'])
    @login_required
    def foro_valorar(company_id):
        my_company_id = getattr(g, 'company_id', None)
        if not my_company_id or my_company_id == company_id:
            flash('No puedes valorarte a ti mismo.', 'warning')
            return redirect(url_for('foro'))

        # Must have relationship
        rel = CompanyRelationship.query.filter(
            db.or_(
                db.and_(CompanyRelationship.company_from_id == my_company_id,
                        CompanyRelationship.company_to_id == company_id),
                db.and_(CompanyRelationship.company_from_id == company_id,
                        CompanyRelationship.company_to_id == my_company_id)
            )).first()
        if not rel:
            flash('Debes tener una relacion comercial para valorar.', 'danger')
            return redirect(url_for('foro'))

        estrellas = int(request.form.get('estrellas', 0))
        if estrellas < 1 or estrellas > 5:
            flash('La valoración debe ser entre 1 y 5 estrellas.', 'danger')
            return redirect(request.referrer or url_for('foro'))

        comentario = request.form.get('comentario', '').strip()
        pub_id = request.form.get('publicacion_id') or None

        val = ForoValoracion(
            proveedor_company_id=company_id,
            cliente_company_id=my_company_id,
            cliente_user_id=current_user.id,
            publicacion_id=int(pub_id) if pub_id else None,
            estrellas=estrellas,
            comentario=comentario,
            estado='activa')
        db.session.add(val)
        db.session.commit()
        flash('Valoración registrada. Gracias por tu opinión.', 'success')
        return redirect(request.form.get('redirect_url') or url_for('foro'))

    # ── Apelar valoracion (/foro/apelar/<int:valoracion_id>)
    @app.route('/foro/apelar/<int:valoracion_id>', methods=['POST'])
    @login_required
    def foro_apelar(valoracion_id):
        val = ForoValoracion.query.get_or_404(valoracion_id)
        my_company_id = getattr(g, 'company_id', None)
        if val.proveedor_company_id != my_company_id:
            flash('Solo el proveedor puede apelar una valoración.', 'danger')
            return redirect(url_for('foro'))

        if val.apelacion:
            flash('Esta valoración ya tiene una apelación en curso.', 'warning')
            return redirect(request.referrer or url_for('foro'))

        motivo = request.form.get('motivo', '').strip()
        if not motivo:
            flash('Debes indicar el motivo de la apelación.', 'danger')
            return redirect(request.referrer or url_for('foro'))

        val.estado = 'apelada'
        db.session.add(ForoApelacion(
            valoracion_id=val.id, solicitado_por=current_user.id, motivo=motivo))
        db.session.commit()
        flash('Apelación enviada. El administrador de Evore revisará el caso.', 'info')
        return redirect(request.referrer or url_for('foro'))

    # ── Admin: resolver apelacion (/foro/apelacion/<id>/resolver)
    @app.route('/foro/apelacion/<int:id>/resolver', methods=['POST'])
    @login_required
    def foro_resolver_apelacion(id):
        apelacion = ForoApelacion.query.get_or_404(id)
        # Only Evore admin
        evore = Company.query.filter_by(es_principal=True).first()
        my_company_id = getattr(g, 'company_id', None)
        if not evore or my_company_id != evore.id or current_user.rol != 'admin':
            flash('Solo el administrador de Evore puede resolver apelaciones.', 'danger')
            return redirect(url_for('foro'))

        decision = request.form.get('decision', '')  # favor_cliente, favor_proveedor
        notas = request.form.get('notas', '').strip()

        apelacion.estado = decision
        apelacion.notas_admin = notas
        apelacion.resuelto_por = current_user.id
        apelacion.resuelto_en = datetime.utcnow()

        val = apelacion.valoracion
        if decision == 'favor_proveedor':
            # Remove the rating
            val.estado = 'eliminada'
            flash('Apelación resuelta a favor del proveedor. Valoración eliminada.', 'success')
        else:
            # Keep the rating
            val.estado = 'activa'
            flash('Apelación resuelta a favor del cliente. Valoración se mantiene.', 'info')

        db.session.commit()
        return redirect(url_for('foro_apelaciones'))

    # ── Admin: ver apelaciones pendientes (/foro/apelaciones)
    @app.route('/foro/apelaciones')
    @login_required
    def foro_apelaciones():
        evore = Company.query.filter_by(es_principal=True).first()
        my_company_id = getattr(g, 'company_id', None)
        if not evore or my_company_id != evore.id or current_user.rol != 'admin':
            flash('Solo el administrador de Evore puede ver apelaciones.', 'danger')
            return redirect(url_for('foro'))
        apelaciones = ForoApelacion.query.order_by(
            case((ForoApelacion.estado == 'pendiente', 0), else_=1),
            ForoApelacion.creado_en.desc()).all()
        return render_template('foro/apelaciones.html', apelaciones=apelaciones)

    # ── Perfil de empresa en foro (/foro/empresa/<int:id>)
    @app.route('/foro/empresa/<int:id>')
    @login_required
    def foro_empresa(id):
        company = Company.query.get_or_404(id)
        publicaciones = ForoPublicacion.query.filter_by(
            company_id=id, activo=True).order_by(ForoPublicacion.creado_en.desc()).all()
        valoraciones = ForoValoracion.query.filter_by(
            proveedor_company_id=id, estado='activa'
        ).order_by(ForoValoracion.creado_en.desc()).all()
        avg_rating = 0
        if valoraciones:
            avg_rating = round(sum(v.estrellas for v in valoraciones) / len(valoraciones), 1)
        ventas_conf = len(valoraciones)

        my_company_id = getattr(g, 'company_id', None)
        ya_relacionado = False
        if my_company_id and my_company_id != id:
            ya_relacionado = CompanyRelationship.query.filter(
                db.or_(
                    db.and_(CompanyRelationship.company_from_id == my_company_id,
                            CompanyRelationship.company_to_id == id),
                    db.and_(CompanyRelationship.company_from_id == id,
                            CompanyRelationship.company_to_id == my_company_id)
                )).first() is not None

        return render_template('foro/empresa.html', company=company,
            publicaciones=publicaciones, valoraciones=valoraciones,
            avg_rating=avg_rating, ventas_conf=ventas_conf,
            ya_relacionado=ya_relacionado, es_mio=(my_company_id == id))

    # ── Configurar industria de mi empresa (/foro/mi-industria)
    @app.route('/foro/mi-industria', methods=['POST'])
    @login_required
    def foro_mi_industria():
        my_company_id = getattr(g, 'company_id', None)
        company = db.session.get(Company, my_company_id) if my_company_id else None
        if company:
            company.industria = request.form.get('industria', '').strip()
            db.session.commit()
            flash('Industria actualizada.', 'success')
        return redirect(request.referrer or url_for('foro'))
