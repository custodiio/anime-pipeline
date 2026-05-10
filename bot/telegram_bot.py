"""
Bot Telegram — Agente de Postagem
Controle completo do pipeline via Telegram.
Protegido por lista de IDs autorizados.
"""

import os
import asyncio
import tempfile
import logging
import uuid
import hashlib
import time
from functools import wraps
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from dotenv import load_dotenv

from bot.database import (
    init_db, get_active_project, get_project,
    format_status, format_cell_status, update_step
)
from bot.pipeline_controller import PipelineController

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "default_secret")

# IDs autorizados (separados por vírgula no .env)
_raw_users = os.getenv("AUTHORIZED_TELEGRAM_USERS", "")
AUTHORIZED_USERS = set(
    int(uid.strip()) for uid in _raw_users.split(",")
    if uid.strip().isdigit()
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

controller = PipelineController()

# Estado temporário
user_uploads = {}  # chat_id -> {"video": path, "audio": path, "mask": path}
active_sessions = {}  # session_token -> {"project_id": ..., "chat_id": ..., "created_at": ...}

# Mapeamento de step -> nome amigável
STEP_LABELS = {
    "step_watermark_pt1": "🧹 WM PT1",
    "step_watermark_pt2": "🧹 WM PT2",
    "step_enhancer_pt1": "⚡ Enhancer PT1",
    "step_enhancer_pt2": "⚡ Enhancer PT2",
    "step_omni": "🧠 Omni",
    "step_render_pt1": "🎬 Render PT1",
    "step_render_pt2": "🎬 Render PT2",
    "step_merge": "📦 Merge Final",
}

STATUS_ICONS = {
    "pending": "⏳",
    "running": "🔄",
    "done": "✅",
    "error": "❌",
    "waiting_config": "⚙️",
}


# ═══════════════════════════════════════════════════════════════════
# 🔒 AUTENTICAÇÃO
# ═══════════════════════════════════════════════════════════════════

def authorized(func):
    """Decorator que bloqueia usuários não autorizados."""
    @wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if AUTHORIZED_USERS and user_id not in AUTHORIZED_USERS:
            logger.warning(f"Acesso negado para user_id={user_id}")
            await update.message.reply_text(
                "🔒 Acesso negado.\n"
                f"Seu ID: `{user_id}`\n"
                "Peça ao administrador para adicionar seu ID.",
                parse_mode="Markdown"
            )
            return
        return await func(update, ctx, *args, **kwargs)
    return wrapper


def gerar_session_token(project_id: str) -> str:
    """Gera token de sessão seguro para o VideoRender."""
    raw = f"{project_id}:{SESSION_SECRET}:{uuid.uuid4().hex}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:24]
    return token

def get_session_link(token: str) -> str:
    videorender_url = os.getenv("VIDEORENDER_URL", "http://localhost:5173")
    webhook_url = os.getenv("PIPELINE_WEBHOOK_URL", "")
    api_param = f"&api={webhook_url}" if webhook_url else ""
    return f"{videorender_url}/?session={token}{api_param}"


# ═══════════════════════════════════════════════════════════════════
# 📋 COMANDOS
# ═══════════════════════════════════════════════════════════════════

@authorized
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mensagem de boas-vindas com menu visual."""
    await update.message.reply_text(
        "🎬 *Agente de Postagem — AnimeRecap*\n\n"
        "Pipeline automatizado de pós-produção.\n\n"
        "📝 *Comandos:*\n"
        "  /novo `<nome>` — Inicia novo projeto\n"
        "  /status — Status do projeto ativo\n"
        "  /cells `[notebook]` — Tracking por célula\n"
        "  /sessao — Gera link do VideoRender\n"
        "  /config — Confirma config (dispara render)\n"
        "  /cancel — Cancela projeto ativo\n"
        "  /myid — Mostra seu User ID\n\n"
        "📦 *Envio de arquivos:*\n"
        "  1. Envie o *vídeo* (com marca d'água)\n"
        "  2. Envie o *áudio* (original do vídeo)\n"
        "  3. (Opcional) Envie a *máscara* (.png)\n"
        "  4. Use `/novo Nome do Anime`",
        parse_mode="Markdown"
    )


@authorized
async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o User ID do Telegram."""
    uid = update.effective_user.id
    await update.message.reply_text(f"🆔 Seu User ID: `{uid}`", parse_mode="Markdown")


@authorized
async def cmd_novo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia um novo projeto."""
    chat_id = str(update.effective_chat.id)

    active = get_active_project(chat_id)
    if active:
        await update.message.reply_text(
            f"⚠️ Já existe um projeto ativo: *{active['project_name']}*\n"
            f"Use /cancel para cancelar ou /status para ver o progresso.",
            parse_mode="Markdown"
        )
        return

    uploads = user_uploads.get(chat_id, {})
    if not uploads.get("video") or not uploads.get("audio"):
        await update.message.reply_text(
            "❌ Envie o *vídeo* e o *áudio* antes de usar /novo!\n\n"
            "1️⃣ Envie o vídeo (com marca d'água)\n"
            "2️⃣ Envie o áudio (original do vídeo)\n"
            "3️⃣ Use: `/novo Nome do Anime`",
            parse_mode="Markdown"
        )
        return

    project_name = " ".join(ctx.args) if ctx.args else f"Projeto_{chat_id[:6]}"

    await update.message.reply_text(
        f"🚀 Iniciando projeto: *{project_name}*\n"
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

        # Gerar sessão VideoRender automaticamente
        token = gerar_session_token(pid)
        active_sessions[token] = {
            "project_id": pid,
            "chat_id": chat_id,
            "created_at": time.time()
        }

        session_link = get_session_link(token)

        await update.message.reply_text(
            f"✅ Projeto criado!\n\n"
            f"🔄 Disparando:\n"
            f"  • Watermark Remover (PT1 + PT2)\n"
            f"  • Omni-Anime-Ver\n\n"
            f"⚙️ *Configure o vídeo quando o Omni terminar:*\n"
            f"[Abrir VideoRender]({session_link})\n\n"
            f"📊 Use /status para acompanhar.",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

        controller.disparar_watermark_e_omni(pid)
        user_uploads.pop(chat_id, None)

    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao iniciar projeto:\n`{e}`", parse_mode="Markdown")


@authorized
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o status visual do projeto ativo."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)

    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo. Use /novo para iniciar.")
        return

    status_text = format_status(project)

    # Botões inline
    buttons = []
    if project.get("status") == "waiting_config":
        buttons.append([InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
        buttons.append([InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
    buttons.append([InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text(status_text, parse_mode="Markdown", reply_markup=reply_markup)


@authorized
async def cmd_cells(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o tracking detalhado por célula dos notebooks."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)
    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo.")
        return
    pid = str(project["id"])
    notebook_filter = " ".join(ctx.args) if ctx.args else None
    cells_text = format_cell_status(pid, notebook_filter)
    await update.message.reply_text(cells_text, parse_mode="Markdown")


@authorized
async def cmd_sessao(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gera um link de sessão para o VideoRender."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)

    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo.")
        return

    pid = str(project["id"])
    token = gerar_session_token(pid)
    active_sessions[token] = {
        "project_id": pid,
        "chat_id": chat_id,
        "created_at": time.time()
    }

    session_link = get_session_link(token)

    await update.message.reply_text(
        f"🎬 *Sessão VideoRender*\n\n"
        f"Projeto: *{project['project_name']}*\n"
        f"⏰ Válida por 2 horas\n\n"
        f"[Abrir Editor]({session_link})",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


@authorized
async def cmd_config(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Marca a configuração como pronta e dispara render."""
    chat_id = str(update.effective_chat.id)
    project = get_active_project(chat_id)

    if not project:
        await update.message.reply_text("❌ Nenhum projeto ativo.")
        return

    pid = str(project["id"])

    if project.get("step_enhancer_pt1") != "done" or project.get("step_enhancer_pt2") != "done":
        update_step(pid, "step_config_ready", "done", "Config pronta, aguardando enhancer")
        await update.message.reply_text(
            "✅ Config marcada como pronta!\n"
            "⏳ Aguardando Video Enhancer finalizar...",
            parse_mode="Markdown"
        )
    else:
        controller.disparar_render(pid)
        await update.message.reply_text(
            "✅ Config pronta! 🎬 Renderização disparada (PT1 + PT2)!\n"
            "📊 Use /status para acompanhar.",
            parse_mode="Markdown"
        )


@authorized
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
        f"🛑 Projeto *{project['project_name']}* cancelado.",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════
# 🔘 CALLBACKS (botões inline)
# ═══════════════════════════════════════════════════════════════════

@authorized
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Trata cliques nos botões inline."""
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat.id)
    data = query.data

    if data == "refresh_status":
        project = get_active_project(chat_id)
        if project:
            status_text = format_status(project)
            buttons = [[InlineKeyboardButton("🔄 Atualizar", callback_data="refresh_status")]]
            if project.get("status") == "waiting_config":
                buttons.insert(0, [InlineKeyboardButton("⚙️ Abrir VideoRender", callback_data="open_session")])
                buttons.insert(1, [InlineKeyboardButton("✅ Config Pronta", callback_data="confirm_config")])
            await query.edit_message_text(status_text, parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup(buttons))

    elif data == "open_session":
        project = get_active_project(chat_id)
        if project:
            pid = str(project["id"])
            token = gerar_session_token(pid)
            active_sessions[token] = {"project_id": pid, "chat_id": chat_id, "created_at": time.time()}
            session_link = get_session_link(token)
            await query.message.reply_text(
                f"[Abrir VideoRender]({session_link})",
                parse_mode="Markdown", disable_web_page_preview=True
            )

    elif data == "confirm_config":
        project = get_active_project(chat_id)
        if project:
            pid = str(project["id"])
            if project.get("step_enhancer_pt1") != "done" or project.get("step_enhancer_pt2") != "done":
                await query.message.reply_text("⏳ Aguardando Enhancer finalizar...")
            else:
                controller.disparar_render(pid)
                await query.message.reply_text("🎬 Renderização disparada!")


# ═══════════════════════════════════════════════════════════════════
# 📁 HANDLERS DE ARQUIVO (com auth)
# ═══════════════════════════════════════════════════════════════════

@authorized
async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe vídeo do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

    file_obj = message.video or message.document
    if not file_obj:
        return

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

    has_audio = user_uploads[chat_id].get("audio")
    await message.reply_text(
        f"✅ Vídeo recebido: `{file_name}`\n"
        f"{'📦 Pronto! Use /novo <nome> para iniciar.' if has_audio else '📎 Agora envie o *áudio* original.'}",
        parse_mode="Markdown"
    )


@authorized
async def handle_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe áudio do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

    file_obj = message.audio or message.voice or message.document
    if not file_obj:
        return

    file_name = getattr(file_obj, "file_name", "audio.mp3") or "audio.mp3"
    if not any(file_name.lower().endswith(ext) for ext in [".mp3", ".wav", ".m4a", ".ogg", ".aac"]):
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

    has_video = user_uploads[chat_id].get("video")
    await message.reply_text(
        f"✅ Áudio recebido: `{file_name}`\n"
        f"{'📦 Pronto! Use /novo <nome> para iniciar.' if has_video else '📎 Agora envie o *vídeo* com marca d\\'água.'}",
        parse_mode="Markdown"
    )


@authorized
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Recebe máscara (imagem) do usuário."""
    chat_id = str(update.effective_chat.id)
    message = update.message

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
# 🌐 API SESSÃO (para o VideoRender chamar)
# ═══════════════════════════════════════════════════════════════════

def validar_sessao(token: str):
    """Valida e retorna dados da sessão (usado pelo webhook_server)."""
    session = active_sessions.get(token)
    if not session:
        return None
    # Expirar após 2 horas
    if time.time() - session["created_at"] > 7200:
        active_sessions.pop(token, None)
        return None
    return session


import requests

# ═══════════════════════════════════════════════════════════════════
# 🚀 INICIALIZAÇÃO
# ═══════════════════════════════════════════════════════════════════

def notificar_omni_concluido(project_id, chat_id, project_name):
    """Callback chamado pelo PipelineController quando o Omni termina."""
    token = gerar_session_token(project_id)
    active_sessions[token] = {
        "project_id": project_id,
        "chat_id": chat_id,
        "created_at": time.time()
    }
    session_link = get_session_link(token)
    
    msg = (
        f"✅ *Omni-Anime-Ver Concluído!*\n\n"
        f"O projeto *{project_name}* teve suas legendas e marcações extraídas com sucesso.\n\n"
        f"🎨 *Próximo passo:*\n"
        f"Preciso que você configure o visual da renderização.\n"
        f"[Abrir VideoRender]({session_link})\n\n"
        f"Ao terminar, clique em 'Salvar no Pipeline'."
    )
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })

def main():
    """Inicia o bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado no .env!")
        return

    if not AUTHORIZED_USERS:
        print("⚠️  AUTHORIZED_TELEGRAM_USERS não configurado! Bot aberto a todos.")
    else:
        print(f"🔒 Usuários autorizados: {AUTHORIZED_USERS}")

    init_db()

    from bot.webhook_server import start_webhook_server, set_session_validator
    set_session_validator(validar_sessao)
    start_webhook_server()

    controller.on_omni_done = notificar_omni_concluido

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("novo", cmd_novo))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cells", cmd_cells))
    app.add_handler(CommandHandler("sessao", cmd_sessao))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("myid", cmd_myid))

    # Callbacks (botões inline)
    app.add_handler(CallbackQueryHandler(handle_callback))

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
