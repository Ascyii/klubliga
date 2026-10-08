# Klubliga – production image: gunicorn serves Django, WhiteNoise the static files.
# The SQLite database lives in /data (a volume, see compose.yaml).

FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

COPY . .

# Collect and compress the static files at build time. The settings need
# DEBUG off (manifest storage) and some secret key; neither is kept.
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=collectstatic \
    python manage.py collectstatic --noinput

RUN useradd --system --uid 1000 --home /app klubliga \
    && mkdir /data && chown klubliga /data
USER klubliga

ENV DJANGO_DB_PATH=/data/db.sqlite3
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi --bind 0.0.0.0:8000 --workers ${WORKERS:-2} --access-logfile - --no-control-socket"]
