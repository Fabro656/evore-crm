# routes/ai.py — AI Chat assistant endpoint with enhanced context and query/update actions
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

    @app.route('/api/ai/chat', methods=['POST'])
    @login_required
    def ai_chat():
        """Main AI chat endpoint. Tries OpenAI first, then Anthropic, then Ollama."""
        data = request.get_json(silent=True) or {}
        user_message = (data.get('message') or '').strip()
        history      = data.get('history', [])
        context_page = data.get('context', '')

        if not user_message:
            return jsonify({'error': 'Mensaje vacío'}), 400

        # ── Build enriched system prompt ──────────────────────────────────────
        empresa = ConfigEmpresa.query.first()
        empresa_nombre = empresa.nombre if empresa else 'la empresa'

        try:
            n_clientes    = Cliente.query.filter_by(activo=True).count()
            n_ventas_act  = Venta.query.filter(Venta.estado.in_(
                ['prospecto','negociacion','anticipo_pagado'])).count()
            n_tareas_pend = Tarea.query.filter(
                Tarea.estado.notin_(['completada','cancelada'])).filter(
                Tarea.asignados.any(TareaAsignado.usuario_id == current_user.id)
            ).count()
            n_gastos_mes  = GastoOperativo.query.filter(
                db.func.date_trunc('month', GastoOperativo.fecha) ==
                db.func.date_trunc('month', datetime.utcnow())
            ).count()
        except Exception:
            n_clientes = n_ventas_act = n_tareas_pend = n_gastos_mes = '?'

        # BLOQUE 8: Contexto ampliado con datos reales
        # ────────────────────────────────────────────
        try:
            # Ventas recientes (últimas 10)
            ventas_recientes = Venta.query.order_by(Venta.creado_en.desc()).limit(10).all()
            ventas_str = '\n'.join([
                f'  - Venta {v.numero or v.id}: {v.titulo[:50]}, estado={v.estado}, total=${v.total:,.0f}'
                for v in ventas_recientes
            ]) or 'Ninguna'

            # Stock bajo mínimo
            stock_bajo = Producto.query.filter(
                Producto.activo==True,
                Producto.stock <= Producto.stock_minimo
            ).all()
            stock_str = ', '.join([f'{p.nombre}(stock:{p.stock})' for p in stock_bajo[:5]]) or 'ninguno'

            # Tareas urgentes del usuario
            tareas_urgentes = Tarea.query.filter(
                Tarea.prioridad == 'alta',
                Tarea.estado == 'pendiente',
                Tarea.asignados.any(TareaAsignado.usuario_id == current_user.id)
            ).limit(5).all()
            tareas_str = '\n'.join([f'  - #{t.id}: {t.titulo}' for t in tareas_urgentes]) or 'Ninguna'

            # Órdenes de compra pendientes
            ocs_pendientes = OrdenCompra.query.filter(
                OrdenCompra.estado.in_(['borrador','enviada'])
            ).count()

            # Cotizaciones vigentes
            cots_vigentes = Cotizacion.query.filter(
                Cotizacion.estado.in_(['borrador','enviada'])
            ).count()

            # v34: Contexto de manufactura
            mp_bajo_min = MateriaPrima.query.filter(
                MateriaPrima.activo == True,
                MateriaPrima.stock_disponible <= MateriaPrima.stock_minimo
            ).all()
            mp_str = ', '.join([f'{m.nombre}(disp:{m.stock_disponible:.1f} {m.unidad})' for m in mp_bajo_min[:5]]) or 'ninguna'

            ordenes_prod = OrdenProduccion.query.filter(
                OrdenProduccion.estado.in_(['pendiente_materiales','en_produccion'])
            ).count()

            recetas_total = RecetaProducto.query.filter_by(activo=True).count()

            # Cotizaciones proveedor vigentes
            from datetime import date as _date_cls
            cots_prov_vigentes = CotizacionProveedor.query.filter(
                CotizacionProveedor.estado == 'vigente',
                CotizacionProveedor.vigencia >= _date_cls.today()
            ).count()

            # Alertas de cotización faltante (MP sin cotización vigente)
            mp_sin_cot = []
            try:
                all_mp = MateriaPrima.query.filter_by(activo=True).all()
                for mp in all_mp:
                    tiene = CotizacionProveedor.query.filter(
                        CotizacionProveedor.materia_prima_id == mp.id,
                        CotizacionProveedor.estado == 'vigente',
                        CotizacionProveedor.vigencia >= _date_cls.today()
                    ).first()
                    if not tiene:
                        mp_sin_cot.append(mp.nombre)
            except: pass
            mp_sin_cot_str = ', '.join(mp_sin_cot[:8]) if mp_sin_cot else 'todas tienen cotización'
        except Exception as e:
            logging.warning(f'AI context building error: {e}')
            ventas_str = 'Error al cargar'
            stock_str = '?'; tareas_str = '?'; mp_str = '?'; mp_sin_cot_str = '?'
            ocs_pendientes = 0; cots_vigentes = 0; ordenes_prod = 0; recetas_total = 0; cots_prov_vigentes = 0

        system_prompt = f"""Eres el asistente de IA de Evore CRM, el ERP de manufactura de {empresa_nombre}.
Ayudas al usuario {current_user.nombre} (rol: {current_user.rol}).

══ MODELO DE NEGOCIO ══
{empresa_nombre} es una empresa manufacturera colombiana (productos quimicos/limpieza).
El flujo central del negocio es:

1. RECETA: define qué materias primas (MP) se necesitan para producir un producto terminado.
   Cada ingrediente de la receta es una materia prima. Al crear un ingrediente sin stock, se agrega a MP en 0.
   Si la MP no tiene cotización vigente de proveedor → ALERTA para que Desarrollo la busque.

2. COSTO: el costo de producción se calcula automáticamente: suma de (cantidad_ingrediente × costo_MP).
   El costo de la MP viene de la cotización de proveedor vigente más barata.
   Si no hay cotización → se usa el último costo registrado → si no hay → alerta.

3. MARCAS: un producto puede tener varias marcas (mismo producto, diferente NSO/nombre comercial).
   Las marcas se registran en módulo legal con registro sanitario/INVIMA.

4. COTIZACIÓN AL CLIENTE: el precio mínimo = costo_receta + empaque + IVA.
   La cotización debe basarse en costos reales, no inventados.

5. VENTA: requiere cliente + productos. Si el cliente tiene envio_responsable='empresa', se necesita transportista.
   Estado "negociación" = NO se produce nada, NO se reserva stock.
   Solo al recibir anticipo (verificado en contabilidad) se activan:
   → Verificar stock de MP → Si falta → OC automática al proveedor con cotización vigente
   → El proveedor debe aceptar la OC desde su portal → Contabilidad paga → MP ingresa
   → Con MP completa → Producción arranca → Producto terminado entra a inventario → Entrega

6. EMPAQUE: la caja seleccionada para un producto se agrega como ingrediente de la receta.
   La remisión indica cuántas cajas y unidades por caja se despachan.

7. CONTABILIDAD: PUC colombiano (102 cuentas), partida doble, Balance General, Estado de Resultados.
   Todo gasto/compra/nómina genera asiento contable automático.

══ CONTEXTO ACTUAL ══
- Clientes activos: {n_clientes}
- Ventas en curso: {n_ventas_act}
- Órdenes producción activas: {ordenes_prod}
- Recetas activas: {recetas_total}
- Tareas pendientes (mías): {n_tareas_pend}
- Gastos este mes: {n_gastos_mes}
- OC pendientes: {ocs_pendientes}
- Cotizaciones cliente vigentes: {cots_vigentes}
- Cotizaciones proveedor vigentes: {cots_prov_vigentes}
- Módulo actual: {context_page or 'inicio'}
- Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}

══ ALERTAS ══
- Productos bajo stock mínimo: {stock_str}
- Materias primas bajo mínimo: {mp_str}
- MP sin cotización vigente: {mp_sin_cot_str}

══ DATOS RECIENTES ══
Ventas (últimas 10):
{ventas_str}

Tareas urgentes:
{tareas_str}

══ CAPACIDADES ══
Puedes crear, consultar y actualizar registros reales en el CRM.

CREAR:
{{"action":"create","type":"cliente","data":{{"nombre":"...","email":"...","telefono":"..."}}}}
{{"action":"create","type":"venta","data":{{"cliente_nombre":"...","descripcion":"...","valor_total":0}}}}
{{"action":"create","type":"orden_compra","data":{{"proveedor_nombre":"...","items":[{{"nombre":"...","cantidad":1,"precio_unit":0}}]}}}}
{{"action":"create","type":"tarea","data":{{"titulo":"...","descripcion":"...","prioridad":"media"}}}}
{{"action":"create","type":"nota","data":{{"titulo":"...","contenido":"..."}}}}
{{"action":"create","type":"evento","data":{{"titulo":"...","fecha":"YYYY-MM-DD"}}}}

CONSULTAR:
{{"action":"query","type":"ventas"}}
{{"action":"query","type":"stock_bajo"}}
{{"action":"query","type":"tareas_pendientes"}}
{{"action":"query","type":"cotizaciones"}}
{{"action":"query","type":"clientes"}}
{{"action":"query","type":"materias_primas"}}
{{"action":"query","type":"recetas"}}
{{"action":"query","type":"ordenes_produccion"}}
{{"action":"query","type":"costo_producto","filter":"<nombre_producto>"}}

ACTUALIZAR:
{{"action":"update","type":"tarea","id":123,"data":{{"estado":"completada"}}}}
{{"action":"update","type":"venta","id":456,"data":{{"estado":"anticipo_pagado"}}}}

══ REGLAS ══
- Solo CRM/ERP. Pregunta ajena → "Solo puedo ayudarte con el CRM de {empresa_nombre}."
- Confirma datos ambiguos antes de crear
- Responde en español, conciso, profesional
- Después de crear → confirma lo creado
- Si preguntan costo/precio de un producto → usa los datos de receta + cotizaciones
- Si preguntan si se puede producir X → verifica stock de MP de la receta
- Si falta cotización para una MP → informa y sugiere buscar proveedor"""

        # ── Providers ────────────────────────────────────────────────
        openai_key    = os.environ.get('OPENAI_API_KEY', '')
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        ollama_base   = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        ollama_model  = os.environ.get('OLLAMA_MODEL', 'llama3')
        ollama_enabled = os.environ.get('OLLAMA_ENABLED', '').lower() in ('1','true','yes')

        messages = []
        for h in history[-20:]:  # BLOQUE 8: aumentar contexto a 20 mensajes
            if h.get('role') in ('user', 'assistant'):
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        response_text = None
        provider_used = None

        # ── 1. OpenAI / GPT-4o (primary) ─────────────────────────────
        if openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                resp = client.chat.completions.create(
                    model='gpt-4o',
                    messages=[{'role':'system','content':system_prompt}] + messages,
                    max_tokens=1024,
                    temperature=0.7
                )
                response_text = resp.choices[0].message.content
                provider_used = 'openai'
            except Exception as e:
                logging.warning(f'OpenAI error: {e}')

        # ── 2. Anthropic / Claude (second) ────────────────────────────
        if response_text is None and anthropic_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=anthropic_key)
                resp = client.messages.create(
                    model='claude-sonnet-4-6',
                    max_tokens=1024,
                    system=system_prompt,
                    messages=messages
                )
                response_text = resp.content[0].text
                provider_used = 'claude'
            except Exception as e:
                logging.warning(f'Anthropic error: {e}')

        # ── 3. Ollama local (third) ───────────────────────────────────
        if response_text is None and ollama_enabled:
            try:
                import urllib.request
                payload = json.dumps({
                    'model': ollama_model,
                    'messages': [{'role':'system','content':system_prompt}] + messages,
                    'stream': False,
                    'options': {'num_predict': 1024}
                }).encode('utf-8')
                req = urllib.request.Request(
                    f'{ollama_base.rstrip("/")}/api/chat',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    ollama_resp = json.loads(r.read().decode('utf-8'))
                response_text = (
                    ollama_resp.get('message', {}).get('content') or
                    ollama_resp.get('response', '')
                ) or None
                if response_text:
                    provider_used = f'ollama:{ollama_model}'
            except Exception as e:
                logging.warning(f'Ollama error: {e}')

        if response_text is None:
            return jsonify({
                'error': 'No hay proveedor de IA configurado. '
                         'Agrega OPENAI_API_KEY o ANTHROPIC_API_KEY en Railway.'
            }), 503

        # ── Detect and execute action ─────────────────────────────────
        # BLOQUE 8: Detectar acciones create, query, y update
        action_match = re.search(
            r'\{[^{}]*"action"\s*:\s*("create"|"query"|"update")[^{}]*\}',
            response_text, re.DOTALL
        )
        if action_match:
            try:
                action_data = json.loads(action_match.group())
                result = _execute_ai_action(action_data)
                response_text = response_text[:action_match.start()].strip()
                if result:
                    response_text += f'\n\n{result}'
            except Exception as e:
                logging.warning(f'AI action parse error: {e}')

        return jsonify({'reply': response_text, 'provider': provider_used})


    @app.route('/api/ai/status')
    @login_required
    def ai_status():
        has_openai    = bool(os.environ.get('OPENAI_API_KEY'))
        has_anthropic = bool(os.environ.get('ANTHROPIC_API_KEY'))
        ollama_enabled = os.environ.get('OLLAMA_ENABLED','').lower() in ('1','true','yes')
        ollama_model   = os.environ.get('OLLAMA_MODEL','llama3')
        ollama_base    = os.environ.get('OLLAMA_BASE_URL','http://localhost:11434')

        ollama_online = False
        if ollama_enabled:
            try:
                import urllib.request
                with urllib.request.urlopen(
                    urllib.request.Request(f'{ollama_base.rstrip("/")}/api/tags'),
                    timeout=3
                ):
                    ollama_online = True
            except Exception:
                pass

        return jsonify({
            'openai':       has_openai,
            'anthropic':    has_anthropic,
            'ollama':       ollama_online,
            'ollama_model': ollama_model if ollama_online else None,
            'available':    has_openai or has_anthropic or ollama_online,
            'primary':      ('openai' if has_openai else
                             'claude' if has_anthropic else
                             f'ollama:{ollama_model}' if ollama_online else None)
        })


    # ══════════════════════════════════════════════════════════════════════════
    # BLOQUE 8 — Ruta de datos para que el frontend solicite datos contextuales
    # ══════════════════════════════════════════════════════════════════════════

    @app.route('/api/ai/data/<entity>')
    @login_required
    def ai_data(entity):
        """Endpoint para que el frontend solicite datos contextuales enriquecidos."""
        try:
            if entity == 'ventas':
                ventas = Venta.query.filter(
                    Venta.estado.notin_(['cancelado','perdido'])
                ).order_by(Venta.creado_en.desc()).limit(20).all()
                return jsonify([{
                    'id': v.id,
                    'numero': v.numero,
                    'titulo': v.titulo,
                    'estado': v.estado,
                    'total': v.total
                } for v in ventas])

            elif entity == 'tareas':
                tareas = Tarea.query.filter(
                    Tarea.estado=='pendiente'
                ).limit(30).all()
                return jsonify([{
                    'id': t.id,
                    'titulo': t.titulo,
                    'prioridad': t.prioridad,
                    'estado': t.estado
                } for t in tareas])

            elif entity == 'inventario':
                prods = Producto.query.filter_by(activo=True).all()
                return jsonify([{
                    'id': p.id,
                    'nombre': p.nombre,
                    'stock': p.stock,
                    'stock_minimo': p.stock_minimo,
                    'bajo_minimo': p.stock <= p.stock_minimo
                } for p in prods])

            elif entity == 'cotizaciones':
                cots = Cotizacion.query.filter(
                    Cotizacion.estado.in_(['borrador','enviada','vencida'])
                ).order_by(Cotizacion.creado_en.desc()).limit(15).all()
                return jsonify([{
                    'id': c.id,
                    'numero': c.numero,
                    'titulo': c.titulo,
                    'estado': c.estado,
                    'total': c.total
                } for c in cots])

            elif entity == 'clientes':
                clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).limit(50).all()
                return jsonify([{
                    'id': c.id,
                    'nombre': c.nombre,
                    'email': c.email
                } for c in clientes])

            else:
                return jsonify({'error': 'Entidad no reconocida'}), 400

        except Exception as e:
            logging.warning(f'ai_data error: {e}')
            return jsonify({'error': str(e)}), 500


