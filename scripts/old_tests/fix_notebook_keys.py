import json

def fix_notebook(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
        
        fixed = False
        for cell in nb.get('cells', []):
            if cell.get('cell_type') == 'code':
                for i, line in enumerate(cell.get('source', [])):
                    if "P1pel!ne_2026" in line:
                        print(f"Encontrado em {path}, linha: {line.strip()}")
                        cell['source'][i] = "    DATABASE_URL = _ks(\"DATABASE_URL\")\\n"
                        fixed = True
                        
        if fixed:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(nb, f, indent=1, ensure_ascii=False)
            print(f"Corrigido: {path}")
    except Exception as e:
        print(f"Erro ao processar {path}: {e}")

fix_notebook("notebooks/omni-anime-ver-final.ipynb")
