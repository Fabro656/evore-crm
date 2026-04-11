# utils.py — Helper functions and utilities
from flask import current_app, session, request, redirect, url_for, flash
from flask_login import current_user
from extensions import db
from datetime import datetime, timedelta, date as date_type
from functools import wraps
import json, io, re, logging

__all__ = [
    # Module/role constants
    '_MODULOS_TODOS', '_MODULOS_ROL',
    # Payroll constants
    'SMLMV_2025', 'AUXILIO_TRANSPORTE_2025',
    'TASA_SALUD_EMP', 'TASA_PENSION_EMP', 'TASA_SALUD_EMPR', 'TASA_PENSION_EMPR',
    'TASA_CAJA_COMP', 'TASA_SENA', 'TASA_ICBF', 'TASA_ARL',
    'TASA_CESANTIAS', 'TASA_INT_CESANTIAS', 'TASA_PRIMA', 'TASA_VACACIONES',
    # Helpers
    'cop', 'moneda', 'moneda0', 'requiere_modulo', 'inject_globals',
    '_send_email', '_log', '_crear_notificacion', '_crear_asiento_auto',
    '_calcular_nomina', '_calcular_liquidacion', '_calcular_impuestos',
    '_descontar_materias', '_descontar_stock_venta', '_save_contactos',
    '_oc_save_items', '_prods_json', '_save_items', '_save_asignados',
    '_inv_form_ctx', '_save_compra', '_make_xlsx',
    '_procesar_orden_produccion', '_procesar_venta_produccion',
    '_modulos_user', 'register_app_hooks',
]

# ── Module constants (originally in app.py global scope)
_MODULOS_TODOS = ['clientes','ventas','cotizaciones','tareas','calendario',
                  'notas','inventario','produccion','gastos','reportes','proveedores',
                  'ordenes_compra','legal','finanzas','cotizaciones_proveedor','comercial','config','nomina',
                  'empaques','servicios']

_MODULOS_ROL = {
    'admin':      _MODULOS_TODOS,
    'tester':     _MODULOS_TODOS,   # acceso a todo, sin crear usuarios ni reset
    'director_financiero': _MODULOS_TODOS,  # Dueño: ve todo, aprueba gastos/compras
    'director_operativo':  ['clientes','ventas','cotizaciones','tareas','calendario','notas',
                            'inventario','produccion','proveedores','ordenes_compra',
                            'cotizaciones_proveedor','empaques','servicios','nomina','reportes'],
    'vendedor':   ['clientes','ventas','cotizaciones','tareas','calendario','notas','nomina'],
    'produccion': ['inventario','produccion','gastos','notas','calendario','tareas'],
    'contador':   ['gastos','reportes','produccion','notas','nomina','finanzas'],
    'usuario':    ['tareas','notas','calendario'],
    'sales_manager': ['clientes','ventas','cotizaciones','tareas','calendario','notas','ordenes_compra','nomina'],
    'cliente':       ['portal_cliente'],
    'proveedor':     ['portal_proveedor'],
}

# Acciones que requieren aprobación de director_financiero
REQUIERE_APROBACION = {
    'gasto_nuevo':       'Registrar gasto operativo',
    'compra_nueva':      'Registrar compra de materia prima',
    'nomina_cerrar':     'Cerrar nómina mensual',
    'orden_compra_nueva':'Crear orden de compra',
}

# ── Colombian labor / payroll constants (originally in app.py global scope)
SMLMV_2025              = 1_423_500   # Salario Mínimo Legal Mensual Vigente 2025
AUXILIO_TRANSPORTE_2025 = 200_000     # Auxilio de transporte 2025
TASA_SALUD_EMP          = 0.04        # 4%
TASA_PENSION_EMP        = 0.04        # 4%
TASA_SALUD_EMPR         = 0.085       # 8.5%
TASA_PENSION_EMPR       = 0.12        # 12%
TASA_CAJA_COMP          = 0.04        # 4%
TASA_SENA               = 0.02        # 2%
TASA_ICBF               = 0.03        # 3%
TASA_ARL = {1: 0.00522, 2: 0.01044, 3: 0.02436, 4: 0.04350, 5: 0.06960}
TASA_CESANTIAS          = 1/12        # ~8.33%
TASA_INT_CESANTIAS      = 0.12        # sobre cesantías
TASA_PRIMA              = 1/12        # ~8.33%
TASA_VACACIONES         = 0.0417      # 15 días hábiles por año

# ── Mail setup (graceful degradation if Flask-Mail not installed/configured)
try:
    from flask_mail import Message as MailMessage
    _mail_ok = True   # confirmed against MAIL_SERVER config when first called
    _mail = None      # actual Mail instance lives in extensions.py
except ImportError:
    MailMessage = None
    _mail = None
    _mail_ok = False

# ── Model imports (no circular dependency: models.py only imports from extensions)
from models import (
    User, Cliente, ContactoCliente, Proveedor,
    Venta, VentaProducto, Producto, LoteProducto,
    MateriaPrima, RecetaProducto, OrdenProduccion, ReservaProduccion,
    OrdenCompraItem, Tarea, TareaAsignado,
    GastoOperativo, Actividad, Notificacion, ReglaTributaria,
)

