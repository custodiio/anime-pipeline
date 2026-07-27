import sys, os
sys.path.insert(0, '/home/ubuntu/apps/anime-pipeline')
from bot.drive_manager import DriveManager, DRIVE_ATIVO
from bot.database import _get_conn, update_step

drive = DriveManager()
proj_id = 'a6b89fe8-75df-4c43-af04-5badbcc66fab'
temp_dir = '/home/ubuntu/apps/anime-pipeline/uploads/split_temp'

print("Iniciando upload das partes divididas faltantes para o Google Drive...")

parts_files = [
    ('split_info.json', f"{DRIVE_ATIVO}/split_info.json"),
]
for i in range(1, 11):
    parts_files.append((f"video_pt{i}.mp4", f"{DRIVE_ATIVO}/video_pt{i}.mp4"))

for fname, drive_path in parts_files:
    lpath = os.path.join(temp_dir, fname)
    if os.path.exists(lpath):
        print(f"Uploading {fname} -> {drive_path}...")
        drive.salvar(lpath, drive_path)
    else:
        print(f"Aviso: {fname} não encontrado em {temp_dir}")

update_step(proj_id, "step_split", "done", "Video dividido em 10 partes")
update_step(proj_id, "step_omni", "manual", "")
update_step(proj_id, "step_config_ready", "manual", "")
for i in range(1, 31):
    update_step(proj_id, f"step_watermark_pt{i}", "manual", "")
for i in range(0, 31):
    update_step(proj_id, f"step_enhancer_pt{i}", "manual", "")
    update_step(proj_id, f"step_render_pt{i}", "manual", "")
update_step(proj_id, "step_merge", "manual", "")

print("Finalizado upload e atualizado status do projeto para done!")
