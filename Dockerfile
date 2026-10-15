FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system --gid 10001 schoolcms \
    && useradd --system --uid 10001 --gid schoolcms --home-dir /app --shell /usr/sbin/nologin schoolcms

RUN apt-get update \
    && apt-get install --yes --no-install-recommends clamav-daemon \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=schoolcms:schoolcms . .

RUN mkdir -p /var/lib/schoolcms/private \
    && chown -R schoolcms:schoolcms /var/lib/schoolcms

# Static assets are immutable image content. This uses development mode only to
# avoid requiring a production secret while building the image.
RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput \
    && chown -R schoolcms:schoolcms /app

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "schoolcms.wsgi:application", "--bind=0.0.0.0:8000", "--workers=3", "--error-logfile=-", "--graceful-timeout=30", "--timeout=60"]
