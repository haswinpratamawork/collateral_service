# Rumah123 listing-extractor API (FastAPI).
#
# The API imports the `scraper` package, so build from the REPO ROOT (not api/):
#   docker build -f api/Dockerfile -t collateral_scrapping .
#   docker run -p 8000:8000 -e GOOGLE_MAPS_API_KEY=AIza... collateral_scrapping
#
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8000

WORKDIR /app

# Install pinned dependencies first so this layer caches unless requirements.txt changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# App code (the scraper + api packages run from /app via PYTHONPATH).
COPY scraper/ ./scraper/
COPY api/ ./api/

# Run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/health',timeout=4).status_code==200 else 1)"

# exec via sh so ${PORT} expands AND signals (SIGTERM) reach uvicorn for clean shutdown.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
