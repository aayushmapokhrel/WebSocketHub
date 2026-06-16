#!/bin/bash
set -e

echo "──────────────────────────────────────────"
echo " Pulse Chat Backend Starting..."
echo "──────────────────────────────────────────"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.5
done
echo "PostgreSQL is ready"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 0.5
done
echo "Redis is ready"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting server..."
exec "$@"