def cop(value):
    try: return '$ {:,.0f}'.format(float(value or 0)).replace(',','.')
    except: return '$ 0'

def moneda(value):
    try: return '${:,.2f}'.format(float(value or 0))
    except: return '$0.00'

def moneda0(value):
    try: return '${:,.0f}'.format(float(value or 0))
    except: return '$0'

def requiere_modulo(modulo):
    def decorator(f):
        @wraps(f)
        def wrapped(*a, **kw):
            if not current_user.is_authenticated:
                return redirect(url_for('login'))
            if current_user.rol == 'admin' or modulo in _modulos_user(current_user):
                return f(*a, **kw)
            flash('No tienes acceso a este módulo.', 'danger')
            return redirect(url_for('dashboard'))
        return wrapped
    return decorator

def inject_globals():
    modulos = _modulos_user(current_user) if current_user.is_authenticated else []
    notif_count = 0
    empresa_cliente_nombre = None
    empresa_proveedor_nombre = None
    if current_user.is_authenticated:
        try:
            notif_count = Notificacion.query.filter_by(
                usuario_id=current_user.id, leida=False).count()
        except: pass
        if current_user.rol == 'cliente':
            try:
                if current_user.cliente_id:
                    cli = db.session.get(Cliente, current_user.cliente_id)
                    if cli: empresa_cliente_nombre = cli.empresa or cli.nombre
            except Exception: pass
        if current_user.rol == 'proveedor':
            try:
                prov_id = getattr(current_user, 'proveedor_id', None)
                if prov_id:
                    prov = db.session.get(Proveedor, prov_id)
                    if prov: empresa_proveedor_nombre = prov.nombre
            except Exception: pass
    return {'now': datetime.utcnow(), 'modulos_user': modulos, 'notif_count': notif_count,
            'empresa_cliente_nombre': empresa_cliente_nombre, 'empresa_proveedor_nombre': empresa_proveedor_nombre}

def _send_email(to, subject, body):
    if not _mail_ok or not MailMessage: return
    try:
        from extensions import mail as _mail_ext, MAIL_AVAILABLE
        if not MAIL_AVAILABLE or not _mail_ext: return
        if not current_app.config.get('MAIL_SERVER'): return
        msg = MailMessage(subject, recipients=[to], body=body)
        _mail_ext.send(msg)
    except Exception as e:
        print(f'Email error: {e}')

def _log(tipo, entidad, entidad_id, descripcion):
    try:
        db.session.add(Actividad(
            tipo=tipo, entidad=entidad, entidad_id=entidad_id,
            descripcion=descripcion, usuario_id=current_user.id))
    except Exception:
        pass

def _crear_asiento_auto(tipo, subtipo, descripcion, monto, cuenta_debe, cuenta_haber,
                        clasificacion='egreso', referencia=None, venta_id=None,
                        orden_compra_id=None, gasto_id=None, proveedor_id=None):
    """Crea un AsientoContable automático con auto-numeración."""
    try:
        ultimo = AsientoContable.query.order_by(AsientoContable.id.desc()).first()
        n_ac = (ultimo.id + 1) if ultimo else 1
        year = datetime.utcnow().year
        numero = f'AC-{year}-{n_ac:04d}'
        asiento = AsientoContable(
            numero=numero,
            fecha=datetime.utcnow().date(),
            descripcion=descripcion[:300],
            tipo=tipo, subtipo=subtipo,
            referencia=referencia,
            debe=float(monto), haber=float(monto),
            cuenta_debe=cuenta_debe, cuenta_haber=cuenta_haber,
            clasificacion=clasificacion,
            venta_id=venta_id, orden_compra_id=orden_compra_id,
            gasto_id=gasto_id, proveedor_id=proveedor_id,
            creado_por=current_user.id if current_user and current_user.is_authenticated else None
        )
        db.session.add(asiento)
        return asiento
    except Exception as e:
        logging.warning(f'_crear_asiento_auto error: {e}')
        return None

def _crear_notificacion(usuario_id, tipo, titulo, mensaje, url=None):
    try:
        n = Notificacion(usuario_id=usuario_id, tipo=tipo, titulo=titulo,
                         mensaje=mensaje, url=url)
        db.session.add(n)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f'Notificacion error: {e}')

