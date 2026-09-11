import logging

from django.views import View
from django.http import HttpResponse, Http404
from django.template.loader import render_to_string
from django.core.exceptions import ImproperlyConfigured

from core.mixins import WanjalaMixin
from core.registry import registry

logger = logging.getLogger(__name__)


class DashboardView(WanjalaMixin, View):
    """
    Registry-driven dashboard (NO TEMPLATE LOGIC, NO FUNCTION CALLS IN HTML)
    """

    template_name = "backwashing/dashboard.html"
    app_label = "backwashing"
    def get(self, request):
        if (r := self.process_request(request)):
            return r

        self.check_idle_timeout()

        context = self.get_context(request)

        return HttpResponse(
            render_to_string(self.template_name, context, request=request)
        )

    # =====================================================
    # CONTEXT PIPELINE
    # =====================================================
    def get_context(self, request):
        entries = self.get_entries()

        return {
            "app_groups": registry.sidebar(self.app_label),
            "app": {
                "name": self.app_label,
                "label": "Dashboard",
            },
            "models": self.serialize_models(entries),
            "stats": self.build_stats(entries),
        }

    # =====================================================
    # REGISTRY ACCESS
    # =====================================================
    def get_entries(self):
        entries = registry.for_app(self.app_label)

        if entries is None:
            raise ImproperlyConfigured(f"Registry returned None for '{self.app_label}'")

        if not entries:
            raise Http404(f"No models registered for app '{self.app_label}'")

        return entries

    # =====================================================
    # SAFE URL BUILDER (SERVER SIDE ONLY)
    # =====================================================
    def build_url(self, model: str, action: str, pk: str | None = None):
        """
        NEVER expose registry.url() to templates.
        """
        return registry.url(
            model=model,
            action=action,
            app_label=self.app_label,
            pk=pk
        )

    # =====================================================
    # SERIALIZER (TEMPLATE SAFE CONTRACT)
    # =====================================================
    def serialize_models(self, entries):
        out = []

        for entry in entries:
            meta = entry.meta
            model = meta.get("model_name")

            if not model:
                continue

            app = meta.get("app_label")

            out.append({
                "key": meta.get("key"),
                "model_name": model,
                "app_label": app,

                # safe display
                "label": meta.get("label_plural") or meta.get("label") or model,

                # IMPORTANT: precomputed URLs only
                "urls": {
                    "list": self.build_url(model, "list"),
                    "create": self.build_url(model, "create"),
                    "export": self.build_url(model, "export"),
                },

                "capabilities": {
                    "create": bool(meta.get("has_create")),
                    "export": bool(meta.get("has_export")),
                    "inline": bool(meta.get("has_inline")),
                },

                "custom_actions": list(entry.custom_actions.keys()),
                "tags": list(entry.tags),
                "icon": meta.get("icon", "cube"),
            })

        return out

    # =====================================================
    # STATS ENGINE
    # =====================================================
    def build_stats(self, entries):
        return {
            "total_models": len(entries),
            "with_create": sum(bool(e.meta.get("has_create")) for e in entries),
            "with_export": sum(bool(e.meta.get("has_export")) for e in entries),
            "with_inline": sum(bool(e.meta.get("has_inline")) for e in entries),
            "tags_count": sum(len(e.tags) for e in entries),
        }
