"""
Pipeline Controller - Orquestrador Central
Gerencia o fluxo completo de processamento de video.
"""

import os
import asyncio
from bot.database import (
    create_project, update_step, get_project,
    mark_project_completed, mark_project_waiting_config
)
from bot.drive_manager import DriveManager, split_video, merge_videos, DRIVE_ATIVO, DRIVE_OMNI
from bot.github_actions import dispatch_workflow, dispatch_parallel


class PipelineController:
    """Controlador central do pipeline de processamento."""

    def __init__(self):
        self.drive = DriveManager()

    async def iniciar_projeto(self, project_name, chat_id,
                               video_path, audio_path, mask_path=None):
        """
        Etapa 1-3: Cria projeto, limpa Drive, faz upload e divide o video.
        """
        project = create_project(project_name, chat_id)
        pid = str(project["id"])
        print(f"Projeto criado: {pid}")

        try:
            update_step(pid, "step_upload", "running", "Limpando Drive...")
            self.drive.limpar_pasta_ativo()

            self.drive.salvar(video_path, f"{DRIVE_ATIVO}/video_original.mp4")
            self.drive.salvar(audio_path, f"{DRIVE_ATIVO}/audio_original.mp3")
            if mask_path and os.path.exists(mask_path):
                self.drive.salvar(mask_path, f"{DRIVE_ATIVO}/mask.png")

            update_step(pid, "step_upload", "done", "Upload concluido")

            update_step(pid, "step_split", "running", "Dividindo video...")
            temp_dir = os.path.join(os.path.dirname(video_path), "split_temp")
            pt1_path, pt2_path = split_video(video_path, temp_dir)

            self.drive.salvar(pt1_path, f"{DRIVE_ATIVO}/video_pt1.mp4")
            self.drive.salvar(pt2_path, f"{DRIVE_ATIVO}/video_pt2.mp4")
            update_step(pid, "step_split", "done", "Video dividido em 2 partes")

            return project

        except Exception as e:
            update_step(pid, "step_upload", "error", str(e))
            raise

    def disparar_watermark_e_omni(self, project_id):
        """Etapa 4-5: Dispara watermark (pt1+pt2 simultaneo) e omni (paralelo)."""
        update_step(project_id, "step_watermark_pt1", "running")
        update_step(project_id, "step_watermark_pt2", "running")
        dispatch_parallel(["wm-pt1", "wm-pt2"], project_id)

        update_step(project_id, "step_omni", "running")
        dispatch_workflow("omni", project_id)

    def disparar_enhancer(self, project_id):
        """Etapa 6: Dispara video enhancer para as 2 partes (simultaneo)."""
        update_step(project_id, "step_enhancer_pt1", "running")
        update_step(project_id, "step_enhancer_pt2", "running")
        dispatch_parallel(["enhancer-pt1", "enhancer-pt2"], project_id)

    def criar_sessao_videorender(self, project_id, session_url):
        """Etapa 7: Marca sessao criada e envia link pro Telegram."""
        mark_project_waiting_config(project_id, session_url)

    def disparar_render(self, project_id):
        """Etapa 9: Dispara renderizadores para as 2 partes."""
        update_step(project_id, "step_config_ready", "done")
        update_step(project_id, "step_render_pt1", "running")
        update_step(project_id, "step_render_pt2", "running")
        dispatch_parallel(["render-pt1", "render-pt2"], project_id)

    def disparar_merge(self, project_id):
        """Etapa 10: Dispara merge final."""
        update_step(project_id, "step_merge", "running")
        dispatch_workflow("merge", project_id)

    def verificar_e_avancar(self, project_id):
        """
        Verifica o status atual do projeto e avanca para a proxima etapa
        se as dependencias estiverem satisfeitas.
        Chamado pelo webhook quando um notebook reporta conclusao.
        """
        project = get_project(project_id)
        if not project:
            return

        # WM pt1 + pt2 done -> disparar Enhancer
        if (project["step_watermark_pt1"] == "done" and
            project["step_watermark_pt2"] == "done" and
            project["step_enhancer_pt1"] == "pending"):
            print(f"  Watermark concluido -> Disparando Enhancer")
            self.disparar_enhancer(project_id)
            return

        # Enhancer pt1 + pt2 done + config ready -> disparar Render
        if (project["step_enhancer_pt1"] == "done" and
            project["step_enhancer_pt2"] == "done" and
            project["step_config_ready"] == "done" and
            project["step_render_pt1"] == "pending"):
            print(f"  Enhancer + Config concluidos -> Disparando Render")
            self.disparar_render(project_id)
            return

        # Render pt1 + pt2 done -> disparar Merge
        if (project["step_render_pt1"] == "done" and
            project["step_render_pt2"] == "done" and
            project["step_merge"] == "pending"):
            print(f"  Render concluido -> Disparando Merge")
            self.disparar_merge(project_id)
            return

        # Merge done -> projeto concluido
        if project["step_merge"] == "done":
            mark_project_completed(project_id)
            print(f"  Projeto {project_id} concluido!")
            return
