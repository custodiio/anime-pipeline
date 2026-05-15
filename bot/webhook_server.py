"""
Webhook Server — Recebe notificações dos notebooks Kaggle
+ API de sessão para o VideoRender (salvar config no Drive).
"""

import os
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import threading
from dotenv import load_dotenv

load_dotenv()

from bot.database import update_step, cell_start, cell_end
from bot.pipeline_controller import PipelineController

logger = logging.getLogger(__name__)

controller = PipelineController()

# Referência para sessões ativas (importado do telegram_bot em runtime)
_session_validator = None

def set_session_validator(validator_func):
    """Recebe a função validar_sessao do telegram_bot."""
    global _session_validator
    _session_validator = validator_func


class PipelineWebhookHandler(BaseHTTPRequestHandler):
    """Handler HTTP para webhooks e API de sessão."""

    def _set_headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Range")
        self.end_headers()

    def do_OPTIONS(self):
        """CORS preflight."""
        self._set_headers(204)

    def do_HEAD(self):
        """Responde HEAD reutilizando do_GET (BaseHTTPRequestHandler não gera automaticamente)."""
        self.do_GET()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        """Endpoints GET."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/api/video":
            name = params.get("name", ["video.mp4"])[0]
            uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
            video_file = os.path.join(uploads_dir, name)
            
            if not os.path.exists(video_file):
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Video not found"}).encode())
                return

            file_size = os.path.getsize(video_file)
            range_header = self.headers.get("Range")
            
            if range_header:
                byte_range = range_header.replace("bytes=", "").split("-")
                start = int(byte_range[0])
                end = int(byte_range[1]) if byte_range[1] else file_size - 1
                content_length = end - start + 1
                
                self.send_response(206)  # Partial Content
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Range")
                self.end_headers()
                
                try:
                    with open(video_file, "rb") as f:
                        f.seek(start)
                        remaining = content_length
                        while remaining > 0:
                            chunk_size = min(65536, remaining)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass  # Browser cancelou a conexão (normal)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Range")
                self.end_headers()
                
                try:
                    with open(video_file, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass  # Browser cancelou a conexão (normal)

        elif path == "/upload":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <!DOCTYPE html>
            <html>
            <head><title>Upload Local AnimeRecap</title>
            <style>
                body { font-family: sans-serif; padding: 40px; background: #121212; color: #fff; }
                .container { max-width: 600px; margin: auto; background: #1e1e1e; padding: 30px; border-radius: 10px; }
                h2 { color: #bb86fc; }
                .drop-zone { border: 2px dashed #bb86fc; padding: 40px; text-align: center; border-radius: 10px; margin-bottom: 20px; cursor: pointer; }
                .progress { height: 20px; background: #333; border-radius: 10px; overflow: hidden; display: none; margin-top: 10px; }
                .progress-bar { height: 100%; background: #03dac6; width: 0%; transition: width 0.2s; }
            </style>
            </head>
            <body>
            <div class="container">
                <h2>Upload Local (Ignora limite de 20MB)</h2>
                <p>Arraste seu arquivo de vídeo e áudio gigante aqui. O upload é instantâneo pois é no seu próprio PC.</p>
                <div class="drop-zone" id="drop-video">Soltar VÍDEO (.mp4, .mkv)</div>
                <div class="progress" id="prog-video"><div class="progress-bar" id="bar-video"></div></div>
                <div class="drop-zone" id="drop-audio" style="border-color: #03dac6;">Soltar ÁUDIO (.mp3, .wav)</div>
                <div class="progress" id="prog-audio"><div class="progress-bar" id="bar-audio"></div></div>
                <div id="status" style="margin-top:20px; color: #03dac6;"></div>
                <p style="margin-top:20px; font-size:14px; color:#aaa;">Após fazer o upload dos dois, vá no Telegram e digite <b>/usar_local Nome do Anime</b></p>
            </div>
            <script>
                function setupDrop(id, type) {
                    const zone = document.getElementById('drop-' + id);
                    const bar = document.getElementById('bar-' + id);
                    const prog = document.getElementById('prog-' + id);
                    zone.ondragover = e => { e.preventDefault(); zone.style.background = '#333'; };
                    zone.ondragleave = e => { e.preventDefault(); zone.style.background = 'transparent'; };
                    zone.ondrop = e => {
                        e.preventDefault();
                        zone.style.background = 'transparent';
                        const file = e.dataTransfer.files[0];
                        if(!file) return;
                        zone.innerText = "Fazendo upload de: " + file.name;
                        prog.style.display = 'block';
                        
                        const xhr = new XMLHttpRequest();
                        xhr.open('POST', '/api/upload-file?type=' + type + '&name=' + encodeURIComponent(file.name));
                        xhr.upload.onprogress = ev => {
                            if(ev.lengthComputable) {
                                bar.style.width = (ev.loaded / ev.total * 100) + '%';
                            }
                        };
                        xhr.onload = () => {
                            if(xhr.status === 200) {
                                document.getElementById('status').innerText += "✅ " + file.name + " salvo no PC!\\n";
                                zone.style.borderColor = '#4CAF50';
                            }
                        };
                        xhr.send(file);
                    };
                }
                setupDrop('video', 'video');
                setupDrop('audio', 'audio');
            </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))

        elif path == "/api/session/validate":
            token = params.get("token", [""])[0]
            if not token or not _session_validator:
                self._set_headers(200)
                self.wfile.write(json.dumps({"valid": False}).encode())
                return

            session = _session_validator(token)
            if session:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "valid": True,
                    "project_id": session["project_id"]
                }).encode())
            else:
                self._set_headers(200)
                self.wfile.write(json.dumps({"valid": False}).encode())

        elif path == "/api/session/video":
            token = params.get("token", [""])[0]
            if not token or not _session_validator:
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
                return

            session = _session_validator(token)
            if not session:
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "Invalid session"}).encode())
                return

            # Buscar vídeo do projeto na pasta uploads
            uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
            video_file = None
            if os.path.exists(uploads_dir):
                for f in os.listdir(uploads_dir):
                    if any(f.lower().endswith(ext) for ext in [".mp4", ".mkv", ".avi", ".mov", ".webm"]):
                        video_file = os.path.join(uploads_dir, f)
                        break

            if not video_file or not os.path.exists(video_file):
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Video not found"}).encode())
                return

            file_size = os.path.getsize(video_file)
            range_header = self.headers.get("Range")

            if range_header:
                byte_range = range_header.replace("bytes=", "").split("-")
                start = int(byte_range[0])
                end = int(byte_range[1]) if byte_range[1] else file_size - 1
                content_length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(content_length))
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Range")
                self.end_headers()

                try:
                    with open(video_file, "rb") as f:
                        f.seek(start)
                        remaining = content_length
                        while remaining > 0:
                            chunk_size = min(65536, remaining)
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
            else:
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Range")
                self.end_headers()

                try:
                    with open(video_file, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def do_POST(self):
        """Endpoints POST."""
        path = urlparse(self.path).path

        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/upload-file":
                params = parse_qs(parsed.query)
                file_type = params.get("type", [""])[0]
                file_name = params.get("name", ["arquivo"])[0]
                
                uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
                os.makedirs(uploads_dir, exist_ok=True)
                
                # Deleta arquivos do mesmo tipo antes de salvar o novo
                video_exts = [".mp4", ".mkv", ".avi", ".mov", ".webm"]
                audio_exts = [".mp3", ".wav", ".m4a", ".ogg", ".aac"]
                
                for existing in os.listdir(uploads_dir):
                    existing_path = os.path.join(uploads_dir, existing)
                    if os.path.isfile(existing_path):
                        if file_type == "video" and any(existing.lower().endswith(e) for e in video_exts):
                            try:
                                os.remove(existing_path)
                                logger.info(f"Vídeo antigo deletado localmente: {existing}")
                            except: pass
                        elif file_type == "audio" and any(existing.lower().endswith(e) for e in audio_exts):
                            try:
                                os.remove(existing_path)
                                logger.info(f"Áudio antigo deletado localmente: {existing}")
                            except: pass
                
                length = int(self.headers.get("Content-Length", 0))
                file_path = os.path.join(uploads_dir, file_name)
                
                with open(file_path, "wb") as f:
                    bytes_read = 0
                    while bytes_read < length:
                        chunk = self.rfile.read(min(8192*8, length - bytes_read))
                        if not chunk: break
                        f.write(chunk)
                        bytes_read += len(chunk)
                        
                self._set_headers(200)
                self.wfile.write(json.dumps({"ok": True, "path": file_path}).encode())
                return

            # Note: _read_body reads everything into JSON, so we do it AFTER /upload-file
            data = self._read_body()

            # ── Webhook: Status macro do notebook ──
            if path == "/webhook/status":
                pid = data.get("project_id")
                step = data.get("step")
                status = data.get("status")
                msg = data.get("message", "")

                if pid and step and status:
                    update_step(pid, step, status, msg)
                    controller.verificar_e_avancar(pid)
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"ok": True}).encode())
                else:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Missing fields"}).encode())

            # ── Webhook: Cell tracking ──
            elif path == "/webhook/cell-start":
                cell_start(data.get("project_id"), data.get("notebook"),
                              data.get("cell_index"), data.get("cell_name", ""))
                self._set_headers(200)
                self.wfile.write(json.dumps({"ok": True}).encode())

            elif path == "/webhook/cell-end":
                cell_end(data.get("project_id"), data.get("notebook"),
                            data.get("cell_index"), data.get("status", "done"),
                            data.get("message", ""))
                self._set_headers(200)
                self.wfile.write(json.dumps({"ok": True}).encode())

            # ── API: Salvar config do VideoRender no Drive ──
            elif path == "/api/session/save-config":
                token = data.get("token")
                config = data.get("config")  # JSON do videorender-project
                ass_content = data.get("ass")  # Conteúdo do .ass

                if not _session_validator:
                    self._set_headers(500)
                    self.wfile.write(json.dumps({"error": "Session system not initialized"}).encode())
                    return

                session = _session_validator(token)
                if not session:
                    self._set_headers(401)
                    self.wfile.write(json.dumps({"error": "Sessão inválida"}).encode())
                    return

                # Salvar config no Drive
                try:
                    from bot.drive_manager import DriveManager
                    import tempfile
                    dm = DriveManager()

                    # Salvar videorender-project.json
                    if config:
                        config_path = os.path.join(tempfile.gettempdir(), "videorender-project.json")
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False)
                        dm.salvar(config_path, "KAGGLE/PIPELINE/OMNI/videorender-project.json")
                        logger.info("Config salva no Drive")

                    # Salvar legendas.ass
                    if ass_content:
                        ass_path = os.path.join(tempfile.gettempdir(), "legendas.ass")
                        with open(ass_path, "w", encoding="utf-8") as f:
                            f.write(ass_content)
                        dm.salvar(ass_path, "KAGGLE/PIPELINE/OMNI/legendas.ass")
                        logger.info("ASS salvo no Drive")
                        
                    # Salvar máscara (se enviada pelo VideoRender)
                    mask_data = data.get("mask") or data.get("mask_data")
                    if mask_data:
                        import base64
                        # Remover cabeçalho data:image/png;base64, se houver
                        if "," in mask_data:
                            mask_data = mask_data.split(",")[1]
                        
                        mask_path = os.path.join(tempfile.gettempdir(), "mask.png")
                        with open(mask_path, "wb") as f:
                            f.write(base64.b64decode(mask_data))
                        dm.salvar(mask_path, "KAGGLE/PIPELINE/ATIVO/mask.png")
                        logger.info("Máscara salva no Drive/ATIVO")

                    # Marcar config como pronta no banco
                    update_step(session["project_id"], "step_config_ready", "done", "Config salva pelo VideoRender")

                    # Verificar se o pipeline pode avançar (ex: disparar watermark/enhancer ou render)
                    try:
                        from bot.pipeline_controller import PipelineController
                        ctrl = PipelineController()
                        ctrl.verificar_e_avancar(session["project_id"])
                    except Exception as ev:
                        logger.error(f"Erro ao verificar avanço: {ev}")

                    self._set_headers(200)
                    self.wfile.write(json.dumps({"ok": True, "message": "Config salva no Drive!"}).encode())

                except Exception as e:
                    logger.error(f"Erro ao salvar config: {e}")
                    self._set_headers(500)
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode())

        except Exception as e:
            logger.error(f"Webhook error: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        logger.info(f"[Webhook] {args[0]}")


def start_webhook_server(port=None):
    """Inicia o servidor webhook em background."""
    port = port or int(os.getenv("WEBHOOK_PORT", "8080"))

    server = HTTPServer(("0.0.0.0", port), PipelineWebhookHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Webhook server rodando na porta {port}")
    return server


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("WEBHOOK_PORT", "8080"))
    print(f"Iniciando webhook server na porta {port}...")
    server = HTTPServer(("0.0.0.0", port), PipelineWebhookHandler)
    server.serve_forever()
