.PHONY: dev dev-pg test test-pg test-all pg-up pg-down reset-test-db

# ── Local development (SQLite) ──
dev:
	SECRET_KEY=dev-local python3 app.py

# ── Local development (PostgreSQL) ──
dev-pg: pg-up
	DATABASE_URL=postgresql://evore:evore_dev@localhost:5432/evore \
	SECRET_KEY=dev-local-pg \
	python3 app.py

# ── Tests (SQLite — fast) ──
test:
	SECRET_KEY=test python3 -m pytest tests/ -v --tb=short

# ── Tests (PostgreSQL — catches real bugs) ──
test-pg: pg-up reset-test-db
	DATABASE_URL=postgresql://evore:evore_dev@localhost:5433/evore_test \
	SECRET_KEY=test-pg \
	python3 -m pytest tests/ -v --tb=short
	DATABASE_URL=postgresql://evore:evore_dev@localhost:5433/evore_test \
	SECRET_KEY=test-pg \
	python3 -m tests.test_pg_flows

# ── Full test suite (SQLite + PostgreSQL) ──
test-all: test test-pg
	@echo "ALL TESTS PASSED (SQLite + PostgreSQL)"

# ── Smoke test ──
smoke:
	SECRET_KEY=test python3 -m tests.smoke_test

# ── PostgreSQL management ──
pg-up:
	docker compose up -d db db-test
	@echo "Waiting for PostgreSQL..."
	@until docker compose exec db pg_isready -U evore 2>/dev/null; do sleep 1; done
	@until docker compose exec db-test pg_isready -U evore 2>/dev/null; do sleep 1; done
	@echo "PostgreSQL ready (dev: 5432, test: 5433)"

pg-down:
	docker compose down

reset-test-db:
	docker compose exec db-test psql -U evore -d postgres -c "DROP DATABASE IF EXISTS evore_test;" 2>/dev/null || true
	docker compose exec db-test psql -U evore -d postgres -c "CREATE DATABASE evore_test;" 2>/dev/null || true
