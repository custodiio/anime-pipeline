"""
Mapeador de Coleções e Séries Virtuais do Douyin.
Consome a API local do Evil0ctal e armazena coleções e episódios no banco SQLite.
"""

import os
import re
import sys
import io
import httpx
import logging
from datetime import datetime
from scrapper import database
from scrapper.config import DOUYIN_API_BASE
from scrapper.episode_detector import extract_episode
from scrapper.translator import translate_zh_to_pt

logger = logging.getLogger(__name__)

def extract_ids(user_input: str) -> tuple[str | None, str | None]:
    """Extrai (mix_id, aweme_id) de URLs ou IDs numéricos."""
    user_input = user_input.strip()
    if user_input.isdigit():
        return user_input, None

    mix_match = re.search(r'collection/(\d+)', user_input)
    if mix_match:
        return mix_match.group(1), None

    video_match = re.search(r'video/(\d+)', user_input)
    if video_match:
        return None, video_match.group(1)

    numbers = re.findall(r'\d{15,22}', user_input)
    if numbers:
        return numbers[0], None

    return None, None

def get_mix_info_from_video(aweme_id: str) -> dict | None:
    """Obtém mix_info a partir de um vídeo avulso."""
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
    cookie_val = database.get_user_setting("DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE", "")
    headers = {"cookie": cookie_val} if cookie_val else {}
    
    for attempt in range(2):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params={"aweme_id": aweme_id}, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    if data and data.get("status_code") == 5:
                        raise ValueError("Cookie expirado/bloqueado (status_code 5)")
                    aweme_detail = data.get("aweme_detail", {})
                    if not aweme_detail:
                        raise ValueError("Detalhes do vídeo vazios ou ausentes")
                    mix_info = aweme_detail.get("mix_info", {})
                    if mix_info:
                        return {
                            "mix_id": str(mix_info.get("mix_id")),
                            "mix_name": mix_info.get("mix_name", ""),
                            "st_at": mix_info.get("st_at"),
                            "author": aweme_detail.get("author", {}).get("nickname", "Desconhecido")
                        }
                    return None
                else:
                    raise ValueError(f"Status HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"Tentativa {attempt+1} falhou para obter mix_info do vídeo {aweme_id}: {e}")
            if attempt == 0:
                logger.info("Auto-refrescando cookies do Douyin para mix_info...")
                from scrapper.auto_cookie import refresh_and_propagate_douyin_cookies_sync
                new_cookie = refresh_and_propagate_douyin_cookies_sync(force=True)
                if new_cookie:
                    headers = {"cookie": new_cookie}
            else:
                logger.error(f"Erro definitivo ao obter mix_info do vídeo {aweme_id}: {e}")
    return None

def extract_episode_num(text_pt: str = "", text_zh: str = "") -> int:
    """
    Tenta capturar inteligentemente o número do episódio no título/descrição (PT ou ZH).
    Retorna int se encontrado, ou None se não houver indicativo numérico de episódio.
    """
    if text_pt:
        # Busca padrões como EP 141, Ep. 141, Episódio 141, Parte 141, Part 141, Cap 141, #141
        patterns = [
            r'(?:ep|episodio|episódio|parte|part|capitulo|capítulo|cap|p)\b\.?\s*#?\s*(\d+)',
            r'\b(\d+)\s*(?:ª|º)?\s*(?:ep|episodio|episódio|parte|part)\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, text_pt, re.IGNORECASE)
            if match:
                val = int(match.group(1))
                if 0 < val < 2000:
                    return val

    if text_zh:
        # Busca padrões como 第141集, 第141期, 第141话, 141集
        patterns = [
            r'第\s*(\d+)\s*[集期话]',
            r'(\d+)\s*[集期话]',
            r'(?:ep|p)\s*(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, text_zh, re.IGNORECASE)
            if match:
                val = int(match.group(1))
                if 0 < val < 2000:
                    return val

    return None

def fetch_and_store_single_video(aweme_id: str, title_pt: str = None, autoposting: bool = True) -> dict:
    """
    Mapeia um vídeo avulso do Douyin agrupando-o em uma coleção virtual unificada de Vídeos Avulsos.
    """
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
    cookie_val = database.get_user_setting("DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE", "")
    headers = {"cookie": cookie_val} if cookie_val else {}
    
    res_json = None
    data = None
    
    for attempt in range(2):
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.get(url, params={"aweme_id": aweme_id}, headers=headers)
                if resp.status_code != 200:
                    raise ValueError(f"Erro HTTP {resp.status_code} ao buscar detalhes do vídeo avulso.")
                
                res_json = resp.json()
                data = res_json.get("data", {})
                
                if data and data.get("status_code") == 5:
                    raise ValueError("Cookie expirado ou bloqueado pelo Douyin (status_code 5).")
                    
                aweme_detail = data.get("aweme_detail", {})
                if not aweme_detail:
                    raise ValueError("Detalhes do vídeo não encontrados na resposta da API.")
                
                break # Sucesso
        except Exception as e:
            logger.warning(f"Tentativa {attempt+1} falhou ao obter detalhes do vídeo {aweme_id}: {e}")
            if attempt == 0:
                logger.info("Auto-refrescando cookies do Douyin...")
                from scrapper.auto_cookie import refresh_and_propagate_douyin_cookies_sync
                new_cookie = refresh_and_propagate_douyin_cookies_sync(force=True)
                if new_cookie:
                    headers = {"cookie": new_cookie}
            else:
                return {"ok": False, "message": f"O Douyin bloqueou a requisição após tentar atualizar os cookies: {e}"}
                
    try:
        aweme_detail = data.get("aweme_detail", {})
        desc = aweme_detail.get("desc", "Vídeo Avulso")
        author = aweme_detail.get("author", {})
        author_name = author.get("nickname", "Autor Douyin")
        video = aweme_detail.get("video", {})
        stats = aweme_detail.get("statistics", {})
        
        cover = ""
        cover_list = video.get("origin_cover", {}).get("url_list", []) or video.get("cover", {}).get("url_list", [])
        if cover_list:
            cover = cover_list[0]
            
        duration_s = video.get("duration", 0) // 1000  # ms -> s
        title_translated = translate_zh_to_pt(desc)
        
        virtual_mix_id = "colecao_avulsos"
        
        # 1. Garante que a Coleção unificada existe
        col_data = {
            "mix_id": virtual_mix_id,
            "title_pt": "Vídeos Avulsos",
            "title_zh": "Vídeos Avulsos",
            "author": "Sistema",
            "cover_url": cover,
            "total_episodes": 0, # Será atualizado dinamicamente
            "autoposting": 0,    # Vídeos avulsos não entram na fila de agendamento automático
            "is_virtual": True,
            "status": "active"
        }
        database.upsert_douyin_collection(col_data)
        
        # 2. Define o episode_num inteligente para o vídeo avulso
        ep_extracted = extract_episode_num(title_translated or "", desc or "")
        if ep_extracted is not None:
            next_ep_num = ep_extracted
        else:
            # Se não houver número de episódio explícito na descrição, usa os últimos 6 dígitos do aweme_id
            # para garantir um identificador único sem forçar uma falsa sequência (EP 1, EP 2...)
            try:
                next_ep_num = int(str(aweme_id)[-6:])
            except Exception:
                next_ep_num = 0
        
        # Criar episódio único dentro da coleção unificada
        status = "opaque_over_5min" if duration_s > 300 else "pending"
        ep_data = {
            "mix_id": virtual_mix_id,
            "episode_num": next_ep_num,
            "aweme_id": aweme_id,
            "title": title_pt or (title_translated if title_translated else desc),
            "duration_seconds": duration_s,
            "likes": stats.get("digg_count", 0),
            "comments": stats.get("comment_count", 0),
            "cover_url": cover,
            "video_url": f"https://www.douyin.com/video/{aweme_id}",
            "status": status,
            "is_compilation": False
        }
        database.upsert_collection_episode(ep_data)
        
        # 3. Atualiza o total_episodes da coleção
        conn = database.get_connection()
        cursor = conn.conn.cursor() if hasattr(conn, "conn") else conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM collection_episodes WHERE mix_id = ?", (virtual_mix_id,))
        total_eps = cursor.fetchone()[0]
        cursor.execute("UPDATE douyin_collections SET total_episodes = ? WHERE mix_id = ?", (total_eps, virtual_mix_id))
        conn.commit()
        conn.close()
        
        return {
            "ok": True,
            "mix_id": virtual_mix_id,
            "title_pt": "Vídeos Avulsos",
            "title_zh": "Vídeos Avulsos",
            "author": "Sistema",
            "total_mapped": total_eps,
            "saved_count": 1,
            "opaque_count": 1 if duration_s > 300 else 0,
            "message": f"Vídeo avulso adicionado com sucesso à coleção 'Vídeos Avulsos' como EP {next_ep_num}!"
        }
    except Exception as e:
        logger.error(f"Erro ao processar e salvar vídeo avulso {aweme_id}: {e}")
        return {"ok": False, "message": f"Erro interno ao mapear vídeo avulso: {e}"}


def fetch_and_store_collection(user_input: str, title_pt: str = None, autoposting: bool = True) -> dict:
    """
    Mapeia uma coleção completa do Douyin e salva no banco de dados SQLite.
    
    Args:
        user_input: URL da coleção, URL de um vídeo ou mix_id numérico.
        title_pt: Título traduzido/personalizado em português.
        autoposting: Define se o autoposting estará ON ou OFF.
        
    Returns:
        Dicionário com resumo da coleção e episódios salvos.
    """
    mix_id, aweme_id = extract_ids(user_input)

    if aweme_id:
        # Se for um link de vídeo (contém aweme_id), mapeia estritamente como vídeo avulso.
        # Evita buscar e importar a coleção inteira automaticamente.
        return fetch_and_store_single_video(aweme_id, title_pt, autoposting)

    if not mix_id:
        return {"ok": False, "message": "Link ou ID de coleção inválido."}

    logger.info(f"📡 Mapeando coleção Douyin MIX_ID: {mix_id}...")

    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_mix_videos"
    cursor = 0
    all_episodes = []
    mix_name = ""
    author_name = ""
    cover_url = ""
    has_more = True

    cookie_val = database.get_user_setting("DOUYIN_COOKIE") or os.getenv("DOUYIN_COOKIE", "")
    headers = {"cookie": cookie_val} if cookie_val else {}

    try:
        while has_more and len(all_episodes) < 200:
            params = {"mix_id": mix_id, "max_cursor": cursor, "counts": 20}
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
                    logger.warning(f"Tentativa {attempt+1} falhou ao obter mix {mix_id}: {e}")
                    if attempt == 0:
                        logger.info("Auto-refrescando cookies do Douyin para coleção...")
                        from scrapper.auto_cookie import refresh_and_propagate_douyin_cookies_sync
                        new_cookie = refresh_and_propagate_douyin_cookies_sync(force=True)
                        if new_cookie:
                            headers = {"cookie": new_cookie}
                    else:
                        return {
                            "ok": False,
                            "message": f"Não foi possível mapear a coleção (Douyin bloqueou): {e}"
                        }

            aweme_list = data.get("aweme_list", []) if data else []
            has_more = bool(data.get("has_more", 0)) if data else False
            cursor = data.get("cursor", 0) if data else 0

            if not aweme_list:
                break

            for item in aweme_list:
                aid = str(item.get("aweme_id"))
                desc = item.get("desc", "")
                mix_info = item.get("mix_info", {})
                author = item.get("author", {})
                video = item.get("video", {})
                stats = item.get("statistics", {})

                if not mix_name and mix_info:
                    mix_name = mix_info.get("mix_name", "")
                if not author_name and author:
                    author_name = author.get("nickname", "")

                # Tenta obter a melhor imagem de capa
                cover = ""
                cover_list = video.get("origin_cover", {}).get("url_list", []) or video.get("cover", {}).get("url_list", [])
                if cover_list:
                    cover = cover_list[0]
                if not cover_url and cover:
                    cover_url = cover

                duration_s = video.get("duration", 0) // 1000  # ms -> s
                ep_num = mix_info.get("st_at") or extract_episode(desc)
                title_translated = translate_zh_to_pt(desc)

                all_episodes.append({
                    "mix_id": mix_id,
                    "episode_num": ep_num,
                    "aweme_id": aid,
                    "title": title_translated if title_translated else desc,
                    "duration_seconds": duration_s,
                    "likes": stats.get("digg_count", 0),
                    "comments": stats.get("comment_count", 0),
                    "cover_url": cover,
                    "video_url": f"https://www.douyin.com/video/{aid}",
                })
    except Exception as e:
        logger.error(f"Erro ao buscar página do mix {mix_id} (cursor={cursor}): {e}")
        return {"ok": False, "message": f"Erro ao mapear episódios do mix: {e}"}

    if not all_episodes:
        return {"ok": False, "message": "Nenhum episódio retornado pela API. Verifique a validade do cookie."}

    # Ordena: quem tem episode_num explícito vem primeiro; sem ep_num mantém ordem de inserção (cronológica da API)
    all_episodes.sort(key=lambda x: x["episode_num"] if x["episode_num"] is not None else 999999)

    # Atribui posição sequencial para episódios sem número detectado (usa a ordem da coleção no Douyin)
    for i, ep in enumerate(all_episodes):
        if ep["episode_num"] is None:
            ep["episode_num"] = i + 1

    # Identifica se já existem episódios curtos para filtrar resumos de 50 min
    has_short_eps = any(ep["duration_seconds"] <= 300 for ep in all_episodes)

    # Salva no banco de dados
    col_data = {
        "mix_id": mix_id,
        "title_pt": title_pt or mix_name or f"Série #{mix_id}",
        "title_zh": mix_name,
        "author": author_name,
        "cover_url": cover_url or (all_episodes[0]["cover_url"] if all_episodes else ""),
        "total_episodes": len(all_episodes),
        "autoposting": autoposting,
        "is_virtual": False,
        "status": "active"
    }
    database.upsert_douyin_collection(col_data)

    opaque_count = 0
    saved_count = 0

    for ep in all_episodes:
        dur = ep["duration_seconds"]
        is_compilation = False

        # Política de Duração > 5 min (300s)
        if dur > 300:
            # Se for > 10 min (600s) e já temos os episódios curtos de 3 min, ignora como resumo
            if dur > 600 and has_short_eps:
                status = "ignored"
                is_compilation = True
            else:
                status = "opaque_over_5min"
                opaque_count += 1
        else:
            status = "pending"

        ep["status"] = status
        ep["is_compilation"] = is_compilation

        if database.upsert_collection_episode(ep):
            saved_count += 1

    return {
        "ok": True,
        "mix_id": mix_id,
        "title_pt": col_data["title_pt"],
        "title_zh": mix_name,
        "author": author_name,
        "total_mapped": len(all_episodes),
        "saved_count": saved_count,
        "opaque_count": opaque_count,
        "message": f"Coleção '{col_data['title_pt']}' mapeada com sucesso! {len(all_episodes)} episódios ({opaque_count} requerem ação por >5min)."
    }
