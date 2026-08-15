import os
import json
import time
import logging
import sys
from instagrapi import Client
from dotenv import load_dotenv
from drive_manager import drive_manager
import db

load_dotenv()

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
except Exception:
    pass

# Configura o logger do instagrapi para mostrar logs no terminal de forma clara
logger = logging.getLogger("instagrapi")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[INSTAGRAM LOG] %(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instagram_session.json")

def get_instagram_client():
    cl = Client()
    # Opcional: configurar timeout mais longo para uploads pesados
    cl.delay_range = [2, 5]
    
    username = os.getenv("INSTAGRAM_USERNAME") or os.getenv("INSTAGRAM_USER")
    password = os.getenv("INSTAGRAM_PASSWORD") or os.getenv("INSTAGRAM_PASS")
        
    session_loaded = False
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
            # Verifica a validade testando uma chamada simples sem forçar re-login
            cl.get_timeline_feed()
            print("[OK] Sessão do Instagram restaurada e ativa com sucesso!", flush=True)
            session_loaded = True
        except Exception as e:
            print(f"[AVISO] Sessão do Instagram expirada/inválida ({e}). Refazendo login...", flush=True)
            if os.path.exists(SESSION_FILE):
                try:
                    os.remove(SESSION_FILE)
                except Exception:
                    pass
                    
    if not session_loaded:
        if not username or not password:
            raise ValueError("[ERRO] Usuário ou senha do Instagram não configurados no .env")
        print(f"Fazendo login no Instagram para o usuário: {username}...", flush=True)
        cl.login(username, password)
        cl.dump_settings(SESSION_FILE)
        print("[OK] Novo login efetuado e sessão salva em:", SESSION_FILE, flush=True)
        
    return cl

def extract_first_frame(video_path, output_image_path):
    """
    Extrai o primeiro frame do vídeo usando ffmpeg em linha de comando.
    """
    import subprocess
    try:
        # Comando para extrair o primeiro frame no segundo 1 (evita tela preta)
        cmd = [
            "ffmpeg", "-y",
            "-ss", "00:00:01",
            "-i", video_path,
            "-vframes", "1",
            output_image_path
        ]
        # Executa em silêncio
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"[AVISO] Falha ao extrair frame do vídeo com ffmpeg no segundo 1: {e}. Tentando no segundo 0...", flush=True)
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vframes", "1",
                output_image_path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception as e2:
            print(f"[ERRO] Falha geral ao extrair frame com ffmpeg: {e2}", flush=True)
            return False

