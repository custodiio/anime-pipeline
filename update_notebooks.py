import os
import json

NOTEBOOKS = [
    "notebooks/anime-renderizador-kaggle-pt-1.ipynb",
    "notebooks/anime-renderizador-kaggle-pt-2.ipynb",
    "notebooks/anime-renderizador-kaggle-pt-3.ipynb",
    "notebooks/anime-renderizador-kaggle-pt-4.ipynb",
    "notebooks/anime-renderizador-kaggle-pt-5.ipynb"
]

FONT_DOWNLOAD_CODE = """
print("Baixando pacote de fontes do Google Drive...")
os.system("mkdir -p /usr/share/fonts/truetype/custom")
try:
    _fid = _buscar_id("KAGGLE/PIPELINE/FONTS")
    if _fid:
        _r = drive_service.files().list(q=f"'{_fid}' in parents and trashed=false", fields="files(id, name)").execute()
        _f_list = _r.get("files", [])
        print(f"  {len(_f_list)} fontes encontradas no Drive")
        for _f in _f_list:
            _dest = f"/usr/share/fonts/truetype/custom/{_f['name']}"
            if os.path.exists(_dest):
                print(f"  Ja existe: {_f['name']}")
                continue
            try:
                _req = drive_service.files().get_media(fileId=_f['id'])
                with open(_dest, "wb") as _fh:
                    _dl = MediaIoBaseDownload(_fh, _req); _done = False
                    while not _done: _, _done = _dl.next_chunk()
                print(f"  Baixado: {_f['name']}")
            except Exception as _ex:
                print(f"  Erro baixando {_f['name']}: {_ex}")
    else:
        print("  ⚠️ Pasta KAGGLE/PIPELINE/FONTS nao encontrada no Drive!")
except Exception as e:
    print(f"  ❌ Erro ao baixar fontes do Drive: {e}")
os.system("fc-cache -f -v > /dev/null 2>&1")
_custom_dir = "/usr/share/fonts/truetype/custom"
if os.path.isdir(_custom_dir):
    _installed = os.listdir(_custom_dir)
    print(f"  Fontes instaladas ({len(_installed)}): {_installed}")
else:
    print("  ⚠️ Diretorio de fontes custom nao existe!")
print("Setup de fontes concluido!")
"""