def _calcular_nomina(empleado):
    """Returns a dict with all payroll calculations for an employee."""
    salario = empleado.salario_base
    aux_transporte = AUXILIO_TRANSPORTE_2025 if (empleado.auxilio_transporte and salario <= 2 * SMLMV_2025) else 0

    # Deducciones empleado
    deduccion_salud     = round(salario * TASA_SALUD_EMP)
    deduccion_pension   = round(salario * TASA_PENSION_EMP)
    # Fondo solidaridad: 1% si salario > 4 SMLMV, 1.2% si > 16 SMLMV
    fondo_solidaridad = 0
    if salario > 16 * SMLMV_2025:
        fondo_solidaridad = round(salario * 0.012)
    elif salario > 4 * SMLMV_2025:
        fondo_solidaridad = round(salario * 0.01)

    total_deducciones = deduccion_salud + deduccion_pension + fondo_solidaridad
    salario_neto = salario + aux_transporte - total_deducciones

    # Aportes empleador (no afectan neto del empleado)
    aporte_salud_empr    = round(salario * TASA_SALUD_EMPR)
    aporte_pension_empr  = round(salario * TASA_PENSION_EMPR)
    tasa_arl             = TASA_ARL.get(empleado.nivel_riesgo_arl, TASA_ARL[1])
    aporte_arl           = round(salario * tasa_arl)
    aporte_caja          = round(salario * TASA_CAJA_COMP)
    aporte_sena          = round(salario * TASA_SENA)
    aporte_icbf          = round(salario * TASA_ICBF)
    total_costo_empr     = salario + aux_transporte + aporte_salud_empr + aporte_pension_empr + aporte_arl + aporte_caja + aporte_sena + aporte_icbf

    # Prestaciones sociales (provisionadas mensualmente)
    provision_cesantias      = round((salario + aux_transporte) * TASA_CESANTIAS)
    provision_int_cesantias  = round(provision_cesantias * TASA_INT_CESANTIAS / 12)
    provision_prima          = round((salario + aux_transporte) * TASA_PRIMA)
    provision_vacaciones     = round(salario * TASA_VACACIONES)
    total_prestaciones       = provision_cesantias + provision_int_cesantias + provision_prima + provision_vacaciones

    return {
        'salario': salario,
        'aux_transporte': aux_transporte,
        'deduccion_salud': deduccion_salud,
        'deduccion_pension': deduccion_pension,
        'fondo_solidaridad': fondo_solidaridad,
        'total_deducciones': total_deducciones,
        'salario_neto': salario_neto,
        'aporte_salud_empr': aporte_salud_empr,
        'aporte_pension_empr': aporte_pension_empr,
        'aporte_arl': aporte_arl,
        'aporte_caja': aporte_caja,
        'aporte_sena': aporte_sena,
        'aporte_icbf': aporte_icbf,
        'total_costo_empr': total_costo_empr,
        'provision_cesantias': provision_cesantias,
        'provision_int_cesantias': provision_int_cesantias,
        'provision_prima': provision_prima,
        'provision_vacaciones': provision_vacaciones,
        'total_prestaciones': total_prestaciones,
        'costo_total_empresa': total_costo_empr + total_prestaciones,
    }

def _calcular_liquidacion(empleado, motivo):
    """
    Calculate employee liquidation.
    motivo: 'renuncia' | 'despido_justa' | 'despido_sin_justa' | 'mutuo_acuerdo'
    """
    from datetime import date as date_t
    hoy = date_t.today()
    fecha_retiro = empleado.fecha_retiro or hoy
    fecha_ingreso = empleado.fecha_ingreso
    if not fecha_ingreso:
        return None

    # Días trabajados
    dias_trabajados = (fecha_retiro - fecha_ingreso).days
    anios = dias_trabajados / 365.25
    meses = dias_trabajados / 30.417

    salario = empleado.salario_base
    aux_transporte = AUXILIO_TRANSPORTE_2025 if (empleado.auxilio_transporte and salario <= 2 * SMLMV_2025) else 0
    salario_con_aux = salario + aux_transporte

    # Cesantías: 1 mes de salario con aux por año trabajado (proporcional)
    cesantias = round(salario_con_aux * dias_trabajados / 365.25)

    # Intereses sobre cesantías: 12% anual proporcional
    int_cesantias = round(cesantias * 0.12 * dias_trabajados / 365.25)

    # Prima de servicios: 15 días de salario con aux por semestre (proporcional al último semestre)
    # Calcular días del semestre en curso
    ultimo_1_julio = date_t(hoy.year, 7, 1) if hoy.month >= 7 else date_t(hoy.year - 1, 7, 1)
    ultimo_1_enero = date_t(hoy.year, 1, 1)
    inicio_semestre = max(ultimo_1_julio, ultimo_1_enero, fecha_ingreso)
    dias_semestre = max((fecha_retiro - inicio_semestre).days, 0)
    prima = round(salario_con_aux * dias_semestre / 360)

    # Vacaciones: 15 días por año (proporcional)
    vacaciones = round(salario * dias_trabajados / 730)  # 15/365 = 1/730 * salario * dias

    # Indemnización por despido sin justa causa (Art. 64 CST)
    indemnizacion = 0
    if motivo == 'despido_sin_justa':
        if empleado.tipo_contrato == 'indefinido':
            if anios < 1:
                indemnizacion = round(salario * 30 / 30)  # 30 días primer año
            elif salario <= 10 * SMLMV_2025:
                indemnizacion = round(salario * 30 / 30 + salario * 20 / 30 * (anios - 1))
            else:
                indemnizacion = round(salario * 20 / 30 * anios)
        elif empleado.tipo_contrato == 'fijo':
            # Suma de salarios al vencimiento del contrato
            dias_restantes = max(0, (empleado.fecha_fin_contrato - fecha_retiro).days) if hasattr(empleado, 'fecha_fin_contrato') else 90
            indemnizacion = round(salario * min(dias_restantes, 180) / 30)

    total = cesantias + int_cesantias + prima + vacaciones + indemnizacion

    return {
        'empleado': empleado,
        'motivo': motivo,
        'fecha_ingreso': fecha_ingreso,
        'fecha_retiro': fecha_retiro,
        'dias_trabajados': dias_trabajados,
        'anios': round(anios, 2),
        'salario': salario,
        'aux_transporte': aux_transporte,
        'cesantias': cesantias,
        'int_cesantias': int_cesantias,
        'prima': prima,
        'vacaciones': vacaciones,
        'indemnizacion': indemnizacion,
        'total': total,
    }

