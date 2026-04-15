"""Smoke tests: verify key routes don't crash (status 200 or redirect)."""
import os
os.environ['SECRET_KEY'] = 'test-secret-key'

from app import create_app
from models import User

app = create_app()

def get_client():
    return app.test_client()

def login(client):
    """Login as admin and return client."""
    with app.app_context():
        admin = User.query.filter_by(rol='admin').first()
        if not admin:
            return False
    with client.session_transaction() as sess:
        sess['_csrf_token'] = 'test'
        sess['_user_id'] = str(admin.id) if admin else '1'
    return True


class TestPublicRoutes:
    """Routes that don't require login."""

    def test_landing(self):
        r = get_client().get('/')
        assert r.status_code == 200

    def test_inicio(self):
        r = get_client().get('/inicio')
        assert r.status_code == 200

    def test_login_page(self):
        r = get_client().get('/login')
        assert r.status_code == 200

    def test_modulo_ventas(self):
        r = get_client().get('/modulo/ventas')
        assert r.status_code == 200

    def test_modulo_produccion(self):
        r = get_client().get('/modulo/produccion')
        assert r.status_code == 200

    def test_modulo_contabilidad(self):
        r = get_client().get('/modulo/contabilidad')
        assert r.status_code == 200

    def test_modulo_nomina(self):
        r = get_client().get('/modulo/nomina')
        assert r.status_code == 200

    def test_modulo_invalid(self):
        r = get_client().get('/modulo/nonexistent')
        assert r.status_code == 404

    def test_contacto_get_rejected(self):
        r = get_client().get('/contacto')
        assert r.status_code in (404, 405, 500)  # Not a GET route

    def test_contacto_post_no_csrf(self):
        r = get_client().post('/contacto', data={'nombre': 'Test', 'email': 'a@b.com'})
        assert r.status_code in (302, 403)  # CSRF rejection or redirect

    def test_404_page(self):
        r = get_client().get('/this-does-not-exist')
        assert r.status_code == 404


class TestProtectedRoutes:
    """Routes that require login — should redirect to /login."""

    def test_dashboard_redirects(self):
        r = get_client().get('/dashboard')
        assert r.status_code == 302
        assert '/login' in r.headers.get('Location', '')

    def test_clientes_redirects(self):
        r = get_client().get('/clientes')
        assert r.status_code == 302

    def test_ventas_redirects(self):
        r = get_client().get('/ventas')
        assert r.status_code == 302

    def test_foro_redirects(self):
        r = get_client().get('/foro')
        assert r.status_code == 302

    def test_planes_redirects(self):
        r = get_client().get('/planes')
        assert r.status_code == 302


if __name__ == '__main__':
    print('Running smoke tests...')
    passed = 0
    failed = 0
    for cls in [TestPublicRoutes, TestProtectedRoutes]:
        obj = cls()
        for name in dir(obj):
            if name.startswith('test_'):
                try:
                    getattr(obj, name)()
                    print(f'  PASS: {cls.__name__}.{name}')
                    passed += 1
                except AssertionError as e:
                    print(f'  FAIL: {cls.__name__}.{name} — {e}')
                    failed += 1
                except Exception as e:
                    print(f'  ERROR: {cls.__name__}.{name} — {e}')
                    failed += 1
    print(f'\n{passed} passed, {failed} failed')
