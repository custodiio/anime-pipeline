"""
Database Manager — Scrapper Douyin & Bilibili (PostgreSQL Neon)
Armazena metadados, status e links de vídeos coletados.
"""

import os
import json
import logging
from datetime import datetime, timedelta
import psycopg2.extras

from shared.db_connection import DBConnectionContext, get_connection, release_connection

logger = logging.getLogger("scrapper.database")


def get_db_connection():
    """Retorna uma conexão com RealDictCursor para compatibilidade."""
    conn = get_connection()
    return conn


def init_db():
    """Garante que as tabelas do scrapper estejam criadas no Neon."""
    from shared.schema_init import init_all_schemas
    init_all_schemas()


# ----------------- OPERAÇÕES DE CANAIS -----------------

def add_channel(uid, name, category="all", content_type="anime", last_video_ref=None):
    """Adiciona um novo canal para monitoramento."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_channels (uid, name, category, content_type, last_video_ref)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (uid) DO UPDATE SET
                        name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        content_type = EXCLUDED.content_type,
                        last_video_ref = COALESCE(EXCLUDED.last_video_ref, scrapper_channels.last_video_ref);
                """, (str(uid).strip(), name.strip(), category, content_type, last_video_ref))
                return True
            except Exception as e:
                logger.error(f"Erro ao adicionar canal: {e}")
                return False

def remove_channel(uid):
    """Remove um canal."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_channels WHERE uid = %s", (str(uid).strip(),))
                return True
            except Exception as e:
                logger.error(f"Erro ao remover canal: {e}")
                return False

def get_channels(category=None, content_type=None):
    """Retorna a lista de canais."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if content_type:
                cursor.execute("""
                    SELECT * FROM scrapper_channels 
                    WHERE content_type = %s
                    ORDER BY name ASC
                """, (content_type,))
            else:
                cursor.execute("SELECT * FROM scrapper_channels ORDER BY name ASC")
            return [dict(row) for row in cursor.fetchall()]


# ----------------- OPERAÇÕES DE HISTÓRICO DE VÍDEOS (FILA / MAPS) -----------------

def is_video_processed(bvid):
    """Verifica se um vídeo já foi mapeado/processado."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM scrapper_processed_videos WHERE bvid = %s", (bvid,))
            return cursor.fetchone() is not None

def register_video(bvid, title, channel_uid=None, source="channel", category="shorts", content_type="anime", status="pending", published_at=None):
    """Registra um vídeo no histórico."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_processed_videos (bvid, title, channel_uid, source, category, content_type, status, published_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bvid) DO UPDATE SET
                        title = EXCLUDED.title,
                        category = EXCLUDED.category,
                        content_type = EXCLUDED.content_type,
                        status = EXCLUDED.status;
                """, (bvid, title, channel_uid, source, category, content_type, status, published_at))
                return True
            except Exception as e:
                logger.error(f"Erro ao registrar vídeo: {e}")
                return False

def get_pending_videos(category, content_type):
    """Retorna os vídeos prontos (baixados) para postagem."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT pv.*, c.name as channel_name 
                FROM scrapper_processed_videos pv
                LEFT JOIN scrapper_channels c ON pv.channel_uid = c.uid
                WHERE pv.category = %s AND pv.content_type = %s AND pv.status = 'downloaded'
                ORDER BY pv.created_at ASC
            """, (category, content_type))
            return [dict(row) for row in cursor.fetchall()]

def get_unposted_videos(category, content_type):
    """Retorna todos os vídeos que ainda não foram postados."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT pv.*, c.name as channel_name 
                FROM scrapper_processed_videos pv
                LEFT JOIN scrapper_channels c ON pv.channel_uid = c.uid
                WHERE pv.category = %s AND pv.content_type = %s AND pv.status != 'posted'
                ORDER BY CASE WHEN pv.status = 'downloaded' THEN 0 ELSE 1 END, pv.created_at ASC
            """, (category, content_type))
            return [dict(row) for row in cursor.fetchall()]

def mark_video_as_posted(bvid):
    """Marca um vídeo como postado."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    UPDATE scrapper_processed_videos 
                    SET status = 'posted', posted_at = NOW()
                    WHERE bvid = %s
                """, (bvid,))
                return True
            except Exception as e:
                logger.error(f"Erro ao marcar vídeo como postado: {e}")
                return False

def update_video_status(bvid, status):
    """Atualiza o status de um vídeo em scrapper_processed_videos."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_processed_videos SET status = %s WHERE bvid = %s", (status, bvid))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar status do vídeo: {e}")
                return False