def _calcular_impuestos(ingresos, utilidad):
    """Retorna (total_impuestos, lista_detalle) según reglas tributarias activas.
    Cada item del detalle: {nombre, aplica_a, porcentaje, base_label, base_monto, monto}
    No incluye reglas de proveedor (se aplican por compra individual)."""
    reglas = ReglaTributaria.query.filter_by(activo=True).all()
    total = 0.0
    detalle = []
    for r in reglas:
        if r.aplica_a in ('proveedor_producto', 'proveedor_granel'):
            continue  # estas aplican por compra, no de forma global
        base_label = ''
        base_monto = 0.0
        monto = 0.0
        if r.aplica_a == 'ventas':
            # IVA se calcula sobre la base SIN impuesto (total / (1 + pct/100))
            pct = r.porcentaje / 100.0
            base_monto = ingresos / (1.0 + pct) if pct > 0 else ingresos
            base_label = 'Base gravable (sin IVA)'
        elif r.aplica_a == 'ingresos':
            pct = r.porcentaje / 100.0
            base_monto = ingresos / (1.0 + pct) if pct > 0 else ingresos
            base_label = 'Base gravable (sin IVA)'
        elif r.aplica_a == 'profit':
            if utilidad > 0:
                base_monto = utilidad
                base_label = 'Utilidad'
            else:
                continue
        monto = base_monto * (r.porcentaje / 100.0)
        total += monto
        detalle.append({
            'nombre': r.nombre,
            'aplica_a': r.aplica_a,
            'porcentaje': r.porcentaje,
            'base_label': base_label,
            'base_monto': base_monto,
            'monto': monto,
        })
    return total, detalle

def _descontar_materias(form):
    """Si el formulario tiene usar_materias=1, descuenta stock de cada materia prima."""
    if not form.get('usar_materias'): return
    mp_ids = form.getlist('mp_id[]')
    mp_cants = form.getlist('mp_cant[]')
    lote_id = form.get('lote_id') or None
    errores = []
    for mid, cant_str in zip(mp_ids, mp_cants):
        if not mid or not cant_str: continue
        try:
            cant = float(cant_str)
            m = db.session.get(MateriaPrima, int(mid))
            if not m:
                errores.append(f'Materia prima ID {mid} no encontrada')
                continue
            if m.stock_disponible < cant:
                errores.append(f'Stock insuficiente de "{m.nombre}": disponible {m.stock_disponible:.3f} {m.unidad}, solicitado {cant:.3f}')
                continue
            m.stock_disponible -= cant
            m.stock_reservado = max(0, m.stock_reservado - cant)
            if lote_id:
                db.session.add(ReservaProduccion(
                    materia_prima_id=m.id, cantidad=cant,
                    lote_id=int(lote_id), estado='usado',
                    notas='Descontado desde inventario',
                    creado_por=None))
        except Exception as e:
            errores.append(str(e))
    return errores

def _descontar_stock_venta(venta):
    """
    Descuenta del inventario (Producto.stock) las cantidades de los items
    de la venta. Se llama exactamente una vez, cuando la venta pasa a
    anticipo_pagado o completado por primera vez.
    """
    try:
        for item in venta.items:
            if not item.producto_id:
                continue
            prod = db.session.get(Producto, item.producto_id)
            if not prod:
                continue
            cant = item.cantidad
            prod.stock = max(0, (prod.stock or 0) - cant)
    except Exception as ex:
        print(f'_descontar_stock_venta error: {ex}')

def _save_contactos(cliente_obj):
    ContactoCliente.query.filter_by(cliente_id=cliente_obj.id).delete()
    nombres   = request.form.getlist('c_nombre[]')
    cargos    = request.form.getlist('c_cargo[]')
    emails    = request.form.getlist('c_email[]')
    telefonos = request.form.getlist('c_telefono[]')
    for i, n in enumerate(nombres):
        if n.strip():
            db.session.add(ContactoCliente(
                cliente_id=cliente_obj.id,
                nombre=n.strip(),
                cargo=cargos[i] if i < len(cargos) else '',
                email=emails[i] if i < len(emails) else '',
                telefono=telefonos[i] if i < len(telefonos) else ''))

