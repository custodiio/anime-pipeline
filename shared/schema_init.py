"""
Schema Initialization — Criação das tabelas de todos os módulos no PostgreSQL Neon.
Garante isolamento via prefixos e armazenamento estrito de metadados/URLs/IDs (zero binários no banco).
"""

import logging
from .db_connection import DBConnectionContext

logger = logging.getLogger("shared.schema")

SCHEMA_SQL = """
-- ==============================================================================
-- 1. SCRAPPER DOUYIN & BILIBILI
-- ==============================================================================

CREATE TABLE IF NOT EXISTS scrapper_channels (
    id SERIAL PRIMARY KEY,
    uid TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    content_type TEXT NOT NULL,
    last_video_ref TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_processed_videos (
    bvid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_uid TEXT,
    source TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'shorts',
    content_type TEXT NOT NULL DEFAULT 'anime',
    status TEXT NOT NULL DEFAULT 'pending',
    published_at TIMESTAMPTZ,
    posted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_channel_updates (
    bvid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    pic TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    views INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    published_at TIMESTAMPTZ,
    content_type TEXT NOT NULL,
    channel_uid TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_search_results (
    bvid TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    pic TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    views INTEGER NOT NULL,
    likes INTEGER NOT NULL,
    hype_score INTEGER NOT NULL,
    published_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'pending',
    content_type TEXT NOT NULL DEFAULT 'anime',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_search_terms (
    id SERIAL PRIMARY KEY,
    term TEXT NOT NULL,
    content_type TEXT NOT NULL,
    UNIQUE(term, content_type)
);

CREATE TABLE IF NOT EXISTS scrapper_web_sessions (
    token TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_douyin_profiles (
    sec_uid TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    avatar_url TEXT,
    profile_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_douyin_collections (
    mix_id TEXT PRIMARY KEY,
    title_pt TEXT NOT NULL,
    title_zh TEXT,
    author TEXT,
    cover_url TEXT,
    total_episodes INTEGER DEFAULT 0,
    autoposting INTEGER DEFAULT 1,
    is_virtual INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrapper_collection_episodes (
    id SERIAL PRIMARY KEY,
    mix_id TEXT NOT NULL REFERENCES scrapper_douyin_collections(mix_id) ON DELETE CASCADE,
    episode_num INTEGER,
    aweme_id TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    duration_seconds INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    comments INTEGER DEFAULT 0,
    cover_url TEXT,
    video_url TEXT,
    status TEXT DEFAULT 'pending',
    is_compilation INTEGER DEFAULT 0,
    posting_guide TEXT,
    scheduled_at TIMESTAMPTZ,
    posted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- 2. POST RECAP & SCHEDULER
-- ==============================================================================

CREATE TABLE IF NOT EXISTS postrecap_post_logs (
    id SERIAL PRIMARY KEY,
    video_path TEXT,
    youtube_title TEXT,
    tiktok_title TEXT,
    instagram_caption TEXT,
    youtube_status TEXT DEFAULT 'skipped',
    tiktok_status TEXT DEFAULT 'skipped',
    instagram_status TEXT DEFAULT 'skipped',
    youtube_url TEXT,
    tiktok_url TEXT,
    instagram_url TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS postrecap_instagram_queue (
    id SERIAL PRIMARY KEY,
    video_drive_path TEXT,
    caption TEXT,
    cover_drive_path TEXT,
    scheduled_time TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS postrecap_scheduled_posts (
    id SERIAL PRIMARY KEY,
    video_path TEXT,
    thumbnail_youtube TEXT,
    thumbnail_tiktok TEXT,
    title_youtube TEXT,
    title_shorts TEXT,
    tiktok_caption TEXT,
    instagram_caption TEXT,
    post_youtube BOOLEAN DEFAULT FALSE,
    post_shorts BOOLEAN DEFAULT FALSE,
    post_tiktok BOOLEAN DEFAULT FALSE,
    post_instagram BOOLEAN DEFAULT FALSE,
    tiktok_privacy TEXT DEFAULT 'public',
    scheduled_time TIMESTAMPTZ NOT NULL,
    shorts_description TEXT,
    youtube_tags TEXT,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==============================================================================
-- 3. TIKTOK APPROVAL & USERS (COM REGRA GLOBAL DE APROVAÇÃO MANUAL)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS tiktok_approved_users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    approved INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tiktok_connections (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL REFERENCES tiktok_approved_users(email) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    open_id TEXT,
    username TEXT,
    avatar TEXT,
    connected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tiktok_youtube_connections (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL REFERENCES tiktok_approved_users(email) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    channel_id TEXT,
    channel_name TEXT,
    avatar TEXT,
    banner TEXT,
    connected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tiktok_audit_logs (
    id SERIAL PRIMARY KEY,
    user_email TEXT,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ==============================================================================
-- 4. SEO ANIME RECAP METADATA
-- ==============================================================================

CREATE TABLE IF NOT EXISTS seo_generated_posts (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    synopsis TEXT,
    tags TEXT,
    thumbnail_drive_id TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def init_all_schemas():
    """Executa o script DDL no Neon PostgreSQL para criar todas as tabelas necessárias."""
    with DBConnectionContext(autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            
            # Insere termos de busca padrão do scrapper se não existirem
            cur.execute("SELECT COUNT(*) FROM scrapper_search_terms;")
            row = cur.fetchone()
            if row and row[0] == 0:
                cur.execute("""
                    INSERT INTO scrapper_search_terms (term, content_type) 
                    VALUES ('新番解说', 'anime'), ('韩漫解说', 'manhwa')
                    ON CONFLICT DO NOTHING;
                """)
            
            # Insere configuração inicial de rate de postagem se não existir
            cur.execute("""
                INSERT INTO scrapper_user_settings (key, value)
                VALUES ('daily_post_rate', '2')
                ON CONFLICT (key) DO NOTHING;
            """)
            
    logger.info("Todos os schemas do PostgreSQL Neon foram inicializados com sucesso!")
    print("[SUCCESS] Todos os schemas do PostgreSQL Neon foram inicializados com sucesso!")

if __name__ == "__main__":
    init_all_schemas()
