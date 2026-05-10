import json

def fix_notebook(filepath):
    print(f"Fixing {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        changed = False
        for cell in data['cells']:
            if cell['cell_type'] == 'code':
                new_source = []
                for line in cell['source']:
                    if line.startswith('def report_step(status, msg=""):') and 'PIPELINE_WEBHOOK_URL' not in line:
                        new_source.append(line)
                        new_source.append('    if PROJECT_ID and PIPELINE_WEBHOOK_URL:\\n')
                        new_source.append('        try:\\n')
                        new_source.append('            http_requests.post(f"{PIPELINE_WEBHOOK_URL}/webhook/status", json={"project_id": PROJECT_ID, "step": STEP_NAME, "status": status, "message": msg}, timeout=15)\\n')
                        new_source.append('        except: pass\\n')
                        changed = True
                    else:
                        new_source.append(line)
                cell['source'] = new_source
        if changed:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            print("  Fixed.")
        else:
            print("  No changes needed.")
    except Exception as e:
        print(f"  Error: {e}")

import glob
for nb in glob.glob("notebooks/*.ipynb"):
    fix_notebook(nb)
