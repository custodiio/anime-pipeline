import glob
import json

for file in glob.glob('notebooks/video-enhancer*.ipynb'):
    with open(file, 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    for cell in nb['cells']:
        if cell['cell_type'] == 'code':
            new_source = []
            for line in cell['source']:
                line = line.replace('"-cq","18"', '"-cq","26"')
                line = line.replace('"-crf","18"', '"-crf","26"')
                new_source.append(line)
            cell['source'] = new_source
            
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")

print("Notebooks atualizados usando modulo JSON!")
