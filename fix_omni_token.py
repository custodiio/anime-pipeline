import json

filepath = 'notebooks/omni-anime-ver-final.ipynb'
print(f"Fixing token in {filepath}")
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    changed = False
    for cell in data['cells']:
        if cell['cell_type'] == 'code':
            new_source = []
            for line in cell['source']:
                if 'token=DRIVE_ACCESS_TOKEN,' in line:
                    new_source.append(line.replace('token=DRIVE_ACCESS_TOKEN,', 'token=DRIVE_ACCESS_TOKEN if DRIVE_ACCESS_TOKEN else None,'))
                    changed = True
                else:
                    new_source.append(line)
            cell['source'] = new_source
    if changed:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        print("  Fixed token.")
    else:
        print("  No changes needed.")
except Exception as e:
    print(f"  Error: {e}")
