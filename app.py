"""
Hugging Face Spaces Entrypoint — AnimeRecap Ecosystem Master Orchestrator
Gerencia e orquestra de forma resiliente e isolada todos os 4 projetos:
  1. Kuma AnimeRecap (Telegram Bot + Webhook na porta 8080)
  2. Scrapper Douyin/Bilibili (FastAPI na porta 5556 + Bot Telegram + Evil0ctal na porta 5555)
  3. Post Recap (Bot Telegram + Scheduler Worker)
  4. TikTok Approval (FastAPI na porta 8000)
  5. SEO Anime Recap (Node.js Express na porta 3333)
  6. Gradio Dashboard & Health Check (Porta 7860)
"""

import os
import sys
import time
import asyncio
import logging
import threading
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Força codificação UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

load_dotenv()

# Configuração de Logging Geral
logging.basicConfig(
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)
logger = logging.getLogger("orchestrator")

# Estado operacional dos serviços para exibição no Dashboard
SERVICE_STATUS = {
    "PostgreSQL Neon": "🔄 Inicializando...",
    "Kuma Recap Bot & Webhook (8080)": "🔄 Aguardando...",
    "Douyin Scrapper Web & Bot (5556)": "🔄 Aguardando...",
    "Evil0ctal Douyin API (5555)": "🔄 Aguardando...",
    "Post Recap Bot & Scheduler": "🔄 Aguardando...",
    "TikTok Approval API (8000)": "🔄 Aguardando...",
    "SEO Anime Recap Node.js (3333)": "🔄 Aguardando..."
}


# ==============================================================================
# 1. SERVIÇO: KUMA RECAP PIPELINE
# ==============================================================================
def start_kuma_service():
    """Inicia o Webhook na porta 8080 e o Bot do Telegram do Kuma Recap."""
    from bot.webhook_server import start_webhook_server
    from bot.telegram_bot import main as run_kuma_bot

    # Inicia o webhook server uma única vez
    try:
        start_webhook_server(8080)
        logger.info("[KUMA] Webhook Server iniciado na porta 8080.")
    except Exception as e:
        logger.warning(f"[KUMA] Webhook Server já ativo ou aviso: {e}")

    SERVICE_STATUS["Kuma Recap Bot & Webhook (8080)"] = "✅ Online (Porta 8080)"

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("[KUMA] TELEGRAM_BOT_TOKEN não configurado no .env. Bot desativado.")
        SERVICE_STATUS["Kuma Recap Bot & Webhook (8080)"] = "⚠️ Webhook Ativo / Bot Sem Token"
        return

    # Loop de execução do bot Telegram
    while True:
        try:
            logger.info("[KUMA] Iniciando Bot Telegram do Kuma Recap...")
            run_kuma_bot()
            time.sleep(5)
        except Exception as e:
            logger.error(f"[KUMA] Falha no Bot Telegram: {e}. Reiniciando em 15s...")
            SERVICE_STATUS["Kuma Recap Bot & Webhook (8080)"] = f"⚠️ Reconectando ({e})"
            time.sleep(15)