def _oc_save_items(oc_id):
    """Guarda ítems del formulario de OC y devuelve la lista."""
    nombres  = request.form.getlist('item_nombre[]')
    descs    = request.form.getlist('item_desc[]')
    cants    = request.form.getlist('item_cant[]')
    units    = request.form.getlist('item_unidad[]')
    precios  = request.form.getlist('item_precio[]')
    cot_ids  = request.form.getlist('item_cot_id[]')
    items = []
    for i, nom in enumerate(nombres):
        if not nom.strip(): continue
        cant   = float(cants[i])  if i < len(cants)   else 1
        precio = float(precios[i]) if i < len(precios) else 0
        cot_id = int(cot_ids[i]) if i < len(cot_ids) and cot_ids[i].strip() else None
        items.append(OrdenCompraItem(
            orden_id=oc_id,
            nombre_item=nom.strip(),
            descripcion=descs[i] if i < len(descs) else '',
            cantidad=cant,
            unidad=units[i] if i < len(units) else 'unidades',
            precio_unit=precio,
            subtotal=cant*precio,
            cotizacion_id=cot_id
        ))
    return items

def _prods_json():
    prods = Producto.query.filter_by(activo=True).order_by(Producto.nombre).all()
    return [{'id':p.id,'nombre':p.nombre,'sku':p.sku or '','precio':p.precio,
             'stock':p.stock,'stock_minimo':p.stock_minimo} for p in prods]

def _save_items(venta_obj):
    VentaProducto.query.filter_by(venta_id=venta_obj.id).delete()
    pids    = request.form.getlist('prod_id[]')
    cants   = request.form.getlist('prod_cant[]')
    precios = request.form.getlist('prod_precio[]')
    for i, pid in enumerate(pids):
        cant  = float(cants[i]) if i < len(cants) else 1
        precio= float(precios[i]) if i < len(precios) else 0
        prod  = db.session.get(Producto, int(pid)) if pid else None
        db.session.add(VentaProducto(
            venta_id=venta_obj.id,
            producto_id=int(pid) if pid else None,
            nombre_prod=prod.nombre if prod else '',
            cantidad=cant, precio_unit=precio, subtotal=cant*precio))

def _save_asignados(tarea_obj):
    TareaAsignado.query.filter_by(tarea_id=tarea_obj.id).delete()
    # asignado principal
    principal = request.form.get('asignado_a')
    # otros asignados (multi-select)
    otros = request.form.getlist('otros_asignados[]')
    seen = set()
    for uid_str in ([principal] if principal else []) + otros:
        try:
            uid = int(uid_str)
            if uid not in seen:
                seen.add(uid)
                db.session.add(TareaAsignado(tarea_id=tarea_obj.id, user_id=uid))
        except (ValueError, TypeError):
            pass
    if not seen:
        db.session.add(TareaAsignado(tarea_id=tarea_obj.id, user_id=current_user.id))

def _inv_form_ctx():
    materias = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
    lotes = LoteProducto.query.order_by(LoteProducto.creado_en.desc()).all()
    mj = [{'id': m.id, 'nombre': m.nombre, 'unidad': m.unidad,
            'stock': m.stock_disponible} for m in materias]
    return {'materias_json': mj, 'lotes': lotes}

