# One image for api, worker, migrations and tests: ffmpeg is needed by worker, seed and tests.
FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

ARG INSTALL_DEV=false
COPY requirements.txt requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then REQ=requirements-dev.txt; else REQ=requirements.txt; fi \
 && pip install --timeout 120 --retries 5 -r "$REQ"

COPY --chown=app:app . .

# Scratch space for ffmpeg (a named volume is mounted here in the worker). It must exist in the
# image owned by `app`: Docker initializes an empty named volume with this ownership. Otherwise
# the volume is root-owned and tempfile silently falls back to the small /tmp tmpfs.
RUN mkdir -p /work && chown app:app /work

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", \
     "--forwarded-allow-ips", "*", "--access-logfile", "-"]
