import os
import re
import time
import httpx
import logging
from datetime import datetime
from scrapper import database

logger = logging.getLogger(__name__)

def clean_html_tags(text: str) -> str:
    """Remove as tags HTML como <em class="keyword"> da string retornada pelo Bilibili."""
    return re.sub(r'<[^>]*>', '', text)

def duration_str_to_seconds(dur_str: str) -> int:
    """Converte strings de duração do Bilibili (ex: '4:44', '01:23:45') em segundos."""
    try:
        parts = list(map(int, dur_str.split(":")))
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        return 0
    except:
        return 0

async def fetch_bilibili_search_videos(keyword: str, max_pages: int = 3) -> list:
    """
    Busca vídeos no Bilibili de forma pública usando sessão com cookies automáticos.
    Não exige login ou WBI signatures complexas.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    
    results = []
    
    # Usando httpx.AsyncClient para manter cookies de visitante
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        try:
            logger.info("Coletando cookies do Bilibili na home page...")
            await client.get("https://www.bilibili.com/")
        except Exception as ec:
            logger.warning(f"Falha ao coletar cookies de visitante na home do Bilibili: {ec}")
            
        import time
        now_ts = int(time.time())
        one_week_ago_ts = now_ts - (7 * 24 * 3600)
        
        search_url = "https://api.bilibili.com/x/web-interface/search/type"
        
        for page in range(1, max_pages + 1):
            params = {
                "search_type": "video",
                "keyword": keyword,
                "order": "totalrank",                     # Classificação abrangente
                "duration": "1",                          # Menos de 10 min
                "pubtime_begin_s": str(one_week_ago_ts),  # Início dos últimos 7 dias
                "pubtime_end_s": str(now_ts),              # Fim (atual)
                "tids": "0",
                "page": str(page)
            }
            try:
                logger.info(f"Buscando termo '{keyword}' no Bilibili - Página {page}...")
                response = await client.get(search_url, params=params)
                if response.status_code != 200:
                    logger.error(f"Erro HTTP {response.status_code} na busca do Bilibili")
                    break
                    
                data = response.json()
                if data.get("code") != 0:
                    logger.error(f"Erro na API de busca do Bilibili (code={data.get('code')}): {data.get('message')}")
                    break
                    
                videos = data.get("data", {}).get("result", [])
                if not videos:
                    logger.info("Nenhum vídeo adicional retornado.")
                    break
                    
                for v in videos:
                    bvid = v.get("bvid")
                    title = clean_html_tags(v.get("title", ""))
                    author = v.get("author", "Desconhecido")
                    pic = v.get("pic", "")
                    # Garante esquema HTTPS para a URL da capa
                    if pic and pic.startswith("//"):
                        pic = "https:" + pic
                        
                    duration_str = v.get("duration", "00:00")
                    duration_secs = duration_str_to_seconds(duration_str)
                    
                    # Views e Likes
                    views = int(v.get("play", 0))
                    likes = int(v.get("like", 0))
                    
                    # Score de Hype
                    hype_score = views + likes * 5
                    
                    pubdate = v.get("pubdate")
                    pubdate_dt = None
                    if pubdate:
                        try:
                            pubdate_dt = datetime.fromtimestamp(pubdate).strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            pass
                            
                    results.append({
                        "bvid": bvid,
                        "title": title,
                        "author": author,
                        "pic": pic,
                        "duration_seconds": duration_secs,
                        "views": views,
                        "likes": likes,
                        "hype_score": hype_score,
                        "published_at": pubdate_dt
                    })
            except Exception as e:
                logger.error(f"Erro ao buscar página {page}: {e}")
                break
                
    return results

async def run_single_scraping(keyword: str, content_type: str) -> tuple[int, list[str]]:
    """Roda a busca para um termo e tipo de conteúdo específicos e grava no banco."""
    logger.info(f"Executando busca no Bilibili por '{keyword}' ({content_type})...")
    raw_videos = await fetch_bilibili_search_videos(keyword, max_pages=3)
    if not raw_videos:
        logger.warning(f"Nenhum resultado obtido na busca por '{keyword}' ({content_type}).")
        return 0, []
        
    filtered_videos = []
    now_ts = time.time()
    one_week_secs = 7 * 24 * 3600
    
    for v in raw_videos:
        pubdate_dt = datetime.strptime(v["published_at"], "%Y-%m-%d %H:%M:%S") if v["published_at"] else None
        pubdate_ts = pubdate_dt.timestamp() if pubdate_dt else 0
        
        is_recent = (now_ts - pubdate_ts <= one_week_secs)
        is_under_10min = (v["duration_seconds"] < 600)
        
        if is_recent and is_under_10min:
            filtered_videos.append(v)
            
    logger.info(f"Filtro para '{keyword}': {len(filtered_videos)}/{len(raw_videos)} vídeos atendem aos critérios.")
    
    inserted = database.add_search_results(filtered_videos, content_type=content_type)
    logger.info(f"Triagem atualizada para '{content_type}': {inserted} novos vídeos adicionados.")
    
    # Coleta todos os bvids encontrados nesta busca
    bvids_found = [v["bvid"] for v in filtered_videos]
    return inserted, bvids_found

async def run_search_scraping():
    """
    Roda o fluxo completo de busca geral no Bilibili para todos os termos de busca cadastrados.
    """
    logger.info("Iniciando cron job de busca geral...")
    
    # Limpa resultados de busca antigos expirados (mais de 14 dias pendentes) para poupar espaço
    database.clear_old_search_results(days=14)
    
    anime_terms = database.get_search_terms("anime")
    manhwa_terms = database.get_search_terms("manhwa")
    
    # Fallbacks de segurança caso não existam termos no banco
    if not anime_terms:
        anime_terms = [{"term": "新番解说"}]
    if not manhwa_terms:
        manhwa_terms = [{"term": "韩漫解说"}]
        
    inserted_anime = 0
    active_anime_bvids = []
    for item in anime_terms:
        try:
            inserted, bvids = await run_single_scraping(item["term"], "anime")
            inserted_anime += inserted
            active_anime_bvids.extend(bvids)
        except Exception as e:
            logger.error(f"Erro ao buscar termo '{item['term']}' (anime): {e}")
        
    # Limpeza de vídeos de anime ausentes na busca atual
    if active_anime_bvids:
        deleted = database.delete_absent_search_results(active_anime_bvids, "anime")
        logger.info(f"Limpeza de triagem anime: {deleted} vídeos ausentes removidos de pendentes.")

    inserted_manhwa = 0
    active_manhwa_bvids = []
    for item in manhwa_terms:
        try:
            inserted, bvids = await run_single_scraping(item["term"], "manhwa")
            inserted_manhwa += inserted
            active_manhwa_bvids.extend(bvids)
        except Exception as e:
            logger.error(f"Erro ao buscar termo '{item['term']}' (manhwa): {e}")
            
    # Limpeza de vídeos de manhwa ausentes na busca atual
    if active_manhwa_bvids:
        deleted = database.delete_absent_search_results(active_manhwa_bvids, "manhwa")
        logger.info(f"Limpeza de triagem manhwa: {deleted} vídeos ausentes removidos de pendentes.")
        
    total_inserted = inserted_anime + inserted_manhwa
    logger.info(f"Busca geral concluída. Total de novos vídeos inseridos: {total_inserted}")
    return total_inserted


async def get_latest_video_for_channel(uid: str) -> dict | None:
    """Busca o vídeo mais recente postado por um canal (usado para referência inicial)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    from scrapper.config import DOUYIN_API_BASE
    api_url = f"{DOUYIN_API_BASE}/api/bilibili/web/fetch_user_post_videos"
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
        try:
            logger.info(f"Buscando vídeo mais recente do canal UID {uid} para referência...")
            response = await client.get(api_url, params={"uid": uid, "pn": 1})
            if response.status_code != 200:
                logger.error(f"Erro HTTP {response.status_code} na busca do canal UID {uid}")
                return None
                
            res_json = response.json()
            if res_json.get("code") != 200:
                logger.error(f"Erro na API Bilibili (code={res_json.get('code')}) para UID {uid}")
                return None
                
            # A API local envelopa o retorno do Bilibili na chave "data", e o Bilibili usa "data" internamente.
            vlist = res_json.get("data", {}).get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                logger.info(f"Nenhum vídeo retornado para UID {uid}")
                return None
                
            # O primeiro item é o mais recente
            video = vlist[0]
            pic = video.get("pic", "")
            if pic and pic.startswith("//"):
                pic = "https:" + pic
                
            return {
                "bvid": video.get("bvid"),
                "title": video.get("title"),
                "pic": pic,
                "created": video.get("created"),
                "length": video.get("length", "00:00")
            }
        except Exception as e:
            logger.error(f"Erro ao obter postagens do canal UID {uid}: {e}")
            return None

