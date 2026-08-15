import os
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

load_dotenv()

def load_and_refresh_youtube_token():
    """
    Carrega o token de acesso do YouTube de duas fontes:
    1. Banco SQLite local do painel (database/users.db ou tiktok_approval/database/users.db).
    2. Fallback fixo para YOUTUBE_REFRESH_TOKEN no .env.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    vps_db_path = os.path.abspath(os.path.join(os.path.dirname(base_dir), "database", "users.db"))
    local_db_path = os.path.abspath(os.path.join(base_dir, "tiktok_approval", "database", "users.db"))
    
    db_path = None
    if os.path.exists(vps_db_path):
        db_path = vps_db_path
    elif os.path.exists(local_db_path):
        db_path = local_db_path
        
    access_token = None
    refresh_token = None
    email_user = None
    token_source = None
    
    if db_path and os.path.exists(db_path):
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Se houver YOUTUBE_USER_EMAIL no .env, busca especificamente para esse e-mail
            email_filter = os.getenv("YOUTUBE_USER_EMAIL")
            if email_filter:
                cursor.execute("SELECT access_token, refresh_token, email FROM youtube_connections WHERE email = ?", (email_filter,))
            else:
                # Pega a última conexão do banco de dados
                cursor.execute("SELECT access_token, refresh_token, email FROM youtube_connections ORDER BY connected_at DESC LIMIT 1")
                
            row = cursor.fetchone()
            if row:
                access_token, refresh_token, email_user = row
                token_source = 'db'
            conn.close()
        except Exception as db_err:
            print(f"[YOUTUBE] Falha ao tentar ler token do banco SQLite do painel: {db_err}", flush=True)

    if not refresh_token:
        refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")
        token_source = 'env'
        
    return access_token, refresh_token, email_user, token_source, db_path

def get_youtube_service():
    client_id = os.getenv("YOUTUBE_CLIENT_ID")
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        raise Exception("[ERRO] Credenciais específicas do YouTube (YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET) incompletas no .env")
        
    access_token, refresh_token, email_user, token_source, db_path = load_and_refresh_youtube_token()
    
    if not refresh_token:
        raise Exception("[ERRO] Nenhum refresh_token do YouTube encontrado no banco de dados ou no .env!")
        
    creds = google.oauth2.credentials.Credentials(
        token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token"
    )
    
    # Tenta renovar o token e atualizar no banco do painel se aplicável
    try:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        if token_source == 'db' and db_path and email_user:
            import sqlite3
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE youtube_connections 
                    SET access_token = ?, refresh_token = ?, connected_at = CURRENT_TIMESTAMP
                    WHERE email = ?
                """, (creds.token, creds.refresh_token or refresh_token, email_user))
                conn.commit()
                conn.close()
                print(f"[YOUTUBE] Token renovado e atualizado no banco para: {email_user}", flush=True)
            except Exception as save_err:
                print(f"[YOUTUBE] Erro ao salvar token renovado no banco: {save_err}", flush=True)
    except Exception as ref_err:
        print(f"[YOUTUBE WARNING] Falha ao renovar token de acesso do YouTube: {ref_err}", flush=True)
        
    return build("youtube", "v3", credentials=creds)

