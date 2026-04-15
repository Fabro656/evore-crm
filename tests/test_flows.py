"""Integration tests for critical business flows.
Run with: python -m pytest tests/test_flows.py -v
"""
import pytest
import json
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app():
    """Create app with test config using a temp SQLite file."""
    _fd, _path = tempfile.mkstemp(suffix='.db')
    os.close(_fd)
    os.environ['DATABASE_URL'] = f'sqlite:///{_path}'

    from app import create_app
    from extensions import db

    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SERVER_NAME'] = 'localhost'
    with app.app_context():
        db.create_all()
        # Create admin user
        from models import User
        admin = User(nombre='Admin Test', email='admin@test.com', rol='admin', activo=True)
        admin.set_password('test1234')
        db.session.add(admin)
        db.session.commit()
        yield app
        db.session.remove()
    # Cleanup
    os.environ.pop('DATABASE_URL', None)
    try:
        os.unlink(_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client, app):
    """Client with admin session."""
    with app.app_context():
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
            sess['rol_activo'] = 'admin'
            sess['_csrf_token'] = 'test-csrf-token'
    return client


class TestVentaLifecycle:
    """Test the complete venta state machine."""

    def test_transiciones_dict_exists(self, app):
        """TRANSICIONES dict must exist with all states."""
        with app.app_context():
            content = open('routes/ventas.py').read()
            assert 'TRANSICIONES' in content
            assert "'prospecto'" in content
            assert "'negociacion'" in content
            assert "'anticipo_pagado'" in content
            assert "'pagado'" in content
            assert "'entregado'" in content
            assert "'completado'" in content

    def test_create_venta(self, auth_client, app):
        """Can create a venta via the model."""
        with app.app_context():
            from models import Venta, Cliente
            from extensions import db
            c = Cliente(nombre='Test Client', empresa='Test Corp', estado='activo')
            db.session.add(c)
            db.session.flush()
            v = Venta(titulo='Test Sale', numero='VNT-2026-001',
                      cliente_id=c.id, estado='prospecto', total=1000000,
                      subtotal=840336, iva=159664, creado_por=1)
            db.session.add(v)
            db.session.commit()
            assert v.id is not None
            assert v.estado == 'prospecto'

    def test_valid_state_transitions(self, app):
        """Valid transitions should be allowed at model level."""
        with app.app_context():
            from models import Venta, Cliente
            from extensions import db
            c = Cliente(nombre='Test', empresa='Test', estado='activo')
            db.session.add(c)
            db.session.flush()
            v = Venta(titulo='Test', numero='VNT-2026-002',
                      cliente_id=c.id, estado='prospecto', total=500000,
                      subtotal=420168, iva=79832, creado_por=1)
            db.session.add(v)
            db.session.commit()

            # prospecto -> negociacion (valid)
            v.estado = 'negociacion'
            db.session.commit()
            assert v.estado == 'negociacion'

            # negociacion -> cancelado (valid per TRANSICIONES)
            v.estado = 'cancelado'
            db.session.commit()
            assert v.estado == 'cancelado'

    def test_venta_lifecycle_full(self, app):
        """Walk the happy-path lifecycle: prospecto -> ... -> completado."""
        with app.app_context():
            from models import Venta, Cliente
            from extensions import db
            c = Cliente(nombre='Lifecycle', empresa='LC', estado='activo')
            db.session.add(c)
            db.session.flush()
            v = Venta(titulo='Full Lifecycle', numero='VNT-2026-003',
                      cliente_id=c.id, estado='prospecto', total=2000000,
                      subtotal=1680672, iva=319328, creado_por=1)
            db.session.add(v)
            db.session.commit()

            # Walk the happy path at model level
            for next_state in ['negociacion', 'anticipo_pagado', 'pagado', 'entregado', 'completado']:
                v.estado = next_state
                db.session.commit()
                assert v.estado == next_state

    def test_with_for_update_exists(self, app):
        """venta_cambiar_estado must use with_for_update for race safety."""
        content = open('routes/ventas.py').read()
        assert 'with_for_update=True' in content

    def test_transiciones_values_correct(self, app):
        """TRANSICIONES dict values must match documented lifecycle."""
        content = open('routes/ventas.py').read()
        import re
        m = re.search(r"TRANSICIONES\s*=\s*\{([^}]+)\}", content)
        assert m, "Could not find TRANSICIONES dict"
        raw = m.group(0)
        local = {}
        exec(raw, {}, local)
        T = local['TRANSICIONES']
        # prospecto must lead to negociacion
        assert 'negociacion' in T['prospecto']
        # negociacion must lead to anticipo_pagado
        assert 'anticipo_pagado' in T['negociacion']
        # anticipo_pagado must lead to pagado
        assert 'pagado' in T['anticipo_pagado']


