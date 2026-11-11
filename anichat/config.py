"""Settings from the environment / .env file. The only module that reads them.

Used by: anichat/container.py (everything else gets settings passed in)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
QDRANT_PATH = os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant"))  # local mode folder
QDRANT_URL = os.getenv("QDRANT_URL")  # set (with QDRANT_API_KEY) to use Qdrant Cloud instead
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or None
# Comma-separated: each Gemini model has its own free daily quota, so listing two roughly
# doubles free capacity (tried in this order, before the next provider).
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODEL", "gemini-2.5-flash,gemini-2.5-flash-lite").split(",") if m.strip()]
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or None
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
LLM_PROVIDERS = [p.strip() for p in os.getenv("LLM_PROVIDERS", "gemini,groq").split(",") if p.strip()]

# Browser origins allowed to call the API (the frontend). Comma-separated; the Vite dev server
# by default. In production, set it to the deployed frontend URL(s).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
                if o.strip()]

# Chat questions allowed per visitor (IP address); 0 = no limit. Protects the free model quotas.
CHAT_PER_MINUTE = int(os.getenv("CHAT_PER_MINUTE", "10"))
CHAT_PER_DAY = int(os.getenv("CHAT_PER_DAY", "200"))
# Behind a hosting proxy (Render, Fly, Railway...) the visitor's IP is in X-Forwarded-For.
# Only enable when deployed behind one: otherwise anyone could fake the header.
TRUST_PROXY = os.getenv("TRUST_PROXY", "0").lower() in ("1", "true", "yes")

# TMDb (movies added one by one with scripts/add_movie.py): a free key from themoviedb.org ->
# Settings -> API. Either the "API Read Access Token" (preferred) or the "API Key".
TMDB_READ_TOKEN = os.getenv("TMDB_READ_TOKEN") or None
TMDB_API_KEY = os.getenv("TMDB_API_KEY") or None

# The admin form's cloud store (Upstash Redis, connected to the Vercel project): the same
# KV_REST_API_URL / KV_REST_API_TOKEN that Vercel gives the form's function.
KV_REST_API_URL = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL") or None
KV_REST_API_TOKEN = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN") or None