def get_video_by_bvid(bvid):
    """Retorna os dados de um vídeo pelo bvid."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM scrapper_processed_videos WHERE bvid = %s", (bvid,))
            row = cursor.fetchone()
            return dict(row) if row else None

def remove_video_from_queue(bvid):
    """Remove o vídeo da fila."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_processed_videos WHERE bvid = %s", (bvid,))
                return True
            except Exception as e:
                logger.error(f"Erro ao deletar vídeo da fila: {e}")
                return False

def get_posted_videos_count_since(days=7):
    """Retorna a quantidade de vídeos postados nos últimos X dias."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT COUNT(*) as count FROM scrapper_processed_videos 
                WHERE status = 'posted' AND posted_at >= NOW() - INTERVAL '%s days'
            """, (days,))
            row = cursor.fetchone()
            return row["count"] if row else 0

def get_downloaded_count_since_last_post(category, content_type):
    """Retorna quantos vídeos foram baixados desde a última postagem."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT posted_at FROM scrapper_processed_videos 
                WHERE category = %s AND content_type = %s AND status = 'posted'
                ORDER BY posted_at DESC LIMIT 1
            """, (category, content_type))
            row = cursor.fetchone()
            
            if row and row["posted_at"]:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM scrapper_processed_videos 
                    WHERE category = %s AND content_type = %s AND status = 'downloaded' AND created_at > %s
                """, (category, content_type, row["posted_at"]))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as count FROM scrapper_processed_videos 
                    WHERE category = %s AND content_type = %s AND status = 'downloaded'
                """, (category, content_type))
                
            res = cursor.fetchone()
            return res["count"] if res else 0


# ----------------- OPERAÇÕES DE BUSCA GERAL (TRIAGEM WEB) -----------------

def add_search_results(results, content_type="anime"):
    """Adiciona novos resultados da busca geral na tabela de triagem."""
    inserted = 0
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            for r in results:
                try:
                    cursor.execute("""
                        INSERT INTO scrapper_search_results (
                            bvid, title, author, pic, duration_seconds, views, likes, hype_score, published_at, status, content_type
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                        ON CONFLICT (bvid) DO NOTHING;
                    """, (
                        r["bvid"], r["title"], r["author"], r["pic"], r["duration_seconds"],
                        r["views"], r["likes"], r["hype_score"], r.get("published_at"), content_type
                    ))
                    if cursor.rowcount > 0:
                        inserted += 1
                except Exception as e:
                    logger.error(f"Erro ao inserir resultado de busca {r.get('bvid')}: {e}")
    return inserted

def get_search_results(status="pending", content_type="anime"):
    """Retorna os resultados de busca para triagem ordenados pelo Hype Score."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM scrapper_search_results 
                WHERE status = %s AND content_type = %s
                ORDER BY hype_score DESC, published_at DESC
            """, (status, content_type))
            return [dict(row) for row in cursor.fetchall()]

def update_search_result_status(bvid, status):
    """Atualiza o status de triagem do vídeo."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_search_results SET status = %s WHERE bvid = %s", (status, bvid))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar status de triagem: {e}")
                return False

def clear_old_search_results(days=14):
    """Remove resultados de busca pendentes mais antigos que X dias."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_search_results WHERE status = 'pending' AND created_at < NOW() - INTERVAL '%s days'", (days,))
                return True
            except Exception as e:
                logger.error(f"Erro ao limpar buscas antigas: {e}")
                return False

