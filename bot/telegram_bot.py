"""
Bot Telegram — Agente de Postagem
Controle completo do pipeline via Telegram.
Protegido por lista de IDs autorizados.
"""

import os
import sys
import asyncio
import tempfile
import logging
import uuid
import hashlib
import time
from functools import wraps

# Força UTF-8 no console do Windows (evita charmap error com emojis)
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from dotenv import load_dotenv

from bot.database import (
    init_db, get_active_project, get_project, get_running_projects,
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
        "  /upload — Obter link para upload local de arquivos\n"
        "  /cancel — Cancela projeto ativo\n"
        "  /myid — Mostra seu User ID\n\n"
        "📦 *Envio de arquivos:*\n"
        "  1. Envie o *vídeo* (com marca d'água)\n"
        "  2. Envie o *áudio* (original do vídeo)\n"
        "  3. Use `/novo Nome do Anime`\n\n"
        "💻 *Para vídeos gigantes (>20MB):*\n"
        "  Use o comando `/upload` para receber o link do painel web,\n"
        "  faça o upload dos arquivos e depois use:\n"
        "  `/usar_local Nome do Anime`",
        parse_mode="Markdown"
    )


@authorized
async def cmd_myid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Mostra o User ID do Telegram."""
    uid = update.effective_user.id
    await update.message.reply_text(f"🆔 Seu User ID: `{uid}`", parse_mode="Markdown")


@authorized
async def cmd_upload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Gera link para upload local de arquivos grandes."""
    upload_url = os.getenv("WEBHOOK_UPLOAD_URL", "http://localhost:8080/upload")
    await update.message.reply_text(
        f"📂 *Upload Local*\n\n"
        f"Use o link abaixo no seu navegador para enviar vídeos maiores que 20MB:\n"
        f"👉 [Acessar Painel de Upload]({upload_url})\n\n"
        f"Após o upload, inicie o projeto com:\n"
        f"`/usar_local Nome do Anime`",
        parse_mode="Markdown"
    )



@authorized
async def cmd_teste_enhancer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Comando de teste isolado para o Video Enhancer."""
    chat_id = str(update.effective_chat.id)
    uploads = user_uploads.get(chat_id, {})
    video_path = uploads.get("video")
    
    if not video_path:
        await update.message.reply_text("❌ Envie um vídeo primeiro e depois chame /teste_enhancer.")
        return

    await update.message.reply_text("🚀 Iniciando Teste do Enhancer (só PT1)...")
    
    import uuid, asyncio
    from bot.drive_manager import DriveManager
    from bot.github_actions import dispatch_parallel
    
    pid = str(uuid.uuid4())
    
    async def run_test():
        try:
            drive = DriveManager()
            await update.message.reply_text("⏳ Fazendo upload do video pro Drive (pt1_limpo.mp4)...")
            await asyncio.to_thread(drive.salvar, video_path, "KAGGLE/PIPELINE/WATERMARK/pt1_limpo.mp4")
            
            await update.message.reply_text("🚀 Disparando workflow do Enhancer no Kaggle...")
            await asyncio.to_thread(dispatch_parallel, ["enhancer-pt1"], pid)
            
            await update.message.reply_text("✅ Workflow disparado! Acompanhe os logs pelo Kaggle.\nO arquivo gerado será KAGGLE/PIPELINE/ENHANCER/pt1_enhanced.mp4")
            
            # Limpa cache do user para não interferir em outros comandos
            user_uploads.pop(chat_id, None)
        except Exception as e:
            await update.message.reply_text(f"❌ Erro no teste: {e}")

    asyncio.create_task(run_test())

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
    
    # Prepara o estado temporário
    user_uploads[chat_id]["name"] = project_name
    user_uploads[chat_id]["local"] = False
    user_uploads[chat_id]["watermark"] = True
    user_uploads[chat_id]["enhancer"] = False
    
    await send_config_menu(update, chat_id)

@authorized
async def cmd_usar_local(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Inicia o projeto pegando os arquivos direto da pasta uploads local."""
    chat_id = str(update.effective_chat.id)
    active = get_active_project(chat_id)
    if active:
        await update.message.reply_text("⚠️ Já existe um projeto ativo. Use /cancel primeiro.")
        return

    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    files = os.listdir(uploads_dir)
    videos = [f for f in files if any(f.lower().endswith(ext) for ext in [".mp4", ".mkv", ".avi", ".mov"])]
    audios = [f for f in files if any(f.lower().endswith(ext) for ext in [".mp3", ".wav", ".m4a", ".aac"])]
    
    if not videos or not audios:
        await update.message.reply_text(
            f"❌ Arquivos não encontrados!\n"
            f"Coloque 1 vídeo e 1 áudio na pasta:\n`{uploads_dir}`\n"
            f"E tente novamente."
        )
        return

    video_path = os.path.join(uploads_dir, videos[0])
    audio_path = os.path.join(uploads_dir, audios[0])
    project_name = " ".join(ctx.args) if ctx.args else f"Projeto_{chat_id[:6]}"

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
        
    user_uploads[chat_id]["video"] = video_path
    user_uploads[chat_id]["audio"] = audio_path
    user_uploads[chat_id]["name"] = project_name
    user_uploads[chat_id]["local"] = True
    user_uploads[chat_id]["watermark"] = True
    user_uploads[chat_id]["enhancer"] = False

    await send_config_menu(update, chat_id)


