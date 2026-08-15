import os
import sys
import html
import json
import threading
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import requests
import re

# Configura o stdout/stderr para flushing imediato no console do terminal
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Módulos locais
try:
    from post_recap import db, youtube_uploader, tiktok_service, instagram_uploader
    from post_recap.drive_manager import drive_manager
except ImportError:
    import db
    from drive_manager import drive_manager
    import youtube_uploader
    import tiktok_service
    import instagram_uploader

load_dotenv()


# Filtra o texto para manter no máximo 5 hashtags
def filter_hashtags(text, max_tags=5):
    import re
    hashtags = re.findall(r'#\w+', text)
    if len(hashtags) <= max_tags:
        return text
    # Remove as hashtags excedentes do texto
    keep = set(hashtags[:max_tags])
    count = {}
    def replacer(m):
        tag = m.group(0)
        count[tag] = count.get(tag, 0) + 1
        if tag in keep and count[tag] == 1:
            return tag
        return ""
    return re.sub(r'#\w+', replacer, text).strip()


# Estados da conversação
SELECT_PLATFORMS, SELECT_YOUTUBE_TITLE, INPUT_YOUTUBE_TITLE_MANUAL, SELECT_SHORTS_TITLE, INPUT_SHORTS_TITLE_MANUAL, SELECT_YOUTUBE_PRIVACY, SELECT_INSTAGRAM_SCHEDULING, INPUT_INSTAGRAM_TIME, SELECT_TIKTOK_PRIVACY, SELECT_TIKTOK_SCHEDULING, INPUT_TIKTOK_TIME, CONFIRM_POST, INPUT_UNIFIED_SCHEDULE_TIME = range(13)

# Lista de usuários aprovados (suporta IDs e Usernames)
APPROVED_USERS = [u.strip() for u in (os.getenv("AUTHORIZED_TELEGRAM_USERS", "") + "," + os.getenv("APPROVED_USERS", "")).split(",") if u.strip()]

def user_is_approved(update: Update) -> bool:
    """Verifica se o usuário que enviou a mensagem está autorizado por username ou ID."""
    user = update.effective_user
    if not user:
        return False
    # Se não houver lista no .env, permite por padrão
    if not APPROVED_USERS:
        return True
    return (user.username in APPROVED_USERS) or (str(user.id) in APPROVED_USERS)

# Worker de fila para agendamentos (roda em segundo plano)
def run_queue_worker(bot):
    print("Iniciando Worker de fila em segundo plano...")
    while True:
        try:
            # Executa a função síncrona de processamento da fila do Instagram antigo
            instagram_uploader.process_instagram_queue()
        except Exception as e:
            print(f"[ERRO] Erro na execução do Worker da fila do Instagram: {e}")
            
        try:
            # Executa o processamento das publicações locais programadas
            process_scheduled_posts(bot)
        except Exception as e:
            print(f"[ERRO] Erro na execução do Worker de agendamentos locais: {e}")
            
        time.sleep(60)

def process_scheduled_posts(bot):
    """
    Worker que processa posts programados que venceram na tabela scheduled_posts.
    Roda na thread em segundo plano.
    """
    jobs = db.get_pending_scheduled_posts()
    if not jobs:
        return
        
    print(f"[SCHEDULER WORKER] Encontrados {len(jobs)} agendamentos unificados para processar.")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    def _notify(msg_html):
        try:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if not bot_token:
                return
            for _uid in APPROVED_USERS:
                if str(_uid).isdigit():
                    requests.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json={"chat_id": int(_uid), "text": msg_html, "parse_mode": "HTML"},
                        timeout=5
                    )
        except Exception as _e:
            print(f"[SCHEDULER WORKER] Falha ao enviar notificação: {_e}", flush=True)

    def _make_progress_cb(platform_label):
        _last = [0]
        def _cb(percent):
            pct = int(percent)
            if pct >= _last[0] + 10 or pct >= 100:
                _last[0] = pct
                print(f"[SCHEDULER WORKER] {platform_label}: {pct}%", flush=True)
        return _cb

    for job in jobs:
        post_id, video_path, thumb_yt, thumb_tt, title_yt, title_shorts, tiktok_caption, instagram_caption, post_yt, post_shorts, post_tt, post_ig, tiktok_privacy, sched_time, shorts_description, youtube_tags = job if len(job) >= 16 else (*job, "")
        print(f"[SCHEDULER WORKER] Processando post #{post_id}...")
        
        db.update_scheduled_post_status(post_id, "processing")
        
        results = []
        errors = []
        
        _platforms = []
        if post_yt: _platforms.append("📺 YouTube")
        if post_shorts: _platforms.append("🎬 YouTube Shorts")
        if post_tt: _platforms.append("🎵 TikTok")
        if post_ig: _platforms.append("📸 Instagram")
        _platforms_str = "  |  ".join(_platforms) if _platforms else "Nenhuma"
        _title_display = title_shorts or title_yt or tiktok_caption[:50] if (title_shorts or title_yt or tiktok_caption) else f"Post #{post_id}"
        _notify(f"🚀 <b>Iniciando publicação #{post_id}</b>\n📌 {_title_display}\n🎯 Plataformas: {_platforms_str}")
        
        # 1. YouTube
        if post_yt:
            try:
                print(f"[SCHEDULER WORKER] Enviando post #{post_id} para o YouTube...", flush=True)
                _notify(f"📤 <b>Enviando para o YouTube...</b>\n📌 {title_yt}")
                _desc_for_yt = shorts_description or tiktok_caption or title_yt
                if youtube_tags and str(youtube_tags).strip():
                    tags_yt = [t.strip() for t in str(youtube_tags).split(",") if t.strip()]
                    print(f"[SCHEDULER WORKER] Usando tags do guia: {tags_yt}", flush=True)
                else:
                    _raw_tags = re.findall(r'#(\w+)', _desc_for_yt)
                    tags_yt = list(dict.fromkeys(_raw_tags)) if _raw_tags else ["anime", "recap", "animerecap"]
                vid_id, vid_url = youtube_uploader.upload_video_to_youtube(
                    video_path=video_path,
                    title=title_yt,
                    description=_desc_for_yt,
                    tags=tags_yt,
                    category_id="24",
                    privacy_status="draft",
                    thumbnail_path=thumb_yt if thumb_yt and os.path.exists(thumb_yt) else None,
                    progress_callback=_make_progress_cb("YouTube")
                )
                _notify(f"✅ <b>YouTube OK!</b> ID: {vid_id}\n🔗 {vid_url}")
                results.append(f"YouTube (URL: {vid_url})")
            except Exception as ex:
                errors.append(f"YouTube: {ex}")
                print(f"[SCHEDULER WORKER] Falha no YouTube: {ex}", flush=True)
                
        # 2. YouTube Shorts
        if post_shorts:
            try:
                print(f"[SCHEDULER WORKER] Enviando post #{post_id} para o YouTube Shorts...", flush=True)
                _notify(f"📤 <b>Enviando para o YouTube Shorts...</b>\n📌 {title_shorts}")
                _desc_for_shorts_tags = shorts_description or tiktok_caption or title_shorts
                if youtube_tags and str(youtube_tags).strip():
                    tags_yt = [t.strip() for t in str(youtube_tags).split(",") if t.strip()]
                    if "Shorts" not in tags_yt:
                        tags_yt.append("Shorts")
                    print(f"[SCHEDULER WORKER] Shorts usando tags do guia: {tags_yt}", flush=True)
                else:
                    _raw_shorts_tags = re.findall(r'#(\w+)', _desc_for_shorts_tags)
                    tags_yt = list(dict.fromkeys(_raw_shorts_tags)) if _raw_shorts_tags else ["anime", "recap", "Shorts", "animerecap"]
                
                desc_shorts_final = shorts_description
                if not desc_shorts_final:
                    desc_shorts_final = tiktok_caption if tiktok_caption else (instagram_caption if instagram_caption else title_shorts)
                    if "#shorts" not in desc_shorts_final.lower():
                        desc_shorts_final = f"{desc_shorts_final}\n\n#Shorts"

                vid_id, vid_url = youtube_uploader.upload_video_to_youtube(
                    video_path=video_path,
                    title=title_shorts,
                    description=desc_shorts_final,
                    tags=tags_yt,
                    category_id="24",
                    privacy_status="draft",
                    thumbnail_path=thumb_yt if thumb_yt and os.path.exists(thumb_yt) else None,
                    progress_callback=_make_progress_cb("YouTube Shorts")
                )
                _notify(f"✅ <b>YouTube Shorts OK!</b> ID: {vid_id}\n🔗 {vid_url}")
                results.append(f"YouTube Shorts (URL: {vid_url})")
            except Exception as ex:
                errors.append(f"YouTube Shorts: {ex}")
                print(f"[SCHEDULER WORKER] Falha no YouTube Shorts: {ex}", flush=True)

        # 3. TikTok
        if post_tt:
            try:
                print(f"[SCHEDULER WORKER] Enviando post #{post_id} para o TikTok...", flush=True)
                _notify(f"📤 <b>Enviando para o TikTok...</b>")
                pub_id = tiktok_service.upload_video_to_tiktok(
                    video_path=video_path,
                    title=tiktok_caption,
                    privacy_level=tiktok_privacy,
                    schedule_time=None,
                    schedule_day=None,
                    progress_callback=None
                )
                results.append(f"TikTok (ID: {pub_id})")
            except Exception as ex:
                errors.append(f"TikTok: {ex}")
                print(f"[SCHEDULER WORKER] Falha no TikTok: {ex}", flush=True)
                
        # 4. Instagram Reels
        if post_ig:
            try:
                print(f"[SCHEDULER WORKER] Enviando post #{post_id} para o Instagram...", flush=True)
                media_id, media_url = instagram_uploader.upload_reel_to_instagram(
                    video_path=video_path,
                    caption=instagram_caption,
                    thumbnail_path=thumb_tt if thumb_tt and os.path.exists(thumb_tt) else None
                )
                results.append(f"Instagram (URL: {media_url})")
            except Exception as ex:
                errors.append(f"Instagram: {ex}")
                print(f"[SCHEDULER WORKER] Falha no Instagram: {ex}", flush=True)

        # Atualiza o status
        if errors:
            err_msg = "; ".join(errors)
            db.update_scheduled_post_status(post_id, "failed", error=err_msg)
            print(f"[SCHEDULER WORKER] Post #{post_id} falhou: {err_msg}", flush=True)
            _notify(f"❌ <b>Falha ao processar Publicação Programada #{post_id}</b>\nData: {sched_time}\nErro: {err_msg}")
        else:
            db.update_scheduled_post_status(post_id, "completed")
            print(f"[SCHEDULER WORKER] Post #{post_id} concluído com sucesso!", flush=True)
            
            # Gatilho automático pós-postagem: aciona a produção do próximo episódio
            try:
                import requests as _rq
                _rq.post("http://localhost:5556/api/douyin/trigger-next", timeout=10)
                print(f"[SCHEDULER WORKER] ⚡ Próxima produção engatilhada automaticamente via API!", flush=True)
            except Exception as _e_trig:
                print(f"[SCHEDULER WORKER] Aviso ao engatilhar próxima produção: {_e_trig}", flush=True)
            
            deleted_count = 0
            for path in [video_path, thumb_yt, thumb_tt]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        deleted_count += 1
                    except Exception as ex:
                        print(f"[SCHEDULER WORKER] Erro ao remover arquivo local: {path}: {ex}", flush=True)
            
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled_posts")
            post_dir = os.path.join(base_dir, f"post_{post_id}")
            if os.path.exists(post_dir):
                try: os.rmdir(post_dir)
                except: pass
                
            # Notifica usuários aprovados sobre o sucesso
            try:
                res_str = "\n".join([f"• {r}" for r in results])
                notify_text = f"✅ <b>Publicação Programada #{post_id} disparada com sucesso!</b>\n\n{res_str}"
                for user_id in APPROVED_USERS:
                    if user_id.isdigit():
                        loop.run_until_complete(bot.send_message(chat_id=int(user_id), text=notify_text, parse_mode="HTML"))
            except Exception as notify_err:
                print(f"[SCHEDULER WORKER] Falha ao enviar notificação de sucesso: {notify_err}", flush=True)

