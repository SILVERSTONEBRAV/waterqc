# sc/context_processors.py
from __future__ import annotations

import logging
from sc.services.shift_service import get_current_shift_data

logger = logging.getLogger(__name__)


def shift_context(request):
    """
    Context processor that supplies current Shift (from SC app),
    Shift Supervisor, and Handover/Takeover window active status
    to all dashboards, excluding the Home View.
    """
    context = {
        "current_plant": None,
        "current_shift": None,
        "current_shift_supervisor": None,
        "is_handover_window_active": False,
        "handover_window_time": "",
        "next_shift": None,
    }

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return context

    # Exclude Home View (root URL '/' or url_name == 'home')
    path = getattr(request, "path", "")
    match = getattr(request, "resolver_match", None)
    url_name = getattr(match, "url_name", "") if match else ""

    if path == "/" or url_name == "home":
        return context

    try:
        shift_data = get_current_shift_data(user, request=request)
        context.update({
            "current_plant": shift_data.get("plant"),
            "current_shift": shift_data.get("current_shift"),
            "current_shift_supervisor": shift_data.get("supervisor"),
            "is_handover_window_active": shift_data.get("is_handover_window_active", False),
            "handover_window_time": shift_data.get("handover_window_time", ""),
            "next_shift": shift_data.get("next_shift"),
        })
    except Exception as exc:
        logger.exception("Failed to resolve shift context: %s", exc)

    return context
