#!/bin/bash
# Start local PostgreSQL and run the app against it
set -e

echo "=== Evore CRM — Local PostgreSQL Dev ==="

# Start PostgreSQL
echo "Starting PostgreSQL..."
docker compose up -d db
echo "Waiting for PostgreSQL to be ready..."
until docker compose exec db pg_isready -U evore 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL ready."

# Set environment
export DATABASE_URL=postgresql://evore:evore_dev@localhost:5432/evore
export SECRET_KEY=dev-local-key-$(date +%s)

echo ""
echo "DATABASE_URL=$DATABASE_URL"
echo ""
echo "Starting Flask..."
python3 app.py
