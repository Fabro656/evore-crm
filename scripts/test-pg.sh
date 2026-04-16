#!/bin/bash
# Run tests against PostgreSQL (catches FK issues that SQLite misses)
set -e

echo "=== Evore CRM — PostgreSQL Test Suite ==="

# Start test database
echo "Starting test PostgreSQL on port 5433..."
docker compose up -d db-test
until docker compose exec db-test pg_isready -U evore 2>/dev/null; do
    sleep 1
done

# Drop and recreate test DB for clean state
docker compose exec db-test psql -U evore -d postgres -c "DROP DATABASE IF EXISTS evore_test;" 2>/dev/null || true
docker compose exec db-test psql -U evore -d postgres -c "CREATE DATABASE evore_test;" 2>/dev/null || true
echo "Test database ready."

# Run tests
export DATABASE_URL=postgresql://evore:evore_dev@localhost:5433/evore_test
export SECRET_KEY=test-pg-key

echo ""
echo "Running smoke test..."
python3 -m tests.smoke_test
echo ""
echo "Running pytest..."
python3 -m pytest tests/ -v --tb=short
echo ""
echo "Running E2E flows against PostgreSQL..."
python3 -m tests.test_pg_flows
echo ""
echo "=== ALL POSTGRESQL TESTS COMPLETE ==="
