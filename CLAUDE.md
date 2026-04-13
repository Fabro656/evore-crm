# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Evore CRM is a Flask-based ERP/CRM system for small manufacturing companies that produce for third parties. 36,800+ LOC across 245 routes, 50 models, 119 templates. Covers sales, production, inventory, purchasing, accounting (Colombian PUC), payroll, legal documents, logistics, and client/supplier portals. Server-side rendered with Jinja2 — no frontend framework.

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
- `models.py` — 50 SQLAlchemy models (2,254 LOC). `init_db()` handles table creation and migrations at startup. **CRITICAL**: `__all__` must include ALL model classes or `from models import *` will miss them.
- `utils.py` — Decorators, template filters, payroll constants, `generar_csv_response()`, shared business logic helpers (1,493 LOC)
- `company_config.py` — Multi-company config (Colombia/Mexico). Payroll params, tax rates, chart of accounts.

**Route registration pattern**: Each module in `routes/` exposes a `register(app)` function. All are wired in `routes/__init__.py:register_all(app)`. 20 route modules, 245 endpoints total.

**Service layer**: `services/inventario.py` (stock FIFO, reservations, lots) and `services/nomina.py` (payroll calculations with Art. 383 ET retention).

**Templates**: Jinja2 in `templates/`, organized by module. 119 HTML files across 24 folders. Base layouts: `templates/base.html` (admin, 1,600+ LOC), `templates/portal_base.html` (portals).

## Key Patterns

**Authorization**: `@login_required` + custom `@requiere_modulo('modulo_name')` decorator. Role-module mapping is in `utils._MODULOS_ROL`. 10 roles: admin, tester, director_financiero, director_operativo, vendedor, sales_manager, produccion, contador, cliente, proveedor.

**Database**: PostgreSQL in production (Railway), SQLite fallback for local dev. Connection string from `DATABASE_URL` env var. `postgres://` is auto-corrected to `postgresql://`. Migrations in `_migrate()` use both `IF NOT EXISTS` (PostgreSQL) and without (SQLite fallback).

**Currency formatting**: Use template filters `cop()`, `moneda()`, `moneda0()` registered in `utils.register_app_hooks`.

**CSV Export**: Use `generar_csv_response(rows, headers, filename)` from utils.py.

**DB sessions**: Auto-rollback on 500 errors and unhandled exceptions. Always use `db.session.commit()` after writes. For payment operations, use `with_for_update=True` to prevent race conditions.

**Asiento auto-creation**: `_crear_asiento_auto()` in utils.py creates AsientoContable + LineaAsiento with PUC lookup. Used when creating ventas and OC.

**AI integration** (`routes/ai.py`): Tries OpenAI first, falls back to Anthropic, then Ollama. System prompt is enriched with live DB stats.

## Critical Flows

**Venta lifecycle**: prospecto → negociacion → anticipo_pagado (only via contable confirmar_ingreso) → pagado → entregado → completado. At anticipo_pagado: auto-reserves stock, creates OC for missing MP, generates contrato_cliente in portal.

**OC lifecycle**: borrador → anticipo_pagado → en_espera_producto → recibida. At creation: auto-generates asiento egreso + contrato_proveedor in portal. Payment confirmed via contable, not manually.

**Bidirectional payments**: Contable confirms payment → proveedor sees "anticipo enviado" → proveedor confirms receipt. Client reports payment in portal → badge in asientos → contable confirms.

**Legal documents**: 9 Colombian templates auto-generated on OC/venta creation. Digital signature + selfie capture via getUserMedia. Ley 527/1999 compliance.

**Nomina**: Payroll params editable from UI (stored in ConfigEmpresa.nomina_params JSON). Horas extra Art. 168-170 CST. Retencion fuente Art. 383 ET with UVT brackets. Prorrateo by days worked.

## Domain Context

- All UI text, comments, and variable names are in **Spanish**
- Payroll constants follow **Colombian labor law** (SMLMV 2025, ARL, cesantias, etc.) or **Mexican law** (IMSS, ISR, INFONAVIT) depending on COMPANY_ID
- PUC (Plan Unico de Cuentas) with 102 accounts per Decreto 2650/1993
- Production orders manage material reservations with FIFO + expiry-based lot tracking
- Deployed on **Railway.app** — see `Procfile` and `railway.toml`

## Files to be careful with

| File | Why |
|------|-----|
| models.py | `__all__` must list ALL models. `_migrate()` runs on every startup. |
| templates/base.html | 1,600+ LOC: dock sidebar, flyouts, onboarding, workspace tabs, dark mode |
| routes/contable.py | Race condition fixes with `with_for_update`. Payment cap logic. |
| services/nomina.py | Tax brackets must match current UVT. Retencion uses salario_completo for brackets, then prorates. |
| routes/ventas.py | State machine in TRANSICIONES dict. Side effects on state change (stock, OC, docs). |
