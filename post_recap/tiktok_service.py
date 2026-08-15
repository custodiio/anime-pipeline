import os
import sys
import json
import time
import requests
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

def load_and_refresh_token():
    """
    Carrega o token de acesso do TikTok de duas fontes possíveis:
    1. Banco SQLite local do painel (tiktok_approval/database/users.db) - que representa logins feitos via web.
    2. Arquivo token.json local na raiz.
    
    Se o token estiver expirado, realiza a renovação automática usando o refresh_token
    e atualiza ambas as fontes para manter o sistema web e o bot sincronizados!
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_dir, "token.json")
    
    # Caminhos inteligentes do banco de dados SQLite
    vps_db_path = os.path.abspath(os.path.join(os.path.dirname(base_dir), "database", "users.db"))
    local_db_path = os.path.abspath(os.path.join(base_dir, "tiktok_approval", "database", "users.db"))
    
    db_path = None
    if os.path.exists(vps_db_path):
        db_path = vps_db_path
    elif os.path.exists(local_db_path):
        db_path = local_db_path
    
    access_token = None
    refresh_token = None
    open_id = None
    email_user = None
    token_source = None
    
    # 1. Fonte A: Tenta obter do banco de dados local SQLite do painel web
    if os.path.exists(db_path):
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Se houver TIKTOK_USER_EMAIL no .env, busca especificamente para esse e-mail
            email_filter = os.getenv("TIKTOK_USER_EMAIL")
            if email_filter:
                cursor.execute("SELECT access_token, refresh_token, open_id, email FROM tiktok_connections WHERE email = ?", (email_filter,))
            else:
                # Pega a última conexão do banco de dados
                cursor.execute("SELECT access_token, refresh_token, open_id, email FROM tiktok_connections ORDER BY connected_at DESC LIMIT 1")
                
            row = cursor.fetchone()
            if row:
                access_token, refresh_token, open_id, email_user = row
                token_source = 'db'
            conn.close()
        except Exception as db_err:
            print(f"[TIKTOK] Falha ao tentar ler token do banco SQLite local: {db_err}", flush=True)
            
    # 2. Fonte B: Fallback para o arquivo token.json na raiz do bot
    if not access_token and os.path.exists(token_path):
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                token_data = json.load(f)
                access_token = token_data.get("access_token")
                refresh_token = token_data.get("refresh_token")
                open_id = token_data.get("open_id")
                token_source = 'json'
        except Exception as json_err:
            print(f"[TIKTOK] Falha ao tentar ler token do arquivo token.json: {json_err}", flush=True)
            
    if not access_token:
        raise Exception(
            "Nenhum token do TikTok encontrado. Por favor, faça login pelo painel web "
            "ou certifique-se de que o arquivo token.json está configurado na raiz."
        )
        
    # 3. Testar a validade do access_token atual
    user_info_url = "https://open.tiktokapis.com/v2/user/info/"
    user_headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    try:
        test_res = requests.get(f"{user_info_url}?fields=open_id", headers=user_headers)
        if test_res.status_code == 200:
            # Token atual está totalmente válido!
            return access_token
    except Exception as e:
        print(f"[TIKTOK] Erro ao testar validade do token: {e}. Tentando renovar...", flush=True)
        
    print("[TIKTOK] Access token expirado ou inválido. Renovando com o refresh_token...", flush=True)
    
    # 4. Se o token expirou, realizar a renovação via refresh_token
    if not refresh_token:
        raise Exception("Access token expirado e refresh_token não disponível para renovação.")
        
    client_key = os.getenv("TIKTOK_CLIENT_KEY")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
    
    if not client_key or not client_secret:
        raise Exception("TIKTOK_CLIENT_KEY ou TIKTOK_CLIENT_SECRET ausente no arquivo .env.")
        
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Cache-Control": "no-cache"
    }
    data = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    
    refresh_res = requests.post(token_url, headers=headers, data=data)
    if refresh_res.status_code != 200:
        raise Exception(f"Falha ao renovar o token do TikTok. Resposta da API: {refresh_res.text}")
        
    new_token_data = refresh_res.json()
    new_access_token = new_token_data.get("access_token")
    new_refresh_token = new_token_data.get("refresh_token") or refresh_token # Mantém o antigo se não rotacionar
    
    if not new_access_token:
        raise Exception(f"A API do TikTok retornou sucesso mas sem o campo access_token: {new_token_data}")
        
    # 5. Sincronizar e salvar o novo token em ambas as fontes
    
    # A. Atualizar no banco SQLite local (se aplicável)
    if os.path.exists(db_path) and email_user:
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE tiktok_connections 
                SET access_token = ?, refresh_token = ?, connected_at = CURRENT_TIMESTAMP
                WHERE email = ?
            """, (new_access_token, new_refresh_token, email_user))
            conn.commit()
            conn.close()
            print("[TIKTOK] Banco SQLite de conexões atualizado com o novo token de acesso.", flush=True)
        except Exception as db_write_err:
            print(f"[TIKTOK ERROR] Falha ao atualizar token no SQLite: {db_write_err}", flush=True)
            
    # B. Atualizar no arquivo token.json
    try:
        token_data = {}
        if os.path.exists(token_path):
            with open(token_path, "r", encoding="utf-8") as f:
                try: token_data = json.load(f)
                except Exception: pass
                
        token_data.update(new_token_data)
        token_data["access_token"] = new_access_token
        token_data["refresh_token"] = new_refresh_token
        token_data["open_id"] = open_id or token_data.get("open_id")
        
        with open(token_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=4, ensure_ascii=False)
        print("[TIKTOK] Arquivo token.json atualizado com o novo token de acesso.", flush=True)
    except Exception as json_write_err:
        print(f"[TIKTOK ERROR] Falha ao salvar novo token no token.json: {json_write_err}", flush=True)
        
    return new_access_token

