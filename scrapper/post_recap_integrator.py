"""
Integrador de Postagens Autônomas: Douyin Recap Scraper <-> Post_recap / Kuma Recap Poster.
Vincula as postagens automáticas à conta 'facelesspipeline@gmail.com' no YouTube/Shorts, TikTok e Instagram.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from scrapper import database, episode_scheduler

logger = logging.getLogger(__name__)

# E-mail vinculado por padrão para autenticação no YouTube/Post_recap
DEFAULT_ACCOUNT_EMAIL = "facelesspipeline@gmail.com"

def get_post_recap_path() -> str | None:
    """Busca a localização raiz do projeto Post_recap no sistema."""
    possible_paths = [
        r"D:\Applications\Post_recap",
        r"C:\Applications\Post_recap",
        "/home/ubuntu/apps/Post_recap",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Post_recap"))
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None

def schedule_episode_post(
    ep_id: int,
    scheduled_time: datetime = None,
    post_youtube: bool = False,
    post_shorts: bool = True,
    post_tiktok: bool = True,
    post_instagram: bool = False
) -> dict:
    """
    Agenda o envio autônomo do episódio processado no Post_recap.
    
    Args:
        ep_id: ID do episódio no SQLite collection_episodes.
        scheduled_time: Data/hora agendada (se None, calcula usando o ritmo diário).
        post_youtube: Ativa envio para YouTube Vídeo Longo.
        post_shorts: Ativa envio para YouTube Shorts.
        post_tiktok: Ativa envio para TikTok.
        post_instagram: Ativa envio para Instagram Reels.
    """
    ep = database.get_episode_by_id(ep_id)
    if not ep:
        return {"ok": False, "message": f"Episódio #{ep_id} não encontrado."}

    # Se não informar horário, calcula baseado no ritmo diário (1, 2 ou 3 vídeos/dia)
    if not scheduled_time:
        rate = episode_scheduler.get_daily_post_rate()
        hours_interval = 24 // rate
        scheduled_time = datetime.now() + timedelta(hours=hours_interval)

    sched_str = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")

    # Extrai o Guia de Postagem PT-BR
    guide = {}
    if ep.get("posting_guide"):
        try:
            guide = json.loads(ep["posting_guide"])
        except Exception:
            guide = {}

    title_pt = guide.get("title", f"EP {ep.get('episode_num', 1)} | {ep.get('title')[:30]}")
    desc_pt = guide.get("description", ep.get("title", ""))

    post_recap_root = get_post_recap_path()
    if not post_recap_root:
        logger.warning("⚠️ Projeto Post_recap não encontrado no disco. Agendamento em modo simulado.")
        return {
            "ok": True,
            "simulated": True,
            "account_email": DEFAULT_ACCOUNT_EMAIL,
            "scheduled_time": sched_str,
            "title": title_pt,
            "message": f"Agendamento simulado com sucesso para {sched_str} na conta {DEFAULT_ACCOUNT_EMAIL}."
        }

    try:
        if post_recap_root not in sys.path:
            sys.path.insert(0, post_recap_root)

        import db as post_db
        
        # Garante a variável de ambiente do e-mail da conta no .env do Post_recap
        os.environ["YOUTUBE_USER_EMAIL"] = DEFAULT_ACCOUNT_EMAIL

        post_id = post_db.add_scheduled_post(
            video_path=ep.get("local_video_path", f"video_ep_{ep_id}.mp4"),
            thumbnail_youtube=ep.get("cover_url", ""),
            thumbnail_tiktok=ep.get("cover_url", ""),
            title_youtube=title_pt,
            title_shorts=title_pt,
            tiktok_caption=title_pt,
            instagram_caption=desc_pt,
            post_youtube=1 if post_youtube else 0,
            post_shorts=1 if post_shorts else 0,
            post_tiktok=1 if post_tiktok else 0,
            post_instagram=1 if post_instagram else 0,
            tiktok_privacy="PUBLIC",
            scheduled_time=sched_str,
            shorts_description=desc_pt
        )

        logger.info(f"✅ Agendamento registrado no Post_recap (Post ID: {post_id}, Horário: {sched_str})!")
        database.update_episode_status(ep_id, "scheduled")

        return {
            "ok": True,
            "post_id": post_id,
            "account_email": DEFAULT_ACCOUNT_EMAIL,
            "scheduled_time": sched_str,
            "title": title_pt,
            "message": f"Postagem agendada com sucesso no Post_recap (ID #{post_id}) para {sched_str}!"
        }

    except Exception as e:
        logger.error(f"Erro ao agendar postagem no Post_recap: {e}")
        return {
            "ok": False,
            "account_email": DEFAULT_ACCOUNT_EMAIL,
            "error": str(e),
            "message": f"Falha ao comunicar com o banco de agendamento do Post_recap: {e}"
        }

def repost_from_staging(ep_id: int) -> dict:
    """
    Reenvia o vídeo armazenado na pasta de staging 'data/next_staging' caso ocorra
    falso poste ou falha na API de postagem.
    """
    staging_file = os.path.join("data", "next_staging", f"next_ep_{ep_id}.mp4")
    if not os.path.exists(staging_file):
        return {"ok": False, "message": f"Arquivo de staging do episódio #{ep_id} não encontrado ou expirado (>6h)."}

    sched_time = datetime.now() + timedelta(minutes=3)
    return schedule_episode_post(ep_id, scheduled_time=sched_time)