async def track_channels_updates(content_type: str) -> int:
    """Varre todos os canais de um content_type buscando novas postagens desde a última referência."""
    logger.info(f"Iniciando varredura de canais para {content_type}...")
    
    channels = database.get_channels(content_type=content_type)
    if not channels:
        logger.info(f"Nenhum canal cadastrado para {content_type}.")
        return 0
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bilibili.com/"
    }
    from scrapper.config import DOUYIN_API_BASE
    api_url = f"{DOUYIN_API_BASE}/api/bilibili/web/fetch_user_post_videos"
    
    total_new_updates = 0
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
        for ch in channels:
            uid = ch["uid"]
            name = ch["name"]
            last_ref = ch.get("last_video_ref")
            
            try:
                logger.info(f"Rastreando novos vídeos de: {name} (UID: {uid}) - Ref Atual: {last_ref}")
                response = await client.get(api_url, params={"uid": uid, "pn": 1})
                
                if response.status_code != 200:
                    logger.error(f"Erro HTTP {response.status_code} para canal {name}")
                    continue
                    
                res_json = response.json()
                if res_json.get("code") != 200:
                    logger.error(f"Erro na API (code={res_json.get('code')}) para canal {name}")
                    continue
                    
                # A API local envelopa o retorno do Bilibili na chave "data", e o Bilibili usa "data" internamente.
                vlist = res_json.get("data", {}).get("data", {}).get("list", {}).get("vlist", [])
                if not vlist:
                    logger.info(f"Canal {name} não possui postagens ou a lista está vazia.")
                    continue
                
                # Caso o canal não tenha referência (novo canal):
                if not last_ref:
                    # Define o vídeo mais recente como a referência inicial
                    new_ref = vlist[0].get("bvid")
                    if new_ref:
                        database.update_channel_ref(uid, new_ref)
                        logger.info(f"Canal {name} inicializado com last_video_ref = {new_ref} (Sem adicionar atualizações).")
                    continue
                
                # Rastreamento de postagens novas
                new_videos = []
                for video in vlist:
                    bvid = video.get("bvid")
                    if not bvid:
                        continue
                        
                    # Se encontrarmos o último vídeo de referência, paramos (os anteriores são mais antigos)
                    if bvid == last_ref:
                        break
                        
                    new_videos.append(video)
                
                if new_videos:
                    logger.info(f"Detectados {len(new_videos)} novos vídeos para o canal {name}.")
                    
                    # Insere os novos vídeos no banco como channel_updates
                    for video in new_videos:
                        bvid = video.get("bvid")
                        title = video.get("title", "")
                        pic = video.get("pic", "")
                        if pic and pic.startswith("//"):
                            pic = "https:" + pic
                            
                        length_str = video.get("length", "00:00")
                        duration_seconds = duration_str_to_seconds(length_str)
                        
                        # Views e Likes
                        views = int(video.get("play", 0))
                        likes = int(video.get("comment", 0)) # comentário usado como proxy de likes
                        
                        created_ts = video.get("created")
                        pub_date = None
                        if created_ts:
                            try:
                                pub_date = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                pass
                                
                        success = database.add_channel_update(
                            bvid=bvid,
                            title=title,
                            author=name, # nome do canal
                            pic=pic,
                            duration_seconds=duration_seconds,
                            views=views,
                            likes=likes,
                            published_at=pub_date,
                            content_type=content_type,
                            channel_uid=uid
                        )
                        if success:
                            total_new_updates += 1
                            
                    # Atualiza a referência do canal para o vídeo mais recente retornado
                    most_recent_bvid = vlist[0].get("bvid")
                    if most_recent_bvid:
                        database.update_channel_ref(uid, most_recent_bvid)
                        logger.info(f"Referência do canal {name} atualizada para {most_recent_bvid}")
                else:
                    logger.info(f"Nenhuma postagem nova para o canal {name}.")
                    
            except Exception as e:
                logger.error(f"Erro ao mapear canal {name}: {e}")
                continue
                
    logger.info(f"Varredura de canais finalizada para {content_type}. Total de novas postagens: {total_new_updates}")
    return total_new_updates


