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
                               video_path, audio_path, mask_path=None, opts=None):
        """
        Etapa 1-3: Cria projeto, limpa Drive, faz upload e divide o video.
        Agora recebe opts para registrar Watermark e Enhancer.
        """
        project = create_project(project_name, chat_id)
        pid = str(project["id"])
        print(f"Projeto criado: {pid}")

        # Se opts diz que não quer, marcamos como skipped
        if opts:
            if not opts.get("watermark", True):
                update_step(pid, "step_watermark_pt1", "skipped", "User disabled")
                update_step(pid, "step_watermark_pt2", "skipped", "User disabled")
            if not opts.get("enhancer", False):
                update_step(pid, "step_enhancer_pt1", "skipped", "User disabled")
                update_step(pid, "step_enhancer_pt2", "skipped", "User disabled")

        try:
            update_step(pid, "step_upload", "running", "Limpando Drive...")
            # Limpa pasta ATIVO e os JSONs de sessão do AUDIO_DUB
            self.drive.limpar_pasta_ativo()
            self.drive.limpar_audio_dub_cache()

            # O áudio vai para KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3
            # (caminho que o notebook Omni espera)
            self.drive.salvar(audio_path, "KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3")

            # O vídeo original também vai para ATIVO (para referência)
            self.drive.salvar(video_path, f"{DRIVE_ATIVO}/video_original.mp4")
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

    def disparar_omni_imediatamente(self, project_id):
        """Etapa inicial: Dispara Omni (Dublagem) imediatamente após upload."""
        update_step(project_id, "step_omni", "running")
        dispatch_workflow("omni", project_id)

    def disparar_watermark(self, project_id):
        """Etapa condicional: Dispara watermark (pt1+pt2 simultaneo)."""
        update_step(project_id, "step_watermark_pt1", "running")
        update_step(project_id, "step_watermark_pt2", "running")
        dispatch_parallel(["wm-pt1", "wm-pt2"], project_id)

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
        update_step(project_id, "step_render_pt1", "running")
        update_step(project_id, "step_render_pt2", "running")
        dispatch_parallel(["render-pt1", "render-pt2"], project_id)

    def disparar_merge(self, project_id):
        """Etapa 10: Dispara merge final."""
        update_step(project_id, "step_merge", "running")
        dispatch_workflow("merge", project_id)

    def converter_json_para_ass(self, project_id):
        """
        Gera o arquivo ASS final combinando a traducao.json gerada pelo Omni
        com o legendas.ass (estilo placeholder) enviado pelo VideoRender.
        """
        import tempfile
        import shutil
        print(f"[{project_id}] Iniciando conversão SRT -> ASS...")
        try:
            # Baixa os arquivos do Drive
            tmp_dir = tempfile.mkdtemp()
            ass_template = os.path.join(tmp_dir, "legendas_placeholder.ass")
            traducao_srt = os.path.join(tmp_dir, "traducao.srt")
            
            # Aqui deveríamos baixar de KAGGLE/PIPELINE/OMNI
            self.drive.baixar("KAGGLE/PIPELINE/OMNI/legendas.ass", ass_template)
            self.drive.baixar("KAGGLE/PIPELINE/OMNI/traducao.srt", traducao_srt)
            
            import re
            
            # Lê template de estilos
            with open(ass_template, "r", encoding="utf-8") as f:
                ass_lines = f.readlines()
                
            # Encontrar início dos [Events]
            event_idx = -1
            for i, line in enumerate(ass_lines):
                if line.strip() == "[Events]":
                    event_idx = i
                    break
                    
            if event_idx == -1:
                print("Arquivo ASS sem seção [Events]")
                return
                
            # Extrair estilos disponíveis
            estilos = []
            for line in ass_lines:
                if line.startswith("Style: "):
                    parts = line.split(",")
                    if len(parts) > 0:
                        estilo_nome = parts[0].replace("Style: ", "").strip()
                        estilos.append(estilo_nome)
            
            estilo_padrao = estilos[0] if estilos else "Default"
            estilo_narracao = "NARRACAO" if "NARRACAO" in estilos else estilo_padrao
            estilo_cena = "CENA" if "CENA" in estilos else estilo_padrao
                    
            # Preservar o cabeçalho (até os eventos)
            final_ass_lines = []
            for line in ass_lines:
                if line.startswith("Dialogue:"):
                    continue # Remove os dialogues antigos
                final_ass_lines.append(line)
                if line.startswith("Format:"):
                    break # Fica pronto para inserir os dialogues
                    
            def format_ass_time_from_srt(srt_time):
                srt_time = srt_time.strip()
                if not srt_time: return "0:00:00.00"
                parts = srt_time.replace(",", ".").split(":")
                if len(parts) == 3:
                    h, m, s = parts
                    h = int(h)
                    if "." in s:
                        sec, ms = s.split(".")
                        s_ass = f"{int(sec):02d}.{ms[:2]}"
                    else:
                        s_ass = f"{int(s):02d}.00"
                    return f"{h}:{m:02d}:{s_ass}"
                return "0:00:00.00"

            # Parsear o SRT
            if os.path.exists(traducao_srt):
                with open(traducao_srt, "r", encoding="utf-8") as f:
                    srt_content = f.read()
                    
                # Split por blocos do SRT
                blocks = re.split(r'\n\s*\n', srt_content.strip())
                
                for block in blocks:
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        time_line = lines[1]
                        texto = " ".join(lines[2:]).replace('\n', '\\N')
                        
                        if "-->" in time_line:
                            t_start, t_end = time_line.split("-->")
                            start = format_ass_time_from_srt(t_start)
                            end = format_ass_time_from_srt(t_end)
                            
                            # Fallback: palavras curtas (whisper) = NARRACAO, longas = CENA
                            style = estilo_narracao if len(texto.split()) <= 3 else estilo_cena
                            
                            dialogue = f"Dialogue: 0,{start},{end},{style},,0,0,0,,{texto}\n"
                            final_ass_lines.append(dialogue)
            else:
                print(f"[{project_id}] AVISO: traducao.srt não encontrado!")

            out_ass = os.path.join(tmp_dir, "legendas_final.ass")
            with open(out_ass, "w", encoding="utf-8") as f:
                f.writelines(final_ass_lines)
                
            self.drive.salvar(out_ass, "KAGGLE/PIPELINE/OMNI/legendas.ass")
            print(f"[{project_id}] ASS Finalizado e salvo no Drive como legendas.ass (sobrescrevendo placeholder).")
            
            shutil.rmtree(tmp_dir, ignore_errors=True)
            
        except Exception as e:
            print(f"[{project_id}] Erro ao gerar ASS final: {e}")


    def verificar_e_avancar(self, project_id):
        """
        Verifica o status atual do projeto e avanca para a proxima etapa.
        Fluxo:
          config_ready -> Watermark (se ativo) -> Enhancer (se ativo) -> aguarda Omni -> Render -> Merge
        """
        project = get_project(project_id)
        if not project:
            return

        w1 = project["step_watermark_pt1"]
        w2 = project["step_watermark_pt2"]
        e1 = project["step_enhancer_pt1"]
        e2 = project["step_enhancer_pt2"]
        conf = project["step_config_ready"]
        omni = project["step_omni"]
        r1 = project["step_render_pt1"]
        r2 = project["step_render_pt2"]

        w_ok = (w1 in ["done", "skipped"]) and (w2 in ["done", "skipped"])
        e_ok = (e1 in ["done", "skipped"]) and (e2 in ["done", "skipped"])

        # 1. Config salva -> disparar Watermark (se pendente e não skipped)
        if conf == "done" and w1 == "pending":
            print(f"[{project_id}] Config concluída -> Disparando Watermark")
            self.disparar_watermark(project_id)
            return

        # 2. Watermark concluído/skipped -> disparar Enhancer (independe de conf)
        #    Copiar vídeos para a pasta correta se Watermark foi pulado
        if w_ok and e1 == "pending":
            if w1 == "skipped":
                print(f"[{project_id}] Watermark pulado, copiando vídeo original para limpo...")
                self.drive.copiar_arquivo("KAGGLE/PIPELINE/ATIVO/video_pt1.mp4", "KAGGLE/PIPELINE/WATERMARK/pt1_limpo.mp4")
                self.drive.copiar_arquivo("KAGGLE/PIPELINE/ATIVO/video_pt2.mp4", "KAGGLE/PIPELINE/WATERMARK/pt2_limpo.mp4")

            print(f"[{project_id}] Watermark concluído/pulado -> Disparando Enhancer")
            self.disparar_enhancer(project_id)
            return

        # 3. Watermark+Enhancer ok e Omni ok e Config ok -> disparar Render
        if conf == "done" and w_ok and e_ok and omni == "done" and r1 == "pending":
            if e1 == "skipped":
                print(f"[{project_id}] Enhancer pulado, copiando vídeo limpo para enhanced...")
                self.drive.copiar_arquivo("KAGGLE/PIPELINE/WATERMARK/pt1_limpo.mp4", "KAGGLE/PIPELINE/ENHANCER/pt1_enhanced.mp4")
                self.drive.copiar_arquivo("KAGGLE/PIPELINE/WATERMARK/pt2_limpo.mp4", "KAGGLE/PIPELINE/ENHANCER/pt2_enhanced.mp4")

            # Copiar output do Omni para a pasta padrão do pipeline
            print(f"[{project_id}] Copiando output do Omni para PIPELINE/OMNI...")
            arquivos_out = self.drive.listar_arquivos("KAGGLE/AUDIO_DUB/OUTPUT")
            mp3_completo = next((a for a in arquivos_out if a['name'].endswith('_Completo.mp3') or a['name'].endswith('.mp3')), None)
            srt_completo = next((a for a in arquivos_out if a['name'].endswith('_Completo.srt') or a['name'].endswith('.srt')), None)

            if mp3_completo:
                self.drive.copiar_arquivo(f"KAGGLE/AUDIO_DUB/OUTPUT/{mp3_completo['name']}", "KAGGLE/PIPELINE/OMNI/audio_dublado.mp3")
            if srt_completo:
                self.drive.copiar_arquivo(f"KAGGLE/AUDIO_DUB/OUTPUT/{srt_completo['name']}", "KAGGLE/PIPELINE/OMNI/traducao.srt")

            print(f"[{project_id}] Tudo pronto -> Gerar ASS e disparar Render")
            self.converter_json_para_ass(project_id)
            self.disparar_render(project_id)
            return

        # 4. Render concluído -> disparar Merge
        if r1 == "done" and r2 == "done" and project["step_merge"] == "pending":
            print(f"[{project_id}] Render concluído -> Disparando Merge")
            self.disparar_merge(project_id)
            return

        if project["step_merge"] == "done" and project["status"] != "completed":
            mark_project_completed(project_id)
            print(f"[{project_id}] Projeto concluido!")