def _save_compra(c, form):
    """Helper to parse and save compra fields from form."""
    fd = form.get('fecha')
    cant  = float(form.get('cantidad',1) or 1)
    costo_p = float(form.get('costo_producto',0) or 0)
    imp   = float(form.get('impuestos',0) or 0)
    trans = float(form.get('transporte',0) or 0)
    costo_total = costo_p + imp + trans
    precio_unit = (costo_total / cant) if cant > 0 else 0
    pid   = form.get('producto_id') or None
    mid   = form.get('materia_id') or None
    fvenc = form.get('fecha_caducidad') or None
    c.producto_id   = int(pid) if pid else None
    c.materia_id    = int(mid) if mid else None
    c.nombre_item   = form['nombre_item']
    c.tipo_compra   = form.get('tipo_compra','insumo')
    c.unidad        = form.get('unidad','unidades')
    c.proveedor     = form.get('proveedor','')
    c.proveedor_id  = int(form.get('proveedor_id')) if form.get('proveedor_id') else None
    c.fecha         = datetime.strptime(fd,'%Y-%m-%d').date() if fd else datetime.utcnow().date()
    c.nro_factura   = form.get('nro_factura','')
    c.cantidad      = cant
    c.costo_producto = costo_p; c.impuestos = imp; c.transporte = trans
    c.costo_total   = costo_total; c.precio_unitario = precio_unit
    c.tiene_caducidad = bool(form.get('tiene_caducidad'))
    c.fecha_caducidad = datetime.strptime(fvenc,'%Y-%m-%d').date() if fvenc else None
    c.notas = form.get('notas','')
    # Update linked product cost
    if pid:
        prod = db.session.get(Producto, int(pid))
        if prod: prod.costo = precio_unit
    # Update materia prima stock if tipo=materia_prima — crea LoteMateriaPrima para trazabilidad FIFO
    if mid and c.tipo_compra == 'materia_prima':
        m = db.session.get(MateriaPrima, int(mid))
        if m:
            m.stock_disponible = (m.stock_disponible or 0) + cant
            try:
                from models import LoteMateriaPrima
                lote_mp = LoteMateriaPrima(
                    materia_prima_id=m.id,
                    numero_lote=form.get('nro_lote_materia','').strip() or None,
                    nro_factura=c.nro_factura or None,
                    proveedor=c.proveedor or None,
                    fecha_compra=c.fecha,
                    fecha_vencimiento=c.fecha_caducidad,
                    cantidad_inicial=cant,
                    cantidad_disponible=cant,
                    cantidad_reservada=0.0,
                    costo_unitario=precio_unit,
                    notas=form.get('notas','') or None,
                )
                db.session.add(lote_mp)
            except Exception as _le:
                import logging; logging.warning(f'LoteMateriaPrima create error: {_le}')
    # Auto-register/update GastoOperativo
    tipo_label = {'materia_prima': 'Materia prima', 'insumo': 'Insumo',
                  'producto': 'Producto', 'servicio': 'Servicio'}.get(c.tipo_compra, c.tipo_compra.capitalize())
    desc_gasto = (f'{c.nombre_item} — {tipo_label}')
    if c.proveedor: desc_gasto += f' | Proveedor: {c.proveedor}'
    if c.nro_factura: desc_gasto += f' | Factura: {c.nro_factura}'
    # Buscar gasto existente para esta compra (evitar duplicados en edición)
    gasto = None
    if c.id:
        gasto = GastoOperativo.query.filter_by(
            tipo='compra_produccion',
            descripcion=db.func.substr(GastoOperativo.descripcion, 1, 50).like(f'%{c.nombre_item[:30]}%')
        ).filter(
            GastoOperativo.fecha == c.fecha,
            GastoOperativo.creado_por == getattr(c, 'creado_por', None)
        ).first()
    if gasto:
        # Actualizar existente
        gasto.fecha = c.fecha
        gasto.tipo_custom = f'Compra / {tipo_label}'
        gasto.descripcion = desc_gasto
        gasto.monto = costo_total
        # Actualizar asiento vinculado
        asiento_link = AsientoContable.query.filter_by(gasto_id=gasto.id).first()
        if asiento_link:
            asiento_link.debe = float(costo_total)
            asiento_link.haber = float(costo_total)
            asiento_link.descripcion = f'Compra: {c.nombre_item} — {tipo_label}'[:300]
            asiento_link.fecha = c.fecha
            asiento_link.referencia = c.nro_factura or None
    else:
        # Crear nuevo
        gasto = GastoOperativo(
            fecha=c.fecha,
            tipo='compra_produccion',
            tipo_custom=f'Compra / {tipo_label}',
            descripcion=desc_gasto,
            monto=costo_total,
            recurrencia='unica',
            es_plantilla=False,
            notas=f'Registrado automáticamente desde módulo Compras.',
            creado_por=getattr(c, 'creado_por', None)
        )
        db.session.add(gasto)
        db.session.flush()
        # Partida doble automática
        _crear_asiento_auto(
            tipo='compra', subtipo='compra_materia',
            descripcion=f'Compra: {c.nombre_item} — {tipo_label}',
            monto=costo_total,
            cuenta_debe='Inventario materias primas',
            cuenta_haber='Cuentas por pagar proveedores',
            clasificacion='egreso',
            referencia=c.nro_factura or None,
            gasto_id=gasto.id,
            proveedor_id=c.proveedor_id
        )
    return c

