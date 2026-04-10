# routes/notas.py — reconstruido desde v27 con CRUD completo
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

    # ── notas (/notas)
    @app.route('/notas')
    @login_required
    def notas():
        cliente_f = request.args.get('cliente_id','')
        q = Nota.query
        if cliente_f: q = q.filter_by(cliente_id=int(cliente_f))
        return render_template('notas/index.html',
            items=q.order_by(Nota.actualizado_en.desc()).all(),
            clientes_list=Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all(),
            productos_list=Producto.query.filter_by(activo=True).order_by(Producto.nombre).all(),
            cliente_f=cliente_f)
    

    # ── nota_nueva (/notas/nueva)
    @app.route('/notas/nueva', methods=['GET','POST'])
    @login_required
    def nota_nueva():
        cl = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        pl = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fd_rev = request.form.get('fecha_revision')
            n = Nota(titulo=request.form.get('titulo','').strip() or None,
                contenido=request.form['contenido'],
                cliente_id=request.form.get('cliente_id') or None,
                producto_id=request.form.get('producto_id') or None,
                modulo=request.form.get('modulo','') or None,
                fecha_revision=datetime.strptime(fd_rev,'%Y-%m-%d').date() if fd_rev else None,
                creado_por=current_user.id)
            db.session.add(n)
            _log('crear','nota',n.id,f'Nota creada: {n.titulo or "(sin título)"}'); db.session.commit()
            flash('Nota guardada.','success'); return redirect(url_for('notas'))
        return render_template('notas/form.html', obj=None, titulo='Nueva Nota',
            clientes_list=cl, productos_list=pl)
    

    # ── nota_editar (/notas/<int:id>/editar)
    @app.route('/notas/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def nota_editar(id):
        obj = Nota.query.get_or_404(id)
        cl  = Cliente.query.order_by(Cliente.empresa, Cliente.nombre).all()
        pl  = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fd_rev = request.form.get('fecha_revision')
            obj.titulo=request.form.get('titulo','').strip() or None
            obj.contenido=request.form['contenido']
            obj.cliente_id=request.form.get('cliente_id') or None
            obj.producto_id=request.form.get('producto_id') or None
            obj.modulo=request.form.get('modulo','') or None
            obj.fecha_revision=datetime.strptime(fd_rev,'%Y-%m-%d').date() if fd_rev else None
            obj.actualizado_en=datetime.utcnow()
            _log('editar','nota',obj.id,f'Nota editada: {obj.titulo or "(sin título)"}'); db.session.commit()
            flash('Nota actualizada.','success'); return redirect(url_for('notas'))
        return render_template('notas/form.html', obj=obj, titulo='Editar Nota',
            clientes_list=cl, productos_list=pl)
    

    # ── nota_eliminar (/notas/<int:id>/eliminar)
    @app.route('/notas/<int:id>/eliminar', methods=['POST'])
    @login_required
    def nota_eliminar(id):
        if current_user.rol != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=Nota.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Nota eliminada.','info'); return redirect(url_for('notas'))
    
