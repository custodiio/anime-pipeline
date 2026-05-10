"""
Webhook Server — Recebe notificações dos notebooks Kaggle
Endpoints:
  POST /webhook/status     — Atualização de step macro
  POST /webhook/cell-start — Início de célula de notebook
  POST /webhook/cell-end   — Fim de célula de notebook
  POST /webhook/config-ready — Config do VideoRender pronta
  GET  /health             — Health check
"""

import os
from aiohttp import web
from dotenv import load_dotenv

from bot.database import update_step, get_project, cell_start, cell_end
from bot.pipeline_controller import PipelineController

load_dotenv()

controller = PipelineController()

# Telegram bot instance (setado externamente pelo main.py)
telegram_bot = None


async def handle_status_update(request: web.Request) -> web.Response:
    """
    POST /webhook/status
    Body: {"project_id", "step", "status", "message"}
    """
    try:
        data = await request.json()
        project_id = data.get("project_id")
        step = data.get("step")
        status = data.get("status")
        message = data.get("message", "")

        if not all([project_id, step, status]):
            return web.json_response(
                {"error": "Campos obrigatórios: project_id, step, status"}, status=400
            )

        update_step(project_id, step, status, message)
        print(f"📩 Webhook: {step} → {status}")

        # Verificar avanço automático
        controller.verificar_e_avancar(project_id)

        # Notificar Telegram
        await _notify_telegram(project_id, step, status, message)

        return web.json_response({"ok": True})
    except Exception as e:
        print(f"❌ Erro: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_cell_start(request: web.Request) -> web.Response:
    """
    POST /webhook/cell-start
    Body: {"project_id", "notebook", "cell_index", "cell_name"}
    """
    try:
        data = await request.json()
        project_id = data.get("project_id")
        notebook = data.get("notebook")
        cell_index = data.get("cell_index")
        cell_name = data.get("cell_name", "")

        if not all([project_id, notebook, cell_index is not None]):
            return web.json_response({"error": "Campos obrigatórios"}, status=400)

        cell_start(project_id, notebook, cell_index, cell_name)
        print(f"📩 Cell: {notebook}[{cell_index}] ▶️ {cell_name}")

        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_cell_end(request: web.Request) -> web.Response:
    """
    POST /webhook/cell-end
    Body: {"project_id", "notebook", "cell_index", "status", "message"}
    """
    try:
        data = await request.json()
        project_id = data.get("project_id")
        notebook = data.get("notebook")
        cell_index = data.get("cell_index")
        status = data.get("status", "done")
        message = data.get("message", "")

        if not all([project_id, notebook, cell_index is not None]):
            return web.json_response({"error": "Campos obrigatórios"}, status=400)

        cell_end(project_id, notebook, cell_index, status, message)
        print(f"📩 Cell: {notebook}[{cell_index}] {'✅' if status == 'done' else '❌'} {message}")

        # Se erro na célula, notificar Telegram
        if status == "error":
            await _notify_telegram(
                project_id, 
                f"{notebook} célula {cell_index}", 
                "error", 
                message
            )

        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_config_ready(request: web.Request) -> web.Response:
    """
    POST /webhook/config-ready
    Body: {"project_id"}
    """
    try:
        data = await request.json()
        project_id = data.get("project_id")
        if not project_id:
            return web.json_response({"error": "project_id obrigatório"}, status=400)

        update_step(project_id, "step_config_ready", "done", "Config salva pelo usuário")
        controller.verificar_e_avancar(project_id)

        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_health(request: web.Request) -> web.Response:
    """GET /health"""
    return web.json_response({"status": "ok", "service": "anime-pipeline-webhook"})


async def _notify_telegram(project_id: str, step_label: str, status: str, message: str):
    """Notifica o usuário via Telegram."""
    if not telegram_bot:
        return
    project = get_project(project_id)
    if not project:
        return

    chat_id = project["telegram_chat_id"]
    label = step_label.replace("step_", "").replace("_", " ").title()
    emoji = "✅" if status == "done" else ("❌" if status == "error" else "🔄")

    try:
        text = f"{emoji} *{label}*: {status}"
        if message:
            text += f"\n{message}"
        await telegram_bot.send_message(
            chat_id=int(chat_id), text=text, parse_mode="Markdown"
        )
    except Exception as e:
        print(f"  ⚠️ Telegram notify falhou: {e}")


def create_webhook_app() -> web.Application:
    """Cria a aplicação web do webhook."""
    app = web.Application()
    app.router.add_post("/webhook/status", handle_status_update)
    app.router.add_post("/webhook/cell-start", handle_cell_start)
    app.router.add_post("/webhook/cell-end", handle_cell_end)
    app.router.add_post("/webhook/config-ready", handle_config_ready)
    app.router.add_get("/health", handle_health)
    return app
