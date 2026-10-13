FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8080
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY claimshield ./claimshield
COPY web ./web
COPY data ./data

RUN useradd --create-home --uid 10001 app && mkdir -p /app/var && chown app /app/var
USER app

CMD ["sh", "-c", "uvicorn claimshield.api.main:app --host 0.0.0.0 --port ${PORT} --timeout-keep-alive 75"]