def _make_xlsx(titulo, headers, rows):
    import io, openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = titulo
    # Cabecera empresa
    ws.merge_cells(f'A1:{chr(64+len(headers))}1')
    ws['A1'] = 'Evore CRM — ' + titulo
    ws['A1'].font = Font(bold=True, size=13, color='FFFFFF')
    ws['A1'].fill = PatternFill('solid', fgColor='5E72E4')
    ws['A1'].alignment = Alignment(horizontal='center')
    # Headers
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=col, value=h)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='1A1F36')
        cell.alignment = Alignment(horizontal='center')
    # Datos
    for r_idx, row in enumerate(rows, 3):
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    # Autofit columns
    for col in ws.columns:
        max_len = max((len(str(c.value or '')) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

def _procesar_orden_produccion(cot):
    """
    Al confirmar una cotización, por cada item:
    1. Verifica stock actual vs requerido y crea OrdenProduccion
    2. Reserva materias primas disponibles según BOM
    3. Si faltan materias, crea tareas comprar_materias + verificar_abono y notifica admins
    """
    admins = User.query.filter_by(rol='admin', activo=True).all()
    primer_admin_id = admins[0].id if admins else current_user.id

    for item in cot.items:
        if not item.producto_id: continue
        prod = db.session.get(Producto, item.producto_id)
        if not prod: continue
        cant_requerida = item.cantidad
        cant_en_stock  = min(prod.stock, cant_requerida)
        cant_producir  = max(0, cant_requerida - cant_en_stock)

        # Crear orden de producción
        orden = OrdenProduccion(
            cotizacion_id=cot.id,
            producto_id=prod.id,
            cantidad_total=cant_requerida,
            cantidad_stock=cant_en_stock,
            cantidad_producir=cant_producir,
            estado='en_produccion' if cant_producir > 0 else 'completado',
            notas=f'Cotización #{cot.numero or cot.id} — {cot.titulo}',
            creado_por=current_user.id
        )
        db.session.add(orden)
        db.session.flush()  # obtener orden.id para vincular reservas

        if cant_producir <= 0:
            continue  # ya hay suficiente stock, sin acción adicional

        # Verificar BOM
        receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
        materias_faltantes = []
        if receta and receta.unidades_produce > 0:
            factor = cant_producir / receta.unidades_produce
            for ri in receta.items:
                mp = db.session.get(MateriaPrima, ri.materia_prima_id)
                if not mp: continue
                necesaria = ri.cantidad_por_unidad * factor
                disponible = mp.stock_disponible
                if disponible >= necesaria:
                    # Reservar automáticamente
                    mp.stock_disponible -= necesaria
                    mp.stock_reservado  += necesaria
                    db.session.add(ReservaProduccion(
                        materia_prima_id=mp.id,
                        cantidad=necesaria,
                        producto_id=prod.id,
                        orden_produccion_id=orden.id,
                        estado='reservado',
                        notas=f'Auto-reserva cot #{cot.numero or cot.id}',
                        creado_por=current_user.id
                    ))
                else:
                    faltante = necesaria - disponible
                    materias_faltantes.append(
                        f'{mp.nombre}: falta {faltante:.3f} {mp.unidad} (disponible {disponible:.3f})'
                    )
                    # Reservar lo que haya
                    if disponible > 0:
                        mp.stock_disponible = 0
                        mp.stock_reservado += disponible
                        db.session.add(ReservaProduccion(
                            materia_prima_id=mp.id,
                            cantidad=disponible,
                            producto_id=prod.id,
                            orden_produccion_id=orden.id,
                            estado='reservado',
                            notas=f'Parcial cot #{cot.numero or cot.id}',
                            creado_por=current_user.id
                        ))

        if materias_faltantes:
            descripcion_falta = '\n'.join(materias_faltantes)
            desc_tareas = (f'Cotización: #{cot.numero or cot.id} — {cot.titulo}\n'
                           f'Producto: {prod.nombre} (x{cant_producir})\n\n'
                           f'Materiales faltantes:\n{descripcion_falta}')
            from datetime import timedelta
            venc = (datetime.utcnow() + timedelta(days=3)).date()

            t_compra = Tarea(
                titulo=f'Comprar materias — {prod.nombre} (cot #{cot.numero or cot.id})',
                descripcion=desc_tareas,
                estado='pendiente', prioridad='alta',
                asignado_a=primer_admin_id,
                creado_por=current_user.id,
                fecha_vencimiento=venc,
                cotizacion_id=cot.id,
                tarea_tipo='comprar_materias'
            )
            db.session.add(t_compra); db.session.flush()

            t_abono = Tarea(
                titulo=f'Verificar abono — {cot.titulo}',
                descripcion=(f'Confirmar recepción del anticipo antes de comprar materias.\n'
                             f'Cotización: #{cot.numero or cot.id}'),
                estado='pendiente', prioridad='alta',
                asignado_a=primer_admin_id,
                creado_por=current_user.id,
                fecha_vencimiento=venc,
                cotizacion_id=cot.id,
                tarea_tipo='verificar_abono',
                tarea_pareja_id=t_compra.id
            )
            db.session.add(t_abono); db.session.flush()
            # link inverso
            t_compra.tarea_pareja_id = t_abono.id

            # Notificar a todos los admins
            for adm in admins:
                _crear_notificacion(
                    adm.id, 'alerta_stock',
                    f'⚠️ Materiales insuficientes — {prod.nombre}',
                    f'Faltan materias para cotización #{cot.numero or cot.id}. '
                    f'Se crearon tareas de compra y abono.',
                    url_for('tareas')
                )

def _procesar_venta_produccion(venta):
    """
    Al guardar una venta, por cada item con producto:
    1. Compara stock actual vs cantidad requerida
    2. Si falta stock → crea OrdenProduccion (vinculada a esta venta)
    3. Reserva/descuenta materias primas disponibles según BOM inmediatamente
    4. Si faltan materias, crea tareas comprar_materias + verificar_abono
    El check de duplicado es POR VENTA+PRODUCTO (no global), así cada venta
    genera sus propias órdenes y las ventas posteriores no se bloquean.
    """
    try:
        admins = User.query.filter_by(rol='admin', activo=True).all()
        primer_admin_id = admins[0].id if admins else current_user.id
        from datetime import timedelta

        for item in venta.items:
            if not item.producto_id:
                continue
            prod = db.session.get(Producto, item.producto_id)
            if not prod:
                continue
            cant_requerida = item.cantidad
            cant_en_stock  = min(prod.stock or 0, cant_requerida)
            cant_producir  = max(0.0, cant_requerida - cant_en_stock)

            if cant_producir <= 0:
                continue  # stock suficiente, sin producción necesaria

            # Check duplicado POR VENTA+PRODUCTO (no bloquea otras ventas del mismo producto)
            existente = OrdenProduccion.query.filter(
                OrdenProduccion.venta_id == venta.id,
                OrdenProduccion.producto_id == prod.id,
                OrdenProduccion.estado != 'completado'
            ).first()
            if existente:
                continue

            orden = OrdenProduccion(
                venta_id=venta.id,
                producto_id=prod.id,
                cantidad_total=cant_requerida,
                cantidad_stock=cant_en_stock,
                cantidad_producir=cant_producir,
                estado='en_produccion',
                notas=f'Venta: {venta.titulo} — {prod.nombre} x{cant_requerida}',
                creado_por=current_user.id
            )
            db.session.add(orden)
            db.session.flush()  # obtener orden.id para vincular reservas

            # Descontar/reservar materias primas del BOM inmediatamente
            receta = RecetaProducto.query.filter_by(producto_id=prod.id, activo=True).first()
            materias_faltantes = []
            if receta and receta.unidades_produce > 0:
                factor = cant_producir / receta.unidades_produce
                for ri in receta.items:
                    mp = db.session.get(MateriaPrima, ri.materia_prima_id)
                    if not mp: continue
                    necesaria  = ri.cantidad_por_unidad * factor
                    disponible = mp.stock_disponible or 0
                    if disponible >= necesaria:
                        # Disponible: reservar completamente
                        mp.stock_disponible -= necesaria
                        mp.stock_reservado   = (mp.stock_reservado or 0) + necesaria
                        db.session.add(ReservaProduccion(
                            materia_prima_id=mp.id, cantidad=necesaria,
                            producto_id=prod.id, venta_id=venta.id,
                            orden_produccion_id=orden.id, estado='reservado',
                            notas=f'Auto-reserva venta: {venta.titulo}',
                            creado_por=current_user.id
                        ))
                    else:
                        # Insuficiente: reservar lo que haya + anotar faltante
                        faltante = necesaria - disponible
                        materias_faltantes.append(
                            f'{mp.nombre}: falta {faltante:.3f} {mp.unidad} (disp. {disponible:.3f})'
                        )
                        if disponible > 0:
                            mp.stock_disponible = 0
                            mp.stock_reservado   = (mp.stock_reservado or 0) + disponible
                            db.session.add(ReservaProduccion(
                                materia_prima_id=mp.id, cantidad=disponible,
                                producto_id=prod.id, venta_id=venta.id,
                                orden_produccion_id=orden.id, estado='reservado',
                                notas=f'Parcial venta: {venta.titulo}',
                                creado_por=current_user.id
                            ))

            if materias_faltantes:
                desc_falta = '\n'.join(materias_faltantes)
                desc_t = (f'Venta: {venta.titulo}\n'
                          f'Producto: {prod.nombre} (x{cant_producir:.2f})\n\n'
                          f'Materiales faltantes:\n{desc_falta}')
                venc = (datetime.utcnow() + timedelta(days=3)).date()
                t_compra = Tarea(
                    titulo=f'Comprar materiales — {prod.nombre} (venta)',
                    descripcion=desc_t, estado='pendiente', prioridad='alta',
                    asignado_a=primer_admin_id, creado_por=current_user.id,
                    fecha_vencimiento=venc, tarea_tipo='comprar_materias'
                )
                db.session.add(t_compra); db.session.flush()
                t_abono = Tarea(
                    titulo=f'Verificar abono — compra {prod.nombre}',
                    descripcion=f'Confirmar anticipo antes de comprar materiales para {prod.nombre}.\n\n{desc_falta}',
                    estado='pendiente', prioridad='alta',
                    asignado_a=primer_admin_id, creado_por=current_user.id,
                    fecha_vencimiento=venc, tarea_tipo='verificar_abono',
                    tarea_pareja_id=t_compra.id
                )
                db.session.add(t_abono); db.session.flush()
                t_compra.tarea_pareja_id = t_abono.id
                orden.estado = 'pendiente_materiales'
                for adm in admins:
                    _crear_notificacion(
                        adm.id, 'alerta_stock',
                        f'⚠️ Materiales insuficientes — {prod.nombre}',
                        f'Venta "{venta.titulo}" requiere producción. Faltan materias.',
                        url_for('tareas')
                    )
    except Exception as ex:
        db.session.rollback()
        print(f'_procesar_venta_produccion error: {ex}')

def _modulos_user(user):
    if not user or not user.is_authenticated: return []
    if user.rol == 'admin': return _MODULOS_TODOS
    try:
        custom = json.loads(user.modulos_permitidos or '[]')
        if custom: return custom
    except: pass
    return _MODULOS_ROL.get(user.rol, ['tareas','notas'])

def register_app_hooks(app):
    """Register template filters and context processors on the Flask app."""
    app.template_filter('cop')(cop)
    app.template_filter('moneda')(moneda)
    app.template_filter('moneda0')(moneda0)
    app.context_processor(inject_globals)