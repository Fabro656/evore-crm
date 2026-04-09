# app.py — Flask app factory + Gunicorn entry point
import os, logging
from flask import Flask
from extensions import db, login_manager, mail, MAIL_AVAILABLE

logging.basicConfig(level=logging.INFO)

def create_app():
    app = Flask(__name__, template_folder='templates')

    # ── Config
    _secret_key = os.environ.get('SECRET_KEY', 'evore-crm-stable-fallback-key-2026-xK9mP')
    if _secret_key == 'evore-crm-stable-fallback-key-2026-xK9mP':
        logging.info('Using fallback SECRET_KEY. Set SECRET_KEY env var for production.')
    app.config['SECRET_KEY'] = _secret_key

    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///crm.db')
    if _db_url.startswith('postgres://'): 
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('RAILWAY_ENVIRONMENT') == 'production'

    # ── Mail config (optional)
    app.config['MAIL_SERVER']          = os.environ.get('MAIL_SERVER', '')
    app.config['MAIL_PORT']            = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS']         = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    app.config['MAIL_USERNAME']        = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD']        = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER']  = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@evore.us')

    # ── Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    if MAIL_AVAILABLE and mail:
        try:
            mail.init_app(app)
        except Exception as e:
            logging.warning(f'Mail init warning: {e}')

    # ── Register routes
    from routes import register_all
    register_all(app)

    # ── App-level hooks
    @app.before_request
    def _force_https():
        if os.environ.get('RAILWAY_ENVIRONMENT') == 'production':
            from flask import request, redirect
            if request.headers.get('X-Forwarded-Proto') == 'http':
                return redirect(request.url.replace('http://', 'https://', 1), code=301)

    @app.after_request
    def _security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # ── DB migrate on startup
    with app.app_context():
        from models import _migrate, load_user as _luser
        login_manager.user_loader(_luser)
        _migrate()

    return app

# Gunicorn entry point
app = create_app()
