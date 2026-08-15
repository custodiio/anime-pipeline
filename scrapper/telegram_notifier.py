"""
Douyin Anime Scraper — Notificador Telegram.
Envia cards formatados com candidatos de vídeos encontrados.
"""

import logging
import httpx
from datetime import date

from scrapper.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from scrapper.scraper import ScrapeResult

log = logging.getLogger(__name__)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ─── Formatação ──────────────────────────────────────────────────────────────

def fmt_duration(seconds: int) -> str:
    """Formata duração em minutos e segundos."""
    m, s = divmod(seconds, 60)
    return f"{m}min {s:02d}s"


def fmt_likes(n: int) -> str:
    """Formata likes (ex: 12400 → 12.4k)."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def build_card(v: dict, is_next_ep: bool = False) -> str:
    """
    Constrói card formatado de um vídeo.

    Formato:
        🎌 [LONGO] Título do vídeo
        👤 Criador: @username
        ⏱ Duração: 8min 32s | 👍 12.4k likes
        📅 Postado: 2025-06-10
        🔗 https://www.douyin.com/video/XXXXX
        📌 Possível continuação: EP 14
    """
    emoji = "⚡" if v["type"] == "SHORT" else "🎌"
    tag = v["type"]

    lines = [
        f"{emoji} [{tag}] {v['title'][:80]}",
        f"👤 Criador: @{v['creator']}",
        f"⏱ Duração: {fmt_duration(v['duration_s'])} | 👍 {fmt_likes(v['likes'])} likes",
        f"📅 Postado: {v['published_at'][:10]}",
        f"🔗 {v['url']}",
        f"🆔 <code>{v['video_id']}</code>",
    ]

    if is_next_ep and v.get("episode"):
        lines.append(f"\n📌 Possível continuação: EP {v['episode']}")

    return "\n".join(lines)


# ─── Envio ───────────────────────────────────────────────────────────────────

def send_message(text: str) -> bool:
    """Envia mensagem de texto ao Telegram."""
    try:
        resp = httpx.post(
            f"{API_URL}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        log.error(f"❌ Telegram erro: {e}")
        return False


def send_results(result: ScrapeResult) -> None:
    """
    Envia resultados completos do scraping via Telegram.

    Inclui:
    - Cabeçalho com data e contagem
    - Top 5 vídeos longos (recaps)
    - Top 5 vídeos curtos (Shorts)
    - Instrução para marcar como postado
    - Estatísticas de filtragem
    """
    total = len(result.long_videos) + len(result.short_videos)

    if total == 0:
        send_message(
            f"🔍 <b>Douyin Scout — {date.today()}</b>\n\n"
            f"Nenhum candidato novo encontrado hoje.\n\n"
            f"📊 {result.total_raw} analisados | "
            f"{result.skipped_seen} já vistos | "
            f"{result.skipped_likes} likes baixos"
        )
        return

    # Cabeçalho
    send_message(
        f"🗓 <b>Douyin Anime Scout — {date.today()}</b>\n"
        f"✅ {total} candidatos encontrados "
        f"({len(result.long_videos)} longos · {len(result.short_videos)} shorts)\n\n"
        f"📊 {result.total_raw} analisados | "
        f"{result.skipped_seen} já vistos | "
        f"{result.skipped_likes} filtrados"
    )

    # Vídeos LONGOS (até top 5)
    if result.long_videos:
        send_message("━━━━━━━━━━━━━━━━\n🎌 <b>VÍDEOS LONGOS (recap)</b>")
        for v in result.long_videos[:5]:
            is_next = (
                result.next_episode is not None
                and v["video_id"] == result.next_episode["video_id"]
            )
            send_message(build_card(v, is_next_ep=is_next))

    # Vídeos CURTOS (até top 5)
    if result.short_videos:
        send_message("━━━━━━━━━━━━━━━━\n⚡ <b>VÍDEOS CURTOS (Shorts)</b>")
        for v in result.short_videos[:5]:
            send_message(build_card(v))

    # Rodapé
    send_message(
        "━━━━━━━━━━━━━━━━\n"
        "Para marcar como postado:\n"
        "<code>/postado VIDEO_ID</code>"
    )
