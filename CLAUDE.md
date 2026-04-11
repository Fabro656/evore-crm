# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Evore CRM is a Flask-based ERP/CRM system for small manufacturing companies, with particular focus on production workflows, inventory management, and Colombian payroll compliance. Server-side rendered with Jinja2 — no frontend framework.

## Commands

```bash
# Run locally (development)
python app.py
# or
flask run

# Production (Railway.app)
gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 60 app:app

# Install dependencies
pip install -r requirements.txt
```

There is no test suite, linter, or build step configured.

## Architecture

**Entry point**: `app.py` — Flask app factory (`create_app()`), Gunicorn imports `app` directly.

**Core files**:
- `extensions.py` — Singleton instances: `db` (SQLAlchemy), `login_manager`, `mail`
- `models.py` — All SQLAlchemy models (~30+). `init_db()` handles table creation and migrations at startup
- `utils.py` — Decorators, template filters, payroll constants, shared business logic helpers

**Route registration pattern**: Each module in `routes/` exposes a `register(app)` function. All are wired in `routes/__init__.py:register_all(app)`. To add a new module: create `routes/new_module.py` with `def register(app):`, then add it to `register_all`.

**Service layer**: `services/inventario.py` (stock operations) and `services/nomina.py` (payroll calculations) extract complex business logic out of routes.

**Templates**: Jinja2 in `templates/`, organized by module (e.g., `templates/ventas/`, `templates/produccion/`). Base layout in `templates/base.html`.

## Key Patterns

**Authorization**: `@login_required` + custom `@requiere_modulo('modulo_name')` decorator. Role-module mapping is in `utils._MODULOS_ROL` (roles: admin, tester, vendedor, produccion, contador, usuario, sales_manager, cliente, proveedor).

**Database**: PostgreSQL in production (Railway), SQLite fallback for local dev. Connection string from `DATABASE_URL` env var. `postgres://` is auto-corrected to `postgresql://`.

**Currency formatting**: Use template filters `cop()`, `moneda()`, `moneda0()` registered in `utils.register_app_hooks`.

**DB sessions**: Auto-rollback on 500 errors and unhandled exceptions (in `app.py` error handlers + teardown). Always use `db.session.commit()` after writes.

**AI integration** (`routes/ai.py`): Tries OpenAI first, falls back to Anthropic, then Ollama. System prompt is enriched with live DB stats.

## Domain Context

- All UI text, comments, and variable names are in **Spanish**
- Payroll constants in `utils.py` follow **Colombian labor law** (SMLMV 2025, ARL, cesantias, etc.)
- Sale lifecycle: prospecto → negociacion → anticipo_pagado → pagado → entregado → completado
- Production orders manage material reservations with FIFO + expiry-based lot tracking
- Deployed on **Railway.app** — see `Procfile` and `railway.toml`