def upload_reel_to_instagram(video_path, caption, thumbnail_path=None):
    """
    Envia um vídeo do tipo Reel para o Instagram com legenda e capa.
    """
    cl = get_instagram_client()
    
    # Se thumbnail_path for vazio/falso, normaliza para None
    if not thumbnail_path:
        thumbnail_path = None
        
    # Se o caminho da capa foi passado mas o arquivo não existe fisicamente, remove
    if thumbnail_path and not os.path.exists(thumbnail_path):
        print(f"[AVISO] Capa especificada não encontrada no caminho local {thumbnail_path}. Tentando gerar capa padrão.", flush=True)
        thumbnail_path = None
        
    temp_thumbnail = None
    # Se não temos capa (ou se foi removida), extraímos o primeiro frame do vídeo programaticamente
    if not thumbnail_path:
        video_dir = os.path.dirname(os.path.abspath(video_path))
        temp_thumbnail = os.path.join(video_dir, f"temp_cover_{int(time.time())}.jpg")
        print(f"[INSTAGRAM] Gerando capa padrão a partir do vídeo...", flush=True)
        if extract_first_frame(video_path, temp_thumbnail):
            thumbnail_path = temp_thumbnail
            print(f"[INSTAGRAM] Capa padrão gerada com sucesso: {thumbnail_path}", flush=True)
        else:
            thumbnail_path = None
            print(f"[AVISO] Não foi possível gerar capa padrão. Enviando sem capa.", flush=True)
        
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"\n[INSTAGRAM] 🚀 Iniciando processo de envio do Reels...", flush=True)
    print(f"[INSTAGRAM] 📊 Tamanho do arquivo de vídeo: {file_size_mb:.2f} MB", flush=True)
    print(f"[INSTAGRAM] ℹ️  Nota: O instagrapi simula um dispositivo móvel e pode re-codificar o vídeo se necessário.", flush=True)
    print(f"[INSTAGRAM] ⏳ Isso PODE DEMORAR de 2 a 10 minutos dependendo da sua conexão e processamento.", flush=True)
    print(f"[INSTAGRAM] 🔍 Acompanhe o progresso detalhado nos logs abaixo:\n", flush=True)
    
    try:
        start_time = time.time()
        media = cl.clip_upload(
            path=video_path,
            caption=caption,
            thumbnail=thumbnail_path
        )
        duration = time.time() - start_time
        media_id = media.id
        media_url = f"https://www.instagram.com/p/{media.code}/"
        print(f"\n[INSTAGRAM] ✅ Reels publicado no Instagram com sucesso em {duration:.1f} segundos!", flush=True)
        print(f"[INSTAGRAM] 🔗 URL: {media_url}", flush=True)
        return media_id, media_url
    except Exception as e:
        print(f"\n[INSTAGRAM] ❌ ERRO AO FAZER UPLOAD DO REELS: {e}", flush=True)
        raise e
    finally:
        # Remove a capa temporária gerada
        if temp_thumbnail and os.path.exists(temp_thumbnail):
            try:
                os.remove(temp_thumbnail)
                print(f"[INSTAGRAM] Capa temporária removida: {temp_thumbnail}", flush=True)
            except Exception as e_clean:
                print(f"[AVISO] Falha ao remover capa temporária: {e_clean}", flush=True)

def process_instagram_queue():
    """
    Processa todos os agendamentos pendentes do Instagram cuja data de envio já chegou.
    """
    jobs = db.get_pending_instagram_jobs()
    if not jobs:
        return
        
    print(f"Encontrados {len(jobs)} agendamentos pendentes do Instagram para processar.")
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_queue")
    os.makedirs(temp_dir, exist_ok=True)
    
    for job in jobs:
        job_id, video_drive_path, caption, cover_drive_path, scheduled_time = job
        print(f"Processando agendamento #{job_id}...")
        db.update_queue_status(job_id, "processing")
        
        local_video = os.path.join(temp_dir, f"video_{job_id}.mp4")
        local_cover = os.path.join(temp_dir, f"cover_{job_id}.png") if cover_drive_path else None
        
        try:
            # 1. Baixar vídeo do Drive
            print(f"Baixando vídeo de {video_drive_path}...")
            drive_manager.download_file_by_path(video_drive_path, local_video)
            
            # 2. Baixar capa do Drive se aplicável
            if cover_drive_path:
                try:
                    print(f"Baixando capa de {cover_drive_path}...")
                    drive_manager.download_file_by_path(cover_drive_path, local_cover)
                except Exception as e_cover:
                    print(f"[AVISO] Não foi possível baixar a capa do Drive ({e_cover}). Continuando o envio sem capa...", flush=True)
                    local_cover = None
                
            # 3. Postar no Instagram
            media_id, media_url = upload_reel_to_instagram(
                video_path=local_video,
                caption=caption,
                thumbnail_path=local_cover
            )
            
            # 4. Atualizar banco de dados como concluído
            db.update_queue_status(job_id, "completed")
            print(f"[OK] Agendamento #{job_id} concluído com sucesso! URL: {media_url}")
            
        except Exception as e:
            error_msg = str(e)
            print(f"[ERRO] Falha ao processar agendamento #{job_id}: {error_msg}")
            db.update_queue_status(job_id, "failed", error=error_msg)
            
        finally:
            # Limpar arquivos temporários
            if os.path.exists(local_video):
                try: os.remove(local_video)
                except: pass
            if local_cover and os.path.exists(local_cover):
                try: os.remove(local_cover)
                except: pass
