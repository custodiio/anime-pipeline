"""
Webhook Server — Recebe notificações dos notebooks Kaggle
+ API de sessão para o VideoRender (salvar config no Drive).
"""

import os
import json
import logging
from http.server import HTTPServerRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import threading
from dotenv import load_dotenv

load_dotenv()

from bot.database import update_step, cell_start_db, cell_end_db
from bot.pipeline_controller import PipelineController

logger = logging.getLogger(__name__)

controller = PipelineController()

# Referência para sessões ativas (importado do telegram_bot em runtime)
_session_validator = None

def set_session_validator(validator_func):
    """Recebe a função validar_sessao do telegram_bot."""
    global _session_validator
    _session_validator = validator_func


class PipelineWebhookHandler(HTTPServerRequestHandler):
    """Handler HTTP para webhooks e API de sessão."""

    def _set_headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_OPTIONS(self):
        """CORS preflight."""
        self._set_headers(204)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        """Endpoints GET."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode())

        elif path == "/api/session/validate":
            # GET /api/session/validate?token=xxx
            params = parse_qs(parsed.query)
            token = params.get("token", [""])[0]

            if not _session_validator:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": "Session system not initialized"}).encode())
                return

            session = _session_validator(token)
            if session:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "valid": True,
                    "project_id": session["project_id"],
                }).encode())
            else:
                self._set_headers(401)
                self.wfile.write(json.dumps({"valid": False, "error": "Sessão inválida ou expirada"}).encode())

        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())

    def do_POST(self):
        """Endpoints POST."""
        path = urlparse(self.path).path

        try:
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
                cell_start_db(data.get("project_id"), data.get("notebook"),
                              data.get("cell_index"), data.get("cell_name", ""))
                self._set_headers(200)
                self.wfile.write(json.dumps({"ok": True}).encode())

            elif path == "/webhook/cell-end":
                cell_end_db(data.get("project_id"), data.get("notebook"),
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
                    dm = DriveManager()

                    # Salvar videorender-project.json
                    if config:
                        config_path = "/tmp/videorender-project.json"
                        with open(config_path, "w", encoding="utf-8") as f:
                            json.dump(config, f, ensure_ascii=False)
                        dm.upload("KAGGLE/PIPELINE/OMNI/videorender-project.json", config_path)
                        logger.info("Config salva no Drive")

                    # Salvar legendas.ass
                    if ass_content:
                        ass_path = "/tmp/legendas.ass"
                        with open(ass_path, "w", encoding="utf-8") as f:
                            f.write(ass_content)
                        dm.upload("KAGGLE/PIPELINE/OMNI/legendas.ass", ass_path)
                        logger.info("ASS salvo no Drive")

                    # Marcar config como pronta no banco
                    update_step(session["project_id"], "step_config_ready", "done", "Config salva pelo VideoRender")

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
