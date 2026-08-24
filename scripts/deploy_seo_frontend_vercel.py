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

# 1. Build
cmd_build = f'npx vercel build --prod --token "{token}" --yes'
print("1. Executando vercel build --prod...")
res_b = subprocess.run(cmd_build, cwd=str(frontend_dir), shell=True, capture_output=True, text=True)
print("BUILD STDOUT:", res_b.stdout)
if res_b.stderr:
    print("BUILD STDERR:", res_b.stderr)

# 2. Deploy prebuilt
cmd_deploy = f'npx vercel deploy --prebuilt --prod --token "{token}" --yes'
print("\n2. Executando deploy prebuilt na Vercel...")
res_d = subprocess.run(cmd_deploy, cwd=str(frontend_dir), shell=True, capture_output=True, text=True)
print("DEPLOY STDOUT:", res_d.stdout)
if res_d.stderr:
    print("DEPLOY STDERR:", res_d.stderr)

print("\n" + "=" * 65)
print("✅ Processo de Deploy finalizado!")
print("=" * 65)
