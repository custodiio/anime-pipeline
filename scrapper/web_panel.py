import os
import re
import sys
import time
import httpx
import logging
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, Form, HTTPException, Request, Response, Cookie, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from scrapper import (
    database, search_scrapper, media_processor, drive_uploader,
    douyin_collection_scraper, episode_scheduler, douyin_profile_scraper, pipeline_integrator,
    translator
)
from scrapper.config import DOUYIN_API_BASE

logger = logging.getLogger(__name__)

ROOT_PATH = os.getenv("ROOT_PATH", "/scrapper")

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Douyin Scrapper & Vitrine", docs_url=None, redoc_url=None)

# Permite conexões CORS para frontends na Vercel e locais
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Localização da build compilada do Vite React (caso servido internamente)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIST = PROJECT_ROOT / "scrapper-frontend" / "dist"
if not FRONTEND_DIST.exists():
    FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    app.mount("/scrapper/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="scrapper_assets")


# --- ROTAS DE API PARA COLEÇÕES, PERFIS E CONFIGURAÇÕES ---

@app.get("/api/douyin/collections")
@app.get("/scrapper/api/douyin/collections")
async def get_douyin_collections_api():
    cols = database.get_douyin_collections()
    daily_rate = episode_scheduler.get_daily_post_rate()
    times = episode_scheduler.get_autopost_times()
    return {"ok": True, "collections": cols, "daily_post_rate": daily_rate, "times": times}

@app.get("/api/douyin/collections/{mix_id}")
@app.get("/scrapper/api/douyin/collections/{mix_id}")
async def get_douyin_collection_detail_api(mix_id: str):
    col = database.get_douyin_collection_by_id(mix_id)
    if not col:
        raise HTTPException(status_code=404, detail="Coleção não encontrada.")
    eps = database.get_collection_episodes(mix_id)
    return {"ok": True, "collection": col, "episodes": eps}

@app.post("/api/douyin/collections/add")
@app.post("/scrapper/api/douyin/collections/add")
async def add_douyin_collection_api(
    url: str = Form(...),
    title_pt: str = Form(None),
    autoposting: int = Form(1)
):
    autoposting_bool = bool(autoposting)
    res = douyin_collection_scraper.fetch_and_store_collection(url, title_pt, autoposting_bool)
    return res

@app.post("/api/douyin/collections/{mix_id}/toggle-autoposting")
@app.post("/scrapper/api/douyin/collections/{mix_id}/toggle-autoposting")
async def toggle_autoposting_api(mix_id: str):
    success = database.toggle_collection_autoposting(mix_id)
    col = database.get_douyin_collection_by_id(mix_id)
    return {"ok": success, "autoposting": col["autoposting"] if col else 0}

@app.post("/api/douyin/collections/{mix_id}/delete")
@app.post("/scrapper/api/douyin/collections/{mix_id}/delete")
async def delete_collection_api(mix_id: str):
    success = database.delete_douyin_collection(mix_id)
    return {"ok": success}

@app.post("/api/douyin/episodes/{ep_id}/action")
@app.post("/scrapper/api/douyin/episodes/{ep_id}/action")
async def apply_episode_action_api(ep_id: int, action: str = Form(...)):
    res = episode_scheduler.apply_episode_action(ep_id, action)
    return res

@app.post("/api/douyin/settings/daily-post-rate")
@app.post("/scrapper/api/douyin/settings/daily-post-rate")
async def set_daily_post_rate_api(rate: int = Form(...)):
    success = episode_scheduler.set_daily_post_rate(rate)
    return {"ok": success, "daily_post_rate": rate, "times": episode_scheduler.get_autopost_times()}

@app.post("/api/douyin/settings/autopost-times")
@app.post("/scrapper/api/douyin/settings/autopost-times")
async def set_autopost_times_api(times: str = Form(...)):
    time_list = [t.strip() for t in times.split(",") if t.strip()]
    success = episode_scheduler.set_autopost_times(time_list)
    return {"ok": success, "times": episode_scheduler.get_autopost_times()}

@app.get("/api/douyin/settings/cookie")
@app.get("/scrapper/api/douyin/settings/cookie")
async def get_cookie_api():
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    return {"ok": True, "cookie": cookie}

@app.post("/api/douyin/settings/cookie")
@app.post("/scrapper/api/douyin/settings/cookie")
async def save_cookie_api(cookie: str = Form(...)):
    cookie_val = cookie.strip().strip("'\"")
    env_path = PROJECT_ROOT / ".env"
    
    try:
        env_text = ""
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                env_text = f.read()

        if "DOUYIN_COOKIE=" in env_text:
            env_text = re.sub(r'DOUYIN_COOKIE=.*', f'DOUYIN_COOKIE="{cookie_val}"', env_text)
        else:
            env_text += f'\nDOUYIN_COOKIE="{cookie_val}"\n'

        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_text)

        os.environ["DOUYIN_COOKIE"] = cookie_val

        from scripts import sync_cookie
        sync_cookie.sync()

        return {"ok": True, "message": "Cookie salvo no .env e sincronizado!"}
    except Exception as e:
        return {"ok": False, "message": f"Erro ao salvar cookie: {e}"}