def upload_video_to_tiktok(
    video_path, 
    title, 
    privacy_level="Public", 
    schedule_time=None, 
    schedule_day=None, 
    progress_callback=None,
    disable_comment=False,
    disable_duet=True,
    disable_stitch=True,
    brand_content_toggle=False,
    brand_organic_toggle=False,
    is_aigc=False
):
    """
    Realiza o envio de um vídeo para o TikTok usando a API Oficial (Content Posting API / Direct Post).
    Mapeia os parâmetros de privacidade e realiza o upload segmentado em chunks.
    """
    if not os.path.exists(video_path):
        raise Exception(f"Arquivo de vídeo não encontrado no caminho: {video_path}")
        
    # 1. Carregar/Renovar Token Oficial
    access_token = load_and_refresh_token()
    
    # 2. Mapear privacidade para as constantes oficiais da API
    priv_lower = privacy_level.lower() if privacy_level else "public"
    if priv_lower in ["private", "self_only", "only_me"]:
        privacy_level_mapped = "SELF_ONLY"
    elif priv_lower in ["friends", "mutual_follow_friends"]:
        privacy_level_mapped = "MUTUAL_FOLLOW_FRIENDS"
    else:
        privacy_level_mapped = "PUBLIC_TO_EVERYONE"
        
    video_size = os.path.getsize(video_path)
    
    # 3. Calcular tamanho dos chunks (máximo de 64MB por chunk)
    # A API do TikTok exige que o chunk_size seja múltiplo de 1024*1024 (1MB),
    # e que total_chunk_count seja igual a video_size // chunk_size.
    # O último chunk (restante) pode ser maior que chunk_size, mas não pode passar de 128MB.
    actual_chunk_size = None
    total_chunk_count = None
    
    if video_size <= 64 * 1024 * 1024:
        actual_chunk_size = video_size
        total_chunk_count = 1
    else:
        # Tenta tamanhos de chunk decrescentes de 64MB até 5MB
        for c_mb in range(64, 4, -1):
            c_bytes = c_mb * 1024 * 1024
            count = video_size // c_bytes
            if count == 0:
                continue
            
            # Tamanho do último chunk (contendo o resto)
            last_chunk_size = video_size - (count - 1) * c_bytes
            
            # Se for apenas 1 chunk, o tamanho não pode passar de 64MB
            if count == 1 and last_chunk_size <= 64 * 1024 * 1024:
                actual_chunk_size = c_bytes
                total_chunk_count = count
                break
            # Se forem múltiplos chunks, o último não pode passar de 128MB
            elif count > 1 and last_chunk_size <= 128 * 1024 * 1024:
                actual_chunk_size = c_bytes
                total_chunk_count = count
                break
                
        if not actual_chunk_size:
            # Fallback seguro caso a busca falhe
            actual_chunk_size = 50 * 1024 * 1024
            total_chunk_count = video_size // actual_chunk_size
            if total_chunk_count < 1:
                total_chunk_count = 1
            
    print(f"[TIKTOK-OFFICIAL] Inicializando postagem oficial. Vídeo: {video_size} bytes, Privacidade: {privacy_level_mapped}, Chunk Size: {actual_chunk_size}, Chunk Count: {total_chunk_count}", flush=True)
    if progress_callback:
        try: progress_callback(5)
        except Exception: pass
        
    # 4. Inicializar upload no TikTok
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8"
    }
    
    # Limite real da API do TikTok: ~2000 chars. O caption já vem curto (hook + 5 hashtags),
    # mas adicionamos um fallback de segurança.
    safe_title = title or "Post Recap Video"
    if len(safe_title) > 2000:
        safe_title = safe_title[:1997] + "..."
        
    post_info = {
        "title": safe_title,
        "privacy_level": privacy_level_mapped,
        "disable_duet": disable_duet,
        "disable_stitch": disable_stitch,
        "disable_comment": disable_comment
    }
    if brand_content_toggle:
        post_info["brand_content_toggle"] = True
    if brand_organic_toggle:
        post_info["brand_organic_toggle"] = True
    if is_aigc:
        post_info["is_aigc"] = True

    payload = {
        "post_info": post_info,
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": actual_chunk_size,
            "total_chunk_count": total_chunk_count
        }
    }
    print(f"[TIKTOK-OFFICIAL] Payload de Envio:\n{json.dumps(payload, indent=2)}", flush=True)
    init_res = requests.post(init_url, headers=headers, json=payload)
    print(f"[TIKTOK-OFFICIAL] Resposta Inicialização: Status {init_res.status_code}, Body: {init_res.text[:300]}", flush=True)
    
    if init_res.status_code != 200:
        raise Exception(f"Erro ao inicializar post no TikTok API: {init_res.text}")
        
    init_json = init_res.json()
    if init_json.get("error", {}).get("code") != "ok":
        err_msg = init_json.get("error", {}).get("message", "Erro desconhecido")
        raise Exception(f"Erro da API do TikTok: {err_msg} (Código: {init_json.get('error', {}).get('code')})")
        
    upload_url = init_json.get("data", {}).get("upload_url")
    publish_id = init_json.get("data", {}).get("publish_id")
    
    if not upload_url:
        raise Exception("A API do TikTok não retornou a URL de upload para envio dos chunks.")
        
    if progress_callback:
        try: progress_callback(15)
        except Exception: pass
        
    # 5. Ler o vídeo e realizar upload dos chunks via PUT
    with open(video_path, "rb") as f:
        contents = f.read()
        
    for chunk_index in range(total_chunk_count):
        start_byte = chunk_index * actual_chunk_size
        remaining = video_size - start_byte
        
        if chunk_index == total_chunk_count - 1:
            this_chunk_size = remaining
        else:
            this_chunk_size = actual_chunk_size
            
        end_byte = start_byte + this_chunk_size - 1
        chunk_data = contents[start_byte : start_byte + this_chunk_size]
        
        # O Content-Type DEVE ser 'video/mp4' para evitar erros de validação do TikTok
        put_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Range": f"bytes {start_byte}-{end_byte}/{video_size}",
            "Content-Type": "video/mp4"
        }
        
        print(f"[TIKTOK-OFFICIAL] Enviando chunk {chunk_index + 1}/{total_chunk_count} ({this_chunk_size} bytes)...", flush=True)
        
        put_res = requests.put(upload_url, data=chunk_data, headers=put_headers)
        print(f"[TIKTOK-OFFICIAL] Resposta chunk {chunk_index + 1}: Status {put_res.status_code}", flush=True)
        
        if put_res.status_code not in [200, 201, 204, 206]:
            if put_res.status_code == 403 and "50001" in put_res.text and "missing or invalid request id" in put_res.text:
                print(f"[TIKTOK-OFFICIAL WARNING] Erro 50001 no chunk {chunk_index + 1}. Prosseguindo mesmo assim.", flush=True)
            else:
                raise Exception(f"Erro no envio da parte {chunk_index + 1}: {put_res.text}")
                
        # Atualiza a porcentagem de progresso
        percent = 15 + int(((chunk_index + 1) / total_chunk_count) * 80)
        if progress_callback:
            try: progress_callback(min(percent, 99))
            except Exception: pass
            
    print(f"[TIKTOK-OFFICIAL] Upload concluído com sucesso! ID de publicação: {publish_id}", flush=True)
    if progress_callback:
        try: progress_callback(100)
        except Exception: pass
        
    return publish_id