async def populate_missing_channel_references() -> int:
    """Busca e define o vídeo de referência para todos os canais que estão com a coluna nula ou vazia."""
    logger.info("Iniciando verificação de canais sem vídeo de referência...")
    channels = database.get_channels()
    updated_count = 0
    
    channels_to_update = [c for c in channels if not c.get("last_video_ref")]
    if not channels_to_update:
        logger.info("Todos os canais cadastrados já possuem vídeo de referência.")
        return 0
        
    logger.info(f"Encontrados {len(channels_to_update)} canais sem referência de vídeo inicial.")
    for ch in channels_to_update:
        uid = ch["uid"]
        name = ch["name"]
        try:
            logger.info(f"Buscando vídeo de referência para canal: {name} (UID: {uid})")
            latest_video = await get_latest_video_for_channel(uid)
            if latest_video and latest_video.get("bvid"):
                new_ref = latest_video["bvid"]
                database.update_channel_ref(uid, new_ref)
                logger.info(f"Canal '{name}' atualizado com a referência: {new_ref}")
                updated_count += 1
            else:
                logger.warning(f"Não foi possível obter o último vídeo para o canal '{name}' (UID: {uid}). A API pode estar indisponível ou o UID é inválido.")
        except Exception as e:
            logger.error(f"Erro ao preencher referência para o canal '{name}' (UID: {uid}): {e}")
            
    logger.info(f"Preenchimento de referências concluído. {updated_count} canais atualizados.")
    return updated_count


