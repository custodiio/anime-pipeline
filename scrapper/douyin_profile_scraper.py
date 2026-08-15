"""
Mapeador de Perfis do Douyin (Últimos 2 Meses).
Mapeia postagens recentes de perfis cadastrados nos horários fixos (08:00, 12:00, 18:00).
"""

import os
import re
import sys
import httpx
import logging
from datetime import datetime, timedelta
from scrapper import database
from scrapper.config import DOUYIN_API_BASE
from scrapper.episode_detector import extract_episode

logger = logging.getLogger(__name__)

def extract_sec_uid(user_input: str) -> str | None:
    """Extrai sec_uid de URLs ou do texto bruto."""
    user_input = user_input.strip()
    match = re.search(r'user/([A-Za-z0-9_-]+)', user_input)
    if match:
        return match.group(1)
    if len(user_input) > 20 and ("MS4" in user_input or "AAAA" in user_input):
        return user_input
    return None

def fetch_and_store_profile(user_input: str) -> dict:
    """
    Mapeia os vídeos postados nos últimos 2 meses de um perfil do Douyin.
    """
    sec_uid = extract_sec_uid(user_input)
    if not sec_uid:
        return {"ok": False, "message": "Link ou sec_uid de perfil do Douyin inválido."}

    logger.info(f"👤 Mapeando perfil Douyin SEC_UID: {sec_uid[:20]}...")

    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_post_videos"
    max_cursor = 0
    all_videos = []
    author_nickname = ""
    avatar_url = ""
    cutoff_date = datetime.now() - timedelta(days=60)  # Limite dos últimos 2 meses
    has_more = True

    # Obtém o Cookie do Douyin do banco ou ambiente
    cookie_val = database.get_user_setting("DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE", "")
    headers = {"cookie": cookie_val} if cookie_val else {}

    try:
        while has_more and len(all_videos) < 100:
            params = {"sec_user_id": sec_uid, "max_cursor": max_cursor, "count": 20}
            res_json = None
            data = None
            
            for attempt in range(2):
                try:
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.get(url, params=params, headers=headers)
                        if resp.status_code != 200:
                            raise ValueError(f"HTTP Status {resp.status_code}")

                        res_json = resp.json()
                        data = res_json.get("data", {})

                        if data and data.get("status_code") == 5:
                            raise ValueError("Cookie expirado/bloqueado (status_code 5)")
                        
                        break # Sucesso
                except Exception as e:
                    logger.warning(f"Tentativa {attempt+1} de buscar perfil {sec_uid[:15]} falhou: {e}")
                    if attempt == 0:
                        logger.info("Auto-refrescando cookies do Douyin para perfil...")
                        from scrapper.auto_cookie import refresh_and_propagate_douyin_cookies_sync
                        new_cookie = refresh_and_propagate_douyin_cookies_sync(force=True)
                        if new_cookie:
                            headers = {"cookie": new_cookie}
                    else:
                        return {
                            "ok": False,
                            "message": f"Não foi possível mapear o perfil (Douyin bloqueou): {e}"
                        }

            aweme_list = data.get("aweme_list", []) if data else []
            has_more = bool(data.get("has_more", 0)) if data else False
            max_cursor = data.get("max_cursor", 0) if data else 0

            if not aweme_list:
                break

            stop_search = False
            for item in aweme_list:
                create_time_ts = item.get("create_time", 0)
                pub_date = datetime.fromtimestamp(create_time_ts) if create_time_ts else datetime.now()

                # Se o vídeo for mais antigo que 60 dias (2 meses), interrompe a busca
                if pub_date < cutoff_date:
                    stop_search = True
                    break

                aid = str(item.get("aweme_id"))
                desc = item.get("desc", "")
                author = item.get("author", {})
                video = item.get("video", {})
                stats = item.get("statistics", {})

                if not author_nickname and author:
                    author_nickname = author.get("nickname", "Perfi Douyin")
                    avatar_url = author.get("avatar_thumb", {}).get("url_list", [""])[0]

                cover = ""
                cover_list = video.get("origin_cover", {}).get("url_list", []) or video.get("cover", {}).get("url_list", [])
                if cover_list:
                    cover = cover_list[0]

                duration_s = video.get("duration", 0) // 1000  # ms -> s
                from scrapper.translator import translate_zh_to_pt
                title_pt = translate_zh_to_pt(desc)

                all_videos.append({
                    "aweme_id": aid,
                    "title": title_pt if title_pt else desc,
                    "duration_seconds": duration_s,
                    "likes": stats.get("digg_count", 0),
                    "comments": stats.get("comment_count", 0),
                    "cover_url": cover,
                    "published_at": pub_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "video_url": f"https://www.douyin.com/video/{aid}"
                })

            if stop_search:
                break
    except Exception as e:
        logger.error(f"Erro ao buscar postagens do perfil {sec_uid[:15]}: {e}")

    # Salva o perfil no banco SQLite
    nickname = author_nickname or f"Perfil #{sec_uid[:10]}"
    database.upsert_douyin_profile(
        sec_uid=sec_uid,
        nickname=nickname,
        avatar_url=avatar_url,
        profile_url=f"https://www.douyin.com/user/{sec_uid}"
    )

    # Cria ou atualiza a Coleção Virtual para este perfil
    virtual_mix_id = f"profile_{sec_uid[:15]}"
    database.upsert_douyin_collection({
        "mix_id": virtual_mix_id,
        "title_pt": f"Postagens de {nickname}",
        "title_zh": nickname,
        "author": nickname,
        "cover_url": avatar_url or (all_videos[0]["cover_url"] if all_videos else ""),
        "total_episodes": len(all_videos),
        "autoposting": 1,
        "is_virtual": 1,
        "status": "active"
    })

    # Ordena vídeos do mais recente ao mais antigo
    all_videos.sort(key=lambda x: x["published_at"], reverse=True)

    saved_count = 0
    for idx, v in enumerate(all_videos, 1):
        dur = v["duration_seconds"]
        status = "opaque_over_5min" if dur > 300 else "pending"
        
        ep_data = {
            "mix_id": virtual_mix_id,
            "episode_num": idx,
            "aweme_id": v["aweme_id"],
            "title": v["title"],
            "duration_seconds": dur,
            "likes": v["likes"],
            "comments": v["comments"],
            "cover_url": v["cover_url"],
            "video_url": v["video_url"],
            "status": status,
            "is_compilation": False
        }
        if database.upsert_collection_episode(ep_data):
            saved_count += 1

    return {
        "ok": True,
        "sec_uid": sec_uid,
        "nickname": nickname,
        "total_mapped": len(all_videos),
        "saved_count": saved_count,
        "message": f"Perfil '{nickname}' mapeado com sucesso! {len(all_videos)} vídeos dos últimos 2 meses carregados."
    }

def sync_all_profiles_and_collections():
    """
    Executa a varredura automática de atualizações de TODAS as coleções e perfis ativos.
    Chamado nos horários fixos de sincronização (08:00, 12:00 e 18:00).
    """
    logger.info("⏰ [CRON 08:00 / 12:00 / 18:00] Iniciando varredura automática de atualizações...")

    # 1. Atualiza Coleções ativas
    cols = database.get_douyin_collections()
    from scrapper import douyin_collection_scraper
    for c in cols:
        if not c.get("is_virtual") and c.get("autoposting"):
            try:
                douyin_collection_scraper.fetch_and_store_collection(c["mix_id"], title_pt=c["title_pt"], autoposting=True)
            except Exception as e:
                logger.error(f"Erro ao sincronizar coleção {c['mix_id']}: {e}")

    # 2. Atualiza Perfis cadastrados
    profs = database.get_douyin_profiles()
    for p in profs:
        try:
            fetch_and_store_profile(p["sec_uid"])
        except Exception as e:
            logger.error(f"Erro ao sincronizar perfil {p['sec_uid']}: {e}")

    logger.info("✅ Varredura automática de coleções e perfis concluída!")
