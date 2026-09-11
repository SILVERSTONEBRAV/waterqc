# core/tasks/workflow_tasks.py
from celery import shared_task

@shared_task(bind=True, max_retries=3)
def execute_step(self, workflow_id, step, payload):
    try:
        # dynamic step execution
        handler = payload.get("handler")
        if callable(handler):
            handler(payload)

    except Exception as e:
        raise self.retry(exc=e, countdown=5)
