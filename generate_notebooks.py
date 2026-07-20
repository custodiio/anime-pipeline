"""
Gera os notebooks padronizados com cell_start/cell_end e caminhos Drive corretos.
Roda: python generate_notebooks.py
"""
import json, os

NOTEBOOKS_DIR = os.path.join(os.path.dirname(__file__), "notebooks")

KAGGLE_META = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.12.12", "mimetype": "text/x-python",
                      "codemirror_mode": {"name": "ipython", "version": 3},
                      "pygments_lexer": "ipython3", "nbconvert_exporter": "python", "file_extension": ".py"},
    "kaggle": {"accelerator": "nvidiaTeslaT4", "dataSources": [], "dockerImageVersionId": 31329,
               "isInternetEnabled": True, "language": "python", "sourceType": "notebook", "isGpuEnabled": True}
}

# ── Celula 0: Setup padrao (igual para todos) ──
SETUP_CELL = r'''import os, sys, json, subprocess, time, io, gc, shutil, glob
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import requests as http_requests

NOTEBOOK_NAME = "__NOTEBOOK_NAME__"
STEP_NAME = "__STEP_NAME__"

print("Instalando dependencias...")
os.system("apt-get install -y ffmpeg > /dev/null 2>&1")

def _load_secrets():
    try:
        from kaggle_secrets import UserSecretsClient
        _s = UserSecretsClient()
        def _get(name):
            try: return _s.get_secret(name)
            except: return ""
        print("Carregando Kaggle Secrets...")
        return _get
    except ImportError:
        from dotenv import load_dotenv; load_dotenv()
        return lambda name: os.getenv(name, "")

_get = _load_secrets()
DRIVE_REFRESH_TOKEN = _get("DRIVE_REFRESH_TOKEN")
DRIVE_CLIENT_ID = _get("DRIVE_CLIENT_ID")
DRIVE_CLIENT_SECRET = _get("DRIVE_CLIENT_SECRET")
HF_TOKEN = _get("HF_TOKEN")
DATABASE_URL = _get("DATABASE_URL")
PROJECT_ID = _get("PIPELINE_PROJECT_ID")
PIPELINE_WEBHOOK_URL = _get("PIPELINE_WEBHOOK_URL")

print("Autenticando Drive...")
try:
    _creds = Credentials(token=None, refresh_token=DRIVE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=DRIVE_CLIENT_ID, client_secret=DRIVE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/drive"])
    _creds.refresh(Request())
    drive_service = build("drive", "v3", credentials=_creds)
    print("Drive autenticado!")
except Exception as e:
    drive_service = None
    print(f"Falha Drive: {e}")

def _buscar_id(caminho):
    partes = caminho.strip("/").split("/")
    pid = "root"
    for p in partes:
        q = f"name='{p}' and '{pid}' in parents and trashed=false"
        r = drive_service.files().list(q=q, fields="files(id,mimeType)", orderBy="modifiedTime desc").execute()
        a = r.get("files", [])
        if not a: return None
        pid = a[0]["id"]
    return pid

def _garantir_pasta(caminho):
    partes = caminho.strip("/").split("/")
    pid = "root"
    for p in partes:
        q = f"name='{p}' and '{pid}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
        r = drive_service.files().list(q=q, fields="files(id)").execute()
        e = r.get("files", [])
        if e: pid = e[0]["id"]
        else:
            nova = drive_service.files().create(body={"name": p, "mimeType": "application/vnd.google-apps.folder", "parents": [pid]}, fields="id").execute()
            pid = nova["id"]
    return pid

def baixar_do_drive(caminho_drive, destino_local):
    if os.path.exists(destino_local): return True
    try:
        fid = _buscar_id(caminho_drive)
        if not fid: print(f"  Nao encontrado: {caminho_drive}"); return False
        req = drive_service.files().get_media(fileId=fid)
        os.makedirs(os.path.dirname(destino_local) or ".", exist_ok=True)
        with open(destino_local, "wb") as fh:
            dl = MediaIoBaseDownload(fh, req); done = False
            while not done: _, done = dl.next_chunk()
        print(f"  Baixado: {caminho_drive}"); return True
    except Exception as ex: print(f"  Erro: {caminho_drive}: {ex}"); return False

def salvar_no_drive(caminho_local, caminho_drive):
    if not drive_service or not os.path.exists(caminho_local): return
    try:
        partes = caminho_drive.strip("/").split("/")
        nome = partes[-1]; pasta = "/".join(partes[:-1]) if len(partes) > 1 else ""
        pid = _garantir_pasta(pasta) if pasta else "root"
        q = f"name='{nome}' and '{pid}' in parents and trashed=false"
        r = drive_service.files().list(q=q, fields="files(id)").execute()
        e = r.get("files", []); media = MediaFileUpload(caminho_local, resumable=True)
        if e: drive_service.files().update(fileId=e[0]["id"], media_body=media).execute()
        else: drive_service.files().create(body={"name": nome, "parents": [pid]}, media_body=media, fields="id").execute()
        print(f"  Salvo: {caminho_drive}")
    except Exception as ex: print(f"  Erro salvar {caminho_drive}: {ex}")

_cell_timers = {}
def _db_exec(query, params):
    if not DATABASE_URL: return
    try:
        import psycopg2; conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute(query, params); conn.commit(); cur.close(); conn.close()
    except: pass

def cell_start(idx, name=""):
    _cell_timers[idx] = time.time()
    print(f"\n{'='*50}\n  CELULA [{idx}] {name}\n{'='*50}")
    if not PROJECT_ID: return
    _db_exec("INSERT INTO pipeline_cell_tracking (project_id,notebook,cell_index,cell_name,status,started_at) VALUES (%s::uuid,%s,%s,%s,'running',NOW()) ON CONFLICT DO NOTHING", (PROJECT_ID, NOTEBOOK_NAME, idx, name))
    _db_exec("UPDATE pipeline_cell_tracking SET status='running',started_at=NOW(),finished_at=NULL,cell_name=%s WHERE project_id=%s::uuid AND notebook=%s AND cell_index=%s", (name, PROJECT_ID, NOTEBOOK_NAME, idx))

def cell_end(idx, status="done", msg=""):
    elapsed = ""
    if idx in _cell_timers:
        s = int(time.time() - _cell_timers.pop(idx))
        elapsed = f" ({s//60}m{s%60}s)" if s >= 60 else f" ({s}s)"
    icon = "OK" if status == "done" else "ERRO"
    print(f"  [{icon}] CELULA [{idx}] {status}{elapsed}: {msg}\n{'─'*50}")
    if not PROJECT_ID: return
    _db_exec("UPDATE pipeline_cell_tracking SET status=%s,finished_at=NOW(),duration_seconds=EXTRACT(EPOCH FROM(NOW()-started_at)),message=%s WHERE project_id=%s::uuid AND notebook=%s AND cell_index=%s", (status, msg, PROJECT_ID, NOTEBOOK_NAME, idx))

def report_step(status, msg=""):
    print(f"\nNOTEBOOK FINALIZADO: {STEP_NAME} -> {status}")
    if PROJECT_ID and PIPELINE_WEBHOOK_URL:
        try:
            http_requests.post(f"{PIPELINE_WEBHOOK_URL}/webhook/status", json={"project_id": PROJECT_ID, "step": STEP_NAME, "status": status, "message": msg}, timeout=15)
        except: pass
    if not PROJECT_ID: return
    _db_exec(f"UPDATE pipeline_projects SET {STEP_NAME}=%s,current_step=%s,updated_at=NOW() WHERE id=%s::uuid", (status, STEP_NAME.replace("step_",""), PROJECT_ID))
    _db_exec("INSERT INTO pipeline_logs (project_id,step,status,message) VALUES (%s::uuid,%s,%s,%s)", (PROJECT_ID, STEP_NAME, status, msg))

DRIVE_ATIVO = "KAGGLE/PIPELINE/ATIVO"
DRIVE_WATERMARK = "KAGGLE/PIPELINE/WATERMARK"
DRIVE_ENHANCER = "KAGGLE/PIPELINE/ENHANCER"
DRIVE_OMNI = "KAGGLE/PIPELINE/OMNI"
DRIVE_RENDER = "KAGGLE/PIPELINE/RENDER"
DRIVE_FINAL = "KAGGLE/PIPELINE/FINAL"
BASE_PATH = "/kaggle/working"
os.makedirs(BASE_PATH, exist_ok=True)

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

cell_end(0, "done", "Setup concluido")'''


