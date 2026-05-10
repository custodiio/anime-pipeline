"""
Main — Ponto de entrada do Agente de Postagem
Roda o Bot Telegram + Webhook Server simultaneamente.
"""

import os
import threading
from dotenv import load_dotenv

load_dotenv()

from bot.database import init_db
from bot.telegram_bot import main as run_bot
from bot.webhook_server import start_webhook_server


if __name__ == "__main__":
    print("=" * 60)
    print("  🎬 Agente de Postagem — AnimeRecap Pipeline")
    print("=" * 60)

    # Inicializar banco de dados
    init_db()

    # Iniciar webhook em thread separada (retorna imediatamente)
    start_webhook_server()

    # Iniciar bot Telegram (blocking)
    print("🤖 Iniciando Bot Telegram...")
    run_bot()
