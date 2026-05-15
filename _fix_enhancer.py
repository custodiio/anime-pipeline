import json
import os

notebooks = [
    "notebooks/video-enhancer-pt-1.ipynb",
    "notebooks/video-enhancer-pt-2.ipynb",
    "notebooks/video-enhancer.ipynb"
]

for nb_path in notebooks:
    if not os.path.exists(nb_path):
        continue
    
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)
        
    changed = False
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            new_src = []
            for line in cell["source"]:
                # 1. Trocar .png por .jpg
                line = line.replace(".png", ".jpg")
                
                # 2. Trocar formato no comando do ffmpeg para jpeg de alta qualidade (-q:v 2)
                if "-qscale:v 1 -qmin 1 -qmax 1" in line:
                    line = line.replace("-qscale:v 1 -qmin 1 -qmax 1", "-q:v 2")
                
                # 3. Trocar formato do output do realesrgan (-f png para -f jpg)
                if "-f png" in line:
                    line = line.replace("-f png", "-f jpg")
                
                # 4. Remover end="\r" dos prints
                if 'end="\\r"' in line:
                    line = line.replace(', end="\\r"', "")
                
                # Aproveitar pra arrumar o cell_start se ele estiver na primeira linha (NameError)
                if 'cell_start(0,' in line and "def cell_start" not in "".join(cell["source"])[:"".join(cell["source"]).index(line)]:
                     pass # we will fix this properly below if needed

                new_src.append(line)
            
            # Se for a cell 0, vamos mover o cell_start(0, ...) pra baixo do def se existir
            # (mesma correcao feita nos renderizadores, caso os enhancers tenham o mesmo bug)
            if 'cell_start(0,' in new_src[0]:
                start_str = new_src.pop(0)
                insert_idx = len(new_src)
                for i, l in enumerate(new_src):
                    if "DRIVE_ATIVO =" in l or "DRIVE_ENHANCER =" in l or "BASE_PATH =" in l:
                        insert_idx = i
                        break
                new_src.insert(insert_idx, start_str)

            if new_src != cell["source"]:
                cell["source"] = new_src
                changed = True
                
    if changed:
        with open(nb_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)
        print(f"Corrigido: {nb_path}")
    else:
        print(f"Sem mudancas: {nb_path}")
