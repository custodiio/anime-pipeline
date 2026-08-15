"""
Fix 1: Corrigir SyntaxError no omni - DATABASE_URL tem \\n literal em vez de newline
Fix 2: Gerar pt1/pt2 do enhancer com JPG (igual pt3/pt4/pt5)
"""
import json, os, sys

NOTEBOOKS_DIR = os.path.join(os.path.dirname(__file__), "notebooks")

# ══════════════════════════════════════════════════════════════
# FIX 1: omni-anime-ver-final.ipynb
# Linha problemática (índice 13 da célula 0):
#   '    DATABASE_URL = _ks("DATABASE_URL")\\n'
# O \\n é literal barra+n. Precisa ser newline real \n
# ══════════════════════════════════════════════════════════════
omni_path = os.path.join(NOTEBOOKS_DIR, "omni-anime-ver-final.ipynb")
with open(omni_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

fixed_omni = False
cell0 = nb["cells"][0]
new_source = []
for line in cell0["source"]:
    # Match exato: linha com \\n literal no final (dois chars: \ e n)
    if line == '    DATABASE_URL = _ks("DATABASE_URL")\\n':
        new_source.append('    DATABASE_URL = _ks("DATABASE_URL")\n')
        fixed_omni = True
        print("  [OK] DATABASE_URL line corrigida (\\n -> newline real)")
    else:
        new_source.append(line)
cell0["source"] = new_source

if fixed_omni:
    with open(omni_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print(f"  Salvo: omni-anime-ver-final.ipynb")
else:
    print("  ERRO: linha nao encontrada. Bytes da linha 13:")
    print(f"    {cell0['source'][13].encode()}")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════
# FIX 2: generate_notebooks.py -> PNG para JPG em make_enhancer_cells
# ══════════════════════════════════════════════════════════════
print("\nCorrigindo generate_notebooks.py (PNG -> JPG)...")

gen_path = os.path.join(os.path.dirname(__file__), "generate_notebooks.py")
with open(gen_path, "r", encoding="utf-8") as f:
    content = f.read()

replacements = [
    # Extrair frames: PNG -> JPG, e -qscale:v 1 -qmin 1 -qmax 1 -> -q:v 2
    (
        r'-qscale:v 1 -qmin 1 -qmax 1 {{FRAMES_DIR}}/frame_%08d.png',
        r'-q:v 2 {{FRAMES_DIR}}/frame_%08d.jpg'
    ),
    # Upscaling: glob de PNG -> JPG
    (
        r'sorted(glob.glob(f\"{{FRAMES_DIR}}/*.png\"))',
        r'sorted(glob.glob(f\"{{FRAMES_DIR}}/*.jpg\"))'
    ),
    # Real-ESRGAN: -f png -> -f jpg
    (
        r'-f png -g 0\",))',
        r'-f jpg -g 0\",))'
    ),
    (
        r'-f png -g 1\",))',
        r'-f jpg -g 1\",))'
    ),
    # Merge upscaled globs
    (
        r'glob.glob(f\"{{BASE_PATH}}/ug0/*.png\")) + sorted(glob.glob(f\"{{BASE_PATH}}/ug1/*.png\"))',
        r'glob.glob(f\"{{BASE_PATH}}/ug0/*.jpg\")) + sorted(glob.glob(f\"{{BASE_PATH}}/ug1/*.jpg\"))'
    ),
    # total_up glob
    (
        r'total_up = len(glob.glob(f\"{{UP_DIR}}/*.png\"))',
        r'total_up = len(glob.glob(f\"{{UP_DIR}}/*.jpg\"))'
    ),
    # Montar Video: frames/*.png -> frames/*.jpg
    (
        r'frames = sorted(glob.glob(f\"{{UP_DIR}}/*.png\"))',
        r'frames = sorted(glob.glob(f\"{{UP_DIR}}/*.jpg\"))'
    ),
]

count = 0
for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f"  [OK] {old[:60]}...")
        count += 1
    else:
        print(f"  [SKIP] nao encontrado: {old[:60]}...")

with open(gen_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"  Salvo: generate_notebooks.py ({count} substituicoes)")

# Regenerar somente pt1 e pt2
print("\nRegenerando pt1 e pt2...")
sys.path.insert(0, os.path.dirname(__file__))
import importlib
import generate_notebooks as gn
importlib.reload(gn)

nb1 = gn.make_nb(gn.make_enhancer_cells(1), "video-enhancer-pt-1", "step_enhancer_pt1")
gn.save_nb(nb1, "video-enhancer-pt-1.ipynb")

nb2 = gn.make_nb(gn.make_enhancer_cells(2), "video-enhancer-pt-2", "step_enhancer_pt2")
gn.save_nb(nb2, "video-enhancer-pt-2.ipynb")

print("\n=== CONCLUIDO ===")
print("  omni-anime-ver-final.ipynb  -> SyntaxError corrigido")
print("  video-enhancer-pt-1.ipynb   -> JPG")
print("  video-enhancer-pt-2.ipynb   -> JPG")
