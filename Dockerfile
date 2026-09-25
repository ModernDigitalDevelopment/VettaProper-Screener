FROM python:3.12-slim

# Non-root user — the app never needs to write to disk at runtime.
RUN useradd -m -u 1000 vetta

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY web/ ./web/
COPY backtest/data/events.json ./backtest/data/events.json
COPY check_config.py .

USER vetta

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

# The screener is I/O bound (waiting on option-chain HTTP calls), so a couple
# of workers is plenty. More workers means more concurrent Polygon requests,
# which can trip rate limits on lower plans.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 2"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://localhost:{os.getenv(\"PORT\",8000)}/api/health').read()"
