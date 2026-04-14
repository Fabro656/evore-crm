# routes/inventario.py — reconstruido desde v27 con CRUD completo
from flask import render_template, redirect, url_for, flash, request, \
                  jsonify, send_file, make_response, current_app
from flask import session as flask_session
from flask_login import login_required, current_user, login_user, logout_user
from extensions import db
from models import *
from utils import *
from datetime import datetime, timedelta, date as date_type
import json, os, re, io, logging

def register(app):

    # ── inventario (/inventario)
    @app.route('/inventario')
    @login_required
    def inventario():
        busqueda=request.args.get('buscar',''); categoria_f=request.args.get('categoria','')
        q=Producto.query.filter_by(activo=True)
        if busqueda:
            q=q.filter(db.or_(Producto.nombre.ilike(f'%{busqueda}%'),
                               Producto.sku.ilike(f'%{busqueda}%'),
                               Producto.nso.ilike(f'%{busqueda}%')))
        if categoria_f: q=q.filter_by(categoria=categoria_f)
        cats=[c[0] for c in db.session.query(Producto.categoria).filter(
            Producto.activo==True,Producto.categoria!=None,Producto.categoria!='').distinct().all()]
        return render_template('inventario/index.html', items=q.order_by(Producto.nombre).all(),
                               busqueda=busqueda, categoria_f=categoria_f, categorias=cats,
                               now=datetime.utcnow())
    

    # ── producto_nuevo (/inventario/nuevo)
    @app.route('/inventario/nuevo', methods=['GET','POST'])
    @login_required
    def producto_nuevo():
        if request.method == 'POST':
            fd_cad = request.form.get('fecha_caducidad')
            db.session.add(Producto(
                nombre=request.form['nombre'], descripcion=request.form.get('descripcion',''),
                sku=request.form.get('sku') or None, nso=request.form.get('nso') or None,
                precio=float(request.form.get('precio',0) or 0),
                costo=float(request.form.get('costo',0) or 0),
                stock=int(request.form.get('stock',0) or 0),
                stock_minimo=int(request.form.get('stock_minimo',5) or 5),
                categoria=request.form.get('categoria',''),
                fecha_caducidad=datetime.strptime(fd_cad,'%Y-%m-%d').date() if fd_cad else None))
            db.session.commit()
            flash('Producto creado.','success'); return redirect(url_for('inventario'))
        return render_template('inventario/form.html', obj=None, titulo='Nuevo Producto')
    

    # ── producto_editar (/inventario/<int:id>/editar)
    @app.route('/inventario/<int:id>/editar', methods=['GET','POST'])
    @login_required
    def producto_editar(id):
        obj=Producto.query.get_or_404(id)
        if request.method == 'POST':
            fd_cad = request.form.get('fecha_caducidad')
            obj.nombre=request.form['nombre']; obj.descripcion=request.form.get('descripcion','')
            obj.sku=request.form.get('sku') or None; obj.nso=request.form.get('nso') or None
            obj.precio=float(request.form.get('precio',0) or 0)
            obj.costo=float(request.form.get('costo',0) or 0)
            obj.stock=int(request.form.get('stock',0) or 0)
            obj.stock_minimo=int(request.form.get('stock_minimo',5) or 5)
            obj.categoria=request.form.get('categoria','')
            obj.fecha_caducidad=datetime.strptime(fd_cad,'%Y-%m-%d').date() if fd_cad else None
            db.session.commit()
            flash('Producto actualizado.','success'); return redirect(url_for('inventario'))
        return render_template('inventario/form.html', obj=obj, titulo='Editar Producto')
    

    # ── producto_eliminar (/inventario/<int:id>/eliminar)
    @app.route('/inventario/<int:id>/eliminar', methods=['POST'])
    @login_required
    def producto_eliminar(id):
        if _get_rol_activo(current_user) != 'admin':
            flash('Solo administradores pueden eliminar registros.', 'danger')
            return redirect(request.referrer or url_for('dashboard'))
        obj=Producto.query.get_or_404(id); obj.activo=False; db.session.commit()
        flash('Producto eliminado.','info'); return redirect(url_for('inventario'))
    

    # ── lotes (/inventario/lotes)
    @app.route('/inventario/lotes')
    @login_required
    @requiere_modulo('inventario')
    def lotes():
        buscar = request.args.get('buscar', '').strip()
        q = LoteProducto.query
        if buscar:
            q = q.join(LoteProducto.producto).filter(
                db.or_(Producto.nombre.ilike(f'%{buscar}%'),
                        LoteProducto.numero_lote.ilike(f'%{buscar}%')))
        items = q.order_by(LoteProducto.creado_en.desc()).all()
        return render_template('inventario/lotes.html', lotes=items, buscar=buscar)
    

    # ── lote_nuevo (/inventario/lotes/nuevo)
    @app.route('/inventario/lotes/nuevo', methods=['GET','POST'])
    @login_required
    @requiere_modulo('inventario')
    def lote_nuevo():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fp = request.form.get('fecha_produccion')
            fv = request.form.get('fecha_vencimiento')
            l = LoteProducto(
                producto_id=int(request.form['producto_id']),
                numero_lote=request.form['numero_lote'],
                nso=request.form.get('nso','') or None,
                fecha_produccion=datetime.strptime(fp,'%Y-%m-%d').date() if fp else None,
                fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
                unidades_producidas=int(request.form.get('unidades_producidas',0)),
                unidades_restantes=int(request.form.get('unidades_restantes',0)),
                notas=request.form.get('notas','') or None,
                creado_por=current_user.id
            )
            db.session.add(l); db.session.commit()
            flash('Lote creado.','success'); return redirect(url_for('lotes'))
        return render_template('inventario/lote_form.html', obj=None, productos=productos, titulo='Nuevo Lote')
    

    # ── lote_editar (/inventario/lotes/<int:id>/editar)
    @app.route('/inventario/lotes/<int:id>/editar', methods=['GET','POST'])
    @login_required
    @requiere_modulo('inventario')
    def lote_editar(id):
        obj = LoteProducto.query.get_or_404(id)
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            fp = request.form.get('fecha_produccion')
            fv = request.form.get('fecha_vencimiento')
            obj.producto_id=int(request.form['producto_id'])
            obj.numero_lote=request.form['numero_lote']
            obj.nso=request.form.get('nso','') or None
            obj.fecha_produccion=datetime.strptime(fp,'%Y-%m-%d').date() if fp else None
            obj.fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None
            obj.unidades_producidas=int(request.form.get('unidades_producidas',0))
            obj.unidades_restantes=int(request.form.get('unidades_restantes',0))
            obj.notas=request.form.get('notas','') or None
            db.session.commit()
            flash('Lote actualizado.','success'); return redirect(url_for('lotes'))
        return render_template('inventario/lote_form.html', obj=obj, productos=productos, titulo='Editar Lote')
    

    # ── lote_eliminar (/inventario/lotes/<int:id>/eliminar)
    @app.route('/inventario/lotes/<int:id>/eliminar', methods=['POST'])
    @login_required
    @requiere_modulo('inventario')
    def lote_eliminar(id):
        obj = LoteProducto.query.get_or_404(id); db.session.delete(obj); db.session.commit()
        flash('Lote eliminado.','info'); return redirect(url_for('lotes'))
    

    # ── inventario_ingresos (/inventario/ingresos)
    @app.route('/inventario/ingresos', methods=['GET','POST'])
    @login_required
    @requiere_modulo('inventario')
    def inventario_ingresos():
        productos = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
        if request.method == 'POST':
            pid = request.form.get('producto_id')
            numero_lote = request.form.get('numero_lote','').strip()
            nso = request.form.get('nso','').strip() or None
            fp  = request.form.get('fecha_produccion')
            fv  = request.form.get('fecha_vencimiento')
            cantidades = request.form.getlist('cantidad[]')
            costos     = request.form.getlist('costo_unit[]')
    
            if not pid or not numero_lote:
                flash('Selecciona un producto e indica el número de lote.','danger')
                return render_template('inventario/ingresos.html', productos=productos)
    
            prod = Producto.query.get_or_404(int(pid))
            total_unidades = 0
            for cant_s, costo_s in zip(cantidades, costos):
                try:
                    cant = float(cant_s)
                    if cant > 0:
                        total_unidades += cant
                        if costo_s:
                            prod.costo = float(costo_s)   # actualiza último costo
                except Exception as _e:
                    logging.warning(f'inventario ingreso parse cantidad/costo: {_e}')
    
            if total_unidades <= 0:
                flash('Ingresa al menos una cantidad válida.','danger')
                return render_template('inventario/ingresos.html', productos=productos)
    
            prod.stock += int(total_unidades)
            lote = LoteProducto(
                producto_id=prod.id,
                numero_lote=numero_lote,
                nso=nso,
                fecha_produccion=datetime.strptime(fp,'%Y-%m-%d').date() if fp else None,
                fecha_vencimiento=datetime.strptime(fv,'%Y-%m-%d').date() if fv else None,
                unidades_producidas=total_unidades,
                unidades_restantes=total_unidades,
                notas=f'Multi-ingreso: {total_unidades} unidades',
                creado_por=current_user.id
            )
            db.session.add(lote)
            db.session.commit()
            flash(f'{total_unidades:.0f} unidades de "{prod.nombre}" ingresadas al lote {numero_lote}.','success')
            return redirect(url_for('inventario'))
        return render_template('inventario/ingresos.html', productos=productos)
    
