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
        """Main AI chat endpoint. Tries Anthropic first, then Ollama, then OpenAI."""
        data = request.get_json(silent=True) or {}
        user_message = (data.get('message') or '').strip()
        history      = data.get('history', [])   # [{role, content}, ...]
        context_page = data.get('context', '')    # current page/module

        if not user_message:
            return jsonify({'error': 'Mensaje vacío'}), 400

        # ── Build system prompt ───────────────────────────────────────
        empresa = ConfigEmpresa.query.first()
        empresa_nombre = empresa.nombre if empresa else 'la empresa'

        # Gather live CRM context
        try:
            n_clientes   = Cliente.query.filter_by(activo=True).count()
            n_ventas_act = Venta.query.filter(Venta.estado.in_(
                ['prospecto','negociacion','anticipo_pagado'])).count()
            n_tareas_pend = Tarea.query.filter(
                Tarea.estado.notin_(['completada','cancelada'])).filter(
                Tarea.asignados.any(TareaAsignado.usuario_id == current_user.id)
            ).count()
            n_gastos_mes = GastoOperativo.query.filter(
                db.func.date_trunc('month', GastoOperativo.fecha) ==
                db.func.date_trunc('month', datetime.utcnow())
            ).count()
        except Exception:
            n_clientes = n_ventas_act = n_tareas_pend = n_gastos_mes = '?'

        system_prompt = f"""Eres el asistente de IA integrado en Evore CRM, el sistema de gestión de {empresa_nombre}.
Ayudas al usuario {current_user.nombre} (rol: {current_user.rol}) con sus tareas diarias en el CRM.

CONTEXTO ACTUAL DEL CRM:
- Clientes activos: {n_clientes}
- Ventas en curso: {n_ventas_act}
- Mis tareas pendientes: {n_tareas_pend}
- Gastos registrados este mes: {n_gastos_mes}
- Módulo actual: {context_page or 'inicio'}
- Fecha/hora: {datetime.now().strftime('%d/%m/%Y %H:%M')}

CAPACIDADES:
1. Responder preguntas sobre el CRM y sus datos
2. Redactar correos, mensajes y comunicaciones para clientes
3. Resumir actividad, ventas, estados de proyectos
4. Ayudar a crear registros (tareas, notas, eventos) — cuando el usuario lo pida,
   responde con un JSON especial: {{"action":"create","type":"tarea|nota|evento","data":{{...}}}}

MÓDULOS DISPONIBLES: clientes, ventas, cotizaciones, tareas, calendario, notas,
inventario, producción, gastos, reportes, proveedores, nómina, finanzas, legal.

Sé conciso, útil y profesional. Responde siempre en español.
Si el usuario pide crear algo, confirma los datos antes de ejecutar."""

        # ── Read provider config from env ─────────────────────────────
        anthropic_key  = os.environ.get('ANTHROPIC_API_KEY', '')
        openai_key     = os.environ.get('OPENAI_API_KEY', '')
        ollama_base    = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
        ollama_model   = os.environ.get('OLLAMA_MODEL', 'llama3')
        ollama_enabled = os.environ.get('OLLAMA_ENABLED', '').lower() in ('1', 'true', 'yes')

        messages = []
        for h in history[-10:]:   # last 10 turns for context
            if h.get('role') in ('user', 'assistant'):
                messages.append({'role': h['role'], 'content': h['content']})
        messages.append({'role': 'user', 'content': user_message})

        response_text = None
        provider_used = None

        # ── 1. Anthropic / Claude (primary) ───────────────────────────
        if anthropic_key:
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
                logging.warning(f'Anthropic AI error: {e}')

        # ── 2. Ollama local LLM (second option) ───────────────────────
        if response_text is None and ollama_enabled:
            try:
                import urllib.request
                ollama_messages = [{'role': 'system', 'content': system_prompt}] + messages
                payload = json.dumps({
                    'model':    ollama_model,
                    'messages': ollama_messages,
                    'stream':   False,
                    'options':  {'num_predict': 1024}
                }).encode('utf-8')
                req = urllib.request.Request(
                    f'{ollama_base.rstrip("/")}/api/chat',
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=30) as resp_raw:
                    ollama_resp = json.loads(resp_raw.read().decode('utf-8'))
                response_text = (
                    ollama_resp.get('message', {}).get('content')
                    or ollama_resp.get('response', '')
                )
                if response_text:
                    provider_used = f'ollama:{ollama_model}'
                else:
                    response_text = None
            except Exception as e:
                logging.warning(f'Ollama AI error: {e}')

        # ── 3. OpenAI / GPT (fallback) ────────────────────────────────
        if response_text is None and openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                msgs_with_system = [{'role': 'system', 'content': system_prompt}] + messages
                resp = client.chat.completions.create(
                    model='gpt-4o',
                    messages=msgs_with_system,
                    max_tokens=1024,
                    temperature=0.7
                )
                response_text = resp.choices[0].message.content
                provider_used = 'openai'
            except Exception as e:
                logging.warning(f'OpenAI AI error: {e}')

        if response_text is None:
            return jsonify({
                'error': 'No hay un proveedor de IA configurado. '
                         'Agrega ANTHROPIC_API_KEY en Railway, o activa Ollama con OLLAMA_ENABLED=true.'
            }), 503

        # ── Check if response contains a create action ─────────────────
        action_data = None
        action_match = re.search(r'\{"action"\s*:\s*"create".*?\}', response_text, re.DOTALL)
        if action_match:
            try:
                action_data = json.loads(action_match.group())
                result = _execute_ai_action(action_data)
                response_text = response_text[:action_match.start()].strip()
                if result:
                    response_text += f'\n\n✅ {result}'
            except Exception as e:
                logging.warning(f'AI action parse error: {e}')

        return jsonify({
            'reply':    response_text,
            'provider': provider_used
        })


    @app.route('/api/ai/status')
    @login_required
    def ai_status():
        """Check which AI providers are configured and available."""
        has_anthropic = bool(os.environ.get('ANTHROPIC_API_KEY'))
        has_openai    = bool(os.environ.get('OPENAI_API_KEY'))
        ollama_enabled = os.environ.get('OLLAMA_ENABLED', '').lower() in ('1', 'true', 'yes')
        ollama_model   = os.environ.get('OLLAMA_MODEL', 'llama3')
        ollama_base    = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')

        # Check if Ollama is actually reachable
        ollama_online = False
        if ollama_enabled:
            try:
                import urllib.request
                req = urllib.request.Request(
                    f'{ollama_base.rstrip("/")}/api/tags',
                    method='GET'
                )
                with urllib.request.urlopen(req, timeout=3):
                    ollama_online = True
            except Exception:
                pass

        return jsonify({
            'anthropic':    has_anthropic,
            'openai':       has_openai,
            'ollama':       ollama_online,
            'ollama_model': ollama_model if ollama_online else None,
            'available':    has_anthropic or has_openai or ollama_online,
            'primary':      'claude' if has_anthropic else (
                            f'ollama:{ollama_model}' if ollama_online else (
                            'openai' if has_openai else None))
        })


def _execute_ai_action(action_data):
    """Execute a CRM action requested by the AI."""
    try:
        atype = action_data.get('type', '')
        adata = action_data.get('data', {})

        if atype == 'tarea':
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
                    t.fecha_limite = datetime.strptime(adata['fecha_limite'], '%Y-%m-%d').date()
                except Exception:
                    pass
            db.session.add(t)
            db.session.flush()
            db.session.add(TareaAsignado(tarea_id=t.id, usuario_id=current_user.id))
            db.session.commit()
            return f'Tarea creada: "{t.titulo}"'

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

        elif atype == 'evento':
            e = Evento(
                titulo=adata.get('titulo', 'Evento desde IA'),
                descripcion=adata.get('descripcion', ''),
                tipo=adata.get('tipo', 'evento'),
                fecha=datetime.strptime(
                    adata.get('fecha', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d'
                ).date(),
                creado_por=current_user.id
            )
            db.session.add(e)
            db.session.commit()
            return f'Evento creado: "{e.titulo}"'

    except Exception as ex:
        db.session.rollback()
        logging.warning(f'AI action execute error: {ex}')
        return None
