"""
Bot Telegram — Agente de Postagem
Controle completo do pipeline via Telegram.
"""

import os
import asyncio
import tempfile
import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from dotenv import load_dotenv

from bot.database import (
    init_db, get_active_project, get_project,
    format_status, format_cell_status, update_step
)
from bot.pipeline_controller import PipelineController

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

controller = PipelineController()

# Estado temporário para upload em 2 etapas
user_uploads = {}  # chat_id -> {"video": path, "audio": path, "mask": path}


# ═══════════════════════════════════════════════════════════════════
# 📋 COMANDOS
# ═══════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas."""
    await update.message.reply_text(
        "🎬 *Agente de Postagem — AnimeRecap*\n\n"
        "Eu controlo todo o pipeline de processamento de vídeo.\n\n"
        "📝 *Comandos:*\n"
        "  /novo `<nome>` — Inicia novo projeto\n"
        "  /status — Status do projeto ativo\n"
        "  /cells — Tracking detalhado por célula\n"
        "  /config — Marca config como pronta\n"
        "  /cancel — Cancela projeto ativo\n\n"
        "📦 *Envio de arquivos:*\n"
        "  Envie o *vídeo* (com marca d'água)\n"
        "  Envie o *áudio* (original do vídeo)\n"
        "  Opcionalmente envie a *máscara* (.png)\n\n"
        "Depois use /novo para iniciar o processamento!",
        parse_mode="Markdown"
    )