async def send_config_menu(update, chat_id, query=None):
    """Envia ou atualiza o menu de configurações do projeto."""
    opts = user_uploads.get(chat_id)
    if not opts:
        return

    wm_text = "✅ Remover Marca d'água" if opts["watermark"] else "❌ Remover Marca d'água"
    enhancer_text = "✅ Aumentar Qualidade" if opts["enhancer"] else "❌ Aumentar Qualidade"

    buttons = [
        [InlineKeyboardButton(wm_text, callback_data="toggle_wm")],
        [InlineKeyboardButton(enhancer_text, callback_data="toggle_enhancer")],
        [InlineKeyboardButton("▶️ Iniciar Projeto", callback_data="start_project")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    
    text = (
        f"⚙️ *Configurações Iniciais*\n"
        f"Projeto: `{opts['name']}`\n\n"
        f"Selecione quais processos opcionais deseja executar antes da dublagem:"
    )

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


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
        f"🎬 Sessão VideoRender\n\n"
        f"Projeto: {project['project_name']}\n"
        f"⏰ Válida por 2 horas\n\n"
        f"🔗 {session_link}"
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

    if data == "toggle_wm":
        if chat_id in user_uploads:
            user_uploads[chat_id]["watermark"] = not user_uploads[chat_id]["watermark"]
            await send_config_menu(None, chat_id, query)
            
    elif data == "toggle_enhancer":
        if chat_id in user_uploads:
            user_uploads[chat_id]["enhancer"] = not user_uploads[chat_id]["enhancer"]
            await send_config_menu(None, chat_id, query)
            
    elif data == "start_project":
        if chat_id not in user_uploads:
            await query.edit_message_text("❌ Sessão expirada. Envie os arquivos novamente.")
            return
            
        opts = user_uploads[chat_id]
        
        await query.edit_message_text(
            f"🚀 Iniciando projeto: *{opts['name']}*\n"
            f"📤 Fazendo upload e dividindo vídeo...",
            parse_mode="Markdown"
        )

        try:
            # Informar ao controller as opções selecionadas (rodando em background para não bloquear o loop)
            project = await asyncio.to_thread(
                controller.iniciar_projeto,
                project_name=opts["name"],
                chat_id=chat_id,
                video_path=opts["video"],
                audio_path=opts["audio"],
                mask_path=opts.get("mask"),
                opts=opts  # Passar as configs para o controller registrar
            )
            pid = str(project["id"])

            token = gerar_session_token(pid)
            active_sessions[token] = {"project_id": pid, "chat_id": chat_id, "created_at": time.time()}
            session_link = get_session_link(token)

            # Dispara o Omni ANTES de enviar a mensagem (pra não bloquear se a msg falhar)
            controller.disparar_omni_imediatamente(pid)

            await query.message.reply_text(
                f"✅ Upload e Divisão Concluídos!\n\n"
                f"🔄 Disparando a Dublagem (Omni)...\n\n"
                f"⚙️ Sessão de Configuração de Legenda:\n"
                f"Configure o estilo da legenda (com um texto placeholder).\n"
                f"Se quiser remover marca d'água, adicione a máscara na tela de config.\n\n"
                f"🎬 Abrir VideoRender:\n{session_link}\n\n"
                f"📊 Use /status para acompanhar."
            )
            
            # Removemos a config após iniciar
            user_uploads.pop(chat_id, None)

        except Exception as e:
            await query.message.reply_text(f"❌ Erro ao iniciar projeto:\n`{e}`", parse_mode="Markdown")

    elif data == "refresh_status":
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
                f"🎬 Abrir VideoRender:\n{session_link}"
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

    msg = await message.reply_text(f"⬇️ Baixando vídeo: `{file_name}`...", parse_mode="Markdown")

    temp_dir = tempfile.mkdtemp(prefix="anime_pipeline_")
    local_path = os.path.join(temp_dir, file_name)

    try:
        if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
            await msg.edit_text("❌ *Erro*: O Telegram limita o download de bots a 20MB. Por favor, envie um vídeo menor ou compactado.", parse_mode="Markdown")
            return

        tg_file = await ctx.bot.get_file(file_obj.file_id)
        
        import httpx
        import time
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", tg_file.file_path) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", file_obj.file_size or 0))
                downloaded = 0
                last_update = time.time()
                
                with open(local_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192 * 4):
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if total_size and (now - last_update > 2.0):
                            percent = (downloaded / total_size) * 100
                            try:
                                await msg.edit_text(f"⬇️ Baixando vídeo: `{file_name}`\n⏳ *{percent:.1f}%* ({downloaded//1024//1024}MB / {total_size//1024//1024}MB)", parse_mode="Markdown")
                            except Exception:
                                pass
                            last_update = now
    except Exception as e:
        await msg.edit_text(f"❌ Erro ao baixar vídeo: `{e}`", parse_mode="Markdown")
        return

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
    user_uploads[chat_id]["video"] = local_path

    has_audio = user_uploads[chat_id].get("audio")
    await msg.edit_text(
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

    msg = await message.reply_text(f"⬇️ Baixando áudio: `{file_name}`...", parse_mode="Markdown")

    temp_dir = tempfile.mkdtemp(prefix="anime_pipeline_")
    local_path = os.path.join(temp_dir, file_name)

    try:
        if file_obj.file_size and file_obj.file_size > 20 * 1024 * 1024:
            await msg.edit_text("❌ *Erro*: O Telegram limita o download de bots a 20MB. Por favor, envie um áudio menor ou compactado.", parse_mode="Markdown")
            return

        tg_file = await ctx.bot.get_file(file_obj.file_id)
        
        import httpx
        import time
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", tg_file.file_path) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("Content-Length", file_obj.file_size or 0))
                downloaded = 0
                last_update = time.time()
                
                with open(local_path, "wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192 * 4):
                        f.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        if total_size and (now - last_update > 2.0):
                            percent = (downloaded / total_size) * 100
                            try:
                                await msg.edit_text(f"⬇️ Baixando áudio: `{file_name}`\n⏳ *{percent:.1f}%* ({downloaded//1024//1024}MB / {total_size//1024//1024}MB)", parse_mode="Markdown")
                            except Exception:
                                pass
                            last_update = now
    except Exception as e:
        await msg.edit_text(f"❌ Erro ao baixar áudio: `{e}`", parse_mode="Markdown")
        return

    if chat_id not in user_uploads:
        user_uploads[chat_id] = {}
    user_uploads[chat_id]["audio"] = local_path

    has_video = user_uploads[chat_id].get("video")
    msg_ready = "📦 Pronto! Use /novo <nome> para iniciar."
    msg_wait = "📎 Agora envie o *vídeo* com marca d'água."
    await msg.edit_text(
        f"✅ Áudio recebido: `{file_name}`\n"
        f"{msg_ready if has_video else msg_wait}",
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
        f"✅ Omni-Anime-Ver Concluído!\n\n"
        f"O projeto {project_name} teve suas legendas e marcações extraídas com sucesso.\n\n"
        f"🎨 Próximo passo:\n"
        f"Configure o visual da renderização.\n"
        f"Ao terminar, clique em 'Salvar no Pipeline'.\n\n"
        f"🔗 {session_link}"
    )
    
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(api_url, json={
        "chat_id": chat_id,
        "text": msg
    })

def main():
    """Inicia o bot."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN não configurado no .env!")
        return

    if not AUTHORIZED_USERS:
        print("AVISO: AUTHORIZED_TELEGRAM_USERS nao configurado! Bot aberto a todos.")
    else:
        print(f"Usuarios autorizados: {AUTHORIZED_USERS}")

    init_db()

    from bot.webhook_server import start_webhook_server, set_session_validator
    set_session_validator(validar_sessao)
    start_webhook_server()

    controller.on_omni_done = notificar_omni_concluido

    # Polling periódico via thread (não depende de job_queue extra)
    import threading

    def _pipeline_poll_loop():
        """Thread que verifica o banco a cada 30s e avança o pipeline."""
        while True:
            try:
                projects = get_running_projects()
                for proj in projects:
                    pid = str(proj["id"])
                    controller.verificar_e_avancar(pid)
            except Exception as e:
                logger.error(f"Erro no polling do pipeline: {e}")
            time.sleep(30)

    poll_thread = threading.Thread(target=_pipeline_poll_loop, daemon=True)
    poll_thread.start()
    print("Pipeline polling ativo (30s via thread).")

    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("start", "Mensagem de boas-vindas"),
            BotCommand("novo", "Inicia novo projeto"),
            BotCommand("status", "Status do projeto ativo"),
            BotCommand("cells", "Tracking por célula"),
            BotCommand("sessao", "Gera link do VideoRender"),
            BotCommand("config", "Confirma config (dispara render)"),
            BotCommand("upload", "Obter link para upload local"),
            BotCommand("cancel", "Cancela projeto ativo"),
            BotCommand("usar_local", "Iniciar projeto com arquivos do PC"),
        ])
        print("Comandos do Telegram registrados no menu azul!")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Comandos
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("novo", cmd_novo))
    app.add_handler(CommandHandler("teste_enhancer", cmd_teste_enhancer))
    app.add_handler(CommandHandler("usar_local", cmd_usar_local))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cells", cmd_cells))
    app.add_handler(CommandHandler("sessao", cmd_sessao))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("upload", cmd_upload))
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

    print("Bot Telegram iniciado! Ctrl+C para parar.")
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