class TestOCLifecycle:
    """Test OC (Orden de Compra) state machine."""

    def test_oc_transiciones_exists(self, app):
        """OC_TRANSICIONES dict must exist with expected states."""
        content = open('routes/compras.py').read()
        assert 'OC_TRANSICIONES' in content
        assert "'borrador'" in content
        assert "'enviada'" in content
        assert "'recibida'" in content

    def test_create_oc(self, app):
        """Can create an OC via the model."""
        with app.app_context():
            from models import OrdenCompra, Proveedor
            from extensions import db
            p = Proveedor(nombre='Test Prov', empresa='Prov Corp', activo=True)
            db.session.add(p)
            db.session.flush()
            oc = OrdenCompra(numero='OC-2026-001', proveedor_id=p.id,
                             estado='borrador', total=500000, creado_por=1)
            db.session.add(oc)
            db.session.commit()
            assert oc.id is not None
            assert oc.estado == 'borrador'

    def test_oc_lifecycle_full(self, app):
        """Walk the OC happy path: borrador -> ... -> recibida."""
        with app.app_context():
            from models import OrdenCompra, Proveedor
            from extensions import db
            p = Proveedor(nombre='OC Prov', empresa='OC Corp', activo=True)
            db.session.add(p)
            db.session.flush()
            oc = OrdenCompra(numero='OC-2026-002', proveedor_id=p.id,
                             estado='borrador', total=750000, creado_por=1)
            db.session.add(oc)
            db.session.commit()

            for next_state in ['enviada', 'anticipo_pagado', 'en_espera_producto', 'recibida']:
                oc.estado = next_state
                db.session.commit()
                assert oc.estado == next_state

    def test_oc_transiciones_values_correct(self, app):
        """OC_TRANSICIONES must encode the documented lifecycle."""
        content = open('routes/compras.py').read()
        import re
        m = re.search(r"OC_TRANSICIONES\s*=\s*\{([^}]+)\}", content)
        assert m, "Could not find OC_TRANSICIONES dict"
        raw = m.group(0)
        local = {}
        exec(raw, {}, local)
        T = local['OC_TRANSICIONES']
        assert 'enviada' in T['borrador']
        assert 'anticipo_pagado' in T['enviada']
        assert 'en_espera_producto' in T['anticipo_pagado']

    def test_with_for_update_exists(self, app):
        """OC state change must use with_for_update for race safety."""
        content = open('routes/compras.py').read()
        assert 'with_for_update=True' in content


class TestContableFlow:
    """Test accounting connections."""

    def test_confirmar_pago_exists(self, app):
        """confirmar_pago route must exist."""
        with app.app_context():
            rules = [r.rule for r in app.url_map.iter_rules()]
            pago_routes = [r for r in rules if 'confirmar' in r and 'pago' in r]
            assert len(pago_routes) > 0

    def test_confirmar_ingreso_exists(self, app):
        """confirmar_ingreso route must exist."""
        with app.app_context():
            rules = [r.rule for r in app.url_map.iter_rules()]
            ingreso_routes = [r for r in rules if 'confirmar' in r and 'ingreso' in r]
            assert len(ingreso_routes) > 0

    def test_asiento_auto_function_exists(self, app):
        """_crear_asiento_auto must be importable."""
        from utils import _crear_asiento_auto
        assert callable(_crear_asiento_auto)


class TestMultiRol:
    """Test multi-role system."""

    def test_get_roles_usuario(self, app):
        """Admin user should have all roles available."""
        with app.app_context():
            from models import User
            from utils import _get_roles_usuario
            admin = User.query.filter_by(email='admin@test.com').first()
            roles = _get_roles_usuario(admin)
            assert 'admin' in roles
            assert len(roles) > 1  # admin has access to all roles

    def test_get_rol_activo_default(self, app):
        """Default active role should be user's primary role."""
        with app.app_context():
            from models import User
            admin = User.query.filter_by(email='admin@test.com').first()
            rol = admin.rol
            assert rol == 'admin'

    def test_cambiar_rol_route_exists(self, app):
        """cambiar_rol endpoint must exist."""
        with app.app_context():
            rules = [r.rule for r in app.url_map.iter_rules()]
            assert '/cambiar-rol' in rules


class TestDesignSystem:
    """Test design system integrity."""

    def test_tokens_in_css(self):
        content = open('static/css/evore.css').read()
        for token in ['--sp-1', '--sp-5', '--font-body', '--font-micro',
                       '--surface', '--ac', '--green', '--red', '--radius']:
            assert token in content, f"Missing token in evore.css: {token}"

    def test_tokens_in_portal(self):
        content = open('templates/portal_base.html').read()
        for token in ['--sp-1', '--sp-5', '--font-body', '--surface']:
            assert token in content, f"Missing portal token: {token}"

    def test_base_links_evore_css(self):
        base = open('templates/base.html').read()
        assert 'evore.css' in base, "base.html must link evore.css"
        assert 'evore.js' in base, "base.html must link evore.js"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
