import sys, os
sys.path.insert(0, '/home/ubuntu/apps/anime-pipeline')
from bot.database import _get_conn
conn = _get_conn()
cur = conn.cursor()
cur.execute('SELECT * FROM pipeline_projects WHERE id = %s::uuid', ('a6b89fe8-75df-4c43-af04-5badbcc66fab',))
proj = cur.fetchone()
for k, v in proj.items():
    if v and v != 'pending' and v != 'skipped':
        print(f"{k}: {v}")
