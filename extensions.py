# extensions.py — Flask extension instances
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()


def tenant_query(model):
    """Return a query for model filtered by current company_id.

    Usage: tenant_query(Cliente) instead of Cliente.query
    Always filters by company_id — impossible to forget.
    Falls back to unfiltered if no company context (CLI, migrations).
    """
    from flask import g, has_request_context
    from flask_login import current_user
    q = model.query
    if not hasattr(model, 'company_id'):
        return q
    if has_request_context():
        cid = getattr(g, 'company_id', None)
        if not cid:
            try:
                cid = current_user.company_id if current_user and current_user.is_authenticated else None
            except Exception:
                pass
        if cid:
            return q.filter(model.company_id == cid)
    return q

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor inicia sesión.'
login_manager.login_message_category = 'warning'

try:
    from flask_mail import Mail
    mail = Mail()
    MAIL_AVAILABLE = True
except ImportError:
    mail = None
    MAIL_AVAILABLE = False
