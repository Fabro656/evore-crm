# routes/ai.py — AI Chat assistant endpoint
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

        # ── Build system prompt ───────────────────────────────────────
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

        system_prompt = f"""Eres el asistente de IA integrado en Evore CRM, el sistema de gestión de {empresa_nombre}.
Ayudas al usuario {current_user.nombre} (rol: {current_user.rol}) con sus tareas diarias.

CONTEXTO ACTUAL:
- Clientes activos: {n_clientes}
- Ventas en curso: {n_ventas_act}
- Mis tareas pendientes: {n_tareas_pend}
- Gastos este mes: {n_gastos_mes}
- Módulo actual: {context_page or 'inicio'}
- Fecha/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}

CAPACIDADES — puedes crear registros reales en el CRM.
Cuando el usuario pida crear algo, responde con un JSON de acción:

Para CLIENTE:
{{"action":"create","type":"cliente","data":{{"nombre":"...","email":"...","telefono":"...","ciudad":"..."}}}}

Para VENTA:
{{"action":"create","type":"venta","data":{{"cliente_nombre":"...","descripcion":"...","valor_total":0,"estado":"prospecto"}}}}

Para ORDEN DE COMPRA:
{{"action":"create","type":"orden_compra","data":{{"proveedor_nombre":"...","descripcion":"...","items":[{{"nombre":"...","cantidad":1,"precio_unit":0}}]}}}}

Para TAREA:
{{"action":"create","type":"tarea","data":{{"titulo":"...","descripcion":"...","prioridad":"media","fecha_limite":"YYYY-MM-DD"}}}}

Para NOTA:
{{"action":"create","type":"nota","data":{{"titulo":"...","contenido":"..."}}}}

Para EVENTO:
{{"action":"create","type":"evento","data":{{"titulo":"...","descripcion":"...","tipo":"evento","fecha":"YYYY-MM-DD"}}}}

REGLAS:
- Confirma datos con el usuario antes de crear si hay ambigüedad
- Si falta el cliente para una venta, pregunta su nombre
- Responde siempre en español, sé conciso y profesional
- Después de crear un registro, confirma con ✅ lo que se creó

MÓDULOS: clientes, ventas, cotizaciones, tareas, calendario, notas,
inventario, producción, gastos, reportes, proveedores, nómina, finanzas, legal."""

        # ── Providers ────────────────────────────────────────────────
        openai_key    = os.environ.get('OPENAI_API_KEY', '')
        anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
        ollama_base   = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        ollama_model  = os.environ.get('OLLAMA_MODEL', 'llama3')
        ollama_enabled = os.environ.get('OLLAMA_ENABLED', '').lower() in ('1','true','yes')

        messages = []
        for h in history[-10:]:
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
        action_match = re.search(
            r'\{[^{}]*"action"\s*:\s*"create"[^{}]*\}',
            response_text, re.DOTALL
        )
        if action_match:
            try:
                action_data = json.loads(action_match.group())
                result = _execute_ai_action(action_data)
                response_text = response_text[:action_match.start()].strip()
                if result:
                    response_text += f'\n\n✅ {result}'
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


def _execute_ai_action(action_data):
    """Execute a CRM action generated by the AI."""
    from flask_login import current_user
    try:
        atype = action_data.get('type', '')
        adata = action_data.get('data', {})

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
            return f'Cliente creado: "{c.nombre}" (ID {c.id})'

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
            return f'Venta {numero} creada{cliente_str} — estado: {v.estado}'

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
            return f'Orden de compra {numero} creada{prov_str} ({len(items_data)} ítems)'

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
            return f'Tarea creada: "{t.titulo}"'

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
            return f'Nota creada: "{n.titulo}"'

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
            return f'Evento creado: "{e.titulo}" para el {e.fecha}'

    except Exception as ex:
        db.session.rollback()
        logging.warning(f'AI action execute error: {ex}')
        return None