def delete_absent_search_results(active_bvids, content_type="anime"):
    """Remove resultados de busca pendentes que não estão na lista de bvids coletados."""
    if not active_bvids:
        return 0
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    DELETE FROM scrapper_search_results 
                    WHERE status = 'pending' 
                      AND content_type = %s 
                      AND bvid != ALL(%s)
                """, (content_type, list(active_bvids)))
                return cursor.rowcount
            except Exception as e:
                logger.error(f"Erro ao remover resultados ausentes: {e}")
                return 0

def update_channel_ref(uid, last_video_ref):
    """Atualiza a referência do último vídeo processado do canal."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_channels SET last_video_ref = %s WHERE uid = %s", (last_video_ref, str(uid).strip()))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar referência do canal: {e}")
                return False


# ----------------- OPERAÇÕES DE ATUALIZAÇÕES DOS CANAIS -----------------

def add_channel_update(bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid):
    """Adiciona uma nova postagem de canal para triagem temporária."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_channel_updates (
                        bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                    ON CONFLICT (bvid) DO NOTHING;
                """, (bvid, title, author, pic, duration_seconds, views, likes, published_at, content_type, channel_uid))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Erro ao adicionar atualização de canal: {e}")
                return False

def get_channel_updates(status="pending", content_type="anime"):
    """Retorna as atualizações recentes de canais pendentes de triagem."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("""
                SELECT * FROM scrapper_channel_updates 
                WHERE status = %s AND content_type = %s
                ORDER BY published_at DESC, created_at DESC
            """, (status, content_type))
            return [dict(row) for row in cursor.fetchall()]

def update_channel_update_status(bvid, status):
    """Atualiza o status do vídeo do canal."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_channel_updates SET status = %s WHERE bvid = %s", (status, bvid))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar status do update de canal: {e}")
                return False

def remove_channel_update(bvid):
    """Remove a atualização de canal."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_channel_updates WHERE bvid = %s", (bvid,))
                return True
            except Exception as e:
                logger.error(f"Erro ao remover update do canal: {e}")
                return False


# ----------------- OPERAÇÕES DE TERMOS DE BUSCA -----------------

def add_search_term(term, content_type):
    """Adiciona um novo termo de busca."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_search_terms (term, content_type)
                    VALUES (%s, %s)
                    ON CONFLICT (term, content_type) DO NOTHING;
                """, (term.strip(), content_type.strip()))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Erro ao adicionar termo de busca: {e}")
                return False

def remove_search_term(term_id):
    """Remove um termo de busca pelo ID."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_search_terms WHERE id = %s", (term_id,))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Erro ao remover termo de busca: {e}")
                return False

def get_search_terms(content_type=None):
    """Retorna os termos de busca cadastrados."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            if content_type:
                cursor.execute("SELECT * FROM scrapper_search_terms WHERE content_type = %s ORDER BY term ASC", (content_type,))
            else:
                cursor.execute("SELECT * FROM scrapper_search_terms ORDER BY content_type, term ASC")
            return [dict(row) for row in cursor.fetchall()]


# ----------------- OPERAÇÕES DE SESSÃO WEB -----------------

def create_web_session(token, duration_minutes=30):
    """Cria uma nova sessão web ativa."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_web_sessions (token, expires_at)
                    VALUES (%s, NOW() + INTERVAL '%s minutes')
                    ON CONFLICT (token) DO UPDATE SET expires_at = EXCLUDED.expires_at;
                """, (token, duration_minutes))
                cleanup_expired_sessions()
                return True
            except Exception as e:
                logger.error(f"Erro ao criar sessão web: {e}")
                return False

def validate_web_session(token):
    """Verifica se a sessão é válida e não está expirada."""
    if not token:
        return False
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT 1 FROM scrapper_web_sessions WHERE token = %s AND expires_at > NOW()", (token,))
                return cursor.fetchone() is not None
            except Exception as e:
                logger.error(f"Erro ao validar sessão web: {e}")
                return False

def renew_web_session(token, duration_minutes=30):
    """Estende a expiração de uma sessão ativa."""
    if not token:
        return False
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    UPDATE scrapper_web_sessions 
                    SET expires_at = NOW() + INTERVAL '%s minutes' 
                    WHERE token = %s AND expires_at > NOW()
                """, (duration_minutes, token))
                return cursor.rowcount > 0
            except Exception as e:
                logger.error(f"Erro ao renovar sessão web: {e}")
                return False

