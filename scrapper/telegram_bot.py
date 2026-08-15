import os
import re
import logging
import httpx
import asyncio
import time
import concurrent.futures
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from scrapper import database, media_processor, drive_uploader
from scrapper.config import DOUYIN_API_BASE, WEB_PANEL_URL

logger = logging.getLogger(__name__)

# Configurações do .env
AUTHORIZED_USERS = [
    u.strip() for u in os.getenv("AUTHORIZED_TELEGRAM_USERS", "").split(",") if u.strip()
]

# Diretório temporário para processamento de mídia
TEMP_DIR = os.path.join("data", "temp_media")

def is_authorized(update: Update) -> bool:
    """Verifica se o usuário é autorizado pelo ID de forma estrita."""
    user = update.effective_user
    if not user:
        return False
    authorized_raw = os.getenv("AUTHORIZED_TELEGRAM_USERS", "")
    auth_list = [u.strip() for u in authorized_raw.split(",") if u.strip()]
    if not auth_list:
        return True
    return str(user.id) in auth_list


# Helper para obter o contexto ativo do usuário
def get_user_context(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str]:
    """Retorna a categoria e o tipo ativo de conteúdo do usuário (padrão: shorts, anime)."""
    category = context.user_data.get("active_category", "shorts")
    content_type = context.user_data.get("active_content_type", "anime")
    return category, content_type

# Helper para limpar cache do Bot e da API do Evil0ctal
def deep_clean_cache():
    logger.info("Iniciando limpeza física profunda de mídias temporárias e caches...")
    
    # 1. Limpa data/temp_media/
    if os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, f)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Removido temp local: {file_path}")
                except Exception as e:
                    logger.warning(f"Erro ao remover temp local {file_path}: {e}")
                    
    # 2. Limpa cache de download da API local do Evil0ctal
    api_dirs = [
        os.path.join("douyin_api", "download", "bilibili_video"),
        os.path.join("douyin_api", "download", "douyin_video")
    ]
    for d in api_dirs:
        if os.path.exists(d):
            for f in os.listdir(d):
                file_path = os.path.join(d, f)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"Removido cache API local: {file_path}")
                    except Exception as e:
                        logger.warning(f"Erro ao remover cache API {file_path}: {e}")

# ----------------- PIPELINE CENTRALIZADO DE DOWNLOAD -----------------

async def run_download_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    is_douyin: bool,
    category: str,
    content_type: str,
    bvid: str = None,
    custom_title: str = None
) -> bool:
    """Executa o download de forma síncrona dentro de um job assíncrono para atualizar o bot do Telegram."""
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📥 **Iniciando Download Pipeline...**\n"
             f"📋 **Contexto:** {cat_title} - {type_title}\n"
             f"🔗 **URL:** {url}\n"
             f"⏳ Conectando à API em {DOUYIN_API_BASE}...",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_video_path = os.path.join(TEMP_DIR, "temp_download_original.mp4")
    
    # Limpa arquivos temporários antigos se houver
    if os.path.exists(temp_video_path):
        try: os.remove(temp_video_path)
        except: pass
        
    api_download_url = f"{DOUYIN_API_BASE}/api/download"
    download_success = False
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("GET", api_download_url, params={"url": url, "with_watermark": "false"}) as r:
                resp_content_type = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "application/json" not in resp_content_type:
                    total_size = int(r.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_update = 0.0
                    last_percent = 0
                    
                    with open(temp_video_path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                now = time.time()
                                if (percent - last_percent >= 20) or (now - last_update >= 10.0) or (percent == 100):
                                    last_percent = percent
                                    last_update = now
                                    try:
                                        await status_msg.edit_text(
                                            f"📥 **Baixando vídeo...**\n"
                                            f"📋 **Contexto:** {cat_title} - {type_title}\n"
                                            f"⏳ Progresso: **{percent}%** ({downloaded/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB)...",
                                            parse_mode="Markdown"
                                        )
                                    except: pass
                    download_success = os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0
                else:
                    # Falha na API ou retorno de erro JSON
                    await r.aread()
                    try:
                        err_data = r.json()
                        err_msg = err_data.get("message", "Erro interno na API de Download")
                    except Exception:
                        err_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    
                    logger.error(f"Erro no download pela API local (bot) para {url}: {err_msg}")
                    await status_msg.edit_text(f"❌ **Falha ao realizar download** pela API local:\n`{err_msg}`", parse_mode="Markdown")
                    return False
    except Exception as e:
        logger.error(f"Exceção ao baixar vídeo da API: {e}")
        await status_msg.edit_text(f"❌ **Exceção no download** pela API local:\n`{str(e)}`", parse_mode="Markdown")
        return False
        
async def complete_download_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    status_msg,
    temp_video_path: str,
    category: str,
    content_type: str,
    bvid: str,
    custom_title: str,
    url: str,
    action: str,
    custom_speed: float = 1.0
) -> bool:
    """Continua o pipeline de download após a seleção de ação de velocidade/duração."""
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    await status_msg.edit_text("✂️ **Executando processamento de mídia** (FFmpeg duration/audio/cut)...", parse_mode="Markdown")
    
    final_video_path, final_audio_path, proc_success = media_processor.process_media_for_pipeline(
        temp_video_path, TEMP_DIR, category, action, custom_speed
    )
    
    if not proc_success:
        await status_msg.edit_text("❌ **Falha no processamento** do vídeo/áudio usando FFmpeg.", parse_mode="Markdown")
        try: os.remove(temp_video_path)
        except: pass
        return False
        
    await status_msg.edit_text("📤 **Mídia processada!** Iniciando upload para o Google Drive...", parse_mode="Markdown")
    
    loop = asyncio.get_running_loop()
    progress_state = {"last_update": 0.0, "last_percent": 0, "last_file_type": ""}
    
    def drive_progress(file_type, percent):
        now = time.time()
        if (percent - progress_state["last_percent"] >= 20) or \
           (now - progress_state["last_update"] >= 10.0) or \
           (percent == 100) or \
           (file_type != progress_state["last_file_type"]):
            
            progress_state["last_percent"] = percent
            progress_state["last_update"] = now
            progress_state["last_file_type"] = file_type
            
            text = (
                f"📤 **Mídia processada!**\n"
                f"📋 **Contexto:** {cat_title} - {type_title}\n"
                f"⏳ Subindo **{file_type}** para o Google Drive: **{percent}%**..."
            )
            asyncio.run_coroutine_threadsafe(
                status_msg.edit_text(text, parse_mode="Markdown"),
                loop
            )
            
    with concurrent.futures.ThreadPoolExecutor() as executor:
        drive_success = await loop.run_in_executor(
            executor,
            drive_uploader.upload_pipeline_media,
            final_video_path,
            final_audio_path,
            drive_progress
        )
        
    if not drive_success:
        await status_msg.edit_text("❌ **Falha ao realizar o upload** para o Google Drive.", parse_mode="Markdown")
        for p in [temp_video_path, final_video_path, final_audio_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass
        return False
        
    # Salva no banco de dados SQLite
    target_bvid = bvid or f"manual_{int(time.time())}"
    title_reg = custom_title or f"Download manual: {url[:30]}..."
    
    database.register_video(
        bvid=target_bvid,
        title=title_reg,
        source="channel" if bvid else "manual",
        category=category,
        content_type=content_type,
        status="downloaded"
    )
    
    success_text = (
        f"✅ **Sucesso! Vídeo enviado ao Drive!**\n\n"
        f"📝 **Título:** {title_reg}\n"
        f"📂 **Arquivos Enviados:**\n"
        f"├ 🎵 `KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3`\n"
        f"└ 🎥 `KAGGLE/PIPELINE/ATIVO/video_original.mp4`\n\n"
        f"O vídeo foi colocado na fila **Próximo a Postar**!"
    )
    await status_msg.edit_text(success_text, parse_mode="Markdown")
    
    # Se for Shorts e < 50MB, envia de volta no Telegram como prévia
    if category.lower() == "shorts" and os.path.exists(final_video_path):
        file_size_mb = os.path.getsize(final_video_path) / (1024 * 1024)
        if file_size_mb < 49.0:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="upload_video")
                with open(final_video_path, "rb") as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption="🎬 **Prévia do vídeo enviado ao Drive** (Sem marca d'água)"
                    )
            except Exception as ev:
                logger.warning(f"Erro ao enviar prévia do vídeo: {ev}")
                
    # Limpeza física de arquivos temporários e do cache do Evil0ctal
    deep_clean_cache()
    
    return True