async def menu_programados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra os agendamentos pendentes ou falhos na fila local."""
    query = update.callback_query
    await query.answer()
    
    rows = db.get_all_pending_scheduled()
    
    if not rows:
        text = "📭 Nenhuma publicação programada localmente na VM no momento."
        keyboard = [[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]]
    else:
        text = "📋 **Publicações Programadas na VM (Aguardando Disparo):**\n\n"
        keyboard = []
        for r in rows:
            post_id, sched_time, title_yt, title_shorts, tiktok_caption, post_yt, post_shorts, post_tt, post_ig, status = r
            
            # Icones das redes
            redes = []
            if post_yt: redes.append("YT")
            if post_shorts: redes.append("Shorts")
            if post_tt: redes.append("TT")
            if post_ig: redes.append("IG")
            redes_str = "/".join(redes)
            
            # Título resumido para exibição
            display_title = title_yt or title_shorts or (tiktok_caption[:30] + "..." if tiktok_caption else "Sem Título")
            
            status_emoji = "⏳" if status == "pending" else "❌"
            
            text += f"{status_emoji} **ID: {post_id}** | {sched_time} | {redes_str}\n💬 {display_title}\n\n"
            
            # Botão de exclusão para este ID
            keyboard.append([InlineKeyboardButton(f"🗑️ Excluir ID {post_id}", callback_data=f"delete_prog_{post_id}")])
            
        keyboard.append([InlineKeyboardButton("Voltar ao Menu", callback_data="back_to_menu")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return SELECT_PLATFORMS

async def delete_programado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exclui a publicação programada local e seus arquivos físicos na VM."""
    query = update.callback_query
    await query.answer()
    
    post_id = int(query.data.split("_")[-1])
    
    # Deleta do banco de dados e retorna os caminhos dos arquivos
    row = db.delete_scheduled_post(post_id)
    
    # Deleta a pasta física e os arquivos
    deleted_files = 0
    if row:
        video_path, thumb_yt, thumb_tt = row
        # Deleta arquivos individuais se existirem
        for path in [video_path, thumb_yt, thumb_tt]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    deleted_files += 1
                except Exception as ex:
                    print(f"[SCHEDULER ERR] Falha ao excluir arquivo local: {path}: {ex}", flush=True)
                    
        # Exclui a pasta post_dir
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled_posts")
        post_dir = os.path.join(base_dir, f"post_{post_id}")
        if os.path.exists(post_dir):
            try:
                os.rmdir(post_dir)
            except Exception as ex:
                print(f"[SCHEDULER ERR] Falha ao remover pasta post_dir: {post_dir}: {ex}", flush=True)
                
    await query.answer(f"Publicação ID {post_id} excluída com sucesso! ({deleted_files} arquivos removidos)", show_alert=True)
    
    # Retorna para a listagem
    return await menu_programados(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o bot e apresenta o menu principal."""
    if not user_is_approved(update):
        await update.message.reply_text("Desculpe, você não está autorizado a usar este bot.")
        return ConversationHandler.END
        
    # Inicializa o dicionário de contexto da postagem
    context.user_data["post_data"] = {
        "platforms": {"youtube": False, "youtube_shorts": False, "tiktok": False, "instagram": False},
        "youtube_title": "",
        "shorts_title": "",
        "instagram_scheduled_time": None,  # None se for postar agora
        "tiktok_scheduled_time": None,
        "unified_scheduled_time": None,
        "is_scheduled_run": False,
        "guia": None,
        "files": None
    }
    
    keyboard = [
        [InlineKeyboardButton("Postar Novo Vídeo 🚀", callback_data="menu_postar")],
        [InlineKeyboardButton("Programar Publicação 📅", callback_data="menu_programar")],
        [InlineKeyboardButton("Ver Publicações Programadas 📋", callback_data="menu_programados")],
        [InlineKeyboardButton("Ver Fila do Instagram 📸", callback_data="menu_fila")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Olá! Bem-vindo ao Post Recap Bot.\nSelecione uma opção no menu abaixo:",
        reply_markup=reply_markup
    )
    return SELECT_PLATFORMS

async def show_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Retorna ao menu principal via callback query."""
    query = update.callback_query
    await query.answer()
    
    context.user_data["post_data"] = {
        "platforms": {"youtube": False, "youtube_shorts": False, "tiktok": False, "instagram": False},
        "youtube_title": "",
        "shorts_title": "",
        "instagram_scheduled_time": None,
        "tiktok_scheduled_time": None,
        "unified_scheduled_time": None,
        "is_scheduled_run": False,
        "guia": None,
        "files": None
    }
    
    keyboard = [
        [InlineKeyboardButton("Postar Novo Vídeo 🚀", callback_data="menu_postar")],
        [InlineKeyboardButton("Programar Publicação 📅", callback_data="menu_programar")],
        [InlineKeyboardButton("Ver Publicações Programadas 📋", callback_data="menu_programados")],
        [InlineKeyboardButton("Ver Fila do Instagram 📸", callback_data="menu_fila")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Selecione uma opção no menu abaixo:",
        reply_markup=reply_markup
    )
    return SELECT_PLATFORMS

async def menu_fila(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mostra os agendamentos pendentes na fila."""
    query = update.callback_query
    await query.answer()
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, scheduled_time, status, video_drive_path 
        FROM instagram_queue 
        ORDER BY scheduled_time ASC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        text = "📭 A fila do Instagram está vazia no momento."
    else:
        text = "📅 Próximos agendamentos do Instagram (limite 10):\n\n"
        for r in rows:
            status_emoji = "⏳" if r[2] == "pending" else ("✅" if r[2] == "completed" else "❌")
            filename = r[3].split("/")[-1]
            text += f"{status_emoji} ID: {r[0]} | {r[1]} | {filename} ({r[2]})\n"
            
    keyboard = [[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)
    return SELECT_PLATFORMS

async def menu_postar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Busca o JSON guia_postagem do Drive e apresenta as opções de plataforma."""
    query = update.callback_query
    await query.answer()
    
    # Define se é uma publicação programada localmente
    is_scheduled = (query.data == "menu_programar")
    if "post_data" not in context.user_data or not context.user_data["post_data"]:
        context.user_data["post_data"] = {
            "platforms": {"youtube": False, "youtube_shorts": False, "tiktok": False, "instagram": False},
            "youtube_title": "",
            "shorts_title": "",
            "instagram_scheduled_time": None,
            "tiktok_scheduled_time": None,
            "unified_scheduled_time": None,
            "is_scheduled_run": is_scheduled,
            "guia": None,
            "files": None
        }
    else:
        context.user_data["post_data"]["is_scheduled_run"] = is_scheduled
        
    await query.edit_message_text("🔍 Conectando ao Google Drive e buscando informações do post...")
    
    try:
        # Busca o ID da pasta e o arquivo guia_postagem.json
        folder_id = os.getenv("DRIVE_FOLDER_ID")
        if not folder_id:
            folder_id = drive_manager.find_id_by_path("KAGGLE/PIPELINE/FINAL")
            
        if not folder_id:
            folder_id = drive_manager.find_id_by_path("PIPELINE/FINAL")
            
        if not folder_id:
            await query.edit_message_text(
                "❌ Erro: Não foi possível localizar a pasta do pipeline final no Drive.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]])
            )
            return SELECT_PLATFORMS

        # Lista arquivos na pasta
        files = drive_manager.list_files_in_folder(folder_id)
        guia_id = None
        for f in files:
            if f["name"] == "guia_postagem.json":
                guia_id = f["id"]
                break
                
        if not guia_id:
            # Guia ausente - define dados padrão genéricos para postagem sem guia
            guia_data = {
                "titulo_principal": f"Video_Recap_{datetime.now().strftime('%Y-%m-%d_%H%M')}",
                "titulos_alternativos": [],
                "descricao": "Vídeo enviado via Post Recap Bot.",
                "hashtags_youtube": ["#anime", "#recap"],
                "tags_youtube": "recap, anime",
                "tiktok_titulo": f"Video_Recap_{datetime.now().strftime('%Y-%m-%d_%H%M')}",
                "tiktok_sinopse": "Recap enviado via Bot.",
                "tiktok_hashtags": ["#anime", "#recap", "#viral"],
                "tiktok_descricao": "Vídeo enviado via Post Recap Bot."
            }
            warning_prefix = "⚠️ *guia_postagem.json não encontrado no Drive. Usando dados genéricos.*\n\n"
        else:
            # Baixa temporariamente o guia_postagem.json para ler os dados
            temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            local_guia_path = os.path.join(temp_dir, "guia_postagem.json")
            
            drive_manager.download_file_by_id(guia_id, local_guia_path)
            
            with open(local_guia_path, "r", encoding="utf-8") as file:
                guia_data = json.load(file)
            warning_prefix = ""
            
        # Salva os dados no contexto
        context.user_data["post_data"]["guia"] = guia_data
        context.user_data["post_data"]["folder_id"] = folder_id
        
        # Mostra o resumo do vídeo e as opções
        title = guia_data.get("titulo_principal", "Sem Título")
        desc = guia_data.get("tiktok_sinopse", "Sem Sinopse")
        
        escaped_title = html.escape(title)
        escaped_desc = html.escape(desc)
        
        message_text = (
            f"🎬 <b>Vídeo Detectado!</b>\n"
            f"<b>Título:</b> {escaped_title}\n"
            f"<b>Sinopse:</b> {escaped_desc}\n\n"
            f"Selecione as redes sociais para envio:"
        )
        
        reply_markup = get_platforms_keyboard(context.user_data["post_data"]["platforms"])
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode="HTML")
        return SELECT_PLATFORMS
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Erro ao ler informações do Drive: {html.escape(str(e))}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Voltar", callback_data="back_to_menu")]]),
            parse_mode="HTML"
        )
        return SELECT_PLATFORMS

def get_platforms_keyboard(platforms):
    """Gera o teclado de seleção de plataformas."""
    yt_check = "✅" if platforms["youtube"] else "⬜"
    ys_check = "✅" if platforms["youtube_shorts"] else "⬜"
    tt_check = "✅" if platforms["tiktok"] else "⬜"
    ig_check = "✅" if platforms["instagram"] else "⬜"
    
    keyboard = [
        [InlineKeyboardButton(f"{yt_check} YouTube", callback_data="toggle_youtube")],
        [InlineKeyboardButton(f"{ys_check} YouTube Shorts", callback_data="toggle_youtube-shorts")],
        [InlineKeyboardButton(f"{tt_check} TikTok", callback_data="toggle_tiktok")],
        [InlineKeyboardButton(f"{ig_check} Instagram", callback_data="toggle_instagram")],
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar Redes", callback_data="confirm_platforms")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def toggle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Alterna a seleção de uma rede social."""
    query = update.callback_query
    await query.answer()
    
    # Extrai o nome da plataforma após "toggle_" (suporta nomes com hífen como youtube-shorts)
    platform_key = query.data.replace("toggle_", "", 1).replace("-", "_")
    platforms = context.user_data["post_data"]["platforms"]
    if platform_key in platforms:
        platforms[platform_key] = not platforms[platform_key]
    
    reply_markup = get_platforms_keyboard(platforms)
    await query.edit_message_reply_markup(reply_markup=reply_markup)
    return SELECT_PLATFORMS

async def confirm_platforms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma a seleção e define o próximo passo do fluxo."""
    query = update.callback_query
    await query.answer()
    
    platforms = context.user_data["post_data"]["platforms"]
    
    # Valida se pelo menos uma plataforma foi escolhida
    if not any(platforms.values()):
        await query.answer("Por favor, selecione pelo menos uma rede social!", show_alert=True)
        return SELECT_PLATFORMS
        
    # Se YouTube foi selecionado, pergunta o título
    if platforms["youtube"]:
        guia = context.user_data["post_data"]["guia"]
        titulo_p = guia.get("titulo_principal", "Sem Título")
        alt_titles = guia.get("titulos_alternativos", [])
        
        escaped_titulo_p = html.escape(titulo_p)
        text = (
            f"📌 <b>Opções de Título para o YouTube:</b>\n\n"
            f"<b>Principal:</b> {escaped_titulo_p}\n\n"
            f"Selecione qual deseja utilizar:"
        )
        
        keyboard = [
            [InlineKeyboardButton("Título Principal", callback_data="yt_title_principal")]
        ]
        
        for idx, alt in enumerate(alt_titles):
            # O texto do botão não é parseado como HTML/Markdown, mas limitamos o tamanho por segurança e legibilidade
            keyboard.append([InlineKeyboardButton(f"Alt {idx+1}: {alt[:30]}...", callback_data=f"yt_title_alt_{idx}")])
            
        keyboard.append([InlineKeyboardButton("✍️ Digitar Título Manualmente", callback_data="yt_title_manual")])
        keyboard.append([InlineKeyboardButton("Voltar", callback_data="menu_postar")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return SELECT_YOUTUBE_TITLE
    
    # Se YouTube Shorts foi selecionado (e YouTube normal não), pergunta o título do Short
    elif platforms["youtube_shorts"]:
        return await ask_shorts_title(query, context)
        
    # Se não tem YouTube nem Shorts, mas tem Instagram
    elif platforms["instagram"]:
        if context.user_data["post_data"].get("is_scheduled_run"):
            if platforms["tiktok"]:
                return await check_tiktok_workflow(update, context)
            else:
                return await ask_unified_schedule_time(query, context)
        else:
            return await ask_instagram_scheduling(query, context)
        
    # Senão, vai direto para a privacidade do TikTok ou confirmação final
    elif platforms["tiktok"]:
        return await check_tiktok_workflow(update, context)
    else:
        if context.user_data["post_data"].get("is_scheduled_run"):
            return await ask_unified_schedule_time(query, context)
        else:
            return await show_final_confirmation(query, context)

async def route_after_titles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Função auxiliar para direcionar para o agendamento IG, configurações do TikTok ou confirmação final."""
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    query = getattr(update, "callback_query", None)
    message = getattr(update, "message", None)
    
    # Helper para responder adequadamente
    async def reply_text_or_edit(text, reply_markup=None, parse_mode=None):
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        elif message:
            await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

    if post_data.get("is_scheduled_run"):
        if platforms["tiktok"]:
            return await check_tiktok_workflow(update, context)
        else:
            return await ask_unified_schedule_time(query or message, context)
    else:
        if platforms["instagram"]:
            keyboard = [
                [InlineKeyboardButton("Postar Agora", callback_data="ig_now")],
                [InlineKeyboardButton("Agendar Postagem", callback_data="ig_schedule")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = "🕐 **Agendamento do Instagram**\nComo deseja enviar o Reels para o Instagram?"
            await reply_text_or_edit(text, reply_markup=reply_markup, parse_mode="Markdown")
            return SELECT_INSTAGRAM_SCHEDULING
        elif platforms["tiktok"]:
            return await check_tiktok_workflow(update, context)
        else:
            if query:
                return await show_final_confirmation(query, context)
            else:
                await show_final_confirmation_message(message, context)
                return CONFIRM_POST

async def handle_youtube_title_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do título do YouTube a partir dos botões."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    guia = context.user_data["post_data"]["guia"]
    
    if data == "yt_title_principal":
        context.user_data["post_data"]["youtube_title"] = guia.get("titulo_principal")
    elif data.startswith("yt_title_alt_"):
        idx = int(data.split("_")[-1])
        context.user_data["post_data"]["youtube_title"] = guia.get("titulos_alternativos", [])[idx]
    elif data == "yt_title_manual":
        await query.edit_message_text("Por favor, digite o título desejado para o YouTube:")
        return INPUT_YOUTUBE_TITLE_MANUAL
        
    # Após definir o título do YouTube, verifica se precisa definir título do Shorts
    if context.user_data["post_data"]["platforms"]["youtube_shorts"]:
        return await ask_shorts_title(query, context)
    else:
        return await ask_youtube_privacy(query, context)
   
async def handle_youtube_title_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o título do YouTube digitado manualmente pelo usuário."""
    if not user_is_approved(update):
        return ConversationHandler.END
        
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Título inválido. Por favor, envie um texto válido:")
        return INPUT_YOUTUBE_TITLE_MANUAL
        
    context.user_data["post_data"]["youtube_title"] = title
    
    # Após definir o título do YouTube, verifica próximo passo
    if context.user_data["post_data"]["platforms"]["youtube_shorts"]:
        # Precisa definir título do Shorts — envia como nova mensagem
        guia = context.user_data["post_data"]["guia"]
        titulo_p = guia.get("titulo_principal", "Sem Título")
        keyboard = [
            [InlineKeyboardButton(f"Usar: {titulo_p[:40]}... #Shorts", callback_data="shorts_title_principal")],
            [InlineKeyboardButton("✍️ Digitar Título Manualmente", callback_data="shorts_title_manual")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🎬 **Título para o YouTube Shorts:**\n\n"
            f"**Sugestão:** {titulo_p} #Shorts\n\n"
            "Selecione ou digite um título:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        return SELECT_SHORTS_TITLE
    else:
        return await ask_youtube_privacy(update, context)

async def ask_shorts_title(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pergunta o título para o YouTube Shorts."""
    guia = context.user_data["post_data"]["guia"]
    titulo_p = guia.get("titulo_principal", "Sem Título")
    alt_titles = guia.get("titulos_alternativos", [])
    
    escaped_titulo_p = html.escape(titulo_p)
    text = (
        f"🎬 <b>Título para o YouTube Shorts:</b>\n\n"
        f"<b>Sugestão:</b> {escaped_titulo_p} #Shorts\n\n"
        f"Selecione ou digite um título:"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"Usar: {titulo_p[:40]}... #Shorts", callback_data="shorts_title_principal")]
    ]
    
    for idx, alt in enumerate(alt_titles):
        keyboard.append([InlineKeyboardButton(f"Alt {idx+1}: {alt[:30]}... #Shorts", callback_data=f"shorts_title_alt_{idx}")])
    
    keyboard.append([InlineKeyboardButton("✍️ Digitar Título Manualmente", callback_data="shorts_title_manual")])
    keyboard.append([InlineKeyboardButton("Voltar", callback_data="menu_postar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    return SELECT_SHORTS_TITLE

async def handle_shorts_title_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha do título do YouTube Shorts."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    guia = context.user_data["post_data"]["guia"]
    
    if data == "shorts_title_principal":
        title = guia.get("titulo_principal", "Sem Título")
        # Adiciona #Shorts se não tiver
        if "#shorts" not in title.lower():
            title = f"{title} #Shorts"
        context.user_data["post_data"]["shorts_title"] = title
    elif data.startswith("shorts_title_alt_"):
        idx = int(data.split("_")[-1])
        title = guia.get("titulos_alternativos", [])[idx]
        if "#shorts" not in title.lower():
            title = f"{title} #Shorts"
        context.user_data["post_data"]["shorts_title"] = title
    elif data == "shorts_title_manual":
        await query.edit_message_text("Por favor, digite o título desejado para o YouTube Shorts:\n\n💡 _Dica: inclua #Shorts no título para melhor visibilidade._", parse_mode="Markdown")
        return INPUT_SHORTS_TITLE_MANUAL
    
    # Próximo passo
    return await ask_youtube_privacy(query, context)

async def handle_shorts_title_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe o título do Shorts digitado manualmente."""
    if not user_is_approved(update):
        return ConversationHandler.END
    
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("Título inválido. Por favor, envie um texto válido:")
        return INPUT_SHORTS_TITLE_MANUAL
    
    # Adiciona #Shorts se o usuário não incluiu
    if "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    context.user_data["post_data"]["shorts_title"] = title
    
    return await ask_youtube_privacy(update, context)

async def ask_youtube_privacy(query_or_update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pergunta a visibilidade do vídeo no YouTube."""
    # Suporta ser chamado com query ou com update completo
    query = getattr(query_or_update, 'callback_query', None) or query_or_update
    message = getattr(query_or_update, 'message', None)
    
    text = (
        "🔒 <b>Visibilidade no YouTube</b>\n"
        "Como deseja publicar o vídeo?"
    )
    keyboard = [
        [
            InlineKeyboardButton("📝 Rascunho", callback_data="yt_priv_draft"),
            InlineKeyboardButton("🌎 Público", callback_data="yt_priv_public")
        ],
        [
            InlineKeyboardButton("🔒 Privado", callback_data="yt_priv_private"),
            InlineKeyboardButton("🔗 Não Listado", callback_data="yt_priv_unlisted")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(query, 'edit_message_text'):
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    elif message:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
    
    return SELECT_YOUTUBE_PRIVACY

async def handle_youtube_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha de visibilidade do YouTube."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    privacy_map = {
        "yt_priv_draft": "draft",
        "yt_priv_public": "public",
        "yt_priv_private": "private",
        "yt_priv_unlisted": "unlisted"
    }
    context.user_data["post_data"]["youtube_privacy"] = privacy_map.get(data, "draft")
    
    return await route_after_titles(update, context)

async def ask_instagram_scheduling(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Pergunta sobre o agendamento do Instagram."""
    keyboard = [
        [InlineKeyboardButton("Postar Agora", callback_data="ig_now")],
        [InlineKeyboardButton("Agendar Postagem", callback_data="ig_schedule")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🕐 **Agendamento do Instagram**\nComo deseja enviar o Reels para o Instagram?",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    return SELECT_INSTAGRAM_SCHEDULING

async def handle_instagram_scheduling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processa a escolha de agendar ou postar agora no Instagram."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "ig_now":
        context.user_data["post_data"]["instagram_scheduled_time"] = None
        if context.user_data["post_data"]["platforms"]["tiktok"]:
            return await check_tiktok_workflow(update, context)
        return await show_final_confirmation(query, context)
    elif data == "ig_schedule":
        await query.edit_message_text(
            "Por favor, digite a data e hora do agendamento.\n"
            "Use o formato: `AAAA-MM-DD HH:MM`\n"
            "Exemplo: `2026-05-24 18:00`",
            parse_mode="Markdown"
        )
        return INPUT_INSTAGRAM_TIME

async def handle_instagram_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data e hora do agendamento digitada pelo usuário."""
    if not user_is_approved(update):
        return ConversationHandler.END
        
    raw_time = update.message.text.strip()
    try:
        # Valida o formato inserido
        dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
        context.user_data["post_data"]["instagram_scheduled_time"] = dt.strftime("%Y-%m-%d %H:%M:00")
        
        if context.user_data["post_data"]["platforms"]["tiktok"]:
            return await check_tiktok_workflow(update, context)
            
        await show_final_confirmation_message(update.message, context)
        return CONFIRM_POST
    except ValueError:
        await update.message.reply_text(
            "❌ Formato inválido! Por favor, utilize o formato correto:\n"
            "`AAAA-MM-DD HH:MM` (ex: `2026-05-24 18:00`)",
            parse_mode="Markdown"
        )
        return INPUT_INSTAGRAM_TIME

async def check_tiktok_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia o fluxo de opções do TikTok."""
    query = getattr(update, "callback_query", None)
    message = getattr(update, "message", None)
    
    text = "🎬 **Configuração do TikTok**\nQual a privacidade desejada para o vídeo?"
    keyboard = [
        [
            InlineKeyboardButton("🌍 Público", callback_data="tt_public"),
            InlineKeyboardButton("👥 Amigos", callback_data="tt_friends"),
            InlineKeyboardButton("🔒 Privado", callback_data="tt_private")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    elif message:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        
    return SELECT_TIKTOK_PRIVACY

async def handle_tiktok_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "tt_public":
        context.user_data["post_data"]["tiktok_privacy"] = "Public"
    elif data == "tt_friends":
        context.user_data["post_data"]["tiktok_privacy"] = "Friends"
    elif data == "tt_private":
        context.user_data["post_data"]["tiktok_privacy"] = "Private"
        
    if context.user_data["post_data"].get("is_scheduled_run"):
        return await ask_unified_schedule_time(query, context)
        
    text = "🕐 **Agendamento do TikTok**\nComo deseja enviar o vídeo para o TikTok?"
    keyboard = [
        [
            InlineKeyboardButton("Postar Agora", callback_data="tt_now"),
            InlineKeyboardButton("Agendar Postagem", callback_data="tt_schedule")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    return SELECT_TIKTOK_SCHEDULING

async def handle_tiktok_scheduling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "tt_now":
        context.user_data["post_data"]["tiktok_scheduled_time"] = None
        return await show_final_confirmation(query, context)
    elif data == "tt_schedule":
        await query.edit_message_text(
            "Por favor, digite a data e hora do agendamento para o TikTok.\n"
            "Use o formato: `AAAA-MM-DD HH:MM`\n"
            "Exemplo: `2026-05-24 18:00`",
            parse_mode="Markdown"
        )
        return INPUT_TIKTOK_TIME

async def handle_tiktok_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not user_is_approved(update):
        return ConversationHandler.END
        
    raw_time = update.message.text.strip()
    try:
        dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
        context.user_data["post_data"]["tiktok_scheduled_time"] = dt.strftime("%Y-%m-%d %H:%M:00")
        
        await show_final_confirmation_message(update.message, context)
        return CONFIRM_POST
    except ValueError:
        await update.message.reply_text(
            "❌ Formato inválido! Por favor, utilize o formato correto:\n"
            "`AAAA-MM-DD HH:MM` (ex: `2026-05-24 18:00`)",
            parse_mode="Markdown"
        )
        return INPUT_TIKTOK_TIME

async def ask_unified_schedule_time(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Solicita a data e hora unificada para o agendamento local."""
    text = (
        "🕐 **Programação Unificada (Salvar Local na VM)**\n\n"
        "Digite a data e hora que deseja realizar o disparo nas redes sociais selecionadas.\n"
        "Use o formato: `AAAA-MM-DD HH:MM`\n"
        "Exemplo: `2026-06-25 18:00`"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return INPUT_UNIFIED_SCHEDULE_TIME

async def handle_unified_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recebe a data e hora unificada do agendamento."""
    if not user_is_approved(update):
        return ConversationHandler.END
        
    raw_time = update.message.text.strip()
    try:
        dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M")
        context.user_data["post_data"]["unified_scheduled_time"] = dt.strftime("%Y-%m-%d %H:%M:00")
        
        await show_final_confirmation_message(update.message, context)
        return CONFIRM_POST
    except ValueError:
        await update.message.reply_text(
            "❌ Formato inválido! Por favor, utilize o formato correto:\n"
            "`AAAA-MM-DD HH:MM` (ex: `2026-06-25 18:00`)",
            parse_mode="Markdown"
        )
        return INPUT_UNIFIED_SCHEDULE_TIME

async def show_final_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gera e exibe a mensagem de confirmação final de postagem."""
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    
    redes = []
    if platforms["youtube"]:
        yt_title = html.escape(post_data['youtube_title'])
        redes.append(f"• YouTube (Título: {yt_title})")
    if platforms["youtube_shorts"]:
        shorts_title = html.escape(post_data['shorts_title'])
        redes.append(f"• YouTube Shorts (Título: {shorts_title})")
    if platforms["tiktok"]:
        priv = post_data.get("tiktok_privacy", "Public")
        sched = post_data.get("tiktok_scheduled_time")
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• TikTok (Privacidade: {priv} | {sched_text})")
    if platforms["instagram"]:
        sched = post_data["instagram_scheduled_time"]
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• Instagram Reels ({sched_text})")
        
    redes_str = "\n".join(redes)
    
    if post_data.get("is_scheduled_run"):
        sched = post_data.get("unified_scheduled_time")
        text = (
            "<b>📝 Resumo da Programação Unificada:</b>\n\n"
            f"As mídias serão baixadas do Google Drive e armazenadas localmente para disparo em:\n"
            f"📅 <b>{sched}</b>\n\n"
            f"<b>Redes sociais ativas:</b>\n{redes_str}\n\n"
            "Confirma a programação?"
        )
    else:
        text = (
            "<b>📝 Resumo da Postagem:</b>\n\n"
            f"As mídias serão baixadas do Google Drive e enviadas para:\n"
            f"{redes_str}\n\n"
            "Confirma o envio?"
        )
    
    keyboard = [
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar e Enviar", callback_data="execute_upload")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    return CONFIRM_POST

async def show_final_confirmation_message(msg_object, context: ContextTypes.DEFAULT_TYPE):
    """Versão auxiliar para enviar a confirmação quando o fluxo vem de entrada de texto."""
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    
    redes = []
    if platforms["youtube"]:
        yt_title = html.escape(post_data['youtube_title'])
        redes.append(f"• YouTube (Título: {yt_title})")
    if platforms["youtube_shorts"]:
        shorts_title = html.escape(post_data['shorts_title'])
        redes.append(f"• YouTube Shorts (Título: {shorts_title})")
    if platforms["tiktok"]:
        priv = post_data.get("tiktok_privacy", "Public")
        sched = post_data.get("tiktok_scheduled_time")
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• TikTok (Privacidade: {priv} | {sched_text})")
    if platforms["instagram"]:
        sched = post_data["instagram_scheduled_time"]
        sched_text = f"Agendado para {sched}" if sched else "Postar Agora"
        redes.append(f"• Instagram Reels ({sched_text})")
        
    redes_str = "\n".join(redes)
    
    if post_data.get("is_scheduled_run"):
        sched = post_data.get("unified_scheduled_time")
        text = (
            "<b>📝 Resumo da Programação Unificada:</b>\n\n"
            f"As mídias serão baixadas do Google Drive e armazenadas localmente para disparo em:\n"
            f"📅 <b>{sched}</b>\n\n"
            f"<b>Redes sociais ativas:</b>\n{redes_str}\n\n"
            "Confirma a programação?"
        )
    else:
        text = (
            "<b>📝 Resumo da Postagem:</b>\n\n"
            f"As mídias serão baixadas do Google Drive e enviadas para:\n"
            f"{redes_str}\n\n"
            "Confirma o envio?"
        )
    
    keyboard = [
        [
            InlineKeyboardButton("Cancelar", callback_data="back_to_menu"),
            InlineKeyboardButton("Confirmar e Enviar", callback_data="execute_upload")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await msg_object.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def execute_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Executa o download dos arquivos do Google Drive e posta nas redes selecionadas."""
    query = update.callback_query
    await query.answer()
    
    post_data = context.user_data["post_data"]
    platforms = post_data["platforms"]
    guia = post_data["guia"]
    
    if post_data.get("is_scheduled_run"):
        status_msg = await query.edit_message_text("⏳ Criando agendamento no banco de dados local...")
        asyncio.create_task(run_local_schedule_pipeline(status_msg, platforms, post_data, guia))
    else:
        status_msg = await query.edit_message_text("📥 Iniciando download dos arquivos do Google Drive...")
        # Executa a postagem em segundo plano para não travar a UI do Telegram
        asyncio.create_task(run_upload_pipeline(status_msg, platforms, post_data, guia))
    
    return ConversationHandler.END

async def run_local_schedule_pipeline(status_msg, platforms, post_data, guia):
    """Pipeline para baixar o vídeo do Drive e programar na fila local da VM."""
    loop = asyncio.get_running_loop()
    
    # Helper assíncrono para atualizar o status
    async def safe_edit_status(text, parse_mode=None):
        try:
            await status_msg.edit_text(text, parse_mode=parse_mode)
        except Exception as edit_err:
            print(f"[TELEGRAM WARNING] Falha ao atualizar mensagem: {edit_err}", flush=True)

    # Helper para progresso do download
    def make_progress_callback(msg, prefix):
        state = {"last_percent": -1, "last_update_time": 0.0}
        def progress_callback(percent):
            now = time.time()
            time_diff = now - state["last_update_time"]
            if percent == 0 or percent == 100 or (percent - state["last_percent"] >= 5 and time_diff >= 5):
                state["last_percent"] = percent
                state["last_update_time"] = now
                async def edit_msg():
                    try: await msg.edit_text(f"{prefix} {percent}%")
                    except: pass
                asyncio.run_coroutine_threadsafe(edit_msg(), loop)
        return progress_callback

    post_id = None
    temp_paths = {}
    try:
        # 1. Registrar agendamento inicial no SQLite (em estado 'downloading')
        yt_title = post_data.get("youtube_title", "")
        shorts_title = post_data.get("shorts_title", "")
        tt_title = guia.get("titulo_principal", "")
        


        # Constrói legendas
        def get_formatted_caption(g):
            if g.get("tiktok_guia"):
                return filter_hashtags(g["tiktok_guia"])
            hook = g.get("tiktok_titulo") or g.get("titulo_principal") or "Você teria coragem de assistir até o final? 😳"
            tags_list = g.get("tiktok_hashtags") or g.get("instagram_hashtags") or ["#anime", "#recap", "#viral"]
            tags_str = " ".join(tags_list[:5]) if isinstance(tags_list, list) else " ".join([t for t in tags_list.split() if t.startswith("#")][:5])
            return f"{hook}\n\n{tags_str}"
            
        caption_texto = get_formatted_caption(guia)
        sched_time = post_data.get("unified_scheduled_time")
        
        # Obtém as hashtags do YouTube do guia para integrar no Shorts
        yt_hashtags = guia.get("hashtags_youtube", [])
        if isinstance(yt_hashtags, list):
            yt_hashtags_str = " ".join(yt_hashtags)
        else:
            yt_hashtags_str = str(yt_hashtags)
            
        shorts_desc = f"{caption_texto}\n\n{yt_hashtags_str}"
        if "#shorts" not in shorts_desc.lower():
            shorts_desc = f"{shorts_desc}\n\n#Shorts"
            
        post_id = db.add_scheduled_post(
            video_path="",
            thumbnail_youtube="",
            thumbnail_tiktok="",
            title_youtube=yt_title if platforms["youtube"] else "",
            title_shorts=shorts_title if platforms["youtube_shorts"] else "",
            tiktok_caption=caption_texto if platforms["tiktok"] else "",
            instagram_caption=caption_texto if platforms["instagram"] else "",
            post_youtube=platforms["youtube"],
            post_shorts=platforms["youtube_shorts"],
            post_tiktok=platforms["tiktok"],
            post_instagram=platforms["instagram"],
            tiktok_privacy=post_data.get("tiktok_privacy", "Public"),
            scheduled_time=sched_time,
            shorts_description=shorts_desc
        )
        
        # Atualiza status inicial
        db.update_scheduled_post_status(post_id, "downloading")
        
        # 2. Criar a pasta física para salvar os arquivos
        base_scheduled_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled_posts")
        os.makedirs(base_scheduled_dir, exist_ok=True)
        
        post_dir = os.path.join(base_scheduled_dir, f"post_{post_id}")
        os.makedirs(post_dir, exist_ok=True)
        
        # 3. Baixar arquivos do Drive
        folder_id = post_data.get("folder_id")
        drive_files = await loop.run_in_executor(None, drive_manager.list_files_in_folder, folder_id)
        
        files_to_download = {
            "video_final.mp4": ("video.mp4", "Vídeo Principal"),
            "thumbnail_youtube.png": ("thumb_yt.png", "Capa YouTube"),
            "thumbnail_tiktok.png": ("thumb_tt.png", "Capa TikTok")
        }
        
        found_files = {}
        for df in drive_files:
            if df["name"] in files_to_download:
                found_files[df["name"]] = df["id"]
                
        for filename, (local_name, display_name) in files_to_download.items():
            if filename == "thumbnail_youtube.png" and not platforms["youtube"] and not platforms["youtube_shorts"]:
                continue
            if filename == "thumbnail_tiktok.png" and not platforms["tiktok"] and not platforms["instagram"]:
                continue
                
            local_path = os.path.join(post_dir, local_name)
            file_id = found_files.get(filename)
            
            if file_id:
                progress_cb = make_progress_callback(status_msg, f"📥 Baixando {display_name}:")
                await safe_edit_status(f"📥 Baixando {display_name}: 0%")
                await loop.run_in_executor(None, drive_manager.download_file_by_id, file_id, local_path, progress_cb)
                temp_paths[local_name] = local_path
            else:
                # Tenta baixar alternativamente por caminho
                try:
                    alt_path = f"KAGGLE/PIPELINE/FINAL/{filename}"
                    progress_cb = make_progress_callback(status_msg, f"📥 Buscando {display_name}:")
                    await safe_edit_status(f"📥 Buscando {display_name} via caminho alternativo...")
                    await loop.run_in_executor(None, drive_manager.download_file_by_path, alt_path, local_path, progress_cb)
                    temp_paths[local_name] = local_path
                except Exception as path_err:
                    print(f"[SCHEDULER] Não foi possível baixar opcional {filename}: {path_err}", flush=True)

        video_path = temp_paths.get("video.mp4")
        if not video_path or not os.path.exists(video_path):
            raise Exception("Vídeo final (video_final.mp4) não pôde ser baixado do Drive.")
            
        # 4. Atualizar o banco de dados com os caminhos corretos e definir status como 'pending'
        thumb_yt = temp_paths.get("thumb_yt.png", "")
        thumb_tt = temp_paths.get("thumb_tt.png", "")
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE scheduled_posts
        SET video_path = ?, thumbnail_youtube = ?, thumbnail_tiktok = ?, status = 'pending'
        WHERE id = ?
        """, (video_path, thumb_yt, thumb_tt, post_id))
        conn.commit()
        conn.close()
        
        # 5. Informar sucesso
        success_text = (
            "✅ <b>Publicação Programada com Sucesso!</b>\n\n"
            f"📅 <b>Data de Disparo:</b> <code>{sched_time}</code>\n"
            "📂 Vídeo e imagens foram baixados do Drive e armazenados localmente na VM para segurança.\n\n"
            "Você pode gerenciar e excluir esta publicação no menu <b>Publicações Programadas</b>."
        )
        await safe_edit_status(success_text, parse_mode="HTML")
        
    except Exception as e:
        error_msg = f"❌ Falha ao criar agendamento local: {e}"
        print(f"[SCHEDULER ERR] {e}", flush=True)
        await safe_edit_status(error_msg)
        if post_id:
            try:
                db.update_scheduled_post_status(post_id, "failed", error=error_msg)
            except: pass

async def run_upload_pipeline(status_msg, platforms, post_data, guia):
    """Pipeline de download e upload assíncrono com barra de progresso no Telegram."""
    temp_paths = {}
    db_post_id = None
    loop = asyncio.get_running_loop()
    
    # Helper assíncrono para atualizar o status sem derrubar o pipeline caso a rede oscile
    async def safe_edit_status(text, parse_mode=None, disable_web_page_preview=None):
        try:
            await status_msg.edit_text(text, parse_mode=parse_mode, disable_web_page_preview=disable_web_page_preview)
        except Exception as edit_err:
            print(f"[TELEGRAM WARNING] Falha ao atualizar mensagem no Telegram: {edit_err}", flush=True)
    
    # Função auxiliar para gerar callback de progresso no Telegram com throttling temporal (10s)
    def make_telegram_progress_callback(msg, prefix):
        state = {
            "last_percent": -1,
            "last_update_time": 0.0
        }
        def progress_callback(percent):
            now = time.time()
            time_diff = now - state["last_update_time"]
            percent_diff = percent - state["last_percent"]
            
            # Atualiza no início (0%), no fim (100%) ou se mudou mais que 5% e passou 10 segundos
            if percent == 0 or percent == 100 or (percent_diff >= 5 and time_diff >= 10):
                state["last_percent"] = percent
                state["last_update_time"] = now
                print(f"[PIPELINE LOG] {prefix} {percent}%", flush=True)
                
                async def edit_msg():
                    try:
                        await msg.edit_text(f"{prefix} {percent}%")
                    except Exception as telegram_err:
                        print(f"[TELEGRAM ERR] Erro ao editar mensagem de progresso: {telegram_err}", flush=True)
                
                asyncio.run_coroutine_threadsafe(edit_msg(), loop)
        return progress_callback

    try:
        print("[PIPELINE LOG] Iniciando pipeline de envio...", flush=True)
        # 1. Registrar no Banco de Dados
        yt_title = post_data.get("youtube_title", "")
        tt_title = guia.get("titulo_principal", "")
        
        hook = guia.get("tiktok_titulo") or guia.get("titulo_principal") or "Você teria coragem de assistir até o final? 😳"
        titulo_anime = guia.get("tiktok_titulo_anime") or guia.get("titulo_anime") or ""
        sinopse = guia.get("tiktok_sinopse") or guia.get("sinopse") or ""
        tags_list = guia.get("tiktok_hashtags") or guia.get("instagram_hashtags") or ["#anime", "#recap", "#viral"]
        
        if isinstance(tags_list, list):
            tags_tt = " ".join(tags_list[:5])
            tags_ig = " ".join(tags_list)
        else:
            all_tags = [t for t in tags_list.split() if t.startswith("#")]
            tags_tt = " ".join(all_tags[:5])
            tags_ig = " ".join(all_tags)
        
        # Caption do TikTok: tiktok_guia completo se existir (mas com max 5 hashtags), ou hook + 5 hashtags
        if guia.get("tiktok_guia"):
            caption_texto = filter_hashtags(guia["tiktok_guia"])
        else:
            caption_texto = f"{hook}\n\n{tags_tt}"
        
        # Caption do Instagram: hook + sinopse completa + todas as hashtags
        ig_parts = [hook]
        if titulo_anime:
            ig_parts.append(f"Titulo: {titulo_anime}")
        if sinopse:
            ig_parts.append(f"Sinopse: {sinopse}")
        ig_parts.append(tags_ig)
        ig_caption = "\n\n".join(ig_parts)
        
        print(f"[PIPELINE LOG] Registrando post no banco de dados. YouTube={platforms['youtube']}, TikTok={platforms['tiktok']}, Instagram={platforms['instagram']}...", flush=True)
        db_post_id = db.log_post(
            video_path="KAGGLE/PIPELINE/FINAL/video_final.mp4",
            youtube_title=yt_title if platforms["youtube"] else "",
            tiktok_title=tt_title if platforms["tiktok"] else "",
            instagram_caption=ig_caption if platforms["instagram"] else "",
            youtube_status="pending" if platforms["youtube"] else "skipped",
            tiktok_status="pending" if platforms["tiktok"] else "skipped",
            instagram_status="pending" if platforms["instagram"] else "skipped"
        )
        
        # 2. Baixar arquivos do Drive
        temp_paths = {}
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        os.makedirs(local_dir, exist_ok=True)
        
        folder_id = post_data.get("folder_id")
        
        print(f"[PIPELINE LOG] Buscando arquivos no Google Drive na pasta ID={folder_id}...", flush=True)
        await safe_edit_status("🔍 Buscando arquivos na pasta do Google Drive...")
        drive_files = await loop.run_in_executor(None, drive_manager.list_files_in_folder, folder_id)
        
        files_to_download = {
            "video_final.mp4": "Vídeo Final (.mp4)",
            "thumbnail_youtube.png": "Thumbnail YouTube (.png)",
            "thumbnail_tiktok.png": "Thumbnail TikTok (.png)"
        }
        
        found_files = {}
        for df in drive_files:
            if df["name"] in files_to_download:
                found_files[df["name"]] = df["id"]
                
        for filename, display_name in files_to_download.items():
            # Só baixa a capa específica se a rede social correspondente foi selecionada
            if filename == "thumbnail_youtube.png" and not platforms["youtube"] and not platforms["youtube_shorts"]:
                continue
            if filename == "thumbnail_tiktok.png" and not platforms["tiktok"] and not platforms["instagram"]:
                continue
                
            local_path = os.path.join(local_dir, filename)
            file_id = found_files.get(filename)
            
            if file_id:
                print(f"[PIPELINE LOG] Baixando '{display_name}' via ID={file_id}...", flush=True)
                progress_cb = make_telegram_progress_callback(status_msg, f"📥 Baixando {display_name}:")
                await safe_edit_status(f"📥 Baixando {display_name}: 0%")
                await loop.run_in_executor(None, drive_manager.download_file_by_id, file_id, local_path, progress_cb)
                temp_paths[filename] = local_path
                print(f"[PIPELINE LOG] Download de '{display_name}' concluído com sucesso!", flush=True)
            else:
                # Tenta baixar pelo caminho alternativo
                try:
                    alt_path = f"KAGGLE/PIPELINE/FINAL/{filename}"
                    print(f"[PIPELINE LOG] Arquivo não listado por ID. Buscando '{display_name}' via caminho alternativo '{alt_path}'...", flush=True)
                    progress_cb = make_telegram_progress_callback(status_msg, f"📥 Buscando {display_name}:")
                    await safe_edit_status(f"📥 Buscando {display_name} via caminho alternativo...")
                    await loop.run_in_executor(None, drive_manager.download_file_by_path, alt_path, local_path, progress_cb)
                    temp_paths[filename] = local_path
                    print(f"[PIPELINE LOG] Download alternativo de '{display_name}' concluído com sucesso!", flush=True)
                except Exception as e:
                    print(f"[PIPELINE LOG] Não foi possível baixar {filename} pelo caminho: {e}", flush=True)
                    
        video_path = temp_paths.get("video_final.mp4")
        yt_thumb = temp_paths.get("thumbnail_youtube.png")
        tt_thumb = temp_paths.get("thumbnail_tiktok.png")
        
        if not video_path or not os.path.exists(video_path):
            raise Exception("Vídeo final (video_final.mp4) não pôde ser baixado do Drive.")
            
        results_text = "🚀 <b>Resultados do Envio:</b>\n\n"
        thumb_warnings = []  # Acumula avisos sobre capas ausentes
        
        # 3. Upload para o YouTube
        if platforms["youtube"]:
            print(f"[PIPELINE LOG] Iniciando upload para o YouTube com o título: '{yt_title}'...", flush=True)
            progress_cb = make_telegram_progress_callback(status_msg, "📤 Enviando para o YouTube:")
            await safe_edit_status("📤 Enviando para o YouTube: 0%")
            try:
                # Constrói a descrição do YouTube com timestamps e hashtags
                desc_yt = guia.get("descricao", "")
                tags_yt = [t.strip() for t in guia.get("tags_youtube", "").split(",") if t.strip()]
                
                if not yt_thumb or not os.path.exists(yt_thumb or ""):
                    thumb_warnings.append("YouTube: thumbnail_youtube.png não encontrada no Drive — vídeo enviado sem capa.")
                    print("[PIPELINE LOG] YouTube: thumbnail ausente, enviando sem capa.", flush=True)
                
                vid_id, vid_url = await loop.run_in_executor(
                    None,
                    youtube_uploader.upload_video_to_youtube,
                    video_path,
                    yt_title,
                    desc_yt,
                    tags_yt,
                    "24", # Categoria Entretenimento
                    post_data.get("youtube_privacy", "draft"),  # Visibilidade escolhida pelo usuário
                    yt_thumb,
                    progress_cb
                )
                db.update_post_status(db_post_id, "youtube", "completed", url=vid_url)
                results_text += f"✅ <b>YouTube:</b> Enviado com sucesso!\n🔗 <a href=\"{vid_url}\">Link do Vídeo</a>\n\n"
                print(f"[PIPELINE LOG] YouTube enviado com sucesso! URL: {vid_url}", flush=True)
            except Exception as e:
                db.update_post_status(db_post_id, "youtube", "failed", error=str(e))
                results_text += f"❌ <b>YouTube:</b> Falhou! Erro: {html.escape(str(e))}\n\n"
                print(f"[PIPELINE LOG] YouTube falhou! Erro: {e}", flush=True)
        
        # 3.5. Upload para o YouTube Shorts
        if platforms["youtube_shorts"]:
            shorts_title = post_data.get("shorts_title", "")
            print(f"[PIPELINE LOG] Iniciando upload para o YouTube Shorts com o título: '{shorts_title}'...", flush=True)
            progress_cb = make_telegram_progress_callback(status_msg, "📤 Enviando YouTube Shorts:")
            await safe_edit_status("📤 Enviando YouTube Shorts: 0%")
            try:
                # Constrói a descrição do Shorts mesclando a legenda do TikTok com hashtags do YouTube
                yt_hashtags = guia.get("hashtags_youtube", [])
                if isinstance(yt_hashtags, list):
                    yt_hashtags_str = " ".join(yt_hashtags)
                else:
                    yt_hashtags_str = str(yt_hashtags)
                
                desc_yt = f"{caption_texto}\n\n{yt_hashtags_str}"
                if "#shorts" not in desc_yt.lower():
                    desc_yt = f"{desc_yt}\n\n#Shorts"
                    
                tags_yt = [t.strip() for t in guia.get("tags_youtube", "").split(",") if t.strip()]
                if "Shorts" not in tags_yt:
                    tags_yt.append("Shorts")
                
                if not yt_thumb or not os.path.exists(yt_thumb or ""):
                    thumb_warnings.append("YouTube Shorts: thumbnail_youtube.png não encontrada — vídeo enviado sem capa.")
                    print("[PIPELINE LOG] YouTube Shorts: thumbnail ausente, enviando sem capa.", flush=True)
                
                vid_id, vid_url = await loop.run_in_executor(
                    None,
                    youtube_uploader.upload_video_to_youtube,
                    video_path,
                    shorts_title,
                    desc_yt,
                    tags_yt,
                    "24",
                    post_data.get("youtube_privacy", "draft"),  # Visibilidade escolhida pelo usuário
                    yt_thumb,
                    progress_cb
                )
                db.update_post_status(db_post_id, "youtube", "completed", url=vid_url)
                results_text += f"✅ <b>YouTube Shorts:</b> Enviado com sucesso!\n🔗 <a href=\"{vid_url}\">Link do Short</a>\n\n"
                print(f"[PIPELINE LOG] YouTube Shorts enviado com sucesso! URL: {vid_url}", flush=True)
            except Exception as e:
                db.update_post_status(db_post_id, "youtube", "failed", error=str(e))
                results_text += f"❌ <b>YouTube Shorts:</b> Falhou! Erro: {html.escape(str(e))}\n\n"
                print(f"[PIPELINE LOG] YouTube Shorts falhou! Erro: {e}", flush=True)
                
        # 4. Upload para o TikTok
        if platforms["tiktok"]:
            sched_time_full = post_data.get("tiktok_scheduled_time")
            if sched_time_full:
                print(f"[PIPELINE LOG] Agendando TikTok localmente na VM para {sched_time_full}...", flush=True)
                await safe_edit_status("📅 Agendando TikTok localmente na VM...")
                try:
                    import shutil
                    # 1. Adiciona registro de agendamento local exclusivo para o TikTok
                    new_post_id = db.add_scheduled_post(
                        video_path="",
                        thumbnail_youtube="",
                        thumbnail_tiktok="",
                        title_youtube="",
                        title_shorts="",
                        tiktok_caption=caption_texto,
                        instagram_caption="",
                        post_youtube=0,
                        post_shorts=0,
                        post_tiktok=1,
                        post_instagram=0,
                        tiktok_privacy=post_data.get("tiktok_privacy", "Public"),
                        scheduled_time=sched_time_full,
                        shorts_description=""
                    )
                    
                    # 2. Cria a pasta permanente para este post agendado na VM
                    base_scheduled_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled_posts")
                    os.makedirs(base_scheduled_dir, exist_ok=True)
                    post_dir = os.path.join(base_scheduled_dir, f"post_{new_post_id}")
                    os.makedirs(post_dir, exist_ok=True)
                    
                    # 3. Copia o vídeo e a capa (se existir) do diretório temporário para a pasta permanente
                    dest_video_path = os.path.join(post_dir, "video.mp4")
                    shutil.copy2(video_path, dest_video_path)
                    
                    dest_thumb_path = ""
                    if tt_thumb and os.path.exists(tt_thumb):
                        dest_thumb_path = os.path.join(post_dir, "thumb_tt.png")
                        shutil.copy2(tt_thumb, dest_thumb_path)
                        
                    # 4. Atualiza o registro com os caminhos físicos corretos
                    conn = db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                    UPDATE scheduled_posts
                    SET video_path = ?, thumbnail_tiktok = ?, status = 'pending'
                    WHERE id = ?
                    """, (dest_video_path, dest_thumb_path, new_post_id))
                    conn.commit()
                    conn.close()
                    
                    # 5. Registra o status de agendado no log de posts do disparo atual
                    db.update_post_status(db_post_id, "tiktok", "scheduled")
                    priv_str = post_data.get("tiktok_privacy", "Public")
                    results_text += f"📅 <b>TikTok:</b> Agendado localmente com sucesso para <code>{sched_time_full}</code> ({priv_str})!\n\n"
                    print(f"[PIPELINE LOG] TikTok agendado localmente com sucesso! ID de agendamento: {new_post_id}", flush=True)
                except Exception as e:
                    db.update_post_status(db_post_id, "tiktok", "failed", error=str(e))
                    results_text += f"❌ <b>TikTok:</b> Falha ao agendar localmente! Erro: {html.escape(str(e))}\n\n"
                    print(f"[PIPELINE LOG] Falha ao agendar TikTok localmente: {e}", flush=True)
            else:
                # Postagem imediata via API Oficial do TikTok
                print(f"[PIPELINE LOG] Iniciando upload imediato para o TikTok...", flush=True)
                progress_cb = make_telegram_progress_callback(status_msg, "📤 Enviando para o TikTok:")
                await safe_edit_status("📤 Enviando para o TikTok: 0%")
                try:
                    tt_desc = caption_texto
                    pub_id = await loop.run_in_executor(
                        None,
                        tiktok_service.upload_video_to_tiktok,
                        video_path,
                        tt_desc,
                        post_data.get("tiktok_privacy", "Public"),
                        None,
                        None,
                        progress_cb
                    )
                    db.update_post_status(db_post_id, "tiktok", "completed", url=f"publish_id:{pub_id}")
                    priv_str = post_data.get("tiktok_privacy", "Public")
                    results_text += f"✅ <b>TikTok:</b> Enviado com sucesso ({priv_str} | Postado Agora)!\n\n"
                    print(f"[PIPELINE LOG] TikTok enviado com sucesso! ID de Publicação: {pub_id}", flush=True)
                except Exception as e:
                    db.update_post_status(db_post_id, "tiktok", "failed", error=str(e))
                    results_text += f"❌ <b>TikTok:</b> Falhou! Erro: {html.escape(str(e))}\n\n"
                    print(f"[PIPELINE LOG] TikTok falhou! Erro: {e}", flush=True)
                
        # 5. Upload para o Instagram (capa opcional)
        if platforms["instagram"]:
            if not tt_thumb or not os.path.exists(tt_thumb or ""):
                thumb_warnings.append("Instagram: thumbnail_tiktok.png não encontrada — Reels enviado sem capa personalizada.")
                print("[PIPELINE LOG] Instagram: thumbnail ausente, enviando sem capa.", flush=True)
            sched_time = post_data["instagram_scheduled_time"]
            if sched_time:
                # Salva na fila
                print(f"[PIPELINE LOG] Enfileirando Reels para o Instagram agendado para: {sched_time}...", flush=True)
                db.add_to_instagram_queue(
                    video_drive_path="KAGGLE/PIPELINE/FINAL/video_final.mp4",
                    caption=ig_caption,
                    cover_drive_path="KAGGLE/PIPELINE/FINAL/thumbnail_tiktok.png" if tt_thumb else None,
                    scheduled_time=sched_time
                )
                db.update_post_status(db_post_id, "instagram", "scheduled")
                results_text += f"📅 <b>Instagram:</b> Agendado com sucesso para <code>{sched_time}</code>!\n\n"
                print(f"[PIPELINE LOG] Reels agendado no banco com sucesso!", flush=True)
            else:
                print(f"[PIPELINE LOG] Iniciando upload imediato para o Instagram Reels...", flush=True)
                await safe_edit_status("📤 Enviando Reels para o Instagram (isso pode levar alguns minutos)...")
                try:
                    media_id, media_url = await loop.run_in_executor(
                        None,
                        instagram_uploader.upload_reel_to_instagram,
                        video_path,
                        ig_caption,
                        tt_thumb
                    )
                    db.update_post_status(db_post_id, "instagram", "completed", url=media_url)
                    results_text += f"✅ <b>Instagram:</b> Publicado Reels com sucesso!\n🔗 <a href=\"{media_url}\">Link do Reels</a>\n\n"
                    print(f"[PIPELINE LOG] Instagram Reels publicado com sucesso! URL: {media_url}", flush=True)
                except Exception as e:
                    db.update_post_status(db_post_id, "instagram", "failed", error=str(e))
                    results_text += f"❌ <b>Instagram:</b> Falhou! Erro: {html.escape(str(e))}\n\n"
                    print(f"[PIPELINE LOG] Instagram Reels falhou! Erro: {e}", flush=True)
                    
        # Adiciona avisos de capas ausentes ao final do resultado
        if thumb_warnings:
            results_text += "⚠️ <b>Avisos sobre capas:</b>\n"
            for tw in thumb_warnings:
                results_text += f"• {tw}\n"
            results_text += "\n"
        
        # Conclusão
        print("[PIPELINE LOG] Pipeline finalizado. Enviando resultado final para o usuário...", flush=True)
        await safe_edit_status(results_text, parse_mode="HTML", disable_web_page_preview=True)
        
    except Exception as e:
        error_msg = f"❌ Ocorreu um erro geral no pipeline: {e}"
        print(f"[PIPELINE LOG] Erro geral: {e}", flush=True)
        await safe_edit_status(error_msg)
        if db_post_id:
            try:
                db.update_post_status(db_post_id, "youtube", "failed", error=error_msg)
            except: pass
            
    finally:
        # Limpa todos os arquivos baixados localmente
        print("[PIPELINE LOG] Limpando arquivos temporários...", flush=True)
        for name, path in temp_paths.items():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    print(f"[PIPELINE LOG] Removido: {path}", flush=True)
                except Exception as ex:
                    print(f"[PIPELINE LOG] Erro ao remover {path}: {ex}", flush=True)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela a operação atual e limpa dados do contexto."""
    if update.message:
        await update.message.reply_text("Operação cancelada.")
    elif update.callback_query:
        await update.callback_query.answer("Operação cancelada.")
        await update.callback_query.edit_message_text("Operação cancelada.")
    return ConversationHandler.END

def main():
    # Define o event loop na thread principal para evitar RuntimeError no Python 3.12+
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    token = os.getenv("POSTRECAP_TELEGRAM_BOT_TOKEN")
    if not token:
        print("[ERRO] POSTRECAP_TELEGRAM_BOT_TOKEN ausente no .env. Configure para rodar o bot.")
        return

        
    # Inicializa o bot
    app = ApplicationBuilder().token(token).build()
    
    # Handler de conversação
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
            CallbackQueryHandler(menu_postar, pattern="^menu_programar$"),
            CallbackQueryHandler(menu_programados, pattern="^menu_programados$"),
            CallbackQueryHandler(delete_programado, pattern="^delete_prog_\\d+$"),
            CallbackQueryHandler(menu_fila, pattern="^menu_fila$"),
            CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$"),
        ],
        states={
            SELECT_PLATFORMS: [
                CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
                CallbackQueryHandler(menu_postar, pattern="^menu_programar$"),
                CallbackQueryHandler(menu_programados, pattern="^menu_programados$"),
                CallbackQueryHandler(delete_programado, pattern="^delete_prog_\\d+$"),
                CallbackQueryHandler(menu_fila, pattern="^menu_fila$"),
                CallbackQueryHandler(toggle_platform, pattern="^toggle_"),
                CallbackQueryHandler(confirm_platforms, pattern="^confirm_platforms$"),
                CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$"),
            ],
            SELECT_YOUTUBE_TITLE: [
                CallbackQueryHandler(handle_youtube_title_selection, pattern="^yt_title_"),
                CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
            ],
            INPUT_YOUTUBE_TITLE_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_youtube_title_manual)
            ],
            SELECT_SHORTS_TITLE: [
                CallbackQueryHandler(handle_shorts_title_selection, pattern="^shorts_title_"),
                CallbackQueryHandler(menu_postar, pattern="^menu_postar$"),
            ],
            INPUT_SHORTS_TITLE_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_shorts_title_manual)
            ],
            SELECT_YOUTUBE_PRIVACY: [
                CallbackQueryHandler(handle_youtube_privacy, pattern="^yt_priv_")
            ],
            SELECT_INSTAGRAM_SCHEDULING: [
                CallbackQueryHandler(handle_instagram_scheduling, pattern="^ig_")
            ],
            INPUT_INSTAGRAM_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_instagram_time)
            ],
            SELECT_TIKTOK_PRIVACY: [
                CallbackQueryHandler(handle_tiktok_privacy, pattern="^tt_")
            ],
            SELECT_TIKTOK_SCHEDULING: [
                CallbackQueryHandler(handle_tiktok_scheduling, pattern="^tt_")
            ],
            INPUT_TIKTOK_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tiktok_time)
            ],
            INPUT_UNIFIED_SCHEDULE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unified_schedule_time)
            ],
            CONFIRM_POST: [
                CallbackQueryHandler(execute_upload, pattern="^execute_upload$"),
                CallbackQueryHandler(show_main_menu_callback, pattern="^back_to_menu$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^cancel$")
        ]
    )
    
    app.add_handler(conv_handler)
    
    # Inicia o worker de fila em segundo plano em uma thread separada
    worker_thread = threading.Thread(target=run_queue_worker, args=(app.bot,), daemon=True)
    worker_thread.start()
    
    while True:
        try:
            print("Bot do Telegram em execução...", flush=True)
            app.run_polling(drop_pending_updates=True, stop_signals=None, close_loop=False)
            break

        except NetworkError as e:
            print(f"[REDE] Erro de conexão com o Telegram: {e}. Tentando novamente em 5 segundos...", flush=True)
            time.sleep(5)
        except Exception as e:
            print(f"[ERRO] Erro inesperado ao rodar o bot: {e}. Reiniciando em 5 segundos...", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    main()
