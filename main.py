"""
Main — Ponto de entrada do Agente de Postagem
Roda o Bot Telegram + Webhook Server simultaneamente.
"""

import os
import asyncio
import threading
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

from bot.database import init_db
from bot.telegram_bot import main as run_bot
from bot.webhook_server import create_webhook_app

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))


def run_webhook_server():
    """Roda o servidor webhook em uma thread separada."""
    app = create_webhook_app()
    web.run_app(app, host="0.0.0.0", port=WEBHOOK_PORT, print=lambda _: None)


if __name__ == "__main__":
    print("=" * 60)
    print("  🎬 Agente de Postagem — AnimeRecap Pipeline")
    print("=" * 60)

    # Inicializar banco de dados
    init_db()

    # Iniciar webhook em thread separada
    print(f"🌐 Webhook server na porta {WEBHOOK_PORT}")
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()

    # Iniciar bot Telegram (blocking)
    print("🤖 Iniciando Bot Telegram...")
    run_bot()
