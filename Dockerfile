FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/shortlink.db

WORKDIR /srv

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir /data \
    && chown appuser:appuser /data
USER appuser
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
