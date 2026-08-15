"""
Database Manager — Post Recap & Agendador de Publicações (PostgreSQL Neon)
Gerencia logs de publicações, fila do Instagram e posts agendados unificados.
"""

import os
import logging
from datetime import datetime
import psycopg2.extras
from shared.db_connection import DBConnectionContext, get_connection, release_connection

logger = logging.getLogger("postrecap.db")

def init_db():
    """Garante que as tabelas do post recap estejam criadas no Neon."""
    from shared.schema_init import init_all_schemas
    init_all_schemas()

def log_post(video_path, youtube_title, tiktok_title, instagram_caption,
             youtube_status='skipped', tiktok_status='skipped', instagram_status='skipped'):
    """Registra uma publicação no histórico."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO postrecap_post_logs (
                    video_path, youtube_title, tiktok_title, instagram_caption, 
                    youtube_status, tiktok_status, instagram_status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (video_path, youtube_title, tiktok_title, instagram_caption, 
                  youtube_status, tiktok_status, instagram_status))
            row = cursor.fetchone()
            return row[0] if row else None

def update_post_status(post_id, platform, status, url=None, error=None):
    """Atualiza o status de postagem para uma plataforma específica (youtube, tiktok, instagram)."""
    if platform not in ['youtube', 'tiktok', 'instagram']:
        raise ValueError("Plataforma inválida para atualização de status.")
        
    status_field = f"{platform}_status"
    url_field = f"{platform}_url"
    
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            if url:
                cursor.execute(f"""
                    UPDATE postrecap_post_logs 
                    SET {status_field} = %s, {url_field} = %s, error_message = %s, updated_at = NOW()
                    WHERE id = %s
                """, (status, url, error, post_id))
            else:
                cursor.execute(f"""
                    UPDATE postrecap_post_logs 
                    SET {status_field} = %s, error_message = %s, updated_at = NOW()
                    WHERE id = %s
                """, (status, error, post_id))

def add_to_instagram_queue(video_drive_path, caption, cover_drive_path, scheduled_time):
    """Adiciona um vídeo à fila do Instagram."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO postrecap_instagram_queue (
                    video_drive_path, caption, cover_drive_path, scheduled_time
                ) VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (video_drive_path, caption, cover_drive_path, scheduled_time))
            row = cursor.fetchone()
            return row[0] if row else None

def get_pending_instagram_jobs():
    """Retorna itens pendentes cuja data agendada já passou."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, video_drive_path, caption, cover_drive_path, scheduled_time
                FROM postrecap_instagram_queue
                WHERE status = 'pending' AND scheduled_time <= NOW()
            """)
            return cursor.fetchall()

def update_queue_status(queue_id, status, error=None):
    """Atualiza o status de um item na fila do Instagram."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE postrecap_instagram_queue
                SET status = %s, error_message = %s
                WHERE id = %s
            """, (status, error, queue_id))

def add_scheduled_post(video_path, thumbnail_youtube, thumbnail_tiktok,
                       title_youtube, title_shorts, tiktok_caption, instagram_caption,
                       post_youtube, post_shorts, post_tiktok, post_instagram,
                       tiktok_privacy, scheduled_time, shorts_description="", youtube_tags=""):
    """Adiciona um post programado para múltiplas plataformas."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO postrecap_scheduled_posts (
                    video_path, thumbnail_youtube, thumbnail_tiktok,
                    title_youtube, title_shorts, tiktok_caption, instagram_caption,
                    post_youtube, post_shorts, post_tiktok, post_instagram,
                    tiktok_privacy, scheduled_time, shorts_description, youtube_tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (video_path, thumbnail_youtube, thumbnail_tiktok,
                  title_youtube, title_shorts, tiktok_caption, instagram_caption,
                  bool(post_youtube), bool(post_shorts), bool(post_tiktok), bool(post_instagram),
                  tiktok_privacy, scheduled_time, shorts_description, youtube_tags))
            row = cursor.fetchone()
            return row[0] if row else None

def get_pending_scheduled_posts():
    """Retorna os posts programados prontos para serem publicados agora."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, video_path, thumbnail_youtube, thumbnail_tiktok,
                       title_youtube, title_shorts, tiktok_caption, instagram_caption,
                       post_youtube, post_shorts, post_tiktok, post_instagram,
                       tiktok_privacy, scheduled_time, shorts_description, youtube_tags
                FROM postrecap_scheduled_posts
                WHERE status = 'pending' AND scheduled_time <= NOW()
            """)
            return cursor.fetchall()

def update_scheduled_post_status(post_id, status, error=None):
    """Atualiza o status de um post programado."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE postrecap_scheduled_posts
                SET status = %s, error_message = %s
                WHERE id = %s
            """, (status, error, post_id))

def get_all_pending_scheduled():
    """Retorna todos os posts programados futuros ou falhos."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, scheduled_time, title_youtube, title_shorts, tiktok_caption,
                       post_youtube, post_shorts, post_tiktok, post_instagram, status
                FROM postrecap_scheduled_posts
                WHERE status = 'pending' OR status = 'failed'
                ORDER BY scheduled_time ASC
            """)
            return cursor.fetchall()

def delete_scheduled_post(post_id):
    """Remove um post programado."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT video_path, thumbnail_youtube, thumbnail_tiktok
                FROM postrecap_scheduled_posts
                WHERE id = %s
            """, (post_id,))
            row = cursor.fetchone()
            if row:
                cursor.execute("DELETE FROM postrecap_scheduled_posts WHERE id = %s", (post_id,))
            return row