@app.get("/api/douyin/settings/social-defaults")
@app.get("/scrapper/api/douyin/settings/social-defaults")
async def get_social_defaults_api():
    post_yt = database.get_user_setting("default_post_youtube", "1") != "0"
    yt_privacy = database.get_user_setting("default_youtube_privacy", "public")

    post_shorts = database.get_user_setting("default_post_shorts", "1") != "0"
    shorts_privacy = database.get_user_setting("default_shorts_privacy", "public")

    post_tiktok = database.get_user_setting("default_post_tiktok", "1") != "0"
    tiktok_privacy = database.get_user_setting("default_tiktok_privacy", "PUBLIC")

    post_insta = database.get_user_setting("default_post_instagram", "0") != "0"
    insta_privacy = database.get_user_setting("default_instagram_privacy", "public")

    return {
        "ok": True,
        "post_youtube": post_yt,
        "youtube_privacy": yt_privacy,
        "post_shorts": post_shorts,
        "shorts_privacy": shorts_privacy,
        "post_tiktok": post_tiktok,
        "tiktok_privacy": tiktok_privacy,
        "post_instagram": post_insta,
        "instagram_privacy": insta_privacy
    }

@app.post("/api/douyin/settings/social-defaults")
@app.post("/scrapper/api/douyin/settings/social-defaults")
async def set_social_defaults_api(
    post_youtube: str = Form("1"),
    youtube_privacy: str = Form("public"),
    post_shorts: str = Form("1"),
    shorts_privacy: str = Form("public"),
    post_tiktok: str = Form("1"),
    tiktok_privacy: str = Form("PUBLIC"),
    post_instagram: str = Form("0"),
    instagram_privacy: str = Form("public")
):
    database.set_user_setting("default_post_youtube", "1" if post_youtube == "1" else "0")
    database.set_user_setting("default_youtube_privacy", youtube_privacy)

    database.set_user_setting("default_post_shorts", "1" if post_shorts == "1" else "0")
    database.set_user_setting("default_shorts_privacy", shorts_privacy)

    database.set_user_setting("default_post_tiktok", "1" if post_tiktok == "1" else "0")
    database.set_user_setting("default_tiktok_privacy", tiktok_privacy)

    database.set_user_setting("default_post_instagram", "1" if post_instagram == "1" else "0")
    database.set_user_setting("default_instagram_privacy", instagram_privacy)

    return {"ok": True, "message": "Padrões de redes sociais e privacidades salvos!"}

@app.get("/api/douyin/profiles")
@app.get("/scrapper/api/douyin/profiles")
async def get_douyin_profiles_api():
    profs = database.get_douyin_profiles()
    return {"ok": True, "profiles": profs}

@app.post("/api/douyin/profiles/add")
@app.post("/scrapper/api/douyin/profiles/add")
async def add_douyin_profile_api(url: str = Form(...)):
    res = douyin_profile_scraper.fetch_and_store_profile(url)
    return res

@app.post("/api/douyin/profiles/{sec_uid}/delete")
@app.post("/scrapper/api/douyin/profiles/{sec_uid}/delete")
async def delete_douyin_profile_api(sec_uid: str):
    success = database.delete_douyin_profile(sec_uid)
    return {"ok": success}

@app.post("/api/douyin/sync")
@app.post("/scrapper/api/douyin/sync")
async def sync_all_content_api(background_tasks: BackgroundTasks):
    background_tasks.add_task(douyin_profile_scraper.sync_all_profiles_and_collections)
    return {"ok": True, "message": "Varredura autônoma iniciada em background."}

def get_access_denied_page():
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Acesso Negado | AnimeRecaps</title>
    <style>
        body { background:#0a0a0f; color:#fff; font-family:sans-serif; display:flex; height:100vh; align-items:center; justify-content:center; margin:0; }
        .box { text-align:center; padding:40px; background:#14141f; border-radius:12px; border:1px solid #e50914; max-width:400px; }
        h1 { color:#e50914; margin-top:0; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🔒 Acesso Não Autorizado</h1>
        <p>Acesse o bot no Telegram e use o comando <code>/start</code> para gerar seu link de acesso seguro.</p>
    </div>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
@app.get("/scrapper", response_class=HTMLResponse)
@app.get("/scrapper/", response_class=HTMLResponse)
async def index(
    request: Request,
    session: str = Query(None)
):
    if session:
        if database.validate_web_session(session):
            redirect_url = "/scrapper/"
            redir_resp = RedirectResponse(url=redirect_url, status_code=303)
            redir_resp.set_cookie(
                key="scrapper_session", value=session, max_age=1800,
                httponly=True, samesite="lax", secure=False, path="/"
            )
            return redir_resp
        else:
            return HTMLResponse(content=get_access_denied_page(), status_code=401)
            
    cookie_token = request.cookies.get("scrapper_session")
    if not database.validate_web_session(cookie_token):
        return HTMLResponse(content=get_access_denied_page(), status_code=401)

    index_html_path = FRONTEND_DIST / "index.html"
    if index_html_path.exists():
        return FileResponse(str(index_html_path))

    return HTMLResponse(content="<h1>Frontend Vite não compilado. Execute 'npm run build' na pasta frontend.</h1>")

def run_panel():
    import uvicorn
    database.init_db()
    print("Iniciando Painel Web (Vite React) na porta 5556 (http://localhost:5556)...")
    uvicorn.run(app, host="0.0.0.0", port=5556, log_level="warning")


@app.post("/api/douyin/trigger-next")
@app.get("/api/douyin/trigger-next")
@app.post("/scrapper/api/douyin/trigger-next")
@app.get("/scrapper/api/douyin/trigger-next")
async def trigger_next_episode_api():
    """Aciona a pré-renderização/produção do próximo episódio na fila Round-Robin."""
    from scrapper import episode_scheduler
    res = episode_scheduler.trigger_pre_render_for_next_episode()
    return {"ok": True if res else False, "result": res}