def optimize_thumbnail(thumbnail_path, max_size=2000000):
    """
    Se a imagem no thumbnail_path for maior que max_size,
    otimiza a imagem reduzindo as dimensões e a qualidade do JPEG,
    salvando em um caminho temporário. Retorna o caminho da imagem otimizada.
    """
    if not os.path.exists(thumbnail_path):
        return thumbnail_path
        
    file_size = os.path.getsize(thumbnail_path)
    if file_size <= max_size:
        return thumbnail_path
        
    print(f"[YOUTUBE] Thumbnail original ({file_size} bytes) excede o limite do YouTube (2MB). Otimizando...", flush=True)
    try:
        from PIL import Image
        img = Image.open(thumbnail_path)
        
        # Converte para RGB se for RGBA (JPEG não suporta canal alpha)
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            # Cria fundo branco
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img = background
        else:
            img = img.convert("RGB")
            
        temp_thumb_path = thumbnail_path + ".optimized.jpg"
        
        quality = 85
        img.save(temp_thumb_path, "JPEG", quality=quality)
        
        # Se ainda for maior que o limite, reduz qualidade
        while os.path.getsize(temp_thumb_path) > max_size and quality > 30:
            quality -= 10
            img.save(temp_thumb_path, "JPEG", quality=quality)
            
        # Se ainda excede o limite, reduz as dimensões da imagem pela metade
        if os.path.getsize(temp_thumb_path) > max_size:
            width, height = img.size
            img = img.resize((width // 2, height // 2), Image.Resampling.LANCZOS)
            img.save(temp_thumb_path, "JPEG", quality=75)
            
        new_size = os.path.getsize(temp_thumb_path)
        print(f"[YOUTUBE] Thumbnail otimizada com sucesso! Novo tamanho: {new_size} bytes", flush=True)
        return temp_thumb_path
    except Exception as e:
        print(f"[AVISO] Erro ao otimizar thumbnail com Pillow: {e}. Enviando arquivo original mesmo assim.", flush=True)
        return thumbnail_path

def sanitize_tags(tags):
    if not tags:
        return []
    sanitized = []
    total_len = 0
    for tag in tags:
        clean_tag = tag.replace("<", "").replace(">", "").replace("\n", "").replace("\r", "").strip()
        if not clean_tag:
            continue
        if len(clean_tag) > 100:
            clean_tag = clean_tag[:100].strip()
        # Limite total de 450 caracteres para segurança (limite do YT é 500)
        if total_len + len(clean_tag) + 2 > 450:
            break
        sanitized.append(clean_tag)
        total_len += len(clean_tag) + 2
    return sanitized

def upload_video_to_youtube(video_path, title, description, tags=None, category_id="24", privacy_status="draft", thumbnail_path=None, progress_callback=None):
    """
    Realiza o envio de um vídeo para o YouTube e define sua capa.
    privacy_status: 'draft' (rascunho, padrão) | 'private' | 'public' | 'unlisted'
    Retorna o ID do vídeo e a URL de visualização.
    """
    youtube = get_youtube_service()
    
    body = {
        "snippet": {
            "title": title[:100],  # Limite do YouTube é 100 caracteres
            "description": description,
            "tags": sanitize_tags(tags),
            "categoryId": category_id
        }
    }
    
    # A API v3 do YouTube não possui um status "draft" oficial. Omitir o status faz o vídeo ir como Público.
    # Portanto, mapeamos "draft" para "private" para que o vídeo seja criado com segurança em modo privado (rascunho).
    mapped_privacy = "private" if (not privacy_status or privacy_status == "draft") else privacy_status
    
    body["status"] = {
        "privacyStatus": mapped_privacy,
        "selfDeclaredMadeForKids": False
    }
    
    upload_part = "snippet,status"
    
    media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
    request = youtube.videos().insert(
        part=upload_part,
        body=body,
        media_body=media
    )
    
    print("[YOUTUBE] Iniciando envio do vídeo...", flush=True)
    response = None
    last_percent = -1
    while response is None:
        status, response = request.next_chunk()
        if status:
            percent = int(status.progress() * 100)
            if percent != last_percent:
                print(f"[YOUTUBE] Progresso de upload: {percent}%", flush=True)
                if progress_callback:
                    try:
                        progress_callback(percent)
                    except Exception as cb_err:
                        print(f"[AVISO] Erro no callback de progresso do YouTube: {cb_err}", flush=True)
                last_percent = percent
            
    video_id = response.get("id")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[OK] Vídeo enviado com sucesso para o YouTube! ID: {video_id}", flush=True)
    
    # Upload da thumbnail se houver
    if thumbnail_path and os.path.exists(thumbnail_path):
        optimized_thumb = optimize_thumbnail(thumbnail_path)
        print(f"Enviando thumbnail {optimized_thumb} para o vídeo {video_id}...", flush=True)
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(optimized_thumb)
            ).execute()
            print("[OK] Thumbnail definida com sucesso!", flush=True)
        except Exception as e:
            print(f"[ERRO] Falha ao enviar thumbnail: {e}", flush=True)
        finally:
            if optimized_thumb != thumbnail_path and os.path.exists(optimized_thumb):
                try:
                    os.remove(optimized_thumb)
                except:
                    pass
            
    return video_id, video_url