def cleanup_expired_sessions():
    """Remove sessões expiradas."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_web_sessions WHERE expires_at <= NOW()")
                return True
            except Exception as e:
                logger.error(f"Erro ao limpar sessões expiradas: {e}")
                return False


# ----------------- OPERAÇÕES DE CONFIGURAÇÕES -----------------

def get_user_setting(key: str, default: str = None) -> str:
    """Retorna o valor de uma configuração em user_settings."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("SELECT value FROM scrapper_user_settings WHERE key = %s", (key,))
                row = cursor.fetchone()
                return row["value"] if row else default
            except Exception as e:
                logger.error(f"Erro ao obter configuração '{key}': {e}")
                return default

def set_user_setting(key: str, value: str) -> bool:
    """Define/atualiza o valor de uma configuração em user_settings."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_user_settings (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
                """, (key, str(value)))
                return True
            except Exception as e:
                logger.error(f"Erro ao salvar configuração '{key}': {e}")
                return False


# ----------------- OPERAÇÕES DE COLEÇÕES DO DOUYIN -----------------

def upsert_douyin_collection(col: dict) -> bool:
    """Insere ou atualiza uma coleção do Douyin no banco."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_douyin_collections (
                        mix_id, title_pt, title_zh, author, cover_url, total_episodes, autoposting, is_virtual, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mix_id) DO UPDATE SET
                        title_pt = COALESCE(EXCLUDED.title_pt, scrapper_douyin_collections.title_pt),
                        title_zh = COALESCE(EXCLUDED.title_zh, scrapper_douyin_collections.title_zh),
                        author = COALESCE(EXCLUDED.author, scrapper_douyin_collections.author),
                        cover_url = COALESCE(EXCLUDED.cover_url, scrapper_douyin_collections.cover_url),
                        total_episodes = GREATEST(EXCLUDED.total_episodes, scrapper_douyin_collections.total_episodes),
                        autoposting = EXCLUDED.autoposting,
                        status = EXCLUDED.status;
                """, (
                    str(col["mix_id"]),
                    col.get("title_pt", col.get("title_zh", f"Coleção #{col['mix_id']}")),
                    col.get("title_zh", ""),
                    col.get("author", "Desconhecido"),
                    col.get("cover_url", ""),
                    col.get("total_episodes", 0),
                    1 if col.get("autoposting", True) else 0,
                    1 if col.get("is_virtual", False) else 0,
                    col.get("status", "active")
                ))
                return True
            except Exception as e:
                logger.error(f"Erro ao inserir/atualizar coleção {col.get('mix_id')}: {e}")
                return False

