import os
import io
import google.auth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

load_dotenv()

class DriveManager:
    def __init__(self):
        self.refresh_token = os.getenv("DRIVE_REFRESH_TOKEN")
        self.client_id = os.getenv("DRIVE_CLIENT_ID")
        self.client_secret = os.getenv("DRIVE_CLIENT_SECRET")
        self.folder_id = os.getenv("DRIVE_FOLDER_ID")
        self.service = None
        self.authenticate()

    def authenticate(self):
        try:
            if not self.refresh_token or not self.client_id or not self.client_secret:
                print("[AVISO] Credenciais do Drive ausentes no .env", flush=True)
                return
            
            # Autenticação via token de atualização OAuth2 (OAuth Playground redirect_uri)
            creds = Credentials(
                token=None,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
                token_uri="https://oauth2.googleapis.com/token"
            )
            
            self.service = build("drive", "v3", credentials=creds)
            print("[OK] Google Drive autenticado com sucesso!", flush=True)
        except Exception as e:
            print(f"[ERRO] Erro na autenticação do Drive: {e}", flush=True)
            self.service = None

    def find_id_by_path(self, drive_path):
        """
        Busca o ID do arquivo ou diretório a partir do caminho (ex: "KAGGLE/PIPELINE/FINAL/guia_postagem.json")
        """
        if not self.service:
            raise Exception("Serviço do Google Drive não inicializado.")
            
        parts = [p for p in drive_path.replace("\\", "/").strip("/").split("/") if p]
        parent_id = "root"

        for part in parts:
            # Escape de aspas simples
            escaped_part = part.replace("'", "\\'")
            query = f"name = '{escaped_part}' and '{parent_id}' in parents and trashed = false"
            results = self.service.files().list(
                q=query,
                fields="files(id, mimeType)",
                spaces="drive",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            
            files = results.get("files", [])
            if not files:
                return None
            parent_id = files[0]["id"]
            
        return parent_id

    def list_files_in_folder(self, folder_id):
        """
        Lista os arquivos de uma pasta específica por ID
        """
        if not self.service:
            raise Exception("Serviço do Google Drive não inicializado.")
            
        query = f"'{folder_id}' in parents and trashed = false"
        results = self.service.files().list(
            q=query,
            fields="files(id, name, mimeType)",
            spaces="drive",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        return results.get("files", [])

    def download_file_by_id(self, file_id, local_dest, progress_callback=None):
        """
        Faz o download de um arquivo pelo ID e salva no destino local. Suporta progress_callback.
        """
        if not self.service:
            raise Exception("Serviço do Google Drive não inicializado.")
            
        request = self.service.files().get_media(fileId=file_id)
        
        # Cria a pasta de destino se não existir
        os.makedirs(os.path.dirname(os.path.abspath(local_dest)), exist_ok=True)
        
        filename = os.path.basename(local_dest)
        print(f"[DRIVE] Iniciando download do arquivo: {filename}", flush=True)
        
        with io.FileIO(local_dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            last_percent = -1
            while not done:
                status, done = downloader.next_chunk()
                percent = int(status.progress() * 100)
                if percent != last_percent:
                    print(f"[DRIVE] Progresso de download '{filename}': {percent}%", flush=True)
                    if progress_callback:
                        try:
                            progress_callback(percent)
                        except Exception as cb_err:
                            print(f"[AVISO] Erro no callback de progresso: {cb_err}", flush=True)
                    last_percent = percent
                
        print(f"[DRIVE] Download concluído: {filename}", flush=True)
        return local_dest

    def download_file_by_path(self, drive_path, local_dest, progress_callback=None):
        file_id = self.find_id_by_path(drive_path)
        if not file_id:
            raise Exception(f"Arquivo não encontrado no Drive: {drive_path}")
        return self.download_file_by_id(file_id, local_dest, progress_callback=progress_callback)

    def download_pipeline_files(self):
        """
        Baixa todos os arquivos necessários da pasta KAGGLE/PIPELINE/FINAL
        Se encontrar os arquivos pelo ID da pasta padrão, usa eles;
        senão, pesquisa pelo caminho 'KAGGLE/PIPELINE/FINAL'.
        """
        local_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        os.makedirs(local_dir, exist_ok=True)
        
        files_to_download = {
            "guia_postagem.json": None,
            "video_final.mp4": None,
            "thumbnail_youtube.png": None,
            "thumbnail_tiktok.png": None
        }
        
        # 1. Tentar listar os arquivos usando o ID da pasta do .env
        folder_id = self.folder_id
        if not folder_id:
            print("Buscando a pasta 'KAGGLE/PIPELINE/FINAL' pelo caminho...")
            folder_id = self.find_id_by_path("KAGGLE/PIPELINE/FINAL")
            
        if not folder_id:
            # Tentar buscar apenas "PIPELINE/FINAL" caso o KAGGLE não seja a raiz
            folder_id = self.find_id_by_path("PIPELINE/FINAL")
            
        if not folder_id:
            raise Exception("Não foi possível encontrar a pasta de pipeline de destino no Google Drive.")
            
        drive_files = self.list_files_in_folder(folder_id)
        for df in drive_files:
            name = df["name"]
            if name in files_to_download:
                files_to_download[name] = df["id"]
                
        # Verificar se encontramos tudo ou tentar caminhos diretos
        downloaded_paths = {}
        for name, file_id in files_to_download.items():
            local_path = os.path.join(local_dir, name)
            if file_id:
                print(f"Baixando {name} do Drive usando ID...")
                self.download_file_by_id(file_id, local_path)
                downloaded_paths[name] = local_path
            else:
                # Tenta baixar pelo caminho alternativo
                try:
                    alt_path = f"KAGGLE/PIPELINE/FINAL/{name}"
                    print(f"Buscando {name} via caminho alternativo {alt_path}...")
                    self.download_file_by_path(alt_path, local_path)
                    downloaded_paths[name] = local_path
                except Exception as e:
                    print(f"[ALERTA] Não foi possível baixar {name}: {e}")
                    
        return downloaded_paths

# Singleton para importação fácil
drive_manager = DriveManager()
