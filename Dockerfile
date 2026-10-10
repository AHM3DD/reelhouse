# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Stage 1: Tailwind standalone CLI (a single binary, no Node.js required).
# Also used directly by the development "css" watcher service.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS tailwind
ARG TAILWIND_VERSION=3.4.17
ARG TARGETARCH
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && case "${TARGETARCH:-amd64}" in \
      amd64) arch=x64 ;; \
      arm64) arch=arm64 ;; \
      *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && curl -fsSL -o /usr/local/bin/tailwindcss \
      "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${arch}" \
 && chmod +x /usr/local/bin/tailwindcss
WORKDIR /app

# ---------------------------------------------------------------------------
# Stage 2: compile and minify the stylesheet by scanning templates and Python.
# ---------------------------------------------------------------------------
FROM tailwind AS css-build
COPY . .
RUN tailwindcss -c tailwind.config.js -i static/src/input.css -o static/dist/app.css --minify

# ---------------------------------------------------------------------------
# Stage 3: the Django application image.
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 1000 app \
 && useradd --system --uid 1000 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=app:app . .
COPY --from=css-build --chown=app:app /app/static/dist/app.css ./static/dist/app.css

# collectstatic needs importable production settings. The throwaway key below exists
# only for this build step and is never used at runtime.
RUN DJANGO_SETTINGS_MODULE=config.settings.production \
    DJANGO_SECRET_KEY=collectstatic-build-step-only-not-a-real-secret-key-0000 \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput \
 && mkdir -p /app/media \
 && chown -R app:app /app/media /app/staticfiles

USER app

EXPOSE 8888

ENTRYPOINT ["python", "/app/docker/entrypoint.py"]
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8888 --workers ${GUNICORN_WORKERS:-3} --timeout 30 --access-logfile - --error-logfile -"]
