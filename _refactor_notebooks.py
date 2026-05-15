import os
import json

base_types = [
    "watermark-remover",
    "video-enhancer",
    "renderizador-kaggle"
]

for base in base_types:
    src_file = f"notebooks/{base}-pt-1.ipynb"
    if not os.path.exists(src_file):
        print(f"Ignorando {src_file}, nao existe.")
        continue
        
    with open(src_file, 'r', encoding='utf-8') as f:
        src_content = f.read()
        
    for i in [3, 4, 5]:
        target_file = f"notebooks/{base}-pt-{i}.ipynb"
        
        # Replace occurrences:
        # "pt1" -> "pt3" (e.g. step_enhancer_pt1, pt1_limpo.mp4)
        # "PT1" -> "PT3" (e.g. Watermark PT1)
        # "pt-1" -> "pt-3" (e.g. watermark-remover-pt-1)
        
        new_content = src_content.replace('pt1', f'pt{i}')
        new_content = new_content.replace('PT1', f'PT{i}')
        new_content = new_content.replace('pt-1', f'pt-{i}')
        
        with open(target_file, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"Criado: {target_file}")

print("Notebooks gerados com sucesso!")