def _execute_ai_action(action_data):
    """Execute a CRM action generated by the AI (create, query, update)."""
    from flask_login import current_user
    try:
        aaction = action_data.get('action', '')
        atype = action_data.get('type', '')
        adata = action_data.get('data', {})

        # ══════════════════════════════════════════════════════════════════════════
        # BLOQUE 8 — Acciones de CONSULTA (query)
        # ══════════════════════════════════════════════════════════════════════════

        if aaction == 'query':
            qtype = action_data.get('type', '')
            qfilter = action_data.get('filter', '')

            if qtype == 'ventas':
                ventas = Venta.query.filter(
                    Venta.estado.notin_(['cancelado','perdido','completado'])
                ).order_by(Venta.creado_en.desc()).limit(20).all()
                result = f'Ventas activas ({len(ventas)}):\n'
                for v in ventas:
                    result += f'  • {v.numero or v.id}: {v.titulo[:40]}, {v.estado}, ${v.total:,.0f}\n'
                return result

            elif qtype == 'stock_bajo':
                prods = Producto.query.filter(
                    Producto.activo==True,
                    Producto.stock <= Producto.stock_minimo
                ).all()
                if not prods:
                    return 'No hay productos con stock bajo en este momento.'
                result = f'Productos con stock bajo ({len(prods)}):\n'
                for p in prods:
                    result += f'  • {p.nombre}: stock={p.stock}, mínimo={p.stock_minimo}\n'
                return result

            elif qtype == 'tareas_pendientes':
                tareas = Tarea.query.filter(
                    Tarea.estado == 'pendiente',
                    Tarea.asignados.any(TareaAsignado.usuario_id == current_user.id)
                ).order_by(Tarea.prioridad.desc()).limit(15).all()
                result = f'Tareas pendientes ({len(tareas)}):\n'
                for t in tareas:
                    result += f'  • #{t.id} [{t.prioridad}]: {t.titulo}\n'
                return result

            elif qtype == 'cotizaciones':
                cots = Cotizacion.query.filter(
                    Cotizacion.estado.in_(['borrador','enviada','vencida'])
                ).order_by(Cotizacion.creado_en.desc()).limit(15).all()
                result = f'Cotizaciones ({len(cots)}):\n'
                for c in cots:
                    estado_str = '⚠️ VENCIDA' if c.estado == 'vencida' else c.estado
                    result += f'  • {c.numero or c.id}: {c.titulo[:40]}, {estado_str}, ${c.total:,.0f}\n'
                return result

            elif qtype == 'clientes':
                clientes = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
                result = f'Clientes activos ({len(clientes)}):\n'
                for cli in clientes[:20]:
                    envio = getattr(cli, 'envio_responsable', 'cliente')
                    result += f'  • {cli.empresa or cli.nombre} (NIT:{cli.nit or "—"}) envío:{envio}\n'
                return result

            elif qtype == 'materias_primas':
                mps = MateriaPrima.query.filter_by(activo=True).order_by(MateriaPrima.nombre).all()
                result = f'Materias primas ({len(mps)}):\n'
                for m in mps:
                    alerta = ' ⚠️ BAJO' if (m.stock_disponible or 0) <= (m.stock_minimo or 0) else ''
                    result += f'  • {m.nombre}: disp={m.stock_disponible:.1f} {m.unidad}, min={m.stock_minimo}, costo=${m.costo_unitario:,.0f}/{m.unidad}{alerta}\n'
                return result

            elif qtype == 'recetas':
                from utils import _calcular_costo_receta
                recetas = RecetaProducto.query.filter_by(activo=True).all()
                result = f'Recetas activas ({len(recetas)}):\n'
                for r in recetas:
                    prod = r.producto
                    costo = _calcular_costo_receta(r.producto_id)
                    n_alertas = len(costo['alertas'])
                    result += f'  • {prod.nombre if prod else "?"}: {r.unidades_produce} und/lote, costo=${costo["costo_unitario"]:,.0f}/und'
                    if n_alertas: result += f' ({n_alertas} alertas)'
                    result += '\n'
                    for d in costo['desglose']:
                        result += f'    - {d["materia"]}: {d["cantidad"]:.2f} {d["unidad"]} × ${d["costo_unit"]:,.0f} = ${d["subtotal"]:,.0f}'
                        if not d['tiene_cotizacion']: result += ' ⚠️ sin cotización'
                        result += '\n'
                return result

            elif qtype == 'ordenes_produccion':
                ops = OrdenProduccion.query.filter(
                    OrdenProduccion.estado.in_(['pendiente_materiales','en_produccion','pausada'])
                ).order_by(OrdenProduccion.creado_en.desc()).limit(20).all()
                result = f'Órdenes de producción activas ({len(ops)}):\n'
                for o in ops:
                    v_num = o.venta.numero if o.venta else 'sin venta'
                    result += f'  • OP#{o.id}: {o.producto.nombre if o.producto else "?"} ×{o.cantidad_producir:.0f}, estado={o.estado}, venta={v_num}\n'
                return result

            elif qtype == 'costo_producto':
                from utils import _calcular_costo_receta, _precio_minimo_venta
                prod = Producto.query.filter(Producto.nombre.ilike(f'%{qfilter}%')).first() if qfilter else None
                if not prod:
                    return f'No encontré producto con nombre "{qfilter}". Intenta con otro nombre.'
                costo = _calcular_costo_receta(prod.id)
                precio = _precio_minimo_venta(prod.id, 1)
                result = f'Análisis de costo — {prod.nombre} (SKU:{prod.sku or "—"}):\n'
                result += f'  Costo producción: ${costo["costo_unitario"]:,.0f}/und\n'
                result += f'  Precio venta actual: ${prod.precio:,.0f}\n'
                result += f'  Precio mínimo (costo+IVA): ${precio["precio_minimo"]:,.0f}\n'
                result += f'  Precio sugerido (+30% margen): ${precio["precio_sugerido"]:,.0f}\n'
                result += f'  Margen actual: {((prod.precio - costo["costo_unitario"]) / prod.precio * 100):.1f}%\n' if prod.precio > 0 else ''
                if costo['alertas']:
                    result += f'  Alertas:\n'
                    for a in costo['alertas']:
                        result += f'    ⚠️ {a}\n'
                result += f'  Desglose:\n'
                for d in costo['desglose']:
                    result += f'    {d["materia"]}: {d["cantidad"]:.2f} {d["unidad"]} × ${d["costo_unit"]:,.0f} = ${d["subtotal"]:,.0f}\n'
                return result

            return 'Consulta no reconocida. Tipos válidos: ventas, stock_bajo, tareas_pendientes, cotizaciones, clientes, materias_primas, recetas, ordenes_produccion, costo_producto'

        # ══════════════════════════════════════════════════════════════════════════
        # Acciones de ACTUALIZACIÓN (update)
        # ══════════════════════════════════════════════════════════════════════════

        elif aaction == 'update':
            utype = action_data.get('type', '')
            uid = action_data.get('id')
            udata = action_data.get('data', {})

            if utype == 'tarea' and uid:
                t = Tarea.query.get(uid)
                if t:
                    # Verificar permisos: solo asignados, creador, o admin
                    asignado_ids = [a.user_id for a in TareaAsignado.query.filter_by(tarea_id=t.id).all()]
                    if current_user.id not in asignado_ids and t.creado_por != current_user.id and current_user.rol != 'admin':
                        return 'No tienes permisos para modificar esta tarea.'
                    if 'estado' in udata and udata['estado'] in ('pendiente','en_progreso','completada','cancelada'):
                        t.estado = udata['estado']
                        db.session.commit()
                        return f'Tarea #{uid} actualizada a estado: {udata["estado"]}'
                return f'Tarea #{uid} no encontrada.'

            elif utype == 'venta' and uid:
                if current_user.rol not in ('admin', 'vendedor', 'sales_manager'):
                    return 'No tienes permisos para modificar ventas.'
                v = Venta.query.get(uid)
                if v:
                    estados_permitidos = ['prospecto','negociacion','anticipo_pagado','pagado','cancelado']
                    if 'estado' in udata and udata['estado'] in estados_permitidos:
                        v.estado = udata['estado']
                        db.session.commit()
                        return f'Venta {v.numero or uid} actualizada a estado: {udata["estado"]}'
                return f'Venta #{uid} no encontrada.'

            return 'Actualización no reconocida.'

        # ══════════════════════════════════════════════════════════════════════════
        # Acciones de CREACIÓN (create) — código original
        # ══════════════════════════════════════════════════════════════════════════

        elif aaction == 'create':
            # Verificar permisos por tipo de entidad
            _permisos_crear = {
                'cliente': ('admin', 'vendedor', 'sales_manager'),
                'venta': ('admin', 'vendedor', 'sales_manager'),
                'orden_compra': ('admin', 'produccion', 'sales_manager'),
                'tarea': ('admin', 'vendedor', 'produccion', 'contador', 'sales_manager', 'usuario'),
                'nota': ('admin', 'vendedor', 'produccion', 'contador', 'sales_manager', 'usuario'),
                'evento': ('admin', 'vendedor', 'produccion', 'contador', 'sales_manager', 'usuario'),
            }
            roles_permitidos = _permisos_crear.get(atype, ('admin',))
            if current_user.rol not in roles_permitidos:
                return f'No tienes permisos para crear {atype}. Se requiere rol: {", ".join(roles_permitidos)}'

            # ── Cliente ───────────────────────────────────────────────────
            if atype == 'cliente':
                c = Cliente(
                    nombre=adata.get('nombre', 'Cliente desde IA'),
                    email=adata.get('email', ''),
                    telefono=adata.get('telefono', ''),
                    ciudad=adata.get('ciudad', ''),
                    activo=True,
                    creado_en=datetime.utcnow()
                )
                db.session.add(c)
                db.session.commit()
                return f'✅ Cliente creado: "{c.nombre}" (ID {c.id})'

            # ── Venta ─────────────────────────────────────────────────────
            elif atype == 'venta':
                # Try to find client by name
                cliente_id = None
                cliente_nombre = adata.get('cliente_nombre', '')
                if cliente_nombre:
                    cliente = Cliente.query.filter(
                        Cliente.nombre.ilike(f'%{cliente_nombre}%')
                    ).first()
                    if cliente:
                        cliente_id = cliente.id

                # Generate venta number
                n = Venta.query.count() + 1
                numero = f'VNT-{n:04d}'

                v = Venta(
                    numero=numero,
                    cliente_id=cliente_id,
                    descripcion=adata.get('descripcion', 'Venta creada desde IA'),
                    valor_total=float(adata.get('valor_total', 0)),
                    estado=adata.get('estado', 'prospecto'),
                    creado_por=current_user.id,
                    creado_en=datetime.utcnow()
                )
                db.session.add(v)
                db.session.commit()
                cliente_str = f' para {cliente_nombre}' if cliente_nombre else ''
                return f'✅ Venta {numero} creada{cliente_str} — estado: {v.estado}'

            # ── Orden de Compra ───────────────────────────────────────────
            elif atype == 'orden_compra':
                # Try to find supplier
                proveedor_id = None
                prov_nombre = adata.get('proveedor_nombre', '')
                if prov_nombre:
                    prov = Proveedor.query.filter(
                        Proveedor.nombre.ilike(f'%{prov_nombre}%')
                    ).first()
                    if prov:
                        proveedor_id = prov.id

                n = OrdenCompra.query.count() + 1
                numero = f'OC-{n:04d}'

                oc = OrdenCompra(
                    numero=numero,
                    proveedor_id=proveedor_id,
                    descripcion=adata.get('descripcion', 'OC creada desde IA'),
                    estado='borrador',
                    creado_por=current_user.id,
                    creado_en=datetime.utcnow(),
                    fecha_emision=datetime.utcnow().date()
                )
                db.session.add(oc)
                db.session.flush()

                # Add items if provided
                items_data = adata.get('items', [])
                total = 0
                for item in items_data:
                    cant   = float(item.get('cantidad', 1))
                    precio = float(item.get('precio_unit', 0))
                    sub    = cant * precio
                    total += sub
                    db.session.add(OrdenCompraItem(
                        orden_id=oc.id,
                        nombre_item=item.get('nombre', 'Ítem'),
                        descripcion=item.get('descripcion', ''),
                        cantidad=cant,
                        unidad=item.get('unidad', 'unidades'),
                        precio_unit=precio,
                        subtotal=sub
                    ))

                oc.total = total
                db.session.commit()
                prov_str = f' a {prov_nombre}' if prov_nombre else ''
                return f'✅ Orden de compra {numero} creada{prov_str} ({len(items_data)} ítems)'

            # ── Tarea ─────────────────────────────────────────────────────
            elif atype == 'tarea':
                t = Tarea(
                    titulo=adata.get('titulo', 'Tarea desde IA'),
                    descripcion=adata.get('descripcion', ''),
                    prioridad=adata.get('prioridad', 'media'),
                    estado='pendiente',
                    creado_por=current_user.id,
                    creado_en=datetime.utcnow()
                )
                if adata.get('fecha_limite'):
                    try:
                        t.fecha_limite = datetime.strptime(
                            adata['fecha_limite'], '%Y-%m-%d').date()
                    except Exception:
                        pass
                db.session.add(t)
                db.session.flush()
                db.session.add(TareaAsignado(
                    tarea_id=t.id, usuario_id=current_user.id))
                db.session.commit()
                return f'✅ Tarea creada: "{t.titulo}"'

            # ── Nota ──────────────────────────────────────────────────────
            elif atype == 'nota':
                n = Nota(
                    titulo=adata.get('titulo', 'Nota desde IA'),
                    contenido=adata.get('contenido', ''),
                    autor_id=current_user.id,
                    creado_en=datetime.utcnow()
                )
                db.session.add(n)
                db.session.commit()
                return f'✅ Nota creada: "{n.titulo}"'

            # ── Evento ────────────────────────────────────────────────────
            elif atype == 'evento':
                e = Evento(
                    titulo=adata.get('titulo', 'Evento desde IA'),
                    descripcion=adata.get('descripcion', ''),
                    tipo=adata.get('tipo', 'evento'),
                    fecha=datetime.strptime(
                        adata.get('fecha', datetime.now().strftime('%Y-%m-%d')),
                        '%Y-%m-%d'
                    ).date(),
                    creado_por=current_user.id
                )
                db.session.add(e)
                db.session.commit()
                return f'✅ Evento creado: "{e.titulo}" para el {e.fecha}'

    except Exception as ex:
        db.session.rollback()
        logging.warning(f'AI action execute error: {ex}')
        return None
