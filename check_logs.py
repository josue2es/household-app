from app.database import get_db
from app.models import TaskLog

with get_db() as db:
    logs = db.query(TaskLog).all()
    print(f'Total logs in DB: {len(logs)}')
    for log in logs[-10:]:
        print(f'  log_id={log.id} task_id={log.task_id} user_id={log.user_id} completed_at={log.completed_at}')
