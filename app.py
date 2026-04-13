# app.py — Flask app factory + Gunicorn entry point
import os, logging
from flask import Flask, jsonify, render_template
from extensions import db, login_manager, mail, MAIL_AVAILABLE

logging.basicConfig(level=logging.INFO)


def create_app():
    app = Flask(__name__, template_folder='templates')

    # ── Company config ────────────────────────────────────────────────
    from company_config import COMPANY, COMPANY_ID
    app.config['COMPANY_NAME'] = COMPANY['name']
    app.config['COMPANY_ID'] = COMPANY_ID

    # ── Config ────────────────────────────────────────────────────────
    _secret_key = os.environ.get('SECRET_KEY', 'evore-crm-stable-fallback-key-2026-xK9mP')
    if _secret_key == 'evore-crm-stable-fallback-key-2026-xK9mP':
        logging.warning('SECRET_KEY not set — using fallback. Set SECRET_KEY in Railway.')
    app.config['SECRET_KEY'] = _secret_key

    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///crm.db')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping':  True,   # verifica conexión antes de usarla
        'pool_recycle':   280,    # recicla antes de los 300s de Railway
        'pool_timeout':   20,
        'pool_size':      5,
        'max_overflow':   10,
    }
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE']   = os.environ.get('RAILWAY_ENVIRONMENT') == 'production'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 horas
    app.config['REMEMBER_COOKIE_DURATION']  = 86400 * 7  # 7 dias

    # ── Mail (opcional) ───────────────────────────────────────────────
    app.config['MAIL_SERVER']         = os.environ.get('MAIL_SERVER', '')
    app.config['MAIL_PORT']           = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS']        = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', f'noreply@{COMPANY["default_email"].split("@")[1]}')

    # ── Init extensions ───────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    if MAIL_AVAILABLE and mail:
        try:
            mail.init_app(app)
        except Exception as e:
            logging.warning(f'Mail init warning: {e}')

    # ── Register routes ───────────────────────────────────────────────
    from routes import register_all
    register_all(app)

    # ── Template filters + context processors ────────────────────────
    from utils import register_app_hooks
    register_app_hooks(app)

    # ── Global error handlers ─────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify({'error': 'Recurso no encontrado', 'code': 404}), 404
        try:
            return render_template('404.html'), 404
        except Exception:
            return '<h1>404 — Página no encontrada</h1>', 404

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify({'error': 'Acceso denegado', 'code': 403}), 403
        try:
            return render_template('403.html'), 403
        except Exception:
            return '<h1>403 — Acceso denegado</h1>', 403

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()   # ← rollback automático en cualquier error 500
        logging.exception(f'Internal Server Error: {e}')
        if _wants_json():
            return jsonify({'error': 'Error interno del servidor', 'code': 500}), 500
        try:
            return render_template('500.html'), 500
        except Exception:
            return '<h1>500 — Error interno</h1>', 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        db.session.rollback()   # ← rollback en cualquier excepción no capturada
        logging.exception(f'Unhandled exception: {e}')
        if _wants_json():
            return jsonify({'error': str(e), 'code': 500}), 500
        try:
            return render_template('500.html'), 500
        except Exception:
            return '<h1>Error inesperado</h1>', 500

    # ── Teardown: siempre cerrar sesión de DB limpiamente ─────────────
    @app.teardown_request
    def _teardown(exc):
        if exc is not None:
            db.session.rollback()

    # ── App-level hooks ───────────────────────────────────────────────
    @app.before_request
    def _force_https():
        if os.environ.get('RAILWAY_ENVIRONMENT') == 'production':
            from flask import request, redirect
            if request.headers.get('X-Forwarded-Proto') == 'http':
                return redirect(request.url.replace('http://', 'https://', 1), code=301)

    @app.after_request
    def _security_headers(response):
        response.headers['X-Content-Type-Options']  = 'nosniff'
        response.headers['X-Frame-Options']          = 'SAMEORIGIN'
        response.headers['Referrer-Policy']          = 'strict-origin-when-cross-origin'
        return response

    # ── DB migrate on startup ─────────────────────────────────────────
    with app.app_context():
        from models import init_db, load_user as _luser
        login_manager.user_loader(_luser)
        try:
            init_db()
        except Exception as e:
            logging.error(f'DB init error: {e}')
        # Cargar parametros de nomina desde DB (sobreescribe defaults de company_config)
        try:
            from utils import _cargar_nomina_params
            _cargar_nomina_params()
        except Exception:
            pass

    return app


def _wants_json():
    """Returns True if the request prefers a JSON response."""
    from flask import request
    return (request.path.startswith('/api/') or
            'application/json' in request.headers.get('Accept', ''))


# Gunicorn entry point
app = create_app()
