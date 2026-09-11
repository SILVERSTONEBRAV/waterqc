# core/context_processors.py

from core.registry import registry


def sidebar_context(request):

    app_label = getattr(request.resolver_match, "app_name", None)

    return {
        "app_groups": registry.sidebar(app_label) if app_label else registry.sidebar(),
    }
