import os
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

class DriveUploader:
    """Gerenciador simplificado do Google Drive para upload dos arquivos do pipeline com progresso."""
    
    def __init__(self, refresh_token=None, client_id=None, client_secret=None):
        self.refresh_token = refresh_token or os.getenv("DRIVE_REFRESH_TOKEN", "")
        self.client_id = client_id or os.getenv("DRIVE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("DRIVE_CLIENT_SECRET", "")
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Autentica com o Google Drive via OAuth2."""
        if not self.refresh_token or not self.client_id or not self.client_secret:
            logger.error("Credenciais do Google Drive ausentes no arquivo .env!")
            return False
            
        try:
            creds = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=["https://www.googleapis.com/auth/drive"]
            )
            creds.refresh(Request())
            self.service = build("drive", "v3", credentials=creds)
            logger.info("Autenticação com Google Drive bem-sucedida!")
            return True
        except Exception as e:
            self.service = None
            logger.error(f"Falha na autenticação do Google Drive: {e}")
            return False

    def _escape_single_quotes(self, name):
        """Escapa aspas simples em nomes de arquivos/pastas para consultas do Drive API."""
        return name.replace("'", "\\'")

    def _resolve_folder_id(self, path_in_drive):
        """
        Resolve o caminho de pastas (ex: 'KAGGLE/AUDIO_DUB/INPUT') para o ID do Google Drive,
        criando as pastas que não existirem no caminho.
        """
        if not self.service:
            logger.error("Serviço do Google Drive não inicializado.")
            return None
            
        parts = path_in_drive.strip("/").split("/")
        parent_id = "root"
        
        for part in parts:
            query = (
                f"name='{self._escape_single_quotes(part)}' "
                f"and '{parent_id}' in parents "
                f"and trashed=false "
                f"and mimeType='application/vnd.google-apps.folder'"
            )
            try:
                results = self.service.files().list(q=query, fields="files(id)").execute()
                files = results.get("files", [])
                
                if files:
                    parent_id = files[0]["id"]
                else:
                    # Cria a pasta caso não exista
                    body = {
                        "name": part,
                        "mimeType": "application/vnd.google-apps.folder",
                        "parents": [parent_id]
                    }
                    folder = self.service.files().create(body=body, fields="id").execute()
                    parent_id = folder["id"]
                    logger.info(f"Pasta criada no Drive: {part} (ID: {parent_id})")
            except Exception as e:
                logger.error(f"Erro ao buscar/criar pasta '{part}': {e}")
                return None
                
        return parent_id

    def upload_file(self, local_path, drive_dest_path, progress_callback=None):
        """
        Faz upload de um arquivo local para o destino no Drive (ex: 'KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3').
        Se o arquivo já existir, ele será atualizado. Evita arquivos duplicados históricos.
        Acompanha o progresso do upload através de chunks e atualiza o callback.
        """
        if not self.service:
            logger.error("Serviço do Google Drive indisponível para upload.")
            return False
            
        if not os.path.exists(local_path):
            logger.error(f"Arquivo local não encontrado para upload: {local_path}")
            return False
            
        try:
            parts = drive_dest_path.strip("/").split("/")
            filename = parts[-1]
            folder_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
            
            # Resolve o ID da pasta pai
            parent_id = self._resolve_folder_id(folder_path) if folder_path else "root"
            if not parent_id:
                logger.error(f"Não foi possível obter o ID da pasta pai para: {folder_path}")
                return False
                
            # Verifica se o arquivo com o mesmo nome já existe na pasta
            query = f"name='{self._escape_single_quotes(filename)}' and '{parent_id}' in parents and trashed=false"
            results = self.service.files().list(q=query, fields="files(id)", orderBy="modifiedTime desc").execute()
            existing_files = results.get("files", [])
            
            media = MediaFileUpload(local_path, chunksize=256*1024, resumable=True)
            
            from datetime import datetime, timezone
            now_rfc3339 = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            if existing_files:
                # Atualiza o arquivo mais recente e força a gravação do modifiedTime correto
                file_id = existing_files[0]["id"]
                logger.info(f"Atualizando arquivo existente no Drive: {drive_dest_path} (ID: {file_id})")
                body = {
                    "modifiedTime": now_rfc3339
                }
                request = self.service.files().update(fileId=file_id, body=body, media_body=media)
                
                # Deleta duplicados históricos adicionais
                for duplicate in existing_files[1:]:
                    try:
                        self.service.files().delete(fileId=duplicate["id"]).execute()
                        logger.info(f"Removido arquivo duplicado antigo: {filename} (ID: {duplicate['id']})")
                    except Exception as ed:
                        logger.warning(f"Erro ao remover arquivo duplicado antigo: {ed}")
            else:
                # Cria um novo arquivo com o modifiedTime atualizado
                body = {
                    "name": filename,
                    "parents": [parent_id],
                    "modifiedTime": now_rfc3339
                }
                request = self.service.files().create(body=body, media_body=media, fields="id")
            
            # Loop de upload com progresso
            response = None
            last_percent = 0
            while response is None:
                status, response = request.next_chunk()
                if status:
                    percent = int(status.progress() * 100)
                    if percent != last_percent:
                        last_percent = percent
                        if progress_callback:
                            try:
                                progress_callback(percent)
                            except Exception as pe:
                                logger.warning(f"Erro no callback de progresso do Drive: {pe}")
            
            # Se for criação de novo arquivo, loga o ID gerado
            if response and not existing_files:
                logger.info(f"Novo arquivo criado no Drive: {drive_dest_path} (ID: {response.get('id')})")
                
            return True
        except Exception as e:
            logger.error(f"Erro durante o upload do arquivo para o Drive: {e}")
            return False

def upload_pipeline_media(local_video_path: str, local_audio_path: str, progress_callback=None) -> bool:
    """
    Realiza o upload do vídeo e áudio processados para as pastas corretas no Google Drive:
    - Áudio -> KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3
    - Vídeo -> KAGGLE/PIPELINE/ATIVO/video_original.mp4
    Se progress_callback for passado, chama-o passando o nome da etapa e o progresso.
    """
    uploader = DriveUploader()
    if not uploader.service:
        logger.error("Falha ao inicializar o uploader do Drive.")
        return False
        
    logger.info("Iniciando uploads para o Google Drive...")
    
    # 1. Upload do Áudio
    audio_dest = "KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3"
    
    def audio_progress(p):
        if progress_callback:
            progress_callback("Áudio 🎵", p)
            
    audio_success = uploader.upload_file(local_audio_path, audio_dest, progress_callback=audio_progress)
    if not audio_success:
        logger.error("Falha no upload do áudio para o Google Drive.")
        return False
        
    # 2. Upload do Vídeo
    video_dest = "KAGGLE/PIPELINE/ATIVO/video_original.mp4"
    
    def video_progress(p):
        if progress_callback:
            progress_callback("Vídeo 🎥", p)
            
    video_success = uploader.upload_file(local_video_path, video_dest, progress_callback=video_progress)
    if not video_success:
        logger.error("Falha no upload do vídeo para o Google Drive.")
        return False
        
    # 3. Sincroniza localmente com a pasta de uploads do AnimeRecap para o fluxo de postagem subsequente (se disponível)
    recap_uploads_dir = os.getenv("ANIME_RECAP_UPLOADS_DIR")
    if not recap_uploads_dir:
        # Fallback dinâmico: tenta detectar se o projeto do AnimeRecap está como pasta irmã
        try:
            parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            possible_dir = os.path.join(parent_dir, "AnimeRecap", "uploads")
            if os.path.exists(os.path.join(parent_dir, "AnimeRecap")):
                recap_uploads_dir = possible_dir
        except Exception:
            pass

    if recap_uploads_dir:
        try:
            import shutil
            logger.info(f"Sincronizando arquivos locais com {recap_uploads_dir}...")
            if not os.path.exists(recap_uploads_dir):
                os.makedirs(recap_uploads_dir, exist_ok=True)
            else:
                # Remove arquivos antigos (.mp4, .mp3, etc) para evitar conflitos de seleção no bot do AnimeRecap
                for f in os.listdir(recap_uploads_dir):
                    file_path = os.path.join(recap_uploads_dir, f)
                    if os.path.isfile(file_path):
                        try:
                            os.remove(file_path)
                            logger.info(f"Removido arquivo antigo em uploads do AnimeRecap: {file_path}")
                        except Exception as e_rm:
                            logger.warning(f"Erro ao remover arquivo antigo {file_path}: {e_rm}")
            
            # Copia o vídeo e o áudio processados
            dest_video = os.path.join(recap_uploads_dir, "video_original.mp4")
            dest_audio = os.path.join(recap_uploads_dir, "anime_audio.mp3")
            
            shutil.copy(local_video_path, dest_video)
            shutil.copy(local_audio_path, dest_audio)
            logger.info(f"Arquivos copiados com sucesso para {recap_uploads_dir}!")
        except Exception as e_copy:
            logger.warning(f"Aviso: Não foi possível copiar os arquivos para a pasta de uploads do AnimeRecap: {e_copy}")
    else:
        logger.info("Cópia local pulada: Pasta de uploads do AnimeRecap não configurada ou não encontrada localmente.")

    logger.info("Uploads para o Google Drive concluídos com sucesso!")
    return True
