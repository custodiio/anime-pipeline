import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

token = os.getenv("VERCEL_TOKEN")
if not token:
    print("❌ VERCEL_TOKEN não encontrado no .env")
    sys.exit(1)

frontend_dir = ROOT_DIR / "seo-frontend"

print("=" * 65)
print("🚀 Deploy do SEO AnimeRecap Frontend na Vercel...")
print(f"Diretório: {frontend_dir}")
print("=" * 65)

# Deploy direto
cmd_deploy = f'npx vercel --prod --token "{token}" --yes --name kuma-seo-frontend'
print("Executando deploy na Vercel...")
res = subprocess.run(cmd_deploy, cwd=str(frontend_dir), shell=True, capture_output=True, text=True)
print("DEPLOY STDOUT:", res.stdout)
print("DEPLOY STDERR:", res.stderr)

print("=" * 65)
