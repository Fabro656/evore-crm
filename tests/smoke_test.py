"""Smoke test — run with: python -m tests.smoke_test"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run():
    print("=== EVORE CRM SMOKE TEST ===\n")
    errors = []

    # 1. App creates successfully
    print("1. App creation...", end=" ")
    try:
        from app import create_app
        app = create_app()
        print(f"OK ({len(list(app.url_map.iter_rules()))} endpoints)")
    except Exception as e:
        print(f"FAIL: {e}")
        errors.append(f"App creation: {e}")
        return errors

    # 2. All Python files compile
    print("2. Python compilation...", end=" ")
    import py_compile
    py_files = ['app.py', 'models.py', 'utils.py', 'services/inventario.py', 'services/nomina.py']
    py_files += [f'routes/{f}' for f in os.listdir('routes') if f.endswith('.py')]
    for f in py_files:
        try:
            py_compile.compile(f, doraise=True)
        except Exception as e:
            errors.append(f"Compile {f}: {e}")
    print(f"OK ({len(py_files)} files)" if not errors else f"FAIL ({len(errors)} errors)")

    # 3. Key routes respond
    print("3. Route responses...", end=" ")
    with app.test_client() as c:
        routes_to_test = [
            ('/', 200), ('/login', 200), ('/health', 200),
            ('/sw.js', 200), ('/api/docs', 302), ('/static/manifest.json', 200),
        ]
        for path, expected in routes_to_test:
            r = c.get(path, follow_redirects=False)
            if r.status_code != expected:
                errors.append(f"Route {path}: expected {expected}, got {r.status_code}")
    print(f"OK ({len(routes_to_test)} routes)" if not [e for e in errors if 'Route' in e] else "FAIL")

    # 4. Models load
    print("4. Models...", end=" ")
    try:
        with app.app_context():
            from models import User, Venta, Cliente, OrdenCompra, Empleado, Producto
            print("OK (6 key models imported)")
    except Exception as e:
        errors.append(f"Models: {e}")
        print(f"FAIL: {e}")

    # 5. Design system tokens exist
    print("5. Design tokens...", end=" ")
    css_content = open('static/css/evore.css').read()
    tokens = ['--sp-1', '--sp-5', '--font-body', '--font-micro', '--surface', '--ac', '--green', '--red']
    missing = [t for t in tokens if t not in css_content]
    if missing:
        errors.append(f"Missing tokens: {missing}")
        print(f"FAIL: missing {missing}")
    else:
        print(f"OK ({len(tokens)} tokens verified)")

    # 6. Critical functions exist
    print("6. Critical functions...", end=" ")
    try:
        from utils import _get_rol_activo, _get_roles_usuario, _modulos_user, _ROL_LABELS
        from services.inventario import verificar_stock_minimo
        print("OK (5 functions)")
    except Exception as e:
        errors.append(f"Functions: {e}")
        print(f"FAIL: {e}")

    # Summary
    print(f"\n{'='*40}")
    if errors:
        print(f"FAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
    else:
        print("ALL TESTS PASSED")
    return errors

if __name__ == '__main__':
    errors = run()
    sys.exit(1 if errors else 0)
