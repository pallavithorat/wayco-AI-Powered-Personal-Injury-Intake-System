#!/bin/bash
set -e

echo "=== Wayco PI Startup ==="
echo "PORT=${PORT:-8000}"
echo "ENVIRONMENT=${ENVIRONMENT:-development}"

echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

echo "Starting API server on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
