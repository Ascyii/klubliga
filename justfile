# Klubliga – development and deployment tasks.
# Settings come from the environment; a `.env` file is loaded if present (see .env.example).

set dotenv-load

host := env("HOST", "127.0.0.1")
port := env("PORT", "8000")
workers := env("WORKERS", "2")

# List the available recipes
default:
    @just --list

# Install the dependencies
install:
    uv sync

# Run the development server
dev: install
    uv run manage.py migrate
    uv run manage.py runserver {{host}}:{{port}}

# Run the test suite
test:
    uv run manage.py test

# Prepare a release: dependencies, database migrations, static files, deployment checks
deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${DJANGO_DEBUG:-1}" != "0" ]; then
        echo "Set DJANGO_DEBUG=0 (and DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS) for a deployment." >&2
        exit 1
    fi
    uv sync --frozen
    uv run manage.py migrate --noinput
    uv run manage.py collectstatic --noinput --clear
    uv run manage.py check --deploy

# Serve the app with gunicorn; WhiteNoise delivers the static files
serve:
    uv run gunicorn config.wsgi --bind {{host}}:{{port}} --workers {{workers}} --access-logfile -

# Deploy and serve in one go
up: deploy serve

# Build and start the Docker container, wait until it is healthy (see compose.yaml)
docker-up:
    docker compose up -d --build --wait

# Follow the container's log
docker-logs:
    docker compose logs -f web
