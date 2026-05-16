from bot.database import get_running_projects
from bot.github_actions import dispatch_parallel
import sys

projects = get_running_projects()
if not projects:
    print("Nenhum projeto rodando!")
    sys.exit(1)

# Pega o primeiro
project_id = str(projects[0]['id'])
print(f"Retriggering RENDER for project {project_id}...")

tasks = [f"render-pt{i}" for i in range(1, 6)]
dispatch_parallel(tasks, project_id)
print("Render disparado!")
