"""
Script de Deploy e Sincronização Unificada para o Hugging Face Space
Envia todos os 5 módulos do ecossistema mantendo total integridade e zero conflitos.
"""

import os
import sys
import socket
from pathlib import Path

# DNS bypass para ambientes locais com problemas de resolução
orig_getaddrinfo = socket.getaddrinfo
def custom_getaddrinfo(host, port, *args, **kwargs):
    if host == 'huggingface.co':
        return orig_getaddrinfo('108.158.173.94', port, *args, **kwargs)
    return orig_getaddrinfo(host, port, *args, **kwargs)
socket.getaddrinfo = custom_getaddrinfo

from dotenv import load_dotenv
from huggingface_hub import HfApi

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

token = os.getenv("HF_TOKEN")
repo_id = os.getenv("HF_SPACE_REPO", "alehcrim/anime-pipeline")

if not token:
    print("❌ ERRO: HF_TOKEN não encontrado no .env")
    sys.exit(1)

print("=" * 65)
print(f"🚀 Iniciando Deploy para Hugging Face Space: {repo_id}")
print("=" * 65)

api = HfApi(token=token, endpoint="https://huggingface.co")

# 1. Enviar requirements.txt
req_file = ROOT_DIR / "requirements.txt"
if req_file.exists():
    print("📦 1. Enviando requirements.txt...", flush=True)
    api.upload_file(
        path_or_fileobj=str(req_file),
        path_in_repo="requirements.txt",
        repo_id=repo_id,
        repo_type="space",
        commit_message="Update requirements.txt"
    )

# 2. Enviar Pastas dos Módulos
MODULES_FOLDERS = [
    ("shared", "Upload shared modules & database schemas"),
    ("scrapper", "Upload Module 1 (Douyin/Bilibili Scrapper)"),
    ("douyin_api", "Upload Module 1 (Evil0ctal Douyin API)"),
    ("bot", "Upload Module 2 (Kuma Pipeline & Webhook)"),
    ("post_recap", "Upload Module 3 (Post Recap & Scheduler)"),
    ("tiktok_approval", "Upload Module 4 (TikTok Approval API)"),
    ("seo", "Upload Module 5 (SEO Anime Recap Node.js)")
]

for idx, (folder_name, commit_msg) in enumerate(MODULES_FOLDERS, start=2):
    folder_path = ROOT_DIR / folder_name
    if folder_path.exists() and folder_path.is_dir():
        print(f"📁 {idx}. Enviando {folder_name}/...", flush=True)
        api.upload_folder(
            folder_path=str(folder_path),
            path_in_repo=folder_name,
            repo_id=repo_id,
            repo_type="space",
            commit_message=commit_msg
        )
    else:
        print(f"⚠️ {idx}. Pasta {folder_name}/ não encontrada. Pulando...")

# 3. Enviar scripts de notebooks se existirem
for f_name in ["generate_notebooks.py", "update_notebooks.py"]:
    f_path = ROOT_DIR / f_name
    if f_path.exists():
        print(f"📓 Enviando {f_name}...", flush=True)
        api.upload_file(
            path_or_fileobj=str(f_path),
            path_in_repo=f_name,
            repo_id=repo_id,
            repo_type="space",
            commit_message=f"Upload {f_name}"
        )

# 4. Enviar app.py mestre da raiz
app_file = ROOT_DIR / "app.py"
if app_file.exists():
    print("🚀 Enviando app.py mestre...", flush=True)
    api.upload_file(
        path_or_fileobj=str(app_file),
        path_in_repo="app.py",
        repo_id=repo_id,
        repo_type="space",
        commit_message="Deploy: Update Master Orchestrator app.py (All Modules)"
    )

print("\n" + "=" * 65)
print("✅ Deploy concluído com sucesso no Hugging Face Space!")
print("=" * 65)
