# The AniChat API (FastAPI) for hosting. The frontend is deployed separately (static site),
# and the vector database is Qdrant (Docker or Qdrant Cloud), set with QDRANT_URL.
#
#   docker build -t anichat-api .
#   docker run --rm -p 8000:8000 --env-file .env -e QDRANT_URL=http://host.docker.internal:6333 anichat-api

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY anichat ./anichat
# Download the embedding models now (~65 MB) so a fresh server doesn't fetch them on startup.
RUN python -c "from anichat.infrastructure.fastembed_embedder import FastEmbedEmbedder; FastEmbedEmbedder()"

RUN useradd --create-home anichat && chown -R anichat /app
USER anichat

EXPOSE 8000
# Hosts like Render set PORT; --proxy-headers so the client IP comes from the host's proxy.
CMD ["sh", "-c", "uvicorn anichat.interfaces.api:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