def get_douyin_collections(status_filter: str = None) -> list[dict]:
    """Retorna todas as coleções cadastradas com estatísticas de episódios."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                query = """
                    SELECT 
                        c.*,
                        COUNT(e.id) as total_episodes_mapped,
                        SUM(CASE WHEN e.status IN ('posted', 'published', 'completed') THEN 1 ELSE 0 END) as posted_count,
                        SUM(CASE WHEN e.status = 'opaque_over_5min' THEN 1 ELSE 0 END) as opaque_count
                    FROM scrapper_douyin_collections c
                    LEFT JOIN scrapper_collection_episodes e ON c.mix_id = e.mix_id
                """
                params = []
                if status_filter:
                    query += " WHERE c.status = %s"
                    params.append(status_filter)

                query += " GROUP BY c.mix_id ORDER BY c.created_at DESC"
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Erro ao buscar coleções do Douyin: {e}")
                return []

def get_douyin_collection_by_id(mix_id: str) -> dict | None:
    """Retorna uma coleção específica pelo mix_id."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("""
                    SELECT 
                        c.*,
                        COUNT(e.id) as total_episodes_mapped,
                        SUM(CASE WHEN e.status IN ('posted', 'published', 'completed') THEN 1 ELSE 0 END) as posted_count,
                        SUM(CASE WHEN e.status = 'opaque_over_5min' THEN 1 ELSE 0 END) as opaque_count
                    FROM scrapper_douyin_collections c
                    LEFT JOIN scrapper_collection_episodes e ON c.mix_id = e.mix_id
                    WHERE c.mix_id = %s
                    GROUP BY c.mix_id
                """, (str(mix_id),))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Erro ao buscar coleção {mix_id}: {e}")
                return None

def toggle_collection_autoposting(mix_id: str, new_state: bool = None) -> bool:
    """Inverte ou define o estado de autoposting (ON/OFF) da coleção."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                if new_state is None:
                    cursor.execute("UPDATE scrapper_douyin_collections SET autoposting = CASE WHEN autoposting = 1 THEN 0 ELSE 1 END WHERE mix_id = %s", (str(mix_id),))
                else:
                    val = 1 if new_state else 0
                    cursor.execute("UPDATE scrapper_douyin_collections SET autoposting = %s WHERE mix_id = %s", (val, str(mix_id)))
                return True
            except Exception as e:
                logger.error(f"Erro ao alterar autoposting da coleção {mix_id}: {e}")
                return False

def update_collection_cover(mix_id: str, cover_url: str) -> bool:
    """Atualiza a imagem de capa de uma coleção."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_douyin_collections SET cover_url = %s WHERE mix_id = %s", (cover_url, str(mix_id)))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar capa da coleção {mix_id}: {e}")
                return False

def delete_douyin_collection(mix_id: str) -> bool:
    """Deleta uma coleção e seus episódios do banco de dados."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_douyin_collections WHERE mix_id = %s", (str(mix_id),))
                return True
            except Exception as e:
                logger.error(f"Erro ao deletar coleção {mix_id}: {e}")
                return False


# ----------------- OPERAÇÕES DE EPISÓDIOS DA COLEÇÃO -----------------

def upsert_collection_episode(ep: dict) -> bool:
    """Insere ou atualiza um episódio de uma coleção."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_collection_episodes (
                        mix_id, episode_num, aweme_id, title, duration_seconds, likes, comments, cover_url, video_url, status, is_compilation
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (aweme_id) DO UPDATE SET
                        episode_num = COALESCE(EXCLUDED.episode_num, scrapper_collection_episodes.episode_num),
                        title = EXCLUDED.title,
                        duration_seconds = EXCLUDED.duration_seconds,
                        likes = EXCLUDED.likes,
                        comments = EXCLUDED.comments,
                        cover_url = COALESCE(EXCLUDED.cover_url, scrapper_collection_episodes.cover_url),
                        video_url = EXCLUDED.video_url,
                        is_compilation = EXCLUDED.is_compilation;
                """, (
                    str(ep["mix_id"]),
                    ep.get("episode_num"),
                    str(ep["aweme_id"]),
                    ep.get("title", ""),
                    ep.get("duration_seconds", 0),
                    ep.get("likes", 0),
                    ep.get("comments", 0),
                    ep.get("cover_url", ""),
                    ep.get("video_url", ""),
                    ep.get("status", "pending"),
                    1 if ep.get("is_compilation", False) else 0
                ))
                return True
            except Exception as e:
                logger.error(f"Erro ao inserir/atualizar episódio {ep.get('aweme_id')}: {e}")
                return False