def update_notebook(path):
    with open(path, "r", encoding="utf-8") as f:
        nb = json.load(f)
    
    # Update Cell 0 for font downloads (idempotent, cleans up old blocks)
    cell_0 = nb["cells"][0]
    src = cell_0["source"]
    
    # Garante que _buscar_id usa orderBy="modifiedTime desc" na célula 0
    for i, line in enumerate(src):
        if 'drive_service.files().list(q=q, fields="files(id,mimeType)")' in line:
            src[i] = line.replace('drive_service.files().list(q=q, fields="files(id,mimeType)")', 'drive_service.files().list(q=q, fields="files(id,mimeType)", orderBy="modifiedTime desc")')
        elif 'drive_service.files().list(q=q, fields=\\"files(id,mimeType)\\")' in line:
            src[i] = line.replace('drive_service.files().list(q=q, fields=\\"files(id,mimeType)\\")', 'drive_service.files().list(q=q, fields=\\"files(id,mimeType)\\", orderBy=\\"modifiedTime desc\\")')
            
    # Localiza a âncora correta: cell_end(0, ...) que fica NO FINAL da célula 0,
    # APÓS toda autenticação do Drive + definição de funções auxiliares.
    # O bloco de fontes PRECISA de _buscar_id(), baixar_do_drive() e drive_service,
    # que só existem depois da autenticação. Inserir antes garante execução correta.
    
    # 1. Primeiro, remove qualquer bloco de fontes antigo que esteja no lugar errado
    clean_src = []
    in_font_block = False
    for line in src:
        # Detecta início do bloco de fontes antigo
        if "Baixando pacote de fontes" in line:
            in_font_block = True
            continue
        # Detecta fim do bloco de fontes antigo
        if in_font_block:
            if "Fontes instaladas!" in line:
                in_font_block = False
                continue
            # Pula linhas internas do bloco de fontes
            if any(x in line for x in ["truetype/custom", "KAGGLE/PIPELINE/FONTS", "_fid", "_f_list", "fc-cache"]):
                continue
            # Se encontrou uma linha que claramente não é do bloco de fontes, saiu dele
            if "def " in line or "cell_start(" in line or "cell_end(" in line or "DRIVE_" in line:
                in_font_block = False
                clean_src.append(line)
            continue
        clean_src.append(line)
    
    # 2. Encontra a posição de cell_end(0, ...) para inserir as fontes antes dela
    idx_cell_end = -1
    for i, line in enumerate(clean_src):
        if "cell_end(0" in line:
            idx_cell_end = i
            break
    
    if idx_cell_end != -1:
        lines_to_insert = [l + "\n" for l in FONT_DOWNLOAD_CODE.strip().split("\n")]
        new_src = clean_src[:idx_cell_end] + ["\n"] + lines_to_insert + ["\n"] + clean_src[idx_cell_end:]
        cell_0["source"] = new_src
    else:
        cell_0["source"] = clean_src


    # Update build_ffmpeg_command Cell
    for cell in nb["cells"]:
        src = cell["source"]
        if not any("build_ffmpeg_command" in line for line in src):
            continue
        
        # We need to rewrite the cropZoom and text overlay parts.
        # It's easier to replace the entire build_ffmpeg_command function.
        
        func_str = """def build_ffmpeg_command(config, video_in, audio_in, ass_in, out_file, start_time=0):
    import os
    import subprocess
    import base64
    
    video_dur = None
    try:
        probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video_in]
        video_dur = float(subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip())
    except Exception:
        pass

    filters = []
    last_stream = "[0:v]"
    overlay_inputs = []
    
    out_format = config["video"].get("outputFormat", "16:9")
    out_w, out_h = (1080, 1920) if out_format == "9:16" else (1920, 1080)
    
    # Background options (solid or blur) - Read from config["video"]["background"]
    bg = config.get("video", {}).get("background", {})
    if not bg:
        bg = config.get("background", {}) # Fallback
    is_blur_bg = bg.get("type") == "blur"
    blur_intensity = bg.get("blurIntensity", 25)
    
    if is_blur_bg:
        # Create a deep blurred background from the original input video
        # We scale it to increase (fill the screen) and crop to exact dimensions, then apply boxblur
        filters.append(f"[0:v]split[bg_src][main_src]")
        filters.append(f"[bg_src]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h},boxblur={blur_intensity}:5[bg_blurred]")
        last_stream = "[main_src]"
    
    # 1. Base Crop / Zoom Logic
    sc = config.get("staticCrop", {})
    cz = config.get("cropZoom", {})
    
    if sc.get("enabled"):
        cx = sc.get("x", 0) / 100.0
        cy = sc.get("y", 0) / 100.0
        cw = sc.get("width", 100) / 100.0
        ch = sc.get("height", 100) / 100.0
        filters.append(f"{last_stream}crop=iw*{cw:.4f}:ih*{ch:.4f}:iw*{cx:.4f}:ih*{cy:.4f}[static_cropped]")
        last_stream = "[static_cropped]"
    elif cz.get("enabled"):
        zs = cz.get("zoomStart", 1.0)
        if zs >= 1.0:
            filters.append(f"{last_stream}scale={out_w}:{out_h}:force_original_aspect_ratio=increase,crop={out_w}:{out_h}[scaled]")
            last_stream = "[scaled]"
            if zs > 1.0:
                fx = cz.get("focusX", 0.5)
                fy = cz.get("focusY", 0.5)
                cw = int(out_w / zs)
                ch = int(out_h / zs)
                cx = int((out_w - cw) * fx)
                cy = int((out_h - ch) * fy)
                filters.append(f"{last_stream}crop={cw}:{ch}:{cx}:{cy},scale={out_w}:{out_h}[cropped]")
                last_stream = "[cropped]"
        else:
            # ZoomStart < 1.0 (zoom out, needs background)
            filters.append(f"{last_stream}scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[scaled]")
            sm_w = int(out_w * zs)
            sm_h = int(out_h * zs)
            sm_w = sm_w - (sm_w % 2)
            sm_h = sm_h - (sm_h % 2)
            filters.append(f"[scaled]scale={sm_w}:{sm_h}[zoomedout]")
            if is_blur_bg:
                # Place zoomedout video on top of blurred background
                filters.append(f"[bg_blurred][zoomedout]overlay=(W-w)/2:(H-h)/2[padded]")
            else:
                bg_color = bg.get("solidColor", "#0a0a0a").replace("#", "")
                filters.append(f"[zoomedout]pad=max(iw\\\\,{out_w}):max(ih\\\\,{out_h}):(ow-iw)/2:(oh-ih)/2:color={bg_color}[padded_zo]")
                filters.append(f"[padded_zo]crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})/2[padded]")
            last_stream = "[padded]"
            
    # 2. Position & Scaling
    vp = config.get("videoPosition", {})
    if vp.get("enabled"):
        scale_factor = vp.get("scale", 1.0)
        tx = vp.get("x", 0) / 100.0
        ty = vp.get("y", 0) / 100.0
        target_w = int(out_w * scale_factor)
        target_h = int(out_h * scale_factor)
        target_w = target_w - (target_w % 2)
        target_h = target_h - (target_h % 2)
        
        filters.append(f"{last_stream}scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[scaled_vp]")
        if is_blur_bg:
            px_overlay = f"(W-w)/2+{int(tx*out_w)}"
            py_overlay = f"(H-h)/2+{int(ty*out_h)}"
            # Place scaled and translated video on top of blurred background
            filters.append(f"[bg_blurred][scaled_vp]overlay={px_overlay}:{py_overlay}[positioned]")
        else:
            px_pad = f"(ow-iw)/2+{int(tx*out_w)}"
            py_pad = f"(oh-ih)/2+{int(ty*out_h)}"
            bg_color = bg.get("solidColor", "#0a0a0a").replace("#", "")
            filters.append(f"[scaled_vp]pad=max(iw\\\\,{out_w}):max(ih\\\\,{out_h}):{px_pad}:{py_pad}:color={bg_color}[padded_vp]")
            filters.append(f"[padded_vp]crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})/2[positioned]")
        last_stream = "[positioned]"
    else:
        # Standard centering if staticCrop is enabled but no custom positioning
        if sc.get("enabled"):
            filters.append(f"{last_stream}scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[scaled_sc]")
            if is_blur_bg:
                filters.append(f"[bg_blurred][scaled_sc]overlay=(W-w)/2:(H-h)/2[padded_sc]")
            else:
                bg_color = bg.get("solidColor", "#0a0a0a").replace("#", "")
                filters.append(f"[scaled_sc]pad=max(iw\\\\,{out_w}):max(ih\\\\,{out_h}):(ow-iw)/2:(oh-ih)/2:color={bg_color}[padded_sc_temp]")
                filters.append(f"[padded_sc_temp]crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})/2[padded_sc]")
            last_stream = "[padded_sc]"
        elif not cz.get("enabled"):
            # Default centering fallback when neither cropZoom nor staticCrop are active
            filters.append(f"{last_stream}scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[scaled_std]")
            if is_blur_bg:
                filters.append(f"[bg_blurred][scaled_std]overlay=(W-w)/2:(H-h)/2[padded_std]")
            else:
                bg_color = bg.get("solidColor", "#0a0a0a").replace("#", "")
                filters.append(f"[scaled_std]pad=max(iw\\\\,{out_w}):max(ih\\\\,{out_h}):(ow-iw)/2:(oh-ih)/2:color={bg_color}[padded_std_temp]")
                filters.append(f"[padded_std_temp]crop={out_w}:{out_h}:(iw-{out_w})/2:(ih-{out_h})/2[padded_std]")
            last_stream = "[padded_std]"
            
    # 3. Geometric Transforms (Flip & Rotation) & Video Speed
    ve = config.get("videoEdit", {})
    if ve:
        if ve.get("hFlip"):
            filters.append(f"{last_stream}hflip[hflipped]")
            last_stream = "[hflipped]"
        if ve.get("vFlip"):
            filters.append(f"{last_stream}vflip[vflipped]")
            last_stream = "[vflipped]"
            
        rot = ve.get("rotate", 0)
        if rot == 90:
            filters.append(f"{last_stream}transpose=1[rotated]")
            last_stream = "[rotated]"
        elif rot == 180:
            filters.append(f"{last_stream}transpose=2,transpose=2[rotated]")
            last_stream = "[rotated]"
        elif rot == 270:
            filters.append(f"{last_stream}transpose=2[rotated]")
            last_stream = "[rotated]"
            
        speed = ve.get("speed", 1.0)
        if speed != 1.0:
            filters.append(f"{last_stream}setpts=PTS/{speed:.2f}[speed_v]")
            last_stream = "[speed_v]"

    # 4. Color Grading
    cg = config.get("colorGrade", {})
    if cg:
        b = cg.get("brightness", 0) / 100.0
        c = 1.0 + cg.get("contrast", 0) / 100.0
        s = 1.0 + cg.get("saturation", 0) / 100.0
        g = cg.get("gamma", 1.0)
        filters.append(f"{last_stream}eq=brightness={b}:contrast={c}:saturation={s}:gamma={g}[colorgraded]")
        last_stream = "[colorgraded]"
        temp = cg.get("temperature", 0)
        if temp != 0:
            red_mod = temp / 100.0 if temp > 0 else 0
            blue_mod = abs(temp) / 100.0 if temp < 0 else 0
            filters.append(f"{last_stream}colorbalance=rm={red_mod}:bm={blue_mod}[temp_applied]")
            last_stream = "[temp_applied]"
        sharp = cg.get("sharpness", 1.0)
        if sharp > 1.0:
            amount = sharp - 1.0
            filters.append(f"{last_stream}unsharp=5:5:{amount}:5:5:0.0[sharpened]")
            last_stream = "[sharpened]"
        v = cg.get("vignette", 0)
        if v > 0:
            filters.append(f"{last_stream}vignette=a={v}[vignetted]")
            last_stream = "[vignetted]"

    # 5. Overlays (Image/Text)
    overlays = config.get("overlays", [])
    for i, ov in enumerate(overlays):
        if ov["type"] in ["image", "watermark"]:
            header, encoded = ov["content"].split(",", 1)
            ext = header.split(";")[0].split("/")[1]
            filename = f"/kaggle/working/temp_overlay_{i}.{ext}"
            with open(filename, "wb") as f:
                f.write(base64.b64decode(encoded))
            overlay_inputs.append(filename)
            input_idx = len(overlay_inputs) + 1
            ox = int((ov["x"] / 100.0) * out_w)
            oy = int((ov["y"] / 100.0) * out_h)
            ow = int((ov["width"] / 100.0) * out_w)
            oh = int((ov["height"] / 100.0) * out_h)
            opacity = ov.get("opacity", 1.0)
            filters.append(f"[{input_idx}:v]scale={ow}:{oh}[ov_scaled_{i}]")
            alpha_filter = f",colorchannelmixer=aa={opacity}" if opacity < 1.0 else ""
            filters.append(f"[ov_scaled_{i}]format=rgba{alpha_filter}[ov_alpha_{i}]")
            time_filter = ""
            tin = ov.get("timeIn", 0) - start_time
            tout = ov.get("timeOut", 0) - start_time
            if ov.get("timeOut", 0) == 0: tout = 999999
            if tout <= 0: continue
            if tin < 0: tin = 0
            time_filter = f":enable='between(t,{tin},{tout})'"
            filters.append(f"{last_stream}[ov_alpha_{i}]overlay=x={ox}:y={oy}{time_filter}[with_ov_{i}]")
            last_stream = f"[with_ov_{i}]"
        elif ov["type"] == "text":
            ox = int((ov["x"] / 100.0) * out_w)
            oy = int((ov["y"] / 100.0) * out_h)
            txt = ov["content"].replace("'", "\\\\\\'").replace(":", "\\\\\\\\:")
            fsize = int((ov.get("fontSize", 32) * (out_h / 1080)))
            fcolor = ov.get("fontColor", "#ffffff")
            
            ffamily = ov.get("fontFamily", "Montserrat")
            ffamily_clean = ffamily.replace(" ", "")  # Clean up spaces for filename search (e.g. Titan One -> TitanOne)
            fweight = ov.get("fontWeight", "normal")
            fstyle = ov.get("fontStyle", "normal")
            
            suffix = "-Regular"
            if fweight in ["bold", "900"]: suffix = "-Bold"
            if fweight == "900" and ffamily == "Montserrat": suffix = "-Black"
            if fstyle == "italic": suffix = "-Italic"
            fontfile = f"/usr/share/fonts/truetype/custom/{ffamily_clean}{suffix}.ttf"
            if not os.path.exists(fontfile):
                fontfile = f"/usr/share/fonts/truetype/custom/{ffamily_clean}-Regular.ttf"
            if os.path.exists(fontfile):
                font_opt = f"fontfile='{fontfile}'"
                print(f"  Fonte overlay: {fontfile}")
            else:
                font_opt = f"font='{ffamily}'"
                print(f"  ⚠️ Fonte {ffamily_clean}{suffix}.ttf nao encontrada, usando fontconfig: {ffamily}")
            
            bg_color = ov.get("bgColor", "")
            bg_op = ov.get("bgOpacity", 0.5)
            box_filter = f":box=1:boxcolor={bg_color.replace('#','')}@{bg_op}:boxborderw={int(fsize*0.2)}" if bg_color else ""
            
            shadow_color = ov.get("shadowColor", "")
            shadow_filter = f":shadowcolor={shadow_color.replace('#','')}:shadowx={ov.get('shadowX', 2)}:shadowy={ov.get('shadowY', 2)}" if shadow_color else ""
            
            time_filter = ""
            tin = ov.get("timeIn", 0) - start_time
            tout = ov.get("timeOut", 0) - start_time
            if ov.get("timeOut", 0) == 0: tout = 999999
            if tout <= 0: continue
            if tin < 0: tin = 0
            time_filter = f":enable='between(t,{tin},{tout})'"
            
            opacity = ov.get("opacity", 1.0)
            alpha_opt = f":alpha={opacity}" if opacity < 1.0 else ""
            
            filters.append(f"{last_stream}drawtext={font_opt}:text=\\'{txt}\\':x={ox}:y={oy}:fontsize={fsize}:fontcolor={fcolor}{box_filter}{shadow_filter}{time_filter}{alpha_opt}[with_txt_{i}]")
            last_stream = f"[with_txt_{i}]"

    # 6. Blur Band
    bb = config.get("blurBand", {})
    if bb.get("enabled"):
        bb_h = int((bb.get("height", 20) / 100) * out_h)
        bb_y = int((bb.get("positionY", 85) / 100) * out_h - bb_h / 2)
        bb_y = max(0, min(out_h - bb_h, bb_y))
        bb_blur = bb.get("blurIntensity", 20)
        bb_feather_pct = bb.get("feather", 40)
        feather_px = int(bb_h * (bb_feather_pct / 100) / 2)
        bb_color = bb.get("color", "#000000").replace("#", "")
        bb_opacity = bb.get("opacity", 0.6)
        color_overlay_enabled = bb.get("colorOverlayEnabled", True)
        
        filters.append(f"{last_stream}split[bb_main][bb_src]")
        filters.append(f"[bb_src]boxblur={bb_blur}:5[bb_blurred_only]")
        if color_overlay_enabled and bb_opacity > 0:
            filters.append(f"[bb_blurred_only]drawbox=x=0:y=0:w=iw:h=ih:color={bb_color}@{bb_opacity}:t=fill[bb_blurred]")
        else:
            filters.append(f"[bb_blurred_only]copy[bb_blurred]")
            
        half_feather = max(1, feather_px)
        filters.append(f"color=black@0:s={out_w}x{out_h},format=yuva420p,geq=lum=\\'if(between(Y,{bb_y}-{half_feather},{bb_y}),255*(Y-{bb_y}+{half_feather})/{half_feather},if(between(Y,{bb_y},{bb_y}+{bb_h}),255,if(between(Y,{bb_y}+{bb_h},{bb_y}+{bb_h}+{half_feather}),255*({bb_y}+{bb_h}+{half_feather}-Y)/{half_feather},0)))\\'[bb_mask]")
        filters.append(f"[bb_blurred][bb_mask]alphamerge[bb_masked]")
        filters.append(f"[bb_main][bb_masked]overlay=0:0[with_blur]")
        last_stream = "[with_blur]"

    filters.append(f"{last_stream}ass=\\'legendas_temp.ass\\':fontsdir=\\'/usr/share/fonts/truetype/custom\\'[subbed]")
    last_stream = "[subbed]"
    
    # 7. Audio Editing Filters (Volume, Speed, Fades)
    audio_filters = []
    last_audio = "[1:a]"
    if ve:
        speed = ve.get("speed", 1.0)
        if speed != 1.0:
            audio_filters.append(f"{last_audio}atempo={speed:.2f}[speed_a]")
            last_audio = "[speed_a]"
            
        vol = ve.get("volume", 100)
        if vol != 100:
            vol_factor = vol / 100.0
            audio_filters.append(f"{last_audio}volume={vol_factor:.2f}[vol_a]")
            last_audio = "[vol_a]"
            
        # Use actual video_dur if available, fallback to config duration
        dur_for_fade = video_dur if video_dur is not None else config.get("video", {}).get("info", {}).get("duration", 0)
        if dur_for_fade > 0:
            actual_duration = dur_for_fade / speed
            fade_in = ve.get("audioFadeIn", 0)
            fade_out = ve.get("audioFadeOut", 0)
            if fade_in > 0:
                audio_filters.append(f"{last_audio}afade=t=in:ss=0:d={fade_in:.1f}[fadein_a]")
                last_audio = "[fadein_a]"
            if fade_out > 0 and actual_duration > fade_out:
                start_fade = actual_duration - fade_out
                audio_filters.append(f"{last_audio}afade=t=out:st={start_fade:.1f}:d={fade_out:.1f}[fadeout_a]")
                last_audio = "[fadeout_a]"

    if audio_filters:
        filters.extend(audio_filters)
        audio_stream = last_audio
    else:
        audio_stream = "1:a"
    
    filter_complex = ";".join(filters)
    cmd = ["ffmpeg", "-y", "-threads", "4", "-filter_threads", "4", "-i", video_in, "-ss", str(start_time), "-i", audio_in]
    for ov_file in overlay_inputs:
        cmd.extend(["-i", ov_file])
    cmd.extend(["-filter_complex", filter_complex, "-map", last_stream, "-map", audio_stream,
        "-c:v", "h264_nvenc", "-cq", "18", "-preset", "p6", "-c:a", "aac", "-b:a", "192k"])
    if video_dur is not None:
        limit_duration = video_dur / speed
        cmd.extend(["-t", f"{limit_duration:.3f}"])
    else:
        cmd.append("-shortest")
    cmd.append(out_file)
    return cmd
"""
        
        # Replace the function definition in the cell
        new_src = []
        in_func = False
        for line in src:
            if line.startswith("def build_ffmpeg_command("):
                in_func = True
                continue
            if in_func and line.startswith("os.chdir(BASE_PATH)"):
                in_func = False
                # Insert new func before this
                for fline in func_str.split("\n"):
                    new_src.append(fline + "\n")
            if not in_func:
                new_src.append(line)
        
        cell["source"] = new_src

    # Update Render Cell (Cell 3)
    render_code = """cell_start(3, "Renderizacao")

import subprocess
import sys

print("Iniciando renderizacao...")
process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
stderr_lines = []
for line in process.stderr:
    stderr_lines.append(line)
    if "frame=" in line:
        print(line.strip(), end="\\r")
process.wait()

if process.returncode != 0:
    error_log = "".join(stderr_lines)
    is_nvenc_error = any(x in error_log.lower() for x in ["nvenc", "unknown encoder", "cuda", "cuinit"])
    if is_nvenc_error and "-c:v h264_nvenc" in " ".join(command):
        print("\\n[GPU Fallback] Erro com h264_nvenc detectado. Tentando renderizacao por CPU (libx264)...")
        cpu_command = []
        skip_next = False
        for k, arg in enumerate(command):
            if skip_next:
                skip_next = False
                continue
            if arg == "-c:v" and command[k+1] == "h264_nvenc":
                cpu_command.extend(["-c:v", "libx264"])
                skip_next = True
            elif arg == "-preset" and command[k+1] == "p6":
                cpu_command.extend(["-preset", "veryfast"])
                skip_next = True
            elif arg == "-cq" and command[k+1] == "18":
                cpu_command.extend(["-crf", "18"])
                skip_next = True
            else:
                cpu_command.append(arg)
        
        print("Rodando renderizacao por CPU...")
        process = subprocess.Popen(cpu_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        stderr_lines = []
        for line in process.stderr:
            stderr_lines.append(line)
            if "frame=" in line:
                print(line.strip(), end="\\r")
        process.wait()

if process.returncode == 0:
    print("\\n\\nRenderizacao concluida com sucesso!")
else:
    print("\\n\\nErro critico na renderizacao do FFmpeg!")
    print("".join(stderr_lines))
    sys.exit(1)

cell_end(3, "done", "Renderizacao concluido")"""

    for cell in nb["cells"]:
        src = cell["source"]
        if any("subprocess.Popen(command" in line for line in src) or any("cell_start(3" in line for line in src):
            cell["source"] = [l + "\n" for l in render_code.split("\n")]

    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)

for nb in NOTEBOOKS:
    update_notebook(nb)
    print(f"Updated {nb}")
