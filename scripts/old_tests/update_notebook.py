import json
import os

with open('notebooks/omni-anime-ver-final.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

def read_cell(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

cel_map = {
    'cell_start(2, "Setup Inicial + Drive + Whisper")': 'omni_atualizado/cel3',
    'cell_start(4, "Transcricao Whisper + Pyannote")': 'omni_atualizado/cel5',
    'cell_start(10, "Montagem Final")': 'omni_atualizado/cel10',
}

for c in nb['cells']:
    if c['cell_type'] == 'code':
        source = "".join(c.get('source', []))
        for prefix, path in cel_map.items():
            if source.startswith(prefix):
                code = read_cell(path)
                c['source'] = [line + '\n' for line in code.split('\n')]
                c['source'][-1] = c['source'][-1].rstrip('\n')
                break

with open('notebooks/omni-anime-ver-final.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print("Notebook updated.")
