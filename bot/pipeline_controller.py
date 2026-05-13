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

    def iniciar_projeto(self, project_name, chat_id,
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
        Gera o arquivo ASS final combinando:
        - O subtitleStyle do videorender-project.json (definido pelo usuário no frontend)
        - O traducao.srt gerado pelo Omni (conteúdo real das legendas)
        
        Se o frontend já enviou um ASS com conteúdo real (não placeholder), ele mantém.
        """
        import tempfile
        import shutil
        import re
        print(f"[{project_id}] Iniciando geração do ASS final...")
        try:
            tmp_dir = tempfile.mkdtemp()
            config_path = os.path.join(tmp_dir, "videorender-project.json")
            srt_path = os.path.join(tmp_dir, "omni_output.srt")
            existing_ass = os.path.join(tmp_dir, "legendas_existente.ass")

            # Baixar config do VideoRender
            has_config = self.drive.baixar("KAGGLE/PIPELINE/OMNI/videorender-project.json", config_path)
            # SRT padronizado copiado pelo verificar_e_avancar
            has_srt = self.drive.baixar("KAGGLE/PIPELINE/OMNI/omni_output.srt", srt_path)

            if not has_srt or not os.path.exists(srt_path):
                print(f"[{project_id}] AVISO: traducao.srt não encontrado. Pulando geração de ASS.")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return

            # Ler estilo do config (ou usar defaults)
            style = {}
            if has_config and os.path.exists(config_path):
                import json as json_mod
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json_mod.load(f)
                # O config pode ter o estilo em "subtitles.style" (exportProject) ou "subtitleStyle"
                style = config.get("subtitles", {}).get("style", {})
                if not style:
                    style = config.get("subtitleStyle", {})
                video_info = config.get("video", {}).get("info", {})
                out_format = config.get("video", {}).get("outputFormat", "9:16")
            else:
                out_format = "9:16"
                video_info = {}

            # Defaults para o estilo
            font = style.get("font", "Montserrat")
            size = style.get("size", 52)
            color = style.get("color", "#FFFFFF")
            outline_color = style.get("outlineColor", "#000000")
            outline_width = style.get("outlineWidth", 2.5)
            shadow_offset = style.get("shadowOffset", 1)
            bold = style.get("bold", True)
            italic = style.get("italic", False)
            alignment = style.get("alignment", 2)
            position_y = style.get("positionY", 85)
            fade_in = style.get("fadeIn", 100)
            fade_out = style.get("fadeOut", 80)
            fade_in_pct = style.get("fadeInLimitPct", 20)
            fade_out_pct = style.get("fadeOutLimitPct", 15)
            bg_box = style.get("bgBox", False)
            bg_box_color = style.get("bgBoxColor", "#000000")
            bg_box_opacity = style.get("bgBoxOpacity", 0.5)
            all_caps = style.get("allCaps", False)

            # Resolução do vídeo
            if out_format == "9:16":
                play_w, play_h = 1080, 1920
            else:
                play_w, play_h = 1920, 1080

            # Converter cores para formato ASS (&HAABBGGRR)
            def hex_to_ass(h, alpha=0):
                h = h.lstrip("#")
                if len(h) < 6:
                    h = "FFFFFF"
                r, g, b = h[0:2], h[2:4], h[4:6]
                a = f"{int(alpha * 255):02X}"
                return f"&H{a}{b}{g}{r}"

            primary_col = hex_to_ass(color)
            outline_col = hex_to_ass(outline_color)
            back_col = hex_to_ass(bg_box_color, 1 - bg_box_opacity) if bg_box else "&HFFFFFFFF"
            ass_font_size = round((size / 1920) * play_h)
            bold_flag = "-1" if bold else "0"
            italic_flag = "-1" if italic else "0"
            margin_v = round(play_h * (1 - position_y / 100))

            # Gerar ASS
            header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{ass_font_size},{primary_col},{primary_col},{outline_col},{back_col},{bold_flag},{italic_flag},0,0,100,100,0,0,1,{outline_width},{shadow_offset},{alignment},0,0,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

            def srt_to_ass_time(srt_time):
                srt_time = srt_time.strip().replace(",", ".")
                parts = srt_time.split(":")
                if len(parts) == 3:
                    h = int(parts[0])
                    m = parts[1]
                    s = parts[2]
                    if "." in s:
                        sec, ms = s.split(".")
                        cs = ms[:2].ljust(2, "0")
                    else:
                        sec = s
                        cs = "00"
                    return f"{h}:{m}:{int(sec):02d}.{cs}"
                return "0:00:00.00"

            # Parsear SRT
            dialogues = []
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            blocks = re.split(r'\n\s*\n', srt_content.strip())
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    time_line = lines[1]
                    texto = " ".join(lines[2:]).replace('\n', '\\N')
                    if all_caps:
                        texto = texto.upper()

                    if "-->" in time_line:
                        t_start, t_end = time_line.split("-->")
                        start = srt_to_ass_time(t_start)
                        end = srt_to_ass_time(t_end)

                        # Calcular fade
                        try:
                            def time_to_ms(t):
                                p = t.replace(",", ".").split(":")
                                return (int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000
                            dur_ms = time_to_ms(t_end.strip()) - time_to_ms(t_start.strip())
                            eff_in = min(fade_in, dur_ms * fade_in_pct / 100)
                            eff_out = min(fade_out, dur_ms * fade_out_pct / 100)
                            fade_tag = f"\\\\fad({int(eff_in)},{int(eff_out)})"
                        except Exception:
                            fade_tag = ""

                        dialogue = f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{{fade_tag}}}{texto}"
                        dialogues.append(dialogue)

            out_ass = os.path.join(tmp_dir, "legendas_final.ass")
            with open(out_ass, "w", encoding="utf-8") as f:
                f.write(header)
                f.write("\n".join(dialogues))

            self.drive.salvar(out_ass, "KAGGLE/PIPELINE/OMNI/legendas.ass")
            print(f"[{project_id}] ASS final gerado ({len(dialogues)} diálogos) e salvo no Drive.")

            shutil.rmtree(tmp_dir, ignore_errors=True)

        except Exception as e:
            print(f"[{project_id}] Erro ao gerar ASS final: {e}")
            import traceback
            traceback.print_exc()


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
            # O Omni salva como: KAGGLE/AUDIO_DUB/OUTPUT/{safe_anime}_{modo_folder}.mp3/.srt
            # Ex: Naruto_Completo.mp3, Naruto_Completo.srt  OU  Naruto_Short.mp3, Naruto_Short.srt
            print(f"[{project_id}] Copiando output do Omni para PIPELINE/OMNI...")
            arquivos_out = self.drive.listar_arquivos("KAGGLE/AUDIO_DUB/OUTPUT")

            # Preferir _Completo se existir, senão pegar qualquer .mp3/.srt
            mp3_file = (
                next((a for a in arquivos_out if '_Completo.mp3' in a['name']), None) or
                next((a for a in arquivos_out if a['name'].endswith('.mp3')), None)
            )
            srt_file = (
                next((a for a in arquivos_out if '_Completo.srt' in a['name']), None) or
                next((a for a in arquivos_out if a['name'].endswith('.srt')), None)
            )

            if mp3_file:
                self.drive.copiar_arquivo(
                    f"KAGGLE/AUDIO_DUB/OUTPUT/{mp3_file['name']}",
                    "KAGGLE/PIPELINE/OMNI/audio_dublado.mp3"
                )
                print(f"[{project_id}] MP3 copiado: {mp3_file['name']}")
            else:
                print(f"[{project_id}] AVISO: Nenhum .mp3 encontrado em AUDIO_DUB/OUTPUT!")

            if srt_file:
                # Salvar com nome padronizado para o converter_json_para_ass encontrar
                self.drive.copiar_arquivo(
                    f"KAGGLE/AUDIO_DUB/OUTPUT/{srt_file['name']}",
                    "KAGGLE/PIPELINE/OMNI/omni_output.srt"
                )
                print(f"[{project_id}] SRT copiado: {srt_file['name']}")
            else:
                print(f"[{project_id}] AVISO: Nenhum .srt encontrado em AUDIO_DUB/OUTPUT!")

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
