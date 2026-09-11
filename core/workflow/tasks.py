# core/workflow/tasks.py

from celery import shared_task
from core.workflow.event_store import WorkflowEventEngine


@shared_task
def execute_transition(model_key, object_id, action, user_id, payload):

    from core.registry import registry

    entry = registry.get(model_key)
    obj = entry.model.objects.get(pk=object_id)

    graph = WorkflowEngine.compile_graph(entry)

    before = WorkflowEngine.resolve_state(obj, graph)

    # execute transition
    if entry.transition_handler:
        entry.transition_handler(payload)
    elif hasattr(obj, "transition_to"):
        obj.transition_to(action, performed_by_id=user_id)

    after = WorkflowEngine.resolve_state(obj, graph)

    WorkflowEventEngine.emit(
        model_key=model_key,
        object_id=object_id,
        action=action,
        from_state=before,
        to_state=after,
        payload=payload,
        user_id=user_id,
    )