# ==============================================================================
# 2. SERVIÇO: EVIL0CTAL DOUYIN DOWNLOAD API (PORTA 5555)
# ==============================================================================
def start_evil0ctal_api():
    """Inicia o servidor de download da API Douyin (Evil0ctal) na porta 5555 em subprocesso isolado."""
    douyin_api_dir = Path(__file__).resolve().parent / "douyin_api"
    if not (douyin_api_dir / "app" / "main.py").exists():
        SERVICE_STATUS["Evil0ctal Douyin API (5555)"] = "⚠️ Pasta douyin_api não encontrada"
        return

    while True:
        try:
            logger.info("[EVIL0CTAL] Iniciando Evil0ctal Douyin API na porta 5555...")
            SERVICE_STATUS["Evil0ctal Douyin API (5555)"] = "✅ Online (Porta 5555)"

            proc = subprocess.Popen(
                [sys.executable, "start.py"],
                cwd=str(douyin_api_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            for line in iter(proc.stdout.readline, ""):
                if line.strip():
                    logger.info(f"[EVIL0CTAL] {line.strip()}")

            proc.wait()
            logger.warning(f"[EVIL0CTAL] Processo encerrou com código {proc.returncode}. Reiniciando em 10s...")
            time.sleep(10)
        except Exception as e:
            logger.error(f"[EVIL0CTAL] Erro na API Evil0ctal: {e}. Reiniciando em 10s...")
            SERVICE_STATUS["Evil0ctal Douyin API (5555)"] = f"⚠️ Reiniciando ({e})"
            time.sleep(10)



# ==============================================================================
# 3. SERVIÇO: SCRAPPER DOUYIN & BILIBILI (PORTA 5556)
# ==============================================================================
def start_scrapper_service():
    """Inicia o Painel Web (FastAPI porta 5556), Scheduler e Bot do Scrapper Douyin."""
    try:
        from scrapper import database, telegram_bot, web_panel, search_scrapper

        # Inicia FastAPI do Scrapper na porta 5556
        def _run_fastapi():
            import uvicorn
            uvicorn.run(web_panel.app, host="0.0.0.0", port=5556, log_level="warning")

        web_t = threading.Thread(target=_run_fastapi, daemon=True, name="Thread-Scrapper-FastAPI")
        web_t.start()
        logger.info("[SCRAPPER] Painel Web FastAPI iniciado na porta 5556.")

        # Inicia Scheduler de buscas em background
        def _run_scheduler():
            time.sleep(20)
            while True:
                try:
                    interval_hours = int(os.getenv("SCRAPE_INTERVAL_HOURS", "3"))
                    time.sleep(interval_hours * 3600)
                except Exception as e:
                    logger.error(f"[SCRAPPER SCHEDULER] Erro: {e}")
                    time.sleep(60)

        sched_t = threading.Thread(target=_run_scheduler, daemon=True, name="Thread-Scrapper-Scheduler")
        sched_t.start()

        SERVICE_STATUS["Douyin Scrapper Web & Bot (5556)"] = "✅ Online (Porta 5556)"

        token = os.getenv("SCRAPPER_TELEGRAM_TOKEN")
        if not token:
            logger.info("[SCRAPPER] SCRAPPER_TELEGRAM_TOKEN não configurado. Painel Web ativo, Bot desativado.")
            return

        # Bot Telegram do Scrapper
        while True:
            try:
                logger.info("[SCRAPPER] Iniciando Bot Telegram do Scrapper...")
                telegram_bot.run_bot()
                time.sleep(10)
            except Exception as e:
                logger.error(f"[SCRAPPER] Falha no Bot Telegram: {e}. Reiniciando em 10s...")
                SERVICE_STATUS["Douyin Scrapper Web & Bot (5556)"] = f"⚠️ Bot Reconectando ({e})"
                time.sleep(10)
    except Exception as e:
        logger.error(f"[SCRAPPER] Erro crítico no Scrapper: {e}")
        SERVICE_STATUS["Douyin Scrapper Web & Bot (5556)"] = f"❌ Erro ({e})"


# ==============================================================================
# 4. SERVIÇO: POST RECAP & AGENDADOR
# ==============================================================================
def start_postrecap_service():
    """Inicia o Bot do Telegram e o worker de publicação do Post Recap."""
    try:
        token = os.getenv("POSTRECAP_TELEGRAM_BOT_TOKEN")
        if not token:
            logger.info("[POSTRECAP] POSTRECAP_TELEGRAM_BOT_TOKEN não configurado no .env. Serviço inativo.")
            SERVICE_STATUS["Post Recap Bot & Scheduler"] = "⏸️ Desativado (Sem Token)"
            return

        from post_recap import bot as postrecap_bot

        SERVICE_STATUS["Post Recap Bot & Scheduler"] = "✅ Online"

        while True:
            try:
                logger.info("[POSTRECAP] Iniciando Bot e Scheduler do Post Recap...")
                postrecap_bot.main()
                time.sleep(10)
            except Exception as e:
                logger.error(f"[POSTRECAP] Falha no Post Recap: {e}. Reiniciando em 10s...")
                SERVICE_STATUS["Post Recap Bot & Scheduler"] = f"⚠️ Reconectando ({e})"
                time.sleep(10)
    except Exception as e:
        logger.error(f"[POSTRECAP] Erro crítico no Post Recap: {e}")
        SERVICE_STATUS["Post Recap Bot & Scheduler"] = f"❌ Erro ({e})"


# ==============================================================================
# 5. SERVIÇO: TIKTOK APPROVAL API (PORTA 8000)
# ==============================================================================
def start_tiktok_approval_service():
    """Inicia a API FastAPI de aprovação e autenticação do TikTok na porta 8000."""
    try:
        import uvicorn
        from tiktok_approval.main import app as tiktok_app

        SERVICE_STATUS["TikTok Approval API (8000)"] = "✅ Online (Porta 8000)"
        logger.info("[TIKTOK APPROVAL] Iniciando FastAPI na porta 8000...")
        uvicorn.run(tiktok_app, host="0.0.0.0", port=8000, log_level="warning")
    except Exception as e:
        logger.error(f"[TIKTOK APPROVAL] Erro ao iniciar API na porta 8000: {e}")
        SERVICE_STATUS["TikTok Approval API (8000)"] = f"❌ Erro ({e})"


# ==============================================================================
# 6. SERVIÇO: SEO ANIME RECAP (NODE.JS EXPRESS - PORTA 3333)
# ==============================================================================
def start_seo_service():
    """Inicia o servidor Node.js Express do SEO Anime Recap na porta 3333 com supervisão."""
    seo_dir = Path(__file__).resolve().parent / "seo"
    server_js = seo_dir / "server.js"

    if not server_js.exists():
        SERVICE_STATUS["SEO Anime Recap Node.js (3333)"] = "⚠️ seo/server.js não encontrado"
        return

    # Garante instalação das dependências Node.js caso ausentes no container
    if not (seo_dir / "node_modules" / "dotenv").exists():
        try:
            logger.info("[SEO] Instalando dependências Node.js (npm install)...")
            subprocess.run(["npm", "install", "--prefix", str(seo_dir)], check=True)
            logger.info("[SEO] Dependências instaladas com sucesso.")
        except Exception as e:
            logger.warning(f"[SEO] Aviso ao instalar dependências Node.js: {e}")

    while True:
        try:
            logger.info("[SEO] Iniciando servidor Express Node.js na porta 3333...")
            SERVICE_STATUS["SEO Anime Recap Node.js (3333)"] = "✅ Online (Porta 3333)"

            env = os.environ.copy()
            env["PORT"] = "3333"
            env["SEO_PORT"] = "3333"

            proc = subprocess.Popen(
                ["node", "server.js"],
                cwd=str(seo_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            for line in iter(proc.stdout.readline, ""):
                if line.strip():
                    logger.info(f"[SEO] {line.strip()}")

            proc.wait()
            logger.warning(f"[SEO] Processo Node.js encerrou com código {proc.returncode}. Reiniciando em 5s...")
            time.sleep(5)
        except Exception as e:
            logger.error(f"[SEO] Falha no processo Node.js: {e}. Tentando novamente em 10s...")
            SERVICE_STATUS["SEO Anime Recap Node.js (3333)"] = f"⚠️ Reiniciando ({e})"
            time.sleep(10)



# ==============================================================================
# 7. GRADIO DASHBOARD & KEEP-ALIVE (PORTA 7860)
# ==============================================================================
def create_dashboard():
    """Cria a interface do Gradio para monitoramento e health check do HF Space."""
    import gradio as gr

    def get_status_table():
        return [[k, v] for k, v in SERVICE_STATUS.items()]

    with gr.Blocks(title="AnimeRecap Central Ecosytem") as demo:
        gr.Markdown("# 🚀 AnimeRecap Central Ecosystem")
        gr.Markdown("Painel de saúde e orquestração de todos os backends na instância.")

        status_table = gr.Dataframe(
            headers=["Serviço / Módulo", "Status Atual"],
            value=get_status_table(),
            interactive=False,
            every=5
        )

        refresh_btn = gr.Button("🔄 Atualizar Status")
        refresh_btn.click(fn=get_status_table, outputs=status_table)

    return demo


# ==============================================================================
# INICIALIZAÇÃO DO ECOSSISTEMA E APLICAÇÃO ASGI GLOBAL
# ==============================================================================
_initialized = False

def init_system():
    """Inicializa conexões e threads de serviço em background."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    print("=" * 70)
    print("  🚀 AnimeRecap Central Ecosystem — Master Multi-Project Orchestrator")
    print("=" * 70)

    # 1. Inicializa os schemas do banco Neon PostgreSQL
    try:
        from shared.schema_init import init_all_schemas
        init_all_schemas()
        SERVICE_STATUS["PostgreSQL Neon"] = "✅ Conectado e Tabelas Prontas"
    except Exception as e:
        logger.error(f"Erro ao inicializar schemas no Neon: {e}")
        SERVICE_STATUS["PostgreSQL Neon"] = f"❌ Erro ({e})"

    # 2. Inicia os serviços em threads separadas
    services = [
        ("Kuma Recap", start_kuma_service),
        ("Evil0ctal Douyin API", start_evil0ctal_api),
        ("Scrapper Douyin", start_scrapper_service),
        ("Post Recap", start_postrecap_service),
        ("TikTok Approval", start_tiktok_approval_service),
        ("SEO Anime Recap", start_seo_service),
    ]

    for name, target_func in services:
        t = threading.Thread(target=target_func, daemon=True, name=f"Thread-{name}")
        t.start()
        logger.info(f"Thread do serviço '{name}' disparada.")


# Dispara inicialização dos serviços
init_system()

# 3. Cria a aplicação ASGI unificada com rotas de API prioritárias e Gradio Dashboard
from scrapper.web_panel import app as scrapper_app
from tiktok_approval.main import app as tiktok_app
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
import gradio as gr

main_app = FastAPI(title="AnimeRecap Central Ecosystem")

# Configura CORS no FastAPI principal
main_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vincula todas as rotas da API com prioridade no FastAPI principal
main_app.include_router(scrapper_app.router)
main_app.include_router(tiktok_app.router)
main_app.mount("/scrapper", scrapper_app)
main_app.mount("/tiktok", tiktok_app)

# Monta o Gradio Dashboard como aplicação base
demo = create_dashboard()
app = gr.mount_gradio_app(main_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    print("Iniciando servidor ASGI unificado na porta 7860...")
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="info")

