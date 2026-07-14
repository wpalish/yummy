FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YUMMY_DB_PATH=/data/yummy.db

WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
    && groupadd --system yummy \
    && useradd --system --gid yummy --home-dir /nonexistent --shell /usr/sbin/nologin yummy \
    && mkdir -p /data \
    && chown yummy:yummy /data
COPY --chown=yummy:yummy app ./app
COPY --chown=yummy:yummy tools ./tools
COPY --chown=yummy:yummy migrations ./migrations
COPY --chown=yummy:yummy alembic.ini ./alembic.ini

USER yummy:yummy
EXPOSE 8000
CMD ["sh","-c","if [ -n \"${DATABASE_URL:-}\" ]; then alembic upgrade head; fi && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header"]
