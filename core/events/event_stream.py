# core/engine/event_stream.py
from core.events.workflow_event import WorkflowEvent
from django.utils import timezone

class EventStream:

    @classmethod
    def publish(cls, topic, event, idempotency_key):
        if WorkflowEvent.objects.filter(idempotency_key=idempotency_key).exists():
            return None  # idempotent skip

        event["ts"] = timezone.now().isoformat()

        WorkflowEvent.objects.create(
            topic=topic,
            workflow_id=str(event.get("id")),
            model=event["model"],
            object_id=event["id"],
            action=event["action"],
            before=event["before"],
            after=event["after"],
            payload=event,
            idempotency_key=idempotency_key,
        )

        return event

    @classmethod
    def replay(cls, model):
        return list(
            WorkflowEvent.objects
            .filter(model=model)
            .values_list("payload", flat=True)
        )
