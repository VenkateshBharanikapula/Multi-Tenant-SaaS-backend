#!/bin/sh

set -e

echo "Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 0.1
done
echo "PostgreSQL is ready!"

echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 0.1
done
echo "Redis is ready!"

# Only run migrations + collectstatic on the web container.
# Celery containers set SKIP_MIGRATE=true in docker-compose.yml.
if [ "$SKIP_MIGRATE" != "true" ]; then
  echo "Applying database migrations..."
  python manage.py migrate --noinput

  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

echo "Starting..."
exec "$@"
