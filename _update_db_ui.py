import re

with open('bot/database.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_steps = """    steps = [
        ("step_upload", "Upload & Preparação"),
        ("step_split", "Divisão em 2 partes"),
        ("step_omni", "Omni-Anime-Ver"),
        ("step_watermark_pt1", "Watermark PT1"),
        ("step_watermark_pt2", "Watermark PT2"),
        ("step_enhancer_pt1", "Enhancer PT1"),
        ("step_enhancer_pt2", "Enhancer PT2"),
        ("step_session_created", "Sessão VideoRender"),
        ("step_config_ready", "Config Pronta"),
        ("step_render_pt1", "Render PT1"),
        ("step_render_pt2", "Render PT2"),
        ("step_merge", "Merge Final"),
    ]"""

new_steps = """    steps = [
        ("step_upload", "Upload & Preparação"),
        ("step_split", "Divisão em 5 partes"),
        ("step_omni", "Omni-Anime-Ver"),
    ]
    for i in range(1, 6): steps.append((f"step_watermark_pt{i}", f"Watermark PT{i}"))
    for i in range(1, 6): steps.append((f"step_enhancer_pt{i}", f"Enhancer PT{i}"))
    steps.append(("step_session_created", "Sessão VideoRender"))
    steps.append(("step_config_ready", "Config Pronta"))
    for i in range(1, 6): steps.append((f"step_render_pt{i}", f"Render PT{i}"))
    steps.append(("step_merge", "Merge Final"))"""

content = content.replace(old_steps, new_steps)

with open('bot/database.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Database formatter atualizado!")
