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
                for i in range(1, 6): update_step(pid, f"step_watermark_pt{i}", "skipped", "User disabled")
            if not opts.get("enhancer", False):
                for i in range(1, 6): update_step(pid, f"step_enhancer_pt{i}", "skipped", "User disabled")

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
            parts_paths = split_video(video_path, temp_dir, parts=5)
            for i, p_path in enumerate(parts_paths, 1):
                self.drive.salvar(p_path, f"{DRIVE_ATIVO}/video_pt{i}.mp4")
            update_step(pid, "step_split", "done", "Video dividido em 5 partes")

            return project

        except Exception as e:
            update_step(pid, "step_upload", "error", str(e))
            raise

    def disparar_omni_imediatamente(self, project_id):
        """Etapa inicial: Dispara Omni (Dublagem) imediatamente após upload."""
        update_step(project_id, "step_omni", "running")
        dispatch_workflow("omni", project_id)

    def disparar_watermark(self, project_id):
        for i in range(1, 6): update_step(project_id, f"step_watermark_pt{i}", "running")
        dispatch_parallel([f"wm-pt{i}" for i in range(1, 6)], project_id)

    def disparar_enhancer(self, project_id):
        for i in range(1, 6): update_step(project_id, f"step_enhancer_pt{i}", "running")
        dispatch_parallel([f"enhancer-pt{i}" for i in range(1, 6)], project_id)

    def criar_sessao_videorender(self, project_id, session_url):
        """Etapa 7: Marca sessao criada e envia link pro Telegram."""
        mark_project_waiting_config(project_id, session_url)

    def disparar_render(self, project_id):
        for i in range(1, 6): update_step(project_id, f"step_render_pt{i}", "running")
        dispatch_parallel([f"render-pt{i}" for i in range(1, 6)], project_id)

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

            glow = style.get("glow", False)
            glow_color = style.get("glowColor", "#FF6B6B")
            glow_blur = style.get("glowBlur", 10)
            glow_intensity = style.get("glowIntensity", 1)


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
WrapStyle: 0

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

            def time_to_ms(t):
                p = t.replace(",", ".").strip().split(":")
                return (int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000

            def ms_to_ass_time(ms):
                ms = max(0, ms)
                total_s = ms / 1000.0
                h = int(total_s // 3600)
                m = int((total_s % 3600) // 60)
                s = total_s % 60
                sec = int(s)
                cs = int((s - sec) * 100)
                return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"

            def wrap_text(text, max_chars=42):
                """Quebra texto longo em linhas de ~max_chars usando \\N do ASS."""
                words = text.split()
                wrapped = []
                current = ""
                for word in words:
                    if current and len(current) + 1 + len(word) > max_chars:
                        wrapped.append(current)
                        current = word
                    else:
                        current = f"{current} {word}" if current else word
                if current:
                    wrapped.append(current)
                return "\\N".join(wrapped)

            # Parsear SRT e coletar blocos com timestamps
            parsed_blocks = []
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            blocks = re.split(r'\n\s*\n', srt_content.strip())
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    time_line = lines[1]
                    raw_text = " ".join(lines[2:])
                    if all_caps:
                        raw_text = raw_text.upper()

                    if "-->" in time_line:
                        t_start, t_end = time_line.split("-->")
                        try:
                            start_ms = time_to_ms(t_start)
                            end_ms = time_to_ms(t_end)
                        except Exception:
                            continue

                        texto = wrap_text(raw_text)
                        parsed_blocks.append({
                            "start_ms": start_ms,
                            "end_ms": end_ms,
                            "text": texto
                        })

            # Ordenar por start_ms e corrigir sobreposições
            parsed_blocks.sort(key=lambda b: b["start_ms"])
            for i in range(len(parsed_blocks) - 1):
                if parsed_blocks[i]["end_ms"] > parsed_blocks[i + 1]["start_ms"]:
                    # Trim end do bloco atual para não sobrepor o próximo
                    parsed_blocks[i]["end_ms"] = parsed_blocks[i + 1]["start_ms"]

            # Gerar dialogues
            dialogues = []
            for pb in parsed_blocks:
                start = ms_to_ass_time(pb["start_ms"])
                end = ms_to_ass_time(pb["end_ms"])
                texto = pb["text"]
                dur_ms = pb["end_ms"] - pb["start_ms"]

                # Calcular fade
                try:
                    eff_in = min(fade_in, dur_ms * fade_in_pct / 100)
                    eff_out = min(fade_out, dur_ms * fade_out_pct / 100)
                    fade_tag = f"\\\\fad({int(eff_in)},{int(eff_out)})"
                except Exception:
                    fade_tag = ""

                if glow:
                    glow_col = hex_to_ass(glow_color)
                    gAlpha = f"{int((1 - min(1, glow_intensity)) * 255):02X}"
                    # Glow mais sutil: bord reduzido e blur proporcional
                    glow_bord = round(outline_width + glow_blur * 0.35, 1)
                    glow_effect = f"\\1c{glow_col}\\3c{glow_col}\\1a&H{gAlpha}&\\3a&H{gAlpha}&\\bord{glow_bord}\\blur{glow_blur}"
                    dialogues.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{{fade_tag}{glow_effect}}}{texto}")
                    main_effect = f"\\1c{primary_col}\\3c{outline_col}\\1a&H00&\\3a&H00&\\bord{outline_width}\\blur0"
                    dialogues.append(f"Dialogue: 1,{start},{end},Default,,0,0,0,,{{{fade_tag}{main_effect}}}{texto}")
                else:
                    dialogues.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{{{fade_tag}}}{texto}")

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

        w_vals = [project.get(f"step_watermark_pt{i}") for i in range(1, 6)]
        e_vals = [project.get(f"step_enhancer_pt{i}") for i in range(1, 6)]
        r_vals = [project.get(f"step_render_pt{i}") for i in range(1, 6)]
        conf = project.get("step_config_ready")
        omni = project.get("step_omni")

        w_ok = all(v in ["done", "skipped"] for v in w_vals)
        e_ok = all(v in ["done", "skipped"] for v in e_vals)
        r_ok = all(v == "done" for v in r_vals)
        split_ok = project.get("step_split") == "done"

        # Aguarda a etapa de upload e divisão terminar antes de despachar qualquer coisa no Kaggle
        if not split_ok:
            return

        # 1. Config salva -> disparar Watermark (se pendente e não skipped)
        if conf == "done" and w_vals[0] == "pending":
            print(f"[{project_id}] Config concluída -> Disparando Watermark")
            self.disparar_watermark(project_id)
            return

        # 2. Watermark concluído/skipped -> disparar Enhancer (independe de conf)
        #    Copiar vídeos para a pasta correta se Watermark foi pulado
        if w_ok and e_vals[0] == "pending":
            if w_vals[0] == "skipped":
                print(f"[{project_id}] Watermark pulado, copiando vídeo original para limpo...")
                all_copied = True
                for i in range(1, 6):
                    ok = self.drive.copiar_arquivo(f"KAGGLE/PIPELINE/ATIVO/video_pt{i}.mp4", f"KAGGLE/PIPELINE/WATERMARK/pt{i}_limpo.mp4")
                    if not ok: all_copied = False
                if not all_copied:
                    print(f"[{project_id}] Falha ao copiar arquivos para o WATERMARK. Retry no próximo ciclo.")
                    return

            print(f"[{project_id}] Watermark concluído/pulado -> Disparando Enhancer")
            self.disparar_enhancer(project_id)
            return

        # 3. Watermark+Enhancer ok e Omni ok e Config ok -> disparar Render
        if conf == "done" and w_ok and e_ok and omni == "done" and r_vals[0] == "pending":
            if e_vals[0] == "skipped":
                print(f"[{project_id}] Enhancer pulado, copiando vídeo limpo para enhanced...")
                all_copied = True
                for i in range(1, 6):
                    ok = self.drive.copiar_arquivo(f"KAGGLE/PIPELINE/WATERMARK/pt{i}_limpo.mp4", f"KAGGLE/PIPELINE/ENHANCER/pt{i}_enhanced.mp4")
                    if not ok: all_copied = False
                if not all_copied:
                    print(f"[{project_id}] Falha ao copiar arquivos para o ENHANCER. Retry no próximo ciclo.")
                    return

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
        if r_ok and project["step_merge"] == "pending":
            print(f"[{project_id}] Render concluído -> Disparando Merge")
            self.disparar_merge(project_id)
            return

        if project["step_merge"] == "done" and project["status"] != "completed":
            mark_project_completed(project_id)
            print(f"[{project_id}] Projeto concluido!")
