from bot.database import _get_conn

conn = _get_conn()
cur = conn.cursor()

columns = [
    'step_watermark_pt3', 'step_watermark_pt4', 'step_watermark_pt5',
    'step_enhancer_pt3', 'step_enhancer_pt4', 'step_enhancer_pt5',
    'step_render_pt3', 'step_render_pt4', 'step_render_pt5'
]

for col in columns:
    try:
        cur.execute(f"ALTER TABLE pipeline_projects ADD COLUMN {col} VARCHAR(20) DEFAULT 'pending'")
        print(f"Added {col}")
    except Exception as e:
        print(f"Could not add {col}: {e}")
        conn.rollback()

conn.commit()
cur.close()
conn.close()
