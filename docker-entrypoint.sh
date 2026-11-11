#!/bin/sh
set -e

# Apply migrations on startup unless disabled (e.g. when running several
# replicas and migrating as a separate release step).
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
