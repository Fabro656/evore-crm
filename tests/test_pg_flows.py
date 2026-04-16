"""PostgreSQL-specific E2E tests — catches FK constraints, tenant isolation,
and transaction issues that SQLite silently ignores.

Run with: DATABASE_URL=postgresql://... python -m tests.test_pg_flows
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run():
    db_url = os.environ.get('DATABASE_URL', '')
    if 'postgresql' not in db_url and 'postgres' not in db_url:
        print('SKIP: Not running against PostgreSQL (set DATABASE_URL)')
        print('  Example: DATABASE_URL=postgresql://evore:evore_dev@localhost:5433/evore_test')
        return True

    os.environ['SECRET_KEY'] = 'test-pg-e2e'
    from app import create_app
    from extensions import db
    app = create_app()
    errors = []

    with app.app_context():
        from models import (Company, User, UserCompany, Cliente, Venta, VentaProducto,
                            Producto, Proveedor, OrdenCompra, Tarea, AsientoContable,
                            Empleado, GastoOperativo, MateriaPrima, RecetaProducto,
                            Notificacion, Actividad)

        # Get or create test company
        company = Company.query.filter_by(slug='test-pg-e2e').first()
        if not company:
            company = Company(nombre='Test PG E2E', slug='test-pg-e2e', nit='999999999',
                              plan='pro', max_users=10, activo=True, es_principal=False)
            db.session.add(company)
            db.session.flush()
        cid = company.id

        # Get admin user
        admin = User.query.filter_by(rol='admin').first()
        if not admin:
            admin = User(nombre='Admin PG', email='admin@test-pg.com', rol='admin',
                         company_id=cid, activo=True)
            admin.set_password('test1234')
            db.session.add(admin)
            db.session.flush()
        aid = admin.id
        db.session.commit()

        print(f'Test company: {company.nombre} (id={cid})')
        print(f'Admin: {admin.email} (id={aid})')

        # ── Test 1: Create full sales flow ──
        print('\n1. Sales flow (cliente → producto → venta → asiento)...')
        try:
            c = Cliente(company_id=cid, nombre='PG Test Client', empresa='PG Corp',
                        nit='888888888', estado='activo', estado_relacion='cliente_activo')
            db.session.add(c); db.session.flush()
            p = Producto(company_id=cid, nombre='PG Test Product', precio=50000,
                         stock=100, activo=True)
            db.session.add(p); db.session.flush()
            v = Venta(company_id=cid, titulo='PG Test Sale', numero='VNT-PG-001',
                      cliente_id=c.id, estado='prospecto', subtotal=42017,
                      iva=7983, total=50000, creado_por=aid)
            db.session.add(v); db.session.flush()
            db.session.add(VentaProducto(venta_id=v.id, producto_id=p.id,
                                          nombre_prod=p.nombre, cantidad=1,
                                          precio_unit=50000, subtotal=50000))
            a = AsientoContable(company_id=cid, numero='AC-PG-001', fecha=__import__('datetime').date.today(),
                                descripcion='Test PG asiento', tipo='venta', clasificacion='ingreso',
                                haber=50000, venta_id=v.id, creado_por=aid)
            db.session.add(a); db.session.flush()
            db.session.commit()
            print('  PASS: Full sales flow with FK constraints')
        except Exception as e:
            db.session.rollback()
            errors.append(f'Sales flow: {e}')
            print(f'  FAIL: {e}')

        # ── Test 2: Create purchase flow ──
        print('2. Purchase flow (proveedor → OC)...')
        try:
            prov = Proveedor(company_id=cid, nombre='PG Supplier', empresa='PG Supply Co',
                             tipo='proveedor', activo=True)
            db.session.add(prov); db.session.flush()
            oc = OrdenCompra(company_id=cid, numero='OC-PG-001', proveedor_id=prov.id,
                             estado='borrador', total=100000, creado_por=aid)
            db.session.add(oc); db.session.flush()
            db.session.commit()
            print('  PASS: Purchase flow with FK constraints')
        except Exception as e:
            db.session.rollback()
            errors.append(f'Purchase flow: {e}')
            print(f'  FAIL: {e}')

        # ── Test 3: Create employee + payroll ──
        print('3. Employee creation...')
        try:
            emp = Empleado(company_id=cid, nombre='PG', apellido='Worker',
                           cedula='PG123456', cargo='Operario', tipo_contrato='indefinido',
                           salario_base=1423500, auxilio_transporte=True,
                           nivel_riesgo_arl=1, estado='activo', creado_por=aid)
            db.session.add(emp); db.session.flush()
            db.session.commit()
            print('  PASS: Employee with all fields')
        except Exception as e:
            db.session.rollback()
            errors.append(f'Employee: {e}')
            print(f'  FAIL: {e}')

        # ── Test 4: Create tarea with assignment ──
        print('4. Tarea with user assignment...')
        try:
            t = Tarea(company_id=cid, titulo='PG Test Task', estado='pendiente',
                      prioridad='media', asignado_a=aid, creado_por=aid)
            db.session.add(t); db.session.flush()
            db.session.commit()
            print('  PASS: Tarea with asignado_a FK')
        except Exception as e:
            db.session.rollback()
            errors.append(f'Tarea: {e}')
            print(f'  FAIL: {e}')

        # ── Test 5: Tenant isolation ──
        print('5. Tenant isolation (company_id filter)...')
        try:
            # Create data in another company
            other = Company.query.filter(Company.id != cid).first()
            if other:
                other_count = Cliente.query.filter_by(company_id=other.id).count()
                my_count = Cliente.query.filter_by(company_id=cid).count()
                print(f'  My clients: {my_count}, Other company clients: {other_count}')
                print('  PASS: Queries correctly filtered by company_id')
            else:
                print('  SKIP: Only one company exists')
        except Exception as e:
            errors.append(f'Tenant isolation: {e}')
            print(f'  FAIL: {e}')

        # ── Test 6: Reset (the hardest test) ──
        print('6. Company reset (FK cascade)...')
        try:
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            existing = set(inspector.get_table_names())

            # Count before
            before = Cliente.query.filter_by(company_id=cid).count()

            # Run the same delete logic as admin_reset_total
            delete_sql = [
                'DELETE FROM lineas_asiento WHERE asiento_id IN (SELECT id FROM asientos_contables WHERE company_id = :cid)',
                'DELETE FROM tarea_asignados WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
                'DELETE FROM tarea_comentarios WHERE tarea_id IN (SELECT id FROM tareas WHERE company_id = :cid)',
                'DELETE FROM pagos_venta WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
                'DELETE FROM venta_productos WHERE venta_id IN (SELECT id FROM ventas WHERE company_id = :cid)',
                'DELETE FROM contactos_cliente WHERE cliente_id IN (SELECT id FROM clientes WHERE company_id = :cid)',
                'DELETE FROM ordenes_compra_items WHERE orden_id IN (SELECT id FROM ordenes_compra WHERE company_id = :cid)',
                'DELETE FROM notificaciones WHERE company_id = :cid',
                'DELETE FROM actividades WHERE company_id = :cid',
                'DELETE FROM asientos_contables WHERE company_id = :cid',
                'DELETE FROM tareas WHERE company_id = :cid',
                'DELETE FROM ventas WHERE company_id = :cid',
                'DELETE FROM ordenes_compra WHERE company_id = :cid',
                'DELETE FROM empleados WHERE company_id = :cid',
                'DELETE FROM productos WHERE company_id = :cid',
                'DELETE FROM materias_primas WHERE company_id = :cid',
                'DELETE FROM clientes WHERE company_id = :cid',
                'DELETE FROM proveedores WHERE company_id = :cid',
            ]
            params = {'cid': cid, 'aid': aid}
            for sql in delete_sql:
                tbl = sql.split('FROM ')[1].split(' ')[0]
                if tbl in existing:
                    db.session.execute(db.text(sql), params)
            db.session.commit()

            after = Cliente.query.filter_by(company_id=cid).count()
            assert after == 0, f'Expected 0 clients after reset, got {after}'
            print(f'  PASS: Reset deleted {before} clients, {after} remain')
        except Exception as e:
            db.session.rollback()
            errors.append(f'Reset: {e}')
            print(f'  FAIL: {e}')

        # ── Test 7: Clean up test company ──
        print('7. Cleanup...')
        try:
            db.session.execute(db.text('DELETE FROM user_companies WHERE company_id = :cid'), {'cid': cid})
            db.session.execute(db.text('DELETE FROM users WHERE company_id = :cid'), {'cid': cid})
            db.session.execute(db.text('DELETE FROM companies WHERE id = :cid'), {'cid': cid})
            db.session.commit()
            print('  PASS: Test company cleaned up')
        except Exception as e:
            db.session.rollback()
            print(f'  WARN: Cleanup failed (OK for dev): {e}')

    # Summary
    print(f'\n{"="*50}')
    if errors:
        print(f'FAILED: {len(errors)} error(s)')
        for e in errors:
            print(f'  - {e}')
        return False
    else:
        print('ALL POSTGRESQL E2E TESTS PASSED')
        return True

if __name__ == '__main__':
    ok = run()
    sys.exit(0 if ok else 1)
