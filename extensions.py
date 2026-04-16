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

# ── Redis cache (optional) ──
_redis_client = None

def get_redis():
    """Get Redis client. Returns None if not configured."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    import os
    url = os.environ.get('REDIS_URL')
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = False  # Don't retry
        return None

def cache_get(key):
    """Get value from Redis cache. Returns None if miss or no Redis."""
    r = get_redis()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception:
        return None

def cache_set(key, value, ttl=60):
    """Set value in Redis cache with TTL in seconds."""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, value)
    except Exception:
        pass

def cache_delete(pattern):
    """Delete keys matching pattern."""
    r = get_redis()
    if not r:
        return
    try:
        for key in r.scan_iter(match=pattern):
            r.delete(key)
    except Exception:
        pass