async def run_download_pipeline(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    is_douyin: bool,
    category: str,
    content_type: str,
    bvid: str = None,
    custom_title: str = None
) -> bool:
    """Executa o download de forma síncrona dentro de um job assíncrono para atualizar o bot do Telegram."""
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"📥 **Iniciando Download Pipeline...**\n"
             f"📋 **Contexto:** {cat_title} - {type_title}\n"
             f"🔗 **URL:** {url}\n"
             f"⏳ Conectando à API em {DOUYIN_API_BASE}...",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    temp_video_path = os.path.join(TEMP_DIR, "temp_download_original.mp4")
    
    # Limpa arquivos temporários antigos se houver
    if os.path.exists(temp_video_path):
        try: os.remove(temp_video_path)
        except: pass
        
    api_download_url = f"{DOUYIN_API_BASE}/api/download"
    download_success = False
    
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("GET", api_download_url, params={"url": url, "with_watermark": "false"}) as r:
                resp_content_type = r.headers.get("Content-Type", "")
                if r.status_code == 200 and "application/json" not in resp_content_type:
                    total_size = int(r.headers.get("Content-Length", 0))
                    downloaded = 0
                    last_update = 0.0
                    last_percent = 0
                    
                    with open(temp_video_path, "wb") as f:
                        async for chunk in r.aiter_bytes():
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                now = time.time()
                                if (percent - last_percent >= 20) or (now - last_update >= 10.0) or (percent == 100):
                                    last_percent = percent
                                    last_update = now
                                    try:
                                        await status_msg.edit_text(
                                            f"📥 **Baixando vídeo...**\n"
                                            f"📋 **Contexto:** {cat_title} - {type_title}\n"
                                            f"⏳ Progresso: **{percent}%** ({downloaded/(1024*1024):.1f}MB / {total_size/(1024*1024):.1f}MB)...",
                                            parse_mode="Markdown"
                                        )
                                    except: pass
                    download_success = os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0
                else:
                    # Falha na API ou retorno de erro JSON
                    await r.aread()
                    try:
                        err_data = r.json()
                        err_msg = err_data.get("message", "Erro interno na API de Download")
                    except Exception:
                        err_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    
                    logger.error(f"Erro no download pela API local (bot) para {url}: {err_msg}")
                    await status_msg.edit_text(f"❌ **Falha ao realizar download** pela API local:\n`{err_msg}`", parse_mode="Markdown")
                    return False
    except Exception as e:
        logger.error(f"Exceção ao baixar vídeo da API: {e}")
        await status_msg.edit_text(f"❌ **Exceção no download** pela API local:\n`{str(e)}`", parse_mode="Markdown")
        return False
        
    if not download_success:
        await status_msg.edit_text("❌ **Falha ao realizar download** do vídeo pela API local. Verifique se a API está ativa.", parse_mode="Markdown")
        return False
        
    duration = media_processor.get_video_duration(temp_video_path)
    
    # Se for maior que 3 minutos (180s), pergunta a ação de velocidade de forma interativa
    if duration > 180.0:
        target_bvid = bvid or f"manual_{int(time.time())}"
        
        # Salva o estado para continuar depois
        context.user_data[f"active_dl_{target_bvid}"] = {
            "temp_video_path": temp_video_path,
            "category": category,
            "content_type": content_type,
            "custom_title": custom_title,
            "status_msg_id": status_msg.message_id,
            "url": url
        }
        
        text = (
            f"⚠️ **Vídeo longo detectado ({duration/60:.1f} min)!**\n"
            f"Escolha uma ação de velocidade/duração para processamento:"
        )
        keyboard = [
            [InlineKeyboardButton("🚀 Acelerar (Corta 4m -> 2m45s)", callback_data=f"dl_speed:accelerate:{target_bvid}")],
            [InlineKeyboardButton("🐢 Desacelerar (0.9x)", callback_data=f"dl_speed:slow_0.9:{target_bvid}")],
            [InlineKeyboardButton("✍️ Personalizado (Digitar fator)", callback_data=f"dl_speed:custom_prompt:{target_bvid}")],
            [InlineKeyboardButton("🎬 Manter Duração Original", callback_data=f"dl_speed:keep_original:{target_bvid}")]
        ]
        await status_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return True
        
    # Se for menor ou igual a 3 minutos, segue o fluxo normal imediatamente
    return await complete_download_pipeline(
        chat_id=chat_id,
        context=context,
        status_msg=status_msg,
        temp_video_path=temp_video_path,
        category=category,
        content_type=content_type,
        bvid=bvid,
        custom_title=custom_title,
        url=url,
        action="keep_original"
    )