async def cmd_novo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia um novo projeto."""
    chat_id = str(update.effective_chat.id)

    # Verificar se já tem projeto ativo
    active = get_active_project(chat_id)
    if active:
        await update.message.reply_text(
            f"⚠️ Já existe um projeto ativo: **{active['project_name']}**\n"
            f"Use /cancel para cancelar ou /status para ver o progresso.",
            parse_mode="Markdown"
        )
        return

    # Verificar se enviou arquivos
    uploads = user_uploads.get(chat_id, {})
    if not uploads.get("video") or not uploads.get("audio"):
        await update.message.reply_text(
            "❌ Envie o **vídeo** e o **áudio** antes de usar /novo!\n\n"
            "1️⃣ Envie o vídeo (com marca d'água)\n"
            "2️⃣ Envie o áudio (original do vídeo)\n"
            "3️⃣ Use: `/novo Nome do Anime`",
            parse_mode="Markdown"
        )
        return

    # Nome do projeto
    if ctx.args:
        project_name = " ".join(ctx.args)
    else:
        project_name = f"Projeto_{chat_id[:6]}"

    await update.message.reply_text(
        f"🚀 Iniciando projeto: **{project_name}**\n"
        f"📤 Fazendo upload e dividindo vídeo...",
        parse_mode="Markdown"
    )

    try:
        project = await controller.iniciar_projeto(
            project_name=project_name,
            chat_id=chat_id,
            video_path=uploads["video"],
            audio_path=uploads["audio"],
            mask_path=uploads.get("mask"),
        )
        pid = str(project["id"])

        await update.message.reply_text(
            f"✅ Upload e split concluídos!\n\n"
            f"🔄 Disparando:\n"
            f"  • Watermark Remover (PT1 + PT2) — simultâneo\n"
            f"  • Omni-Anime-Ver — paralelo\n\n"
            f"📊 Use /status para acompanhar.",
            parse_mode="Markdown"
        )

        # Disparar watermark + omni
        controller.disparar_watermark_e_omni(pid)

        # Limpar uploads temporários
        user_uploads.pop(chat_id, None)

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao iniciar projeto:\n`{e}`", parse_mode="Markdown")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o status do projeto ativo."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)
    status_text = format_status(project)
    await update.message.reply_text(status_text, parse_mode="Markdown")


async def cmd_cells(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o tracking detalhado por célula dos notebooks."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)
    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo.")
        return
    pid = str(project["id"])
    # Filtrar por notebook específico se passado como argumento
    notebook_filter = " ".join(ctx.args) if ctx.args else None
    cells_text = format_cell_status(pid, notebook_filter)
    await update.message.reply_text(cells_text, parse_mode="Markdown")


async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marca a configuração como pronta e dispara render."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)

    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo.")
        return

    pid = str(project["id"])

    if project["status"] != "waiting_config":
        await update.message.reply_text(
            "⚠️ O projeto não está aguardando configuração.\n"
            f"Status atual: **{project['status']}**",
            parse_mode="Markdown"
        )
        return

    # Verificar se enhancer já terminou
    if project["step_enhancer_pt1"] != "done" or project["step_enhancer_pt2"] != "done":
        update_step(pid, "step_config_ready", "done", "Config pronta, aguardando enhancer")
        await update.message.reply_text(
            "✅ Config marcada como pronta!\n"
            "⏳ Aguardando o Video Enhancer finalizar para iniciar render...",
            parse_mode="Markdown"
        )
    else:
        # Enhancer já done → disparar render
        controller.disparar_render(pid)
        await update.message.reply_text(
            "✅ Config pronta! 🎬 Renderização disparada (PT1 + PT2 simultâneo)!\n"
            "📊 Use /status para acompanhar.",
            parse_mode="Markdown"
        )


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Cancela o projeto ativo."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)
    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo para cancelar.")
        return

    pid = str(project["id"])
    update_step(pid, "step_upload", "error", "Cancelado pelo usuário")
    await update.message.reply_text(
        f"🛑 Projeto **{project['project_name']}** cancelado.",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
# 📁 HANDLERS DE ARQUIVO
# ═══════════════════════════════════════════════════════════════════

async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe vídeo do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

    # Pode vir como document ou video
    file_obj = message.video or message.document
    if not file_obj:
        return

    # Verificar se é vídeo
    file_name = getattr(file_obj, "file_name", "video.mp4") or "video.mp4"
    if not any(file_name.lower().endswith(ext) for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]):
        return

    await message.reply_text(f"⬇️ Baixando vídeo: `{file_name}`...", parse_mode="Markdown")

    temp_dir = tempfile.mkdtemp(prefix="anime_pipeline_")
    local_path = os.path.join(temp_dir, file_name)

    tg_file = await ctx.bot.get_file(file_obj.file_id)
    await tg_file.download_to_drive(local_path)

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
    user_uploads[chat_id]["video"] = local_path

    await message.reply_text(
        f"✅ Vídeo recebido: `{file_name}`\n"
        f"{'📎 Agora envie o **áudio** original.' if not user_uploads[chat_id].get('audio') else '📦 Pronto! Use /novo <nome> para iniciar.'}",
        parse_mode="Markdown"
    )


async def handle_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe áudio do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

    file_obj = message.audio or message.voice or message.document
    if not file_obj:
        return

    file_name = getattr(file_obj, "file_name", "audio.mp3") or "audio.mp3"
    if not any(file_name.lower().endswith(ext) for ext in [".mp3", ".wav", ".m4a", ".ogg", ".aac"]):
        # Pode ser um document que é áudio
        mime = getattr(file_obj, "mime_type", "") or ""
        if "audio" not in mime:
            return

    await message.reply_text(f"⬇️ Baixando áudio: `{file_name}`...", parse_mode="Markdown")

    temp_dir = tempfile.mkdtemp(prefix="anime_pipeline_")
    local_path = os.path.join(temp_dir, file_name)

    tg_file = await ctx.bot.get_file(file_obj.file_id)
    await tg_file.download_to_drive(local_path)

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
    user_uploads[chat_id]["audio"] = local_path

    await message.reply_text(
        f"✅ Áudio recebido: `{file_name}`\n"
        f"{'📎 Agora envie o **vídeo** com marca d\'água.' if not user_uploads[chat_id].get('video') else '📦 Pronto! Use /novo <nome> para iniciar.'}",
        parse_mode="Markdown"
    )


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe máscara (imagem) do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

    # Pega a maior resolução
    photo = message.photo[-1] if message.photo else None
    if not photo:
        return

    temp_dir = tempfile.mkdtemp(prefix="anime_pipeline_")
    local_path = os.path.join(temp_dir, "mask.png")

    tg_file = await ctx.bot.get_file(photo.file_id)
    await tg_file.download_to_drive(local_path)

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
    user_uploads[chat_id]["mask"] = local_path

    await message.reply_text("✅ Máscara de watermark recebida!")


# ═══════════════════════════════════════════════════════════════════
# 🚀 INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════

def main():
    """Inicia o bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado no .env!")
        return

    # Inicializar banco
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("novo", cmd_novo))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cells", cmd_cells))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Handlers de arquivo
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | filters.Document.AUDIO, handle_audio
    ))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🤖 Bot Telegram iniciado! Ctrl+C para parar.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
