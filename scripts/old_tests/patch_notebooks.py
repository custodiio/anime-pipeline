import json, glob

for f in glob.glob('notebooks/watermark-remover-pt-*.ipynb'):
    with open(f, 'r') as fp:
        nb = json.load(fp)
    
    src = nb['cells'][2]['source']
    src_str = ''.join(src)
    
    if "if mask_np is None:" in src_str:
        continue # Already patched
        
    # We want to replace the whole else block.
    # It's easier to just construct the new source string.
    new_src = """cell_start(2, 'Processamento Watermark')

INPUT = f"{BASE_PATH}/video_pt1.mp4".replace("pt1", f"pt{STEP_NAME.split('pt')[-1]}")
MASK = f"{BASE_PATH}/mask.png"
OUTPUT = f"{BASE_PATH}/pt1_limpo.mp4".replace("pt1", f"pt{STEP_NAME.split('pt')[-1]}")

import cv2, numpy as np, shutil, subprocess, os

if not os.path.exists(MASK):
    print("  Mask nao encontrada, copiando video sem watermark removal...")
    shutil.copy2(INPUT, OUTPUT)
    count = 0
else:
    cap = cv2.VideoCapture(INPUT)
    if not cap.isOpened():
        print(f"  Erro: Nao foi possivel abrir {INPUT}! Copiando arquivo original...")
        shutil.copy2(INPUT, OUTPUT)
        count = 0
    else:
        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if W == 0 or H == 0:
            print(f"  Erro: Dimensoes invalidas W={W}, H={H}. Copiando arquivo original...")
            shutil.copy2(INPUT, OUTPUT)
            count = 0
        else:
            FPS = cap.get(cv2.CAP_PROP_FPS)
            TOTAL = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            mask_np = cv2.imread(MASK, cv2.IMREAD_GRAYSCALE)
            if mask_np is None:
                print("  Aviso: mask.png invalida ou vazia! Copiando sem watermark removal...")
                cap.release()
                shutil.copy2(INPUT, OUTPUT)
                count = 0
            else:
                mask_np = cv2.resize(mask_np, (W, H))
                _, mask_bin = cv2.threshold(mask_np, 10, 255, cv2.THRESH_BINARY)

                pipe = subprocess.Popen([
                    "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
                    "-s", f"{W}x{H}", "-pix_fmt", "bgr24", "-r", str(FPS), "-i", "pipe:0",
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
                        print(f"  Frame {count}/{TOTAL} ({count/TOTAL*100:.1f}%)")

                cap.release()
                pipe.stdin.close()
                pipe.wait()
                print(f"  {count} frames processados")

cell_end(2, 'done', 'Processamento Watermark concluido')
"""
    
    # Split back into lines
    new_lines = [line + '\n' for line in new_src.split('\n')]
    new_lines[-1] = new_lines[-1].strip('\n') # Remove trailing newline from last element
    
    nb['cells'][2]['source'] = new_lines
    
    with open(f, 'w') as fp:
        json.dump(nb, fp, indent=1)

print("Notebooks patched!")
