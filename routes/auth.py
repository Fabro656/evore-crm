# routes/auth.py — reconstruido desde v27 con CRUD completo
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
    def _noop(*a, **kw): pass

    # ── login (/login)
    @app.route('/login', methods=['GET','POST'])
    def login():
        if current_user.is_authenticated: return redirect(url_for('dashboard'))
        if request.method == 'POST':
            user = User.query.filter_by(email=request.form.get('email','').strip()).first()
            if user and user.check_password(request.form.get('password','')) and user.activo:
                login_user(user, remember=bool(request.form.get('remember')))
                from flask import session as flask_session
                flask_session['show_onboarding_once'] = True
                ses = UserSesion(user_id=user.id); db.session.add(ses); db.session.commit()
                flask_session['sesion_id'] = ses.id
                flash(f'¡Bienvenido, {user.nombre}!', 'success')
                return redirect(request.args.get('next') or url_for('dashboard'))
            flash('Email o contraseña incorrectos.', 'danger')
        return render_template('login.html')
    

    # ── logout (/logout)
    @app.route('/logout')
    @login_required
    def logout():
        from flask import session as flask_session
        if 'sesion_id' in flask_session:
            ses = db.session.get(UserSesion, flask_session.get('sesion_id'))
            if ses and not ses.logout_at:
                ses.logout_at = datetime.utcnow()
                delta = ses.logout_at - ses.login_at
                ses.duracion_min = round(delta.total_seconds()/60, 1)
                db.session.commit()
        logout_user(); flash('Sesión cerrada.', 'info'); return redirect(url_for('login'))
    

    # ── onboarding_dismiss (/onboarding/dismiss)
    @app.route('/onboarding/dismiss', methods=['POST'])
    @login_required
    def onboarding_dismiss():
        current_user.onboarding_dismissed = True
        db.session.commit()
        return ('', 204)
    

    # ── onboarding_reset (/onboarding/reset)
    @app.route('/onboarding/reset', methods=['POST'])
    @login_required
    def onboarding_reset():
        current_user.onboarding_dismissed = False
        db.session.commit()
        flash('Tutorial restablecido.', 'info')
        return redirect(request.referrer or url_for('dashboard'))
    

    # ── perfil (/perfil)
    @app.route('/perfil', methods=['GET','POST'])
    @login_required
    def perfil():
        if request.method == 'POST':
            accion = request.form.get('accion')
            if accion == 'datos':
                nuevo_email = request.form.get('email','').strip()
                if nuevo_email != current_user.email and User.query.filter_by(email=nuevo_email).first():
                    flash('Ese email ya está en uso.','danger')
                else:
                    current_user.nombre = request.form.get('nombre','').strip() or current_user.nombre
                    current_user.email  = nuevo_email or current_user.email
                    db.session.commit()
                    flash('Datos actualizados.','success')
            elif accion == 'password':
                pw_actual    = request.form.get('password_actual','')
                pw_nueva     = request.form.get('password_nueva','')
                pw_confirmar = request.form.get('password_confirmar','')
                if not current_user.check_password(pw_actual):
                    flash('La contraseña actual es incorrecta.','danger')
                elif len(pw_nueva) < 8:
                    flash('La nueva contraseña debe tener al menos 8 caracteres.','danger')
                elif pw_nueva != pw_confirmar:
                    flash('Las contraseñas nuevas no coinciden.','danger')
                else:
                    current_user.set_password(pw_nueva)
                    db.session.commit()
                    flash('Contraseña cambiada exitosamente.','success')
        return render_template('perfil.html')
    