def get_collection_episodes(mix_id: str) -> list[dict]:
    """Retorna todos os episódios de uma coleção."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("""
                    SELECT * FROM scrapper_collection_episodes
                    WHERE mix_id = %s
                    ORDER BY CASE WHEN episode_num IS NULL THEN 999999 ELSE episode_num END ASC, id ASC
                """, (str(mix_id),))
                return [dict(row) for row in cursor.fetchall()]
            except Exception as e:
                logger.error(f"Erro ao buscar episódios da coleção {mix_id}: {e}")
                return []

def get_episode_by_id(ep_id: int) -> dict | None:
    """Retorna um episódio pelo seu ID interno."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("SELECT * FROM scrapper_collection_episodes WHERE id = %s", (ep_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e:
                logger.error(f"Erro ao buscar episódio #{ep_id}: {e}")
                return None

def get_episodes_by_status(status: str) -> list:
    """Retorna todos os episódios com o status informado."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("SELECT * FROM scrapper_collection_episodes WHERE status = %s", (status,))
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            except Exception as e:
                logger.error(f"Erro ao buscar episódios com status '{status}': {e}")
                return []

def update_episode_status(ep_id: int, status: str, scheduled_at: str = None, posted_at: str = None) -> bool:
    """Atualiza o status e datas de um episódio."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                fields = ["status = %s"]
                params = [status]

                if scheduled_at:
                    fields.append("scheduled_at = %s")
                    params.append(scheduled_at)
                if posted_at:
                    fields.append("posted_at = %s")
                    params.append(posted_at)

                params.append(ep_id)
                query = f"UPDATE scrapper_collection_episodes SET {', '.join(fields)} WHERE id = %s"
                cursor.execute(query, params)
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar status do episódio #{ep_id}: {e}")
                return False

def update_episode_posting_guide(ep_id: int, guide_data) -> bool:
    """Salva o guia de postagem (título PT, descrição, hashtags) no episódio."""
    if isinstance(guide_data, (dict, list)):
        guide_json_str = json.dumps(guide_data, ensure_ascii=False)
    else:
        guide_json_str = str(guide_data)

    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("UPDATE scrapper_collection_episodes SET posting_guide = %s WHERE id = %s", (guide_json_str, ep_id))
                return True
            except Exception as e:
                logger.error(f"Erro ao atualizar guia de postagem do episódio #{ep_id}: {e}")
                return False


# ----------------- OPERAÇÕES DE PERFIS DOUYIN -----------------

def upsert_douyin_profile(sec_uid: str, nickname: str, avatar_url: str = "", profile_url: str = "") -> bool:
    """Insere ou atualiza um perfil monitorado do Douyin."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("""
                    INSERT INTO scrapper_douyin_profiles (sec_uid, nickname, avatar_url, profile_url, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (sec_uid) DO UPDATE SET
                        nickname = EXCLUDED.nickname,
                        avatar_url = EXCLUDED.avatar_url,
                        profile_url = EXCLUDED.profile_url,
                        updated_at = NOW();
                """, (sec_uid, nickname, avatar_url, profile_url))
                return True
            except Exception as e:
                logger.error(f"Erro ao inserir/atualizar perfil Douyin {sec_uid}: {e}")
                return False

def get_douyin_profiles() -> list[dict]:
    """Retorna todos os perfis monitorados do Douyin."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            try:
                cursor.execute("SELECT * FROM scrapper_douyin_profiles ORDER BY updated_at DESC")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Erro ao buscar perfis Douyin: {e}")
                return []

def delete_douyin_profile(sec_uid: str) -> bool:
    """Deleta um perfil do Douyin."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute("DELETE FROM scrapper_douyin_profiles WHERE sec_uid = %s", (sec_uid,))
                return True
            except Exception as e:
                logger.error(f"Erro ao deletar perfil Douyin {sec_uid}: {e}")
                return False
