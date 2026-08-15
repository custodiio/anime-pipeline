"""
Integrador de Pipeline: Douyin Recap Scraper <-> AnimeRecap Dubbing Pipeline.
Gerencia as predefinições universais de dublagem, download, aceleração de velocidade (2:45 min),
disparo simultâneo do Omni com presets, notificações no Telegram e envio posterior de configs/legendas.
"""

import os
import sys
import json
import shutil
import logging
from datetime import datetime
from scrapper import database, media_processor, telegram_notifier

logger = logging.getLogger(__name__)

# Diretório dos arquivos de predefinição
PRESET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "predefinição"))
PRESET_CONFIG_JSON = os.path.join(PRESET_DIR, "videorender-project.json")
PRESET_LEGENDAS_ASS = os.path.join(PRESET_DIR, "legendas.ass")

# Predefinições Universais Padrão (conforme alinhado na interface do AnimeRecap)
DEFAULT_PIPELINE_PRESETS = {
    "watermark": False,       # ❌ Remover Marca d'água (vídeos já vêm sem watermark da API)
    "enhancer": True,         # ✅ Aumentar Qualidade (Enhancer ativo)
    "thumbnail": False,       # ❌ Gerar Thumbnail (desativado por padrão)
    "bg_audio": True,         # 🎵 Áudio: Fundo + Dub
    "srt_type": "word_by_word",  # 📝 SRT: Palavra/Palavra
    "azure_enabled": True,    # 🤖 Modelo Azure: Ativo
    "manual_mode": False      # 🤖 Modo: Automático — Omni inicia imediatamente
}

def generate_posting_guide(episode_title: str, collection_title_pt: str, episode_num: int = 1, roteiro_pt: dict = None) -> dict:
    """
    Gera um Guia de Postagem Otimizado (PT-BR) baseado no Roteiro Simplificado/Traduzido pelo Omni.
    """
    sinopse = ""
    if roteiro_pt and isinstance(roteiro_pt, dict):
        falas = roteiro_pt.get("falas", []) or roteiro_pt.get("dialogos", [])
        if falas and isinstance(falas, list):
            primeiras_falas = [f.get("texto", "") for f in falas[:4] if isinstance(f, dict) and f.get("texto")]
            if primeiras_falas:
                sinopse = " ".join(primeiras_falas)

    if not sinopse:
        sinopse = episode_title.strip()

    title_pt = f"PART {episode_num} | {collection_title_pt} 🍿"
    
    desc_pt = (
        f"🔥 Acompanhe o episódio {episode_num} de '{collection_title_pt}'!\n\n"
        f"📌 Destaque do Roteiro: {sinopse[:250]}...\n\n"
        f"🔔 Se inscreva e ative as notificações para o próximo episódio!\n\n"
        f"#manhwa #anime #recap #animerecap #douyin #shorts"
    )
    
    tags = ["manhwa", "anime", "animerecap", "recap", "douyin", "shorts", "viral", collection_title_pt.lower().replace(" ", "")]

    return {
        "title": title_pt,
        "description": desc_pt,
        "tags": tags,
        "generated_at": datetime.now().isoformat()
    }

def get_animerecap_path() -> str | None:
    """Busca o caminho raiz do projeto AnimeRecap/anime-pipeline no sistema."""
    possible_paths = [
        "/home/ubuntu/apps/anime-pipeline",
        "/home/ubuntu/apps/AnimeRecap",
        "/home/ubuntu/apps/SeoAnimeRecap",
        r"D:\Applications\AnimeRecap",
        r"C:\Applications\AnimeRecap",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "AnimeRecap")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "anime-pipeline"))
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None

