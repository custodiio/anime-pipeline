"""
Douyin Anime Scraper — Configuração centralizada.
Carrega variáveis do .env e valida as obrigatórias.
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

log = logging.getLogger("scrapper.config")

# ─── Telegram ────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN: str = os.getenv("SCRAPPER_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("SCRAPPER_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID", "7321866230")
AUTHORIZED_USERS: list[str] = [
    uid.strip()
    for uid in os.getenv("AUTHORIZED_TELEGRAM_USERS", TELEGRAM_CHAT_ID).split(",")
    if uid.strip()
]


# ─── Douyin ──────────────────────────────────────────────────────────────────

DOUYIN_COOKIE: str = os.getenv("DOUYIN_COOKIE", "")
DOUYIN_API_BASE: str = os.getenv("DOUYIN_API_BASE", "http://localhost:5555")
WEB_PANEL_URL: str = os.getenv("WEB_PANEL_URL", "https://animesrecaps.me/scrapper")


# ─── Busca ───────────────────────────────────────────────────────────────────

SEARCH_TERM: str = os.getenv("SEARCH_TERM", "新番解说")
MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "30"))
MIN_LIKES: int = int(os.getenv("MIN_LIKES", "1"))


# ─── Duração (segundos) ─────────────────────────────────────────────────────

SHORT_MAX: int = 4 * 60      # < 4 min → candidato para Shorts
LONG_MIN: int = 4 * 60       # > 4 min
LONG_MAX: int = 10 * 60      # ≤ 10 min → candidato para recap


# ─── Logging ─────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO):
    """Configura logging padrão do projeto."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

