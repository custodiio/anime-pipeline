import re

with open('bot/pipeline_controller.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. iniciar_projeto
content = re.sub(
    r'update_step\(pid, "step_watermark_pt1", "skipped", "User disabled"\)\s+update_step\(pid, "step_watermark_pt2", "skipped", "User disabled"\)',
    r'for i in range(1, 6): update_step(pid, f"step_watermark_pt{i}", "skipped", "User disabled")',
    content
)

content = re.sub(
    r'update_step\(pid, "step_enhancer_pt1", "skipped", "User disabled"\)\s+update_step\(pid, "step_enhancer_pt2", "skipped", "User disabled"\)',
    r'for i in range(1, 6): update_step(pid, f"step_enhancer_pt{i}", "skipped", "User disabled")',
    content
)

content = re.sub(
    r'pt1_path, pt2_path = split_video\(video_path, temp_dir\)\s+self\.drive\.salvar\(pt1_path, f"\{DRIVE_ATIVO\}/video_pt1\.mp4"\)\s+self\.drive\.salvar\(pt2_path, f"\{DRIVE_ATIVO\}/video_pt2\.mp4"\)\s+update_step\(pid, "step_split", "done", "Video dividido em 2 partes"\)',
    r'parts_paths = split_video(video_path, temp_dir, parts=5)\n            for i, p_path in enumerate(parts_paths, 1):\n                self.drive.salvar(p_path, f"{DRIVE_ATIVO}/video_pt{i}.mp4")\n            update_step(pid, "step_split", "done", "Video dividido em 5 partes")',
    content
)

# 2. disparar_*
content = re.sub(
    r'def disparar_watermark.*?dispatch_parallel.*?project_id\)',
    r'def disparar_watermark(self, project_id):\n        for i in range(1, 6): update_step(project_id, f"step_watermark_pt{i}", "running")\n        dispatch_parallel([f"wm-pt{i}" for i in range(1, 6)], project_id)',
    content, flags=re.DOTALL
)

content = re.sub(
    r'def disparar_enhancer.*?dispatch_parallel.*?project_id\)',
    r'def disparar_enhancer(self, project_id):\n        for i in range(1, 6): update_step(project_id, f"step_enhancer_pt{i}", "running")\n        dispatch_parallel([f"enhancer-pt{i}" for i in range(1, 6)], project_id)',
    content, flags=re.DOTALL
)

content = re.sub(
    r'def disparar_render.*?dispatch_parallel.*?project_id\)',
    r'def disparar_render(self, project_id):\n        for i in range(1, 6): update_step(project_id, f"step_render_pt{i}", "running")\n        dispatch_parallel([f"render-pt{i}" for i in range(1, 6)], project_id)',
    content, flags=re.DOTALL
)

# 3. verificar_e_avancar - variables
old_vars = """        w1 = project["step_watermark_pt1"]
        w2 = project["step_watermark_pt2"]
        e1 = project["step_enhancer_pt1"]
        e2 = project["step_enhancer_pt2"]
        conf = project["step_config_ready"]
        omni = project["step_omni"]
        r1 = project["step_render_pt1"]
        r2 = project["step_render_pt2"]

        w_ok = (w1 in ["done", "skipped"]) and (w2 in ["done", "skipped"])
        e_ok = (e1 in ["done", "skipped"]) and (e2 in ["done", "skipped"])"""

new_vars = """        w_vals = [project.get(f"step_watermark_pt{i}") for i in range(1, 6)]
        e_vals = [project.get(f"step_enhancer_pt{i}") for i in range(1, 6)]
        r_vals = [project.get(f"step_render_pt{i}") for i in range(1, 6)]
        conf = project.get("step_config_ready")
        omni = project.get("step_omni")

        w_ok = all(v in ["done", "skipped"] for v in w_vals)
        e_ok = all(v in ["done", "skipped"] for v in e_vals)
        r_ok = all(v == "done" for v in r_vals)"""

content = content.replace(old_vars, new_vars)

# w1, e1 replacements
content = content.replace('w1 == "pending"', 'w_vals[0] == "pending"')
content = content.replace('e1 == "pending"', 'e_vals[0] == "pending"')
content = content.replace('w1 == "skipped"', 'w_vals[0] == "skipped"')
content = content.replace('e1 == "skipped"', 'e_vals[0] == "skipped"')
content = content.replace('r1 == "pending"', 'r_vals[0] == "pending"')

content = content.replace('r1 == "done" and r2 == "done"', 'r_ok')

# 4. Copy logic for watermark
old_wm_copy = """                ok1 = self.drive.copiar_arquivo("KAGGLE/PIPELINE/ATIVO/video_pt1.mp4", "KAGGLE/PIPELINE/WATERMARK/pt1_limpo.mp4")
                ok2 = self.drive.copiar_arquivo("KAGGLE/PIPELINE/ATIVO/video_pt2.mp4", "KAGGLE/PIPELINE/WATERMARK/pt2_limpo.mp4")
                if not (ok1 and ok2):"""

new_wm_copy = """                all_copied = True
                for i in range(1, 6):
                    ok = self.drive.copiar_arquivo(f"KAGGLE/PIPELINE/ATIVO/video_pt{i}.mp4", f"KAGGLE/PIPELINE/WATERMARK/pt{i}_limpo.mp4")
                    if not ok: all_copied = False
                if not all_copied:"""
content = content.replace(old_wm_copy, new_wm_copy)

# 5. Copy logic for enhancer
old_enh_copy = """                ok1 = self.drive.copiar_arquivo("KAGGLE/PIPELINE/WATERMARK/pt1_limpo.mp4", "KAGGLE/PIPELINE/ENHANCER/pt1_enhanced.mp4")
                ok2 = self.drive.copiar_arquivo("KAGGLE/PIPELINE/WATERMARK/pt2_limpo.mp4", "KAGGLE/PIPELINE/ENHANCER/pt2_enhanced.mp4")
                if not (ok1 and ok2):"""

new_enh_copy = """                all_copied = True
                for i in range(1, 6):
                    ok = self.drive.copiar_arquivo(f"KAGGLE/PIPELINE/WATERMARK/pt{i}_limpo.mp4", f"KAGGLE/PIPELINE/ENHANCER/pt{i}_enhanced.mp4")
                    if not ok: all_copied = False
                if not all_copied:"""
content = content.replace(old_enh_copy, new_enh_copy)

with open('bot/pipeline_controller.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Pipeline controller atualizado!")