def apply_preset_files_to_animerecap(animerecap_root: str, project_id: str = None) -> bool:
    """
    Envia videorender-project.json e legendas.ass diretamente para a pasta
    KAGGLE/PIPELINE/OMNI/ no Google Drive APÓS a inicialização do Omni e marca step_config_ready = done.
    """
    try:
        uploads_dir = os.path.join(animerecap_root, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        if os.path.exists(PRESET_CONFIG_JSON):
            dest_config = os.path.join(uploads_dir, "videorender-project.json")
            shutil.copy2(PRESET_CONFIG_JSON, dest_config)
            logger.info(f"✅ 'videorender-project.json' copiado localmente para {dest_config}")

        if os.path.exists(PRESET_LEGENDAS_ASS):
            dest_ass = os.path.join(uploads_dir, "legendas.ass")
            shutil.copy2(PRESET_LEGENDAS_ASS, dest_ass)
            logger.info(f"✅ 'legendas.ass' copiado localmente para {dest_ass}")

        try:
            if animerecap_root not in sys.path:
                sys.path.insert(0, animerecap_root)

            from bot.pipeline_controller import PipelineController
            controller = PipelineController()
            
            if os.path.exists(PRESET_CONFIG_JSON):
                controller.drive.salvar(PRESET_CONFIG_JSON, "KAGGLE/PIPELINE/OMNI/videorender-project.json")
                logger.info("☁️ 'videorender-project.json' enviado diretamente para KAGGLE/PIPELINE/OMNI/ no Google Drive!")

            if os.path.exists(PRESET_LEGENDAS_ASS):
                controller.drive.salvar(PRESET_LEGENDAS_ASS, "KAGGLE/PIPELINE/OMNI/legendas.ass")
                logger.info("☁️ 'legendas.ass' enviado diretamente para KAGGLE/PIPELINE/OMNI/ no Google Drive!")

            if project_id:
                from bot import database as animerecap_db
                animerecap_db.update_step(project_id, "step_config_ready", "done", "Presets e configs salvos no Drive em KAGGLE/PIPELINE/OMNI/")
                logger.info(f"✅ 'step_config_ready' marcado como CONCLUÍDO (done) para o projeto {project_id}!")

        except Exception as e_drive:
            logger.warning(f"Aviso ao realizar upload no Google Drive / atualizar banco do AnimeRecap: {e_drive}")

        return True
    except Exception as e:
        logger.error(f"Erro ao aplicar arquivos de predefinição no AnimeRecap: {e}")
        return False

def dispatch_episode_to_pipeline(ep_id: int, custom_presets: dict = None, force: bool = False) -> dict:
    """
    Aciona o pipeline do AnimeRecap para um episódio específico.
    Garante a regra de APENAS 1 EPISÓDIO POR VEZ (a menos que force=True).
    Envia atualizações em tempo real para o Telegram.
    """
    ep = database.get_episode_by_id(ep_id)
    if not ep:
        return {"ok": False, "message": f"Episódio #{ep_id} não encontrado."}

    # 🛑 Trava de Segurança: Apenas 1 projeto em processamento por vez
    if not force:
        active_eps = database.get_episodes_by_status("processing_dubbing")
        other_actives = [e for e in active_eps if e["id"] != ep_id]
        if other_actives:
            # Verifica se realmente existe projeto ativo no anime-pipeline
            has_running = False
            try:
                import psycopg2
                pg_url = os.getenv("DATABASE_URL")
                if pg_url:
                    pg_conn = psycopg2.connect(pg_url)
                    pg_cur = pg_conn.cursor()
                    pg_cur.execute("SELECT COUNT(*) FROM pipeline_projects WHERE status IN ('running', 'pending')")
                    has_running = pg_cur.fetchone()[0] > 0
                    pg_conn.close()
            except Exception as e_pg:
                logger.warning(f"Não foi possível verificar status no Postgres: {e_pg}")
                has_running = True # Fallback seguro

            if not has_running:
                logger.info("ℹ️ Episódios em processing_dubbing não possuem projeto ativo no pipeline. Auto-liberando a trava...")
                for e_stuck in other_actives:
                    database.update_episode_status(e_stuck["id"], "published")
            else:
                active_name = other_actives[0].get("title", "")[:35]
                msg_busy = f"⚠️ Já existe o Episódio #{other_actives[0]['id']} ('{active_name}') em processamento no pipeline. Aguarde a conclusão antes de disparar o próximo."
                logger.warning(msg_busy)
                return {"ok": False, "busy": True, "message": msg_busy}

    col = database.get_douyin_collection_by_id(ep["mix_id"])
    col_title = col.get("title_pt", "Série Douyin") if col else "Série Douyin"
    ep_num_str = f"EP {ep.get('episode_num') or 1}"

    # 📲 1. Notificação Telegram: Início
    telegram_notifier.send_message(
        f"🚀 <b>Iniciando Processamento de Episódio</b>\n\n"
        f"🍿 <b>Série:</b> {col_title}\n"
        f"📌 <b>Episódio:</b> {ep_num_str}\n"
        f"🆔 <b>ID:</b> #{ep_id}\n"
        f"⏳ <i>Status: Baixando vídeo HD do Douyin...</i>"
    )

    presets = DEFAULT_PIPELINE_PRESETS.copy()
    if custom_presets:
        presets.update(custom_presets)

    logger.info(f"🚀 Iniciando disparo do pipeline para o EP #{ep_id} ({ep['title'][:30]})...")

    # Localiza o módulo AnimeRecap no sistema
    animerecap_root = get_animerecap_path()
    if not animerecap_root:
        logger.warning("⚠️ Diretório do AnimeRecap não encontrado no disco. Disparo em modo simulado.")
        database.update_episode_status(ep_id, "processing_dubbing")
        return {
            "ok": True,
            "simulated": True,
            "message": "AnimeRecap não localizado no disco. Disparo simulado.",
            "presets": presets
        }

    try:
        if animerecap_root not in sys.path:
            sys.path.insert(0, animerecap_root)

        uploads_dir = os.path.join(animerecap_root, "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        video_path = os.path.join(uploads_dir, f"ep_{ep_id}_original.mp4")
        adjusted_video_path = os.path.join(uploads_dir, f"ep_{ep_id}_2m45s.mp4")
        audio_path = os.path.join(uploads_dir, f"ep_{ep_id}_audio.mp3")

        # Garante limpeza completa de arquivos locais anteriores do mesmo episódio
        for old_f in [video_path, adjusted_video_path, audio_path]:
            if os.path.exists(old_f):
                try:
                    os.remove(old_f)
                except Exception:
                    pass

        # 2. Download do Vídeo HD do Douyin (Sempre atualizado)
        if ep.get("video_url"):
            logger.info(f"Baixando vídeo HD do Douyin ({ep['video_url']})...")
            from scrapper import scraper
            downloaded = scraper.download_douyin_video(ep["video_url"], video_path)
            if not downloaded or not os.path.exists(video_path):
                msg_fail = f"❌ Falha ao baixar o vídeo do Douyin ({ep['video_url']}). Verifique a validade do cookie."
                logger.error(msg_fail)
                telegram_notifier.send_message(msg_fail)
                return {"ok": False, "message": msg_fail}

        # 3. Análise de Duração e Aceleração Proporcional de Velocidade (2:45 min)
        final_video_file = video_path
        if os.path.exists(video_path):
            orig_dur = media_processor.get_video_duration(video_path)
            proc_video, status_dur = media_processor.adjust_video_duration_for_pipeline(video_path, adjusted_video_path, target_max_seconds=165.0)

            if status_dur == "error":
                msg_err = f"❌ Falha ao processar a duração do vídeo de {orig_dur:.1f}s. Verifique o arquivo manualmente."
                telegram_notifier.send_message(msg_err)
                return {
                    "ok": False,
                    "status": "error",
                    "message": msg_err
                }

            final_video_file = proc_video
            new_dur = media_processor.get_video_duration(final_video_file)

            if status_dur == "truncated":
                telegram_notifier.send_message(
                    f"✂️ <b>Corte e Aceleração Proporcional Aplicados</b>\n\n"
                    f"⏱️ Duração original: {orig_dur:.1f}s ({orig_dur/60:.2f} min — acima de 4 min)\n"
                    f"⚡ Os primeiros 4:00 min foram cortados e acelerados (1.45x) para durar exatamente {new_dur:.1f}s (2:45 min)!"
                )
            elif status_dur == "adjusted":
                speed_factor = orig_dur / 165.0
                telegram_notifier.send_message(
                    f"⚡ <b>Ajuste de Velocidade Aplicado (sem corte)</b>\n\n"
                    f"⏱️ Duração original: {orig_dur:.1f}s ({orig_dur/60:.2f} min)\n"
                    f"🚀 Fator de aceleração: {speed_factor:.3f}x\n"
                    f"🎯 Nova duração: {new_dur:.1f}s (2:45 min)"
                )
            else:
                telegram_notifier.send_message(f"✅ <b>Duração do Vídeo OK:</b> {orig_dur:.1f}s (dentro do limite de 2:45 min).")

            # Extrai o áudio MP3 do vídeo final ajustado
            media_processor.extract_audio(final_video_file, audio_path)

        project_name = f"Recap_Col_{ep['mix_id']}_EP{ep['episode_num'] or 1}"

        from bot.pipeline_controller import PipelineController
        from bot import database as animerecap_db

        controller = PipelineController()

        # 4. Upload das Mídias Brutas para o Drive (limpeza + envio)
        telegram_notifier.send_message(
            f"☁️ <b>Fazendo Upload das Mídias Brutas para o Google Drive...</b>\n"
            f"📁 Limpando pasta <code>ATIVO</code> e preparando áudio <code>AUDIO_DUB</code>..."
        )

        input_vid = final_video_file if os.path.exists(final_video_file) else os.path.join(uploads_dir, f"ep_{ep_id}_original.mp4")
        input_aud = audio_path if os.path.exists(audio_path) else os.path.join(uploads_dir, f"ep_{ep_id}_audio.mp3")

        from scrapper.config import TELEGRAM_CHAT_ID
        chat_id_to_use = str(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else "default_scrapper"

        project = controller.iniciar_projeto(
            project_name=project_name,
            chat_id=chat_id_to_use,
            video_path=input_vid,
            audio_path=input_aud,
            opts=presets
        )
        real_project_id = str(project["id"]) if project else None

        # 5. Disparo do Omni no AnimeRecap com Presets Universais
        if real_project_id:
            animerecap_db.set_project_opts(
                real_project_id,
                manual_mode=False,
                thumbnail_enabled=False,
                bg_audio=True,
                srt_type="word_by_word",
                azure_enabled=True
            )
            controller.disparar_omni_imediatamente(real_project_id)
            logger.info(f"⚡ Omni disparado com sucesso no AnimeRecap para o projeto UUID {real_project_id}!")

            telegram_notifier.send_message(
                f"🤖 <b>Omni Disparado com Sucesso no AnimeRecap!</b>\n\n"
                f"🆔 <b>UUID Projeto:</b> <code>{real_project_id[:8]}...</code>\n"
                f"⚙️ <b>Presets:</b> Enhancer ON | Legenda Word-by-Word | Azure ON | Fundo ON\n"
                f"⏳ <i>Enviando arquivo de legenda/projeto pro Drive e iniciando síntese de voz (TTS PT-BR)...</i>"
            )

        # 6. Envia as configurações (videorender-project.json e legendas.ass) após a limpeza inicial
        apply_preset_files_to_animerecap(animerecap_root, project_id=real_project_id or project_name)

        database.update_episode_status(ep_id, "processing_dubbing")

        telegram_notifier.send_message(
            f"✅ <b>Etapa Inicial Concluída!</b>\n"
            f"O robô Kaggle está dublando e renderizando o {ep_num_str} de '{col_title}'.\n"
            f"O Guia de Postagem PT-BR será gerado assim que o roteiro for traduzido pelo Omni!"
        )

        return {
            "ok": True,
            "project_name": project_name,
            "project_id": real_project_id,
            "message": f"Episódio enviado com sucesso para o AnimeRecap! Notificações enviadas ao Telegram.",
            "presets": presets
        }

    except Exception as e:
        logger.error(f"Erro ao conversar com o pipeline AnimeRecap: {e}")
        database.update_episode_status(ep_id, "processing_dubbing")
        telegram_notifier.send_message(f"⚠️ <b>Aviso no Pipeline:</b> {e}")
        return {
            "ok": True,
            "warning": str(e),
            "message": f"Pipeline acionado com os arquivos de mídia e presets.",
            "presets": presets
        }
