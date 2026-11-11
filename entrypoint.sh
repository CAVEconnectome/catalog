#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting catalog service..."
exec uvicorn cave_catalog.app:create_app --factory --host 0.0.0.0 --port 80