# ----------------- MENUS INLINE -----------------

def get_main_menu_keyboard():
    """Gera o teclado do menu principal."""
    keyboard = [
        [InlineKeyboardButton("📱 Mapeamento Shorts", callback_data="menu:shorts")],
        [InlineKeyboardButton("🎬 Mapeamento Vídeos Longos", callback_data="menu:longos")],
        [InlineKeyboardButton("📋 Fila 'Próximo a Postar'", callback_data="menu_queue:select")],
        [InlineKeyboardButton("🌐 Triagem de Busca Web", callback_data="menu:search_web")],
        [InlineKeyboardButton("⚙️ Configurações / Status", callback_data="menu_config")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_type_menu_keyboard(category):
    """Gera o teclado para selecionar Anime ou Manhwa."""
    keyboard = [
        [
            InlineKeyboardButton("🌸 Anime", callback_data=f"submenu:{category}:anime"),
            InlineKeyboardButton("🇰🇷 Manhwa", callback_data=f"submenu:{category}:manhwa"),
        ],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_panel_keyboard(category, content_type):
    """Gera o teclado do painel de controle do canal."""
    keyboard = [
        [
            InlineKeyboardButton("🔄 Mapear Novos Vídeos", callback_data=f"map:{category}:{content_type}"),
            InlineKeyboardButton("📋 Listar Canais", callback_data=f"list_ch:{category}:{content_type}"),
        ],
        [
            InlineKeyboardButton("➕ Adicionar Canal", callback_data=f"add_ch_prompt:{category}:{content_type}"),
            InlineKeyboardButton("❌ Remover Canal", callback_data=f"del_ch_list:{category}:{content_type}"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data=f"menu:{category}")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_queue_category_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📱 Shorts", callback_data="queue_cat:shorts"),
            InlineKeyboardButton("🎬 Vídeos Longos", callback_data="queue_cat:longos"),
        ],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_queue_type_keyboard(category):
    keyboard = [
        [
            InlineKeyboardButton("🌸 Anime", callback_data=f"queue_type:{category}:anime"),
            InlineKeyboardButton("🇰🇷 Manhwa", callback_data=f"queue_type:{category}:manhwa"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_queue:select")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------- COMANDOS DO BOT -----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o bot e apresenta o menu principal."""
    if not is_authorized(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return

    context.user_data["active_category"] = "shorts"
    context.user_data["active_content_type"] = "anime"
    
    text = (
        "👋 **Bem-vindo ao Scrapper Douyin/Bilibili Bot!**\n\n"
        "💡 **Como usar:** Envie diretamente qualquer link do **Douyin** ou **Bilibili** no chat a qualquer momento "
        "para baixar sem marca d'água, cortar automaticamente (se Shorts > 3min) e enviar direto para o seu Google Drive!\n\n"
        "Selecione uma opção abaixo para navegar:"
    )
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra ajuda básica."""
    if not is_authorized(update): return
    help_text = (
        "📖 **Como usar o Bot:**\n\n"
        "1. Selecione a categoria no menu principal para configurar o contexto.\n"
        "2. Cadastre perfis do Bilibili usando a opção de adicionar canal.\n"
        "3. Clique em **Mapear Novos Vídeos** para mapear posts de canais cadastrados.\n"
        "4. Acesse a fila **Próximo a Postar** para ver todos os posts não publicados (inclusive mapeados pendentes).\n"
        "5. Pela própria Fila, baixe do Bilibili ou envie o link correspondente do Douyin."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# ----------------- FILA "PRÓXIMO A POSTAR" -----------------

async def show_queue_list(message, context, category, content_type):
    posted_7d = database.get_posted_videos_count_since(7)
    since_last = database.get_downloaded_count_since_last_post(category, content_type)
    
    cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
    type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
    
    header_text = (
        f"📋 **Fila 'Próximo a Postar' — {cat_title} - {type_title}**\n\n"
        f"📊 **Estatísticas de Postagem:**\n"
        f"├ 📅 Vídeos publicados nos últimos 7 dias: **{posted_7d}**\n"
        f"└ 📥 Baixados desde sua última publicação: **{since_last}**\n\n"
        f"Abaixo estão os vídeos mapeados (pendentes de download ou prontos no Drive)."
    )
    
    await message.reply_text(header_text, parse_mode="Markdown")
    
    # Busca todos os vídeos não postados (pending e downloaded)
    unposted_items = database.get_unposted_videos(category, content_type)
    
    if not unposted_items:
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_queue:select")]]
        await message.reply_text(
            "📭 Nenhum vídeo mapeado ou pendente de postagem nesta categoria.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    for item in unposted_items:
        origin_label = "👤 Criador"
        if item.get("source") == "search":
            origin_label = "🔍 Busca Geral"
        elif item.get("source") == "manual":
            origin_label = "✍️ Manual"
            
        channel_info = f" ({item['channel_name']})" if item.get("channel_name") else ""
        
        # Formata o status visual do item
        if item["status"] == "downloaded":
            status_visual = "🟢 **[PRONTO NO DRIVE]** (Aguardando Publicação)"
            keyboard = [
                [
                    InlineKeyboardButton("✅ Marcar como Postado", callback_data=f"post:{item['bvid']}:{category}:{content_type}"),
                    InlineKeyboardButton("❌ Remover da Fila", callback_data=f"remove_q:{item['bvid']}:{category}:{content_type}")
                ]
            ]
        else:
            status_visual = "⏳ **[APENAS MAPEADO]** (Aguardando Download)"
            keyboard = [
                [
                    InlineKeyboardButton("📥 Baixar Bilibili", callback_data=f"dl_bili:{item['bvid']}:{category}:{content_type}"),
                    InlineKeyboardButton("🔗 Enviar Link Douyin", callback_data=f"dl_douyin_prompt:{item['bvid']}:{category}:{content_type}")
                ],
                [
                    InlineKeyboardButton("❌ Descartar", callback_data=f"discard:{item['bvid']}:{category}:{content_type}")
                ]
            ]
            
        card_text = (
            f"{status_visual}\n\n"
            f"🎥 **{item['title']}**\n"
            f"├ 🔗 BVID: `{item['bvid']}`\n"
            f"├ 📁 Origem: {origin_label}{channel_info}\n"
            f"└ 🕒 Mapeado em: {item['created_at']}\n\n"
            f"🔗 [Ver no Bilibili](https://www.bilibili.com/video/{item['bvid']})"
        )
        
        await message.reply_text(
            card_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        
    keyboard = [
        [InlineKeyboardButton("🌐 Visualizar Triagem de Busca Web", callback_data="menu:search_web")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu da Fila", callback_data="menu_queue:select")],
        [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]
    ]
    await message.reply_text("Fim da Fila.", reply_markup=InlineKeyboardMarkup(keyboard))

# ----------------- TRATAMENTO DE CALLBACKS (BOTÕES INLINE) -----------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processa cliques nos botões inline do menu."""
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(update):
        await query.message.reply_text("Você não está autorizado.")
        return

    data = query.data
    logger.info(f"Callback recebido: {data}")

    # Cancela qualquer estado de digitação pendente ao navegar
    context.user_data.pop("waiting_for_channel_uid", None)
    context.user_data.pop("waiting_for_douyin_url", None)
    context.user_data.pop("waiting_for_search_term", None)

    # Menu Principal
    if data == "main_menu":
        await query.edit_message_text(
            "Selecione uma categoria de gerenciamento abaixo:",
            reply_markup=get_main_menu_keyboard(),
        )
        
    # Categoria selecionada
    elif data.startswith("menu:"):
        category = data.split(":")[1]
        
        # Direciona para a triagem web
        if category == "search_web":
            import secrets
            # Gera um token seguro de 32 hex chars (16 bytes)
            session_token = secrets.token_hex(16)
            # Salva no banco de dados com validade de 30 minutos
            database.create_web_session(session_token, duration_minutes=30)
            
            # Garante que a URL base termina com barra antes de concatenar o token de sessão, evitando redirecionamento 301 do Nginx que remove os argumentos
            base_url = WEB_PANEL_URL
            if not base_url.endswith("/"):
                base_url += "/"
                
            # Monta a URL com o token
            separator = "&" if "?" in base_url else "?"
            session_url = f"{base_url}{separator}session={session_token}"
            
            text = (
                "🌐 **Painel de Triagem Web**\n\n"
                "O painel web permite triar a busca geral e atualizações de canais de forma visual, com capas e pontuações de Hype!\n\n"
                "👉 Acesse o painel pelo link abaixo (válido por 30 minutos):\n"
                f"🔗 {session_url}\n\n"
                "💡 **Dica:** Os vídeos baixados pelo painel web também aparecerão na fila **Próximo a Postar** do seu Telegram bot!"
            )
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        context.user_data["active_category"] = category
        cat_text = "📱 Shorts (Reels/TikTok)" if category == "shorts" else "🎬 Vídeos Longos"
        await query.edit_message_text(
            f"Selecione o tipo de conteúdo para **{cat_text}**:",
            reply_markup=get_type_menu_keyboard(category),
            parse_mode="Markdown"
        )
        
    # Tipo de Conteúdo selecionado
    elif data.startswith("submenu:"):
        _, category, content_type = data.split(":")
        context.user_data["active_category"] = category
        context.user_data["active_content_type"] = content_type
        
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        await query.edit_message_text(
            f"📂 **Painel: {cat_title} - {type_title}**\n\n"
            f"Gerencie os canais cadastrados ou mapeie novas postagens recentes no Bilibili.",
            reply_markup=get_panel_keyboard(category, content_type),
            parse_mode="Markdown"
        )
        
    # Listar Canais Mapeados
    elif data.startswith("list_ch:"):
        _, category, content_type = data.split(":")
        channels = database.get_channels(category, content_type)
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime" if content_type == "anime" else "Manhwa"
        
        if not channels:
            text = f"📭 Nenhum canal do Bilibili cadastrado em **{cat_title} - {type_title}**."
        else:
            text = f"📋 **Canais cadastrados ({cat_title} - {type_title}):**\n\n"
            for c in channels:
                text += f"👤 **{c['name']}**\n└ UID: `{c['uid']}`\n\n"
                
        keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Prompt para Adicionar Canal
    elif data.startswith("add_ch_prompt:"):
        _, category, content_type = data.split(":")
        context.user_data["waiting_for_channel_uid"] = (category, content_type)
        
        text = (
            "➕ **Adicionar Canal do Bilibili**\n\n"
            "Envie no chat o UID do canal e o nome do canal separados por hífen.\n"
            "Exemplo:\n"
            "`178360345 - Nome do Criador`\n\n"
            "O UID é o número presente no link do perfil (ex: `space.bilibili.com/178360345`)."
        )
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Listar Canais para Remover
    elif data.startswith("del_ch_list:"):
        _, category, content_type = data.split(":")
        channels = database.get_channels(category, content_type)
        
        if not channels:
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            await query.edit_message_text("Nenhum canal cadastrado para remover.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        text = "❌ **Selecione o canal que deseja remover:**"
        keyboard = []
        for c in channels:
            keyboard.append([InlineKeyboardButton(f"❌ {c['name']} (UID: {c['uid']})", callback_data=f"del_ch_exec:{category}:{content_type}:{c['uid']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"submenu:{category}:{content_type}")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    # Executar Remoção de Canal
    elif data.startswith("del_ch_exec:"):
        _, category, content_type, uid = data.split(":")
        success = database.remove_channel(uid)
        
        text = "✅ Canal removido com sucesso!" if success else "❌ Falha ao remover o canal."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data=f"submenu:{category}:{content_type}")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Mapear e Buscar Novos Vídeos do Bilibili (Atualizações)
    elif data.startswith("map:"):
        _, category, content_type = data.split(":")
        
        # Avisa que iniciou
        await query.edit_message_text("🔄 Rastreando postagens recentes dos canais cadastrados... Por favor, aguarde.")
        
        # Executa o mapeamento no banco
        try:
            from scrapper import search_scrapper
            new_count = await search_scrapper.track_channels_updates(content_type)
        except Exception as e:
            logger.error(f"Erro ao rastrear canais: {e}")
            new_count = 0
            
        # Pega as postagens pendentes e filtra pela duração da categoria (Shorts < 4min, Longos >= 4min)
        all_updates = database.get_channel_updates(status="pending", content_type=content_type)
        filtered_updates = []
        for u in all_updates:
            is_short = u["duration_seconds"] < 240
            if category == "shorts" and is_short:
                filtered_updates.append(u)
            elif category == "longos" and not is_short:
                filtered_updates.append(u)
                
        cat_title = "Shorts" if category == "shorts" else "Vídeos Longos"
        type_title = "Anime" if content_type == "anime" else "Manhwa"
        
        if not filtered_updates:
            text = f"✅ **Tudo atualizado!** Nenhuma postagem nova de **{cat_title}** encontrada nos canais de **{type_title}**."
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        else:
            await query.message.reply_text(
                f"✨ **Varredura concluída!** Foram identificadas **{len(filtered_updates)}** novas postagens para triagem em **{cat_title} - {type_title}**.\n\n"
                f"Selecione as que você deseja enviar para o carrinho de downloads:"
            )
            
            for item in filtered_updates:
                duration_str = f"{item['duration_seconds'] // 60}:{item['duration_seconds'] % 60:02d}"
                card_text = (
                    f"🔔 **Mapeamento: Nova Postagem**\n\n"
                    f"🎥 **{item['title']}**\n"
                    f"├ 📺 Canal: {item['author']}\n"
                    f"├ 🕒 Duração: {duration_str}\n"
                    f"└ 📅 Publicado em: {item['published_at']}\n\n"
                    f"🔗 [Ver no Bilibili](https://www.bilibili.com/video/{item['bvid']})"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("🛒 Add ao Carrinho", callback_data=f"cart_add:{item['bvid']}:{category}:{content_type}"),
                        InlineKeyboardButton("🗑️ Ignorar", callback_data=f"update_ignore:{item['bvid']}:{category}:{content_type}")
                    ]
                ]
                await query.message.reply_text(card_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown", disable_web_page_preview=True)
                
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            await query.message.reply_text("Fim da lista de atualizações.", reply_markup=InlineKeyboardMarkup(keyboard))

    # Configurações / Status
    elif data == "menu_config":
        api_status = "🔴 Offline"
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{DOUYIN_API_BASE}/docs")
                if res.status_code == 200:
                    api_status = "🟢 Online"
        except:
            pass
            
        text = (
            "⚙️ **Painel de Configurações e Status**\n\n"
            f"🔌 **API Evil0ctal:** {api_status} ({DOUYIN_API_BASE})\n"
            f"📁 **Diretório Temp:** `{TEMP_DIR}`\n\n"
            "Selecione uma opção de manutenção ou gerencie os termos de busca:"
        )
        keyboard = [
            [InlineKeyboardButton("🔍 Termos de Busca (Anime/Manhwa)", callback_data="menu_search_terms")],
            [InlineKeyboardButton("🧹 Limpar Arquivos Físicos e Cache", callback_data="config_clear_cache")],
            [InlineKeyboardButton("❌ Limpar Banco de Dados (Limpar Tudo)", callback_data="config_clear_db")],
            [InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="main_menu")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "config_clear_cache":
        deep_clean_cache()
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_config")]]
        await query.edit_message_text("✅ Caches físicos e diretório temporário apagados com sucesso!", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "config_clear_db":
        success = database.clean_database()
        text = "✅ Banco de dados limpo com sucesso!" if success else "❌ Falha ao limpar o banco de dados."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_config")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # ─── GERENCIAMENTO DE TERMOS DE BUSCA ───
    elif data == "menu_search_terms":
        anime_terms = database.get_search_terms("anime")
        manhwa_terms = database.get_search_terms("manhwa")
        
        anime_list = "\n".join(f"• `{t['term']}`" for t in anime_terms) if anime_terms else "_Nenhum termo cadastrado_"
        manhwa_list = "\n".join(f"• `{t['term']}`" for t in manhwa_terms) if manhwa_terms else "_Nenhum termo cadastrado_"
        
        text = (
            "🔍 **Gerenciamento de Termos de Busca**\n\n"
            "Aqui estão os termos cadastrados para a triagem automatizada no Bilibili:\n\n"
            f"🌸 **Anime:**\n{anime_list}\n\n"
            f"🇰🇷 **Manhwa:**\n{manhwa_list}\n\n"
            "Selecione uma opção abaixo para gerenciar:"
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ Add Anime", callback_data="add_term_prompt:anime"),
                InlineKeyboardButton("➕ Add Manhwa", callback_data="add_term_prompt:manhwa")
            ],
            [
                InlineKeyboardButton("❌ Del Anime", callback_data="del_term_list:anime"),
                InlineKeyboardButton("❌ Del Manhwa", callback_data="del_term_list:manhwa")
            ],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_config")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("add_term_prompt:"):
        content_type = data.split(":")[1]
        context.user_data["waiting_for_search_term"] = content_type
        
        type_label = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        text = (
            f"➕ **Adicionar Termo de Busca - {type_label}**\n\n"
            "Envie agora no chat o termo que deseja adicionar à busca do Bilibili.\n"
            "Exemplo:\n`韩漫解说` ou o nome de um anime em chinês."
        )
        keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data="menu_search_terms")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("del_term_list:"):
        content_type = data.split(":")[1]
        terms = database.get_search_terms(content_type)
        
        type_label = "Anime 🌸" if content_type == "anime" else "Manhwa 🇰🇷"
        
        if not terms:
            keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_search_terms")]]
            await query.edit_message_text(f"Não há termos de busca cadastrados para {type_label} para remover.", reply_markup=InlineKeyboardMarkup(keyboard))
            return
            
        text = f"❌ **Selecione o termo de {type_label} que deseja remover:**"
        keyboard = []
        for t in terms:
            keyboard.append([InlineKeyboardButton(f"❌ {t['term']}", callback_data=f"del_term_exec:{content_type}:{t['id']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_search_terms")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("del_term_exec:"):
        _, content_type, term_id = data.split(":")
        success = database.remove_search_term(int(term_id))
        
        text = "✅ Termo de busca removido com sucesso!" if success else "❌ Falha ao remover o termo de busca."
        keyboard = [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_search_terms")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Callbacks da fila "Próximo a Postar"
    elif data == "menu_queue:select":
        await query.edit_message_text(
            "📋 **Fila 'Próximo a Postar'**\n\nSelecione a categoria de visualização:",
            reply_markup=get_queue_category_keyboard(),
            parse_mode="Markdown"
        )

    elif data.startswith("queue_cat:"):
        category = data.split(":")[1]
        await query.edit_message_text(
            "Selecione o tipo de conteúdo para a Fila:",
            reply_markup=get_queue_type_keyboard(category),
            parse_mode="Markdown"
        )

    elif data.startswith("queue_type:"):
        _, category, content_type = data.split(":")
        await query.edit_message_text("🔄 Carregando fila de postagem... Por favor, aguarde.")
        await show_queue_list(query.message, context, category, content_type)

    # Ações da fila (Marcar como Postado)
    elif data.startswith("post:"):
        _, bvid, category, content_type = data.split(":")
        success = database.mark_video_as_posted(bvid)
        if success:
            await query.edit_message_text("✅ Vídeo marcado como publicado e removido da fila!")
        else:
            await query.edit_message_text("❌ Falha ao atualizar o status do vídeo no banco.")

    # Ações da fila (Remover/Descartar da fila)
    elif data.startswith("remove_q:") or data.startswith("discard:"):
        _, bvid, category, content_type = data.split(":")
        database.update_search_result_status(bvid, "pending")
        database.update_channel_update_status(bvid, "pending")
        success = database.remove_video_from_queue(bvid)
        if success:
            await query.edit_message_text("❌ Vídeo removido/descartado com sucesso da fila!")
        else:
            await query.edit_message_text("❌ Falha ao remover o vídeo do banco.")
            
    # Triagem direta no Telegram (Add ao Carrinho)
    elif data.startswith("cart_add:"):
        _, bvid, category, content_type = data.split(":")
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channel_updates WHERE bvid = ?", (bvid,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            item = dict(row)
            success = database.register_video(
                bvid=bvid,
                title=item["title"],
                source="channel",
                category=category,
                content_type=content_type,
                status="pending"
            )
            if success:
                database.update_channel_update_status(bvid, "in_cart")
                await query.edit_message_text(f"🛒 **Adicionado ao Carrinho!**\n\n🎥 {item['title'][:60]}")
            else:
                await query.message.reply_text("Erro ao adicionar ao carrinho.")
        else:
            await query.message.reply_text("Erro: Postagem não encontrada no banco.")
            
    # Triagem direta no Telegram (Ignorar Update)
    elif data.startswith("update_ignore:"):
        _, bvid, category, content_type = data.split(":")
        success = database.update_channel_update_status(bvid, "ignored")
        if success:
            await query.edit_message_text("🗑️ **Postagem Ocultada/Ignorada!**")
        else:
            await query.message.reply_text("Erro ao atualizar status.")

    # Download direto do Bilibili na fila
    elif data.startswith("dl_bili:"):
        _, bvid, category, content_type = data.split(":")
        url = f"https://www.bilibili.com/video/{bvid}"
        
        await query.edit_message_text("📥 Download do Bilibili iniciado! Aguarde o processamento...")
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=query.message.chat_id,
                context=context,
                url=url,
                is_douyin=False,
                category=category,
                content_type=content_type,
                bvid=bvid,
                custom_title=f"Mapeado: {bvid}"
            )
        )
        
    # Solicitar link Douyin na fila
    elif data.startswith("dl_douyin_prompt:"):
        _, bvid, category, content_type = data.split(":")
        context.user_data["waiting_for_douyin_url"] = (bvid, category, content_type)
        
        await query.edit_message_text(
            f"🔗 **Enviar Link Douyin para BVID `{bvid}`**\n\n"
            f"Envie agora no chat o link do Douyin sem marca d'água correspondente a este vídeo."
        )

    # Lógica de ação de velocidade na fila de download manual
    elif data.startswith("dl_speed:"):
        parts = data.split(":")
        action = parts[1]
        target_bvid = parts[2]
        
        dl_state = context.user_data.get(f"active_dl_{target_bvid}")
        if not dl_state:
            await query.answer("Esta sessão de download expirou ou é inválida.", show_alert=True)
            return
            
        status_msg = query.message
        
        if action == "custom_prompt":
            # Pergunta para digitar o fator
            context.user_data[f"waiting_for_dl_speed_{target_bvid}"] = dl_state
            await query.edit_message_text(
                "✍️ **Digitar Velocidade Customizada**\n\n"
                "Envie agora no chat o fator de velocidade desejado (ex: `0.85`, `0.9` ou `1.15`):",
                reply_markup=None,
                parse_mode="Markdown"
            )
            return
            
        # Remover estado ativo
        context.user_data.pop(f"active_dl_{target_bvid}", None)
        await query.answer("Ação de velocidade selecionada!")
        
        # Obter velocidade
        custom_speed = 1.0
        if action.startswith("slow_"):
            custom_speed = float(action.split("_")[1])
            action = "speedup_custom"
            
        asyncio.create_task(
            complete_download_pipeline(
                chat_id=query.message.chat_id,
                context=context,
                status_msg=status_msg,
                temp_video_path=dl_state["temp_video_path"],
                category=dl_state["category"],
                content_type=dl_state["content_type"],
                bvid=target_bvid,
                custom_title=dl_state["custom_title"],
                url=dl_state["url"],
                action=action,
                custom_speed=custom_speed
            )
        )

# ----------------- TRATAMENTO DE MENSAGENS DE TEXTO -----------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trata mensagens de texto enviadas no chat (links ou cadastro de canais)."""
    if not is_authorized(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return

    text = update.message.text.strip()
    logger.info(f"Mensagem recebida: {text}")

    # Intercepta se estiver aguardando um fator de velocidade customizado para download avulso
    waiting_dl_speed_key = next((k for k in context.user_data if k.startswith("waiting_for_dl_speed_")), None)
    if waiting_dl_speed_key:
        target_bvid = waiting_dl_speed_key.replace("waiting_for_dl_speed_", "")
        dl_state = context.user_data.pop(waiting_dl_speed_key)
        
        # Limpa estado ativo de download
        context.user_data.pop(f"active_dl_{target_bvid}", None)
        
        text_input = text.strip()
        try:
            custom_speed = float(text_input)
            if custom_speed <= 0.1 or custom_speed > 3.0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ Fator de velocidade inválido! Digite um número positivo entre 0.1 e 3.0 (ex: 0.9). Download abortado.")
            try: os.remove(dl_state["temp_video_path"])
            except: pass
            return
            
        status_msg = await update.message.reply_text(f"⏳ Processando com a velocidade customizada de {custom_speed}x...")
        
        asyncio.create_task(
            complete_download_pipeline(
                chat_id=update.effective_chat.id,
                context=context,
                status_msg=status_msg,
                temp_video_path=dl_state["temp_video_path"],
                category=dl_state["category"],
                content_type=dl_state["content_type"],
                bvid=target_bvid,
                custom_title=dl_state["custom_title"],
                url=dl_state["url"],
                action="speedup_custom",
                custom_speed=custom_speed
            )
        )
        return

    # 0. Adicionar termo de busca
    if "waiting_for_search_term" in context.user_data:
        content_type = context.user_data["waiting_for_search_term"]
        term = text.strip()
        
        success = database.add_search_term(term, content_type)
        context.user_data.pop("waiting_for_search_term", None)
        
        keyboard = [[InlineKeyboardButton("⬅️ Voltar aos Termos", callback_data="menu_search_terms")]]
        if success:
            await update.message.reply_text(
                f"✅ Termo de busca **{term}** adicionado com sucesso para **{content_type}**!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"❌ Erro ao adicionar o termo de busca (ou o termo já existe).",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return

    # 1. Cadastro de canal
    if "waiting_for_channel_uid" in context.user_data:
        category, content_type = context.user_data["waiting_for_channel_uid"]
        
        match = re.match(r"^(\d+)\s*-\s*(.+)$", text)
        if match:
            uid = match.group(1).strip()
            name = match.group(2).strip()
            
            await update.message.reply_text("⏳ Buscando último post do canal como referência inicial...")
            try:
                from scrapper import search_scrapper
                latest_video = await search_scrapper.get_latest_video_for_channel(uid)
                last_ref = latest_video["bvid"] if latest_video else None
            except Exception as e:
                logger.error(f"Erro ao obter referência de canal: {e}")
                last_ref = None
                
            success = database.add_channel(uid, name, category, content_type, last_video_ref=last_ref)
            context.user_data.pop("waiting_for_channel_uid", None)
            
            keyboard = [[InlineKeyboardButton("⬅️ Voltar ao Painel", callback_data=f"submenu:{category}:{content_type}")]]
            if success:
                if last_ref:
                    ref_msg = f"\n\n*(Referência inicial: `{last_ref}`)*"
                else:
                    ref_msg = "\n\n*(Sem referência inicial. O sistema tentará buscá-la de forma automática na inicialização ou no próximo mapeamento.)*"
                await update.message.reply_text(f"✅ Canal **{name}** (UID: {uid}) adicionado!{ref_msg}", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

            else:
                await update.message.reply_text("❌ Erro ao salvar o canal no banco de dados.", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(
                "⚠️ Formato inválido! Envie no formato:\n"
                "`UID - Nome do Criador`\n\n"
                "Exemplo:\n`178360345 - Azulsolitan`"
            )
        return

    # 2. Upload associado ao Douyin sob demanda
    if "waiting_for_douyin_url" in context.user_data:
        bvid, category, content_type = context.user_data["waiting_for_douyin_url"]
        
        douyin_match = re.search(r"(https?://\S*douyin\.com\S*)", text)
        if not douyin_match:
            await update.message.reply_text(
                "⚠️ Link do Douyin inválido! Por favor, envie um link válido do Douyin para associar a este vídeo."
            )
            return
            
        url = douyin_match.group(1)
        context.user_data.pop("waiting_for_douyin_url", None)
        
        await update.message.reply_text("✅ Link do Douyin recebido! Iniciando pipeline de download...")
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=update.effective_chat.id,
                context=context,
                url=url,
                is_douyin=True,
                category=category,
                content_type=content_type,
                bvid=bvid,
                custom_title=f"Douyin associado ao BVID: {bvid}"
            )
        )
        return

    # 3. Downloads manuais avulsos
    douyin_match = re.search(r"(https?://\S*douyin\.com\S*)", text)
    bilibili_match = re.search(r"(https?://\S*(bilibili\.com|b23\.tv)\S*)", text)
    
    if douyin_match or bilibili_match:
        url = (douyin_match or bilibili_match).group(1)
        category, content_type = get_user_context(context)
        is_douyin = bool(douyin_match)
        
        asyncio.create_task(
            run_download_pipeline(
                chat_id=update.effective_chat.id,
                context=context,
                url=url,
                is_douyin=is_douyin,
                category=category,
                content_type=content_type,
                bvid=f"manual_{int(time.time())}",
                custom_title=f"Manual: {url[:30]}..."
            )
        )
        return

    await update.message.reply_text(
        "❓ Comando ou link não reconhecido. Envie um link válido do Douyin ou Bilibili, "
        "ou utilize o menu abaixo para navegar pelas opções.",
        reply_markup=get_main_menu_keyboard()
    )

async def cookie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para atualizar o DOUYIN_COOKIE dinamicamente pelo Telegram."""
    if not is_authorized(update):
        return
        
    args = context.args
    if not args:
        await update.message.reply_text(
            "🍪 *Como usar o comando /cookie:*\n\n"
            "Envie: `/cookie SEU_COOKIE_AQUI`\n\n"
            "O robô salvará no `.env` e sincronizará automaticamente com a API local!",
            parse_mode="Markdown"
        )
        return

    cookie_val = " ".join(args).strip()
    
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    
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

        from scripts import sync_cookie
        sync_cookie.sync()

        await update.message.reply_text("✅ *Cookie do Douyin atualizado e sincronizado com sucesso!*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar cookie: {e}")

async def bili_cookie_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para atualizar o cookie do Bilibili dinamicamente pelo Telegram."""
    if not is_authorized(update):
        return
        
    args = context.args
    if not args:
        await update.message.reply_text(
            "📺 *Como usar o comando /bili_cookie:*\n\n"
            "Envie: `/bili_cookie SEU_COOKIE_BILIBILI_AQUI`\n\n"
            "O robô salvará no `config.yaml` do Bilibili e reiniciará o serviço da API local automaticamente!",
            parse_mode="Markdown"
        )
        return

    cookie_val = " ".join(args).strip()
    
    from pathlib import Path
    import yaml
    import subprocess
    
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "douyin_api" / "crawlers" / "bilibili" / "web" / "config.yaml"
    
    if not config_path.exists():
        await update.message.reply_text("❌ Arquivo de configuração do Bilibili não encontrado.")
        return
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
            
        # Atualiza o cookie
        if 'TokenManager' in config_data and 'bilibili' in config_data['TokenManager']:
            config_data['TokenManager']['bilibili']['headers']['cookie'] = cookie_val
            
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(config_data, f, allow_unicode=True)
                
            # Reinicia o serviço douyin-api na VPS
            subprocess.run(["sudo", "systemctl", "restart", "douyin-api.service"])
            
            await update.message.reply_text("✅ *Cookie do Bilibili atualizado e serviço reiniciado com sucesso!*", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Estrutura do arquivo config.yaml do Bilibili é inválida.")
    except Exception as e:
        await update.message.reply_text(f"❌ Erro ao atualizar cookie: {e}")

async def colecoes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para listar coleções cadastradas e o status de autoposting."""
    if not is_authorized(update):
        return

    cols = database.get_douyin_collections()
    if not cols:
        await update.message.reply_text("📚 Nenhuma coleção cadastrada no momento.")
        return

    msg = "📚 *Coleções Cadastradas (Douyin):*\n\n"
    for c in cols[:10]:
        autopost = "🟢 ON" if c.get("autoposting") else "🔴 OFF"
        msg += f"🎬 *{c['title_pt']}* ({c['title_zh']})\n"
        msg += f"   📊 Progresso: {c.get('posted_count', 0)} / {c.get('total_episodes_mapped', 0)} EPs\n"
        msg += f"   ⚡ Autoposting: {autopost}\n"
        msg += f"   🔗 ID: `{c['mix_id']}`\n\n"

    msg += f"💡 _Total de {len(cols)} coleções ativas._"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ----------------- INICIALIZAÇÃO DO BOT -----------------

def run_bot():
    token = os.getenv("SCRAPPER_TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERRO: SCRAPPER_TELEGRAM_TOKEN não configurado no arquivo .env!")
        return
        
    database.init_db()

    
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cookie", cookie_command))
    app.add_handler(CommandHandler("bili_cookie", bili_cookie_command))
    app.add_handler(CommandHandler("colecoes", colecoes_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("Iniciando Bot de Download do Douyin/Bilibili...")
    app.run_polling(drop_pending_updates=True, stop_signals=None, close_loop=False)


