import json, os

for i in range(1, 6):
    nb_path = f"notebooks/renderizador-kaggle-pt-{i}.ipynb"
    if not os.path.exists(nb_path):
        continue
        
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
        
    # Cell 0: Add DRIVE_ATIVO
    cell0 = nb["cells"][0]
    src0 = "".join(cell0["source"])
    if 'DRIVE_ATIVO = "KAGGLE/PIPELINE/ATIVO"' not in src0:
        src0 = src0.replace('DRIVE_ENHANCER = "KAGGLE/PIPELINE/ENHANCER"', 'DRIVE_ATIVO = "KAGGLE/PIPELINE/ATIVO"\nDRIVE_ENHANCER = "KAGGLE/PIPELINE/ENHANCER"')
        cell0["source"] = [line + "\n" if not line.endswith("\n") else line for line in src0.splitlines()]

    # Cell 1: Download split_info and slice ASS
    cell1 = nb["cells"][1]
    src1 = "".join(cell1["source"])
    if "split_info.json" not in src1:
        new_logic = f'''baixar_do_drive(f"{{DRIVE_ATIVO}}/split_info.json", f"{{BASE_PATH}}/split_info.json")

import json
with open(f"{{BASE_PATH}}/split_info.json", "r") as f:
    split_info = json.load(f)

part_idx = {i}
start_time = (part_idx - 1) * split_info["part_duration"]
print(f"Start time para pt{{part_idx}}: {{start_time}}")

def parse_ass_time(t_str):
    h, m, s = t_str.split(':')
    s, cs = s.split('.')
    return int(h)*3600 + int(m)*60 + int(s) + int(cs)/100.0

def format_ass_time(secs):
    if secs < 0: secs = 0
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    cs = int(round((secs - int(secs)) * 100))
    if cs == 100:
        s += 1; cs = 0
    return f"{{h}}:{{m:02d}}:{{s:02d}}.{{cs:02d}}"

out = []
with open(f"{{BASE_PATH}}/legendas.ass", "r", encoding="utf-8") as f:
    for line in f:
        if line.startswith('Dialogue:'):
            parts = line.split(',', 9)
            start_ms = parse_ass_time(parts[1]) - start_time
            end_ms = parse_ass_time(parts[2]) - start_time
            if end_ms <= 0: continue
            if start_ms < 0: start_ms = 0
            parts[1] = format_ass_time(start_ms)
            parts[2] = format_ass_time(end_ms)
            out.append(','.join(parts))
        else:
            out.append(line)

with open(f"{{BASE_PATH}}/legendas_temp.ass", "w", encoding="utf-8") as f:
    f.writelines(out)
print("Legendas ajustadas e cortadas para esta parte.")

'''
        src1 = src1.replace('shutil.copy2(f"{BASE_PATH}/legendas.ass", f"{BASE_PATH}/legendas_temp.ass")', new_logic)
        cell1["source"] = [line + "\n" if not line.endswith("\n") else line for line in src1.splitlines()]

    # Cell 2: ffmpeg command modification
    cell2 = nb["cells"][2]
    src2 = "".join(cell2["source"])
    if "start_time" not in src2:
        src2 = src2.replace('def build_ffmpeg_command(config, video_in, audio_in, ass_in, out_file):', 'def build_ffmpeg_command(config, video_in, audio_in, ass_in, out_file, start_time=0):')
        
        # update overlays timeOut and timeIn
        src2 = src2.replace('tin = ov.get("timeIn", 0)', 'tin = ov.get("timeIn", 0) - start_time')
        src2 = src2.replace('tout = ov.get("timeOut", 0)', 'tout = ov.get("timeOut", 0) - start_time')
        src2 = src2.replace('if tout == 0: tout = 999999', 'if ov.get("timeOut", 0) == 0: tout = 999999\n            if tout <= 0: continue\n            if tin < 0: tin = 0')
        
        # Add -ss start_time to input audio
        src2 = src2.replace('"-i", audio_in]', '"-ss", str(start_time), "-i", audio_in]')
        
        # pass start_time to the function call
        src2 = src2.replace('command = build_ffmpeg_command(config, VIDEO_INPUT, AUDIO_INPUT, ASS_LOCAL, OUTPUT_FILE)', 'command = build_ffmpeg_command(config, VIDEO_INPUT, AUDIO_INPUT, ASS_LOCAL, OUTPUT_FILE, start_time)')
        
        cell2["source"] = [line + "\n" if not line.endswith("\n") else line for line in src2.splitlines()]
        
    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1)
        
    print(f"Patched {nb_path}")