def make_cell(source_str):
    lines = source_str.split("\n")
    # Jupyter exige que cada linha (exceto a última) termine com \n
    source = [line + "\n" for line in lines[:-1]]
    if lines[-1]:  # Última linha sem \n (padrão Jupyter)
        source.append(lines[-1])
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source}

def make_nb(cells_source, notebook_name, step_name):
    setup = SETUP_CELL.replace("__NOTEBOOK_NAME__", notebook_name).replace("__STEP_NAME__", step_name)
    # NÃO chamar cell_start(0,...) antes do setup, pois a função ainda não existe
    cells = [make_cell(setup)]
    for i, (name, code) in enumerate(cells_source, 1):
        wrapped = f"cell_start({i}, '{name}')\n\n{code}\n\ncell_end({i}, 'done', '{name} concluido')"
        cells.append(make_cell(wrapped))
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": KAGGLE_META, "cells": cells}
    return nb

def save_nb(nb, filename):
    path = os.path.join(NOTEBOOKS_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print(f"  Salvo: {filename}")

# ══════════════════════════════════════════════════════════════
# WATERMARK REMOVER PT1
# ══════════════════════════════════════════════════════════════
def make_watermark_cells(part_num):
    pt = f"pt{part_num}"
    return [
        ("Download dos Arquivos", f'''import cv2, numpy as np
baixar_do_drive(f"{{DRIVE_ATIVO}}/video_{pt}.mp4", f"{{BASE_PATH}}/video_{pt}.mp4")
baixar_do_drive(f"{{DRIVE_ATIVO}}/mask.png", f"{{BASE_PATH}}/mask.png")
print("Arquivos prontos!")'''),

        ("Processamento Watermark", f'''INPUT = f"{{BASE_PATH}}/video_{pt}.mp4"
MASK = f"{{BASE_PATH}}/mask.png"
OUTPUT = f"{{BASE_PATH}}/{pt}_limpo.mp4"

import cv2, numpy as np

# Se mask não existe, copiar direto sem processamento
if not os.path.exists(MASK):
    print("  Mask nao encontrada, copiando video sem watermark removal...")
    shutil.copy2(INPUT, OUTPUT)
    count = 0
else:
    cap = cv2.VideoCapture(INPUT)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    FPS = cap.get(cv2.CAP_PROP_FPS)
    TOTAL = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    mask_np = cv2.imread(MASK, cv2.IMREAD_GRAYSCALE)
    mask_np = cv2.resize(mask_np, (W, H))
    _, mask_bin = cv2.threshold(mask_np, 10, 255, cv2.THRESH_BINARY)

    pipe = subprocess.Popen([
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{{W}}x{{H}}", "-pix_fmt", "bgr24", "-r", str(FPS), "-i", "pipe:0",
        "-c:v", "h264_nvenc", "-preset", "p2", "-b:v", "5M", "-c:a", "copy", OUTPUT
    ], stdin=subprocess.PIPE)

    count = 0
    while True:
        ret, frame = cap.read()
        if not ret: break
        out = cv2.inpaint(frame, mask_bin, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
        pipe.stdin.write(out.tobytes())
        count += 1
        if count % 500 == 0:
            print(f"  Frame {{count}}/{{TOTAL}} ({{count/TOTAL*100:.1f}}%)")

    cap.release()
    pipe.stdin.close()
    pipe.wait()
print(f"  {{count}} frames processados")'''),

        ("Upload Resultado", f'''salvar_no_drive(f"{{BASE_PATH}}/{pt}_limpo.mp4", f"{{DRIVE_WATERMARK}}/{pt}_limpo.mp4")'''),

        ("Finalizacao", f'''report_step("done", f"Watermark {pt.upper()} concluido - {{count}} frames")'''),
    ]

# ══════════════════════════════════════════════════════════════
# VIDEO ENHANCER PT1
# ══════════════════════════════════════════════════════════════
VE_COMMON_SETUP = '''print("Instalando Vulkan + Real-ESRGAN...")
os.system("apt-get update -qq")
os.system("apt-get remove -y mesa-vulkan-drivers -qq 2>/dev/null")
os.system("apt-get install -y libvulkan1 vulkan-tools -qq 2>/dev/null")
driver_ver = subprocess.check_output("nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1", shell=True).decode().strip().split(".")[0]
os.system(f"apt-get install -y libnvidia-gl-{driver_ver} -qq 2>/dev/null || apt-get install -y libnvidia-gl-550 -qq 2>/dev/null")
icd = "/usr/share/vulkan/icd.d/nvidia_icd.json"
if os.path.exists(icd): os.environ["VK_ICD_FILENAMES"] = icd
os.system("wget -q https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip")
os.system("unzip -o realesrgan-ncnn-vulkan-20220424-ubuntu.zip -d realesrgan > /dev/null")
os.system("chmod +x realesrgan/realesrgan-ncnn-vulkan")
REALESRGAN = "/kaggle/working/realesrgan/realesrgan-ncnn-vulkan"
print("Real-ESRGAN pronto!")'''

def make_enhancer_cells(part_num):
    pt = f"pt{part_num}"
    return [
        ("Setup Real-ESRGAN", VE_COMMON_SETUP),
        ("Download Video Limpo", f'''baixar_do_drive(f"{{DRIVE_WATERMARK}}/{pt}_limpo.mp4", f"{{BASE_PATH}}/{pt}_limpo.mp4")
print("Video baixado!")'''),
        ("Extrair Frames", f'''FRAMES_DIR = f"{{BASE_PATH}}/frames_{pt}"
os.makedirs(FRAMES_DIR, exist_ok=True)
subprocess.run(f"ffmpeg -i {{BASE_PATH}}/{pt}_limpo.mp4 -q:v 2 {{FRAMES_DIR}}/frame_%08d.jpg -hide_banner -loglevel error", shell=True)
total_frames = len(os.listdir(FRAMES_DIR))
print(f"  {{total_frames}} frames extraidos")'''),
        ("Upscaling Dual GPU", f'''FRAMES_DIR = f"{{BASE_PATH}}/frames_{pt}"
UP_DIR = f"{{BASE_PATH}}/upscaled_{pt}"
os.makedirs(UP_DIR, exist_ok=True)
os.makedirs(f"{{BASE_PATH}}/fg0", exist_ok=True)
os.makedirs(f"{{BASE_PATH}}/fg1", exist_ok=True)
os.makedirs(f"{{BASE_PATH}}/ug0", exist_ok=True)
os.makedirs(f"{{BASE_PATH}}/ug1", exist_ok=True)
import threading
all_f = sorted(glob.glob(f"{{FRAMES_DIR}}/*.jpg"))
mid = len(all_f) // 2
for f in all_f[:mid]: shutil.copy(f, f"{{BASE_PATH}}/fg0/")
for f in all_f[mid:]: shutil.copy(f, f"{{BASE_PATH}}/fg1/")
print(f"  GPU0: {{mid}} | GPU1: {{len(all_f)-mid}}")
def run_gpu(cmd): subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
t0 = threading.Thread(target=run_gpu, args=(f"{{REALESRGAN}} -i {{BASE_PATH}}/fg0/ -o {{BASE_PATH}}/ug0/ -n realesr-animevideov3 -s 2 -f jpg -g 0",))
t1 = threading.Thread(target=run_gpu, args=(f"{{REALESRGAN}} -i {{BASE_PATH}}/fg1/ -o {{BASE_PATH}}/ug1/ -n realesr-animevideov3 -s 2 -f jpg -g 1",))
t0.start(); t1.start()
while t0.is_alive() or t1.is_alive():
    d0 = len(glob.glob(f"{{BASE_PATH}}/ug0/*.jpg"))
    d1 = len(glob.glob(f"{{BASE_PATH}}/ug1/*.jpg"))
    print(f"  GPU0: {{d0}}/{{mid}} | GPU1: {{d1}}/{{len(all_f)-mid}}", end="\\r")
    time.sleep(5)
t0.join(); t1.join()
for f in sorted(glob.glob(f"{{BASE_PATH}}/ug0/*.jpg")) + sorted(glob.glob(f"{{BASE_PATH}}/ug1/*.jpg")):
    shutil.move(f, UP_DIR)
total_up = len(glob.glob(f"{{UP_DIR}}/*.jpg"))
print(f"\\n  {{total_up}} frames upscaled")
shutil.rmtree(f"{{BASE_PATH}}/fg0", ignore_errors=True)
shutil.rmtree(f"{{BASE_PATH}}/fg1", ignore_errors=True)
shutil.rmtree(f"{{BASE_PATH}}/ug0", ignore_errors=True)
shutil.rmtree(f"{{BASE_PATH}}/ug1", ignore_errors=True)'''),
        ("Montar Video Final", f'''UP_DIR = f"{{BASE_PATH}}/upscaled_{pt}"
INPUT_VIDEO = f"{{BASE_PATH}}/{pt}_limpo.mp4"
OUTPUT = f"{{BASE_PATH}}/{pt}_enhanced.mp4"
frames = sorted(glob.glob(f"{{UP_DIR}}/*.jpg"))
fps_raw = subprocess.check_output(f"ffprobe -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 {{INPUT_VIDEO}}", shell=True).decode().strip()
num, den = (fps_raw.split("/") + ["1"])[:2]
fps = float(num) / float(den)
dur_f = 1.0 / fps
concat = f"{{BASE_PATH}}/concat_{pt}.txt"
with open(concat, "w") as fl:
    for fr in frames:
        fl.write(f"file '{{os.path.abspath(fr)}}'\\n")
        fl.write(f"duration {{dur_f:.6f}}\\n")
ret = subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat,"-i",INPUT_VIDEO,"-map","0:v:0","-map","1:a:0?","-c:a","copy","-pix_fmt","yuv420p","-c:v","h264_nvenc","-preset","p4","-cq","18",OUTPUT], capture_output=True).returncode
if ret != 0:
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat,"-i",INPUT_VIDEO,"-map","0:v:0","-map","1:a:0?","-c:a","copy","-pix_fmt","yuv420p","-c:v","libx264","-preset","veryfast","-crf","18",OUTPUT], capture_output=True)
print(f"  Video montado: {{OUTPUT}}")'''),
        ("Upload e Limpeza", f'''salvar_no_drive(f"{{BASE_PATH}}/{pt}_enhanced.mp4", f"{{DRIVE_ENHANCER}}/{pt}_enhanced.mp4")
shutil.rmtree(f"{{BASE_PATH}}/frames_{pt}", ignore_errors=True)
shutil.rmtree(f"{{BASE_PATH}}/upscaled_{pt}", ignore_errors=True)
report_step("done", "Enhancer {pt.upper()} concluido")'''),
    ]

# ══════════════════════════════════════════════════════════════
# MERGE FINAL
# ══════════════════════════════════════════════════════════════
MERGE_CELLS = [
    ("Download das Partes", '''parts_list = []
if baixar_do_drive(f"{DRIVE_RENDER}/pt0_renderizado.mp4", f"{BASE_PATH}/pt0_renderizado.mp4"):
    parts_list.append(0)
    print("  [INTRO] pt0_renderizado.mp4 baixado com sucesso!")

for i in range(1, 31):
    if baixar_do_drive(f"{DRIVE_RENDER}/pt{i}_renderizado.mp4", f"{BASE_PATH}/pt{i}_renderizado.mp4"):
        parts_list.append(i)
        print(f"  Parte {i} (pt{i}_renderizado.mp4) baixada!")

print(f"Total de {len(parts_list)} partes baixadas para o merge: {parts_list}")'''),
    ("Merge Final", '''OUTPUT = f"{BASE_PATH}/video_final.mp4"
concat_file = f"{BASE_PATH}/merge_concat.txt"
with open(concat_file, "w") as f:
    for i in parts_list:
        f.write(f"file '{BASE_PATH}/pt{i}_renderizado.mp4'\\n")
subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",concat_file,"-c","copy",OUTPUT], check=True)
print(f"  Merge concluido: {OUTPUT}")'''),
    ("Upload Final", '''salvar_no_drive(f"{BASE_PATH}/video_final.mp4", f"{DRIVE_FINAL}/video_final.mp4")
report_step("done", "Merge final concluido")
print("VIDEO FINAL PRONTO!")'''),
]

# ══════════════════════════════════════════════════════════════
# GERAR TUDO
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs(NOTEBOOKS_DIR, exist_ok=True)
    
    print("Gerando notebooks padronizados...")
    
    # 1. Gerar todas as 30 partes de Watermark Remover (pt1 a pt30)
    for i in range(1, 31):
        nb = make_nb(make_watermark_cells(i), f"anime-watermark-remover-pt-{i}", f"step_watermark_pt{i}")
        save_nb(nb, f"anime-watermark-remover-pt-{i}.ipynb")
        
    # 2. Gerar todas as 31 partes de Video Enhancer (pt0 a pt30)
    for i in range(0, 31):
        nb = make_nb(make_enhancer_cells(i), f"anime-video-enhancer-pt-{i}", f"step_enhancer_pt{i}")
        save_nb(nb, f"anime-video-enhancer-pt-{i}.ipynb")
        
    # 3. Gerar todas as 11 partes do Renderizador (pt0 a pt10) clonando o pt-1 base
    base_render_path = os.path.join(NOTEBOOKS_DIR, "anime-renderizador-kaggle-pt-1.ipynb")
    if os.path.exists(base_render_path):
        with open(base_render_path, "r", encoding="utf-8") as f_base:
            base_render_nb = json.load(f_base)
            
        for i in range(0, 31):
            # Clona o base_render_nb
            part_nb = json.loads(json.dumps(base_render_nb))
            
            # Ajusta o setup (célula 0)
            setup_source = part_nb["cells"][0]["source"]
            new_setup = []
            for line in setup_source:
                line = line.replace('NOTEBOOK_NAME = "renderizador-kaggle-pt-1"', f'NOTEBOOK_NAME = "renderizador-kaggle-pt-{i}"')
                line = line.replace('STEP_NAME = "step_render_pt1"', f'STEP_NAME = "step_render_pt{i}"')
                new_setup.append(line)
            part_nb["cells"][0]["source"] = new_setup
            
            # Ajusta o download (célula 1)
            if i == 0:
                download_source = [
                    "cell_start(1, \"Download Arquivos do Drive\")\n",
                    "\n",
                    "# Definir variaveis do render pt0 (introdução)\n",
                    "VIDEO_INPUT = f\"{BASE_PATH}/pt0_enhanced.mp4\"\n",
                    "AUDIO_INPUT = f\"{BASE_PATH}/audio_dublado.mp3\"\n",
                    "ASS_LOCAL = f\"{BASE_PATH}/legendas.ass\"\n",
                    "OUTPUT_FILE = f\"{BASE_PATH}/pt0_renderizado.mp4\"\n",
                    "start_time = 0\n",
                    "\n",
                    "# Baixar video enhanced + config + legendas + audio para pt0\n",
                    "baixar_do_drive(f\"{DRIVE_ENHANCER}/pt0_enhanced.mp4\", VIDEO_INPUT)\n",
                    "if not os.path.exists(VIDEO_INPUT):\n",
                    "    baixar_do_drive(f\"{DRIVE_WATERMARK}/pt0_limpo.mp4\", VIDEO_INPUT)\n",
                    "baixar_do_drive(f\"{DRIVE_OMNI}/videorender-project.json\", f\"{BASE_PATH}/videorender-project.json\")\n",
                    "baixar_do_drive(f\"{DRIVE_OMNI}/intro_legendas.ass\", ASS_LOCAL)\n",
                    "if not os.path.exists(ASS_LOCAL):\n",
                    "    baixar_do_drive(f\"{DRIVE_OMNI}/legendas.ass\", ASS_LOCAL)\n",
                    "baixar_do_drive(f\"{DRIVE_OMNI}/intro_audio.mp3\", AUDIO_INPUT)\n",
                    "if not os.path.exists(AUDIO_INPUT):\n",
                    "    baixar_do_drive(f\"{DRIVE_OMNI}/audio_dublado.mp3\", AUDIO_INPUT)\n",
                    "if not os.path.exists(AUDIO_INPUT):\n",
                    "    baixar_do_drive(\"KAGGLE/AUDIO_DUB/OUTPUT/audio_dublado_Completo.mp3\", AUDIO_INPUT)\n",
                    "if not os.path.exists(AUDIO_INPUT):\n",
                    "    baixar_do_drive(\"KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3\", AUDIO_INPUT)\n",
                    "if not os.path.exists(AUDIO_INPUT):\n",
                    "    print(\"  AVISO: Nenhum audio encontrado! Gerando faixa silenciosa de emergencia...\")\n",
                    "    subprocess.run([\"ffmpeg\", \"-y\", \"-f\", \"lavfi\", \"-i\", \"anullsrc=r=44100:cl=stereo\", \"-t\", \"60\", AUDIO_INPUT])\n",
                    "\n",
                    "if os.path.exists(ASS_LOCAL):\n",
                    "    with open(ASS_LOCAL, 'r', encoding='utf-8') as f_ass:\n",
                    "        ass_c = f_ass.read()\n",
                    "    with open(f\"{BASE_PATH}/legendas_temp.ass\", 'w', encoding='utf-8') as f_ass:\n",
                    "        f_ass.write(ass_c)\n",
                    "\n",
                    "config = {}\n",
                    "proj_json = f\"{BASE_PATH}/videorender-project.json\"\n",
                    "if os.path.exists(proj_json):\n",
                    "    with open(proj_json, 'r', encoding='utf-8') as f:\n",
                    "        config = json.load(f)\n",
                    "\n",
                    "cell_end(1, \"done\", \"Download Arquivos do Drive concluido\")"
                ]
                part_nb["cells"][1]["source"] = [line + "\n" if not line.endswith("\n") else line for line in download_source]
            else:
                download_source = part_nb["cells"][1]["source"]
                new_download = []
                for line in download_source:
                    line = line.replace('pt1_enhanced.mp4', f'pt{i}_enhanced.mp4')
                    line = line.replace('pt1_limpo.mp4', f'pt{i}_limpo.mp4')
                    line = line.replace('part_idx = 1', f'part_idx = {i}')
                    if 'baixar_do_drive(f"{DRIVE_OMNI}/audio_dublado.mp3"' in line:
                        line = (
                            'AUDIO_INPUT = f"{BASE_PATH}/audio_dublado.mp3"\n'
                            'if not baixar_do_drive(f"{DRIVE_OMNI}/audio_dublado.mp3", AUDIO_INPUT):\n'
                            '    if not baixar_do_drive("KAGGLE/AUDIO_DUB/OUTPUT/audio_dublado_Completo.mp3", AUDIO_INPUT):\n'
                            '        baixar_do_drive("KAGGLE/AUDIO_DUB/INPUT/anime_audio.mp3", AUDIO_INPUT)\n'
                            'if not os.path.exists(AUDIO_INPUT):\n'
                            '    print("  AVISO: Nenhum audio encontrado! Gerando faixa silenciosa de emergencia...")\n'
                            '    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "60", AUDIO_LOCAL if "AUDIO_LOCAL" in locals() else AUDIO_INPUT])\n'
                        )
                    new_download.append(line)
                part_nb["cells"][1]["source"] = new_download
                
            # Ajusta a build do comando FFmpeg (célula 2)
            build_source = part_nb["cells"][2]["source"]
            new_build = []
            for line in build_source:
                line = line.replace('pt1_enhanced.mp4', f'pt{i}_enhanced.mp4')
                new_build.append(line)
            part_nb["cells"][2]["source"] = new_build
            
            # Ajusta o upload (célula 4)
            upload_source = part_nb["cells"][4]["source"]
            new_upload = []
            for line in upload_source:
                line = line.replace('pt1_renderizado.mp4', f'pt{i}_renderizado.mp4')
                line = line.replace('Renderizacao PT1', f'Renderizacao PT{i}')
                new_upload.append(line)
            part_nb["cells"][4]["source"] = new_upload
            
            # Salva o notebook gerado
            save_nb(part_nb, f"anime-renderizador-kaggle-pt-{i}.ipynb")
            
    # 4. Gerar o Merge Final
    nb = make_nb(MERGE_CELLS, "anime-merge-final", "step_merge")
    save_nb(nb, "anime-merge-final.ipynb")
    
    # 5. Compilar os 3 notebooks da nova arquitetura Omni:
    # A) anime-omni-main.ipynb
    print("Compilando anime-omni-main.ipynb a partir de omni_main/...")
    main_cell_files = ["cel1", "cel2", "cel3", "cel4", "cel5", "cel_split"]
    omni_main_cells = []
    for cf in main_cell_files:
        cel_path = os.path.join(os.path.dirname(__file__), "omni_main", cf)
        if os.path.exists(cel_path):
            with open(cel_path, "r", encoding="utf-8") as f_cel:
                code = f_cel.read()
            lines = code.split("\n")
            source = [line + "\n" for line in lines[:-1]]
            if lines[-1]: source.append(lines[-1])
            omni_main_cells.append({
                "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source
            })
    save_nb({"nbformat": 4, "nbformat_minor": 5, "metadata": KAGGLE_META, "cells": omni_main_cells}, "anime-omni-main.ipynb")

    # B) anime-omni-tts-pt1.ipynb ate pt4.ipynb
    print("Compilando anime-omni-tts-pt1.ipynb ate pt4.ipynb a partir de omni_tts/...")
    tts_cell_files = ["cel1", "cel2", "cel8", "cel9"]
    for pt in range(1, 5):
        omni_tts_cells = []
        for cf in tts_cell_files:
            cel_path = os.path.join(os.path.dirname(__file__), "omni_tts", cf)
            if os.path.exists(cel_path):
                with open(cel_path, "r", encoding="utf-8") as f_cel:
                    code = f_cel.read()
                # Personalizar o cel1 para cada parte
                if cf == "cel1":
                    code = code.replace('TASK_KEY = "omni-tts-pt1"', f'TASK_KEY = "omni-tts-pt{pt}"')
                lines = code.split("\n")
                source = [line + "\n" for line in lines[:-1]]
                if lines[-1]: source.append(lines[-1])
                omni_tts_cells.append({
                    "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source
                })
        save_nb({"nbformat": 4, "nbformat_minor": 5, "metadata": KAGGLE_META, "cells": omni_tts_cells}, f"anime-omni-tts-pt{pt}.ipynb")

    # C) anime-omni-assemble.ipynb
    print("Compilando anime-omni-assemble.ipynb a partir de omni_assemble/...")
    assemble_cell_files = ["cel1", "cel2", "cel10", "cel11"]
    omni_assemble_cells = []
    for cf in assemble_cell_files:
        cel_path = os.path.join(os.path.dirname(__file__), "omni_assemble", cf)
        if os.path.exists(cel_path):
            with open(cel_path, "r", encoding="utf-8") as f_cel:
                code = f_cel.read()
            lines = code.split("\n")
            source = [line + "\n" for line in lines[:-1]]
            if lines[-1]: source.append(lines[-1])
            omni_assemble_cells.append({
                "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": source
            })
    save_nb({"nbformat": 4, "nbformat_minor": 5, "metadata": KAGGLE_META, "cells": omni_assemble_cells}, "anime-omni-assemble.ipynb")

    # Manter retrocompatibilidade de nome caso necessario
    save_nb({"nbformat": 4, "nbformat_minor": 5, "metadata": KAGGLE_META, "cells": omni_main_cells}, "anime-omni-ver-final.ipynb")

    print("\nTodos os notebooks gerados com sucesso!")

