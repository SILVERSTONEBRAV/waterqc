from collections import defaultdict
import uuid
import traceback
import logging

from django.views.generic import TemplateView
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.db import transaction

from core.mixins import WanjalaMixin
from core.registry import registry
from core.events.event_stream import EventStream
from core.engine.temporal import TemporalEngine
from core.engine.ws import broadcast_event

logger = logging.getLogger(__name__)


# =========================================================
# 🧠 ANOMALY ENGINE (HARDENED + NORMALIZED SCORING)
# =========================================================

class AnomalyEngine:

    @classmethod
    def embed_path(cls, events):
        events = events or []

        actions = [e.get("action") for e in events if e.get("action")]

        return {
            "length": len(events),
            "unique_actions": len(set(actions)),
            "entropy": len(set(actions)) / (len(actions) + 1e-6),
            "transitions": [
                (e.get("before"), e.get("after"))
                for e in events
                if e.get("before") or e.get("after")
            ]
        }

    @classmethod
    def detect(cls, embedding):
        score = (
            embedding["length"] * 0.5 +
            embedding["unique_actions"] * 0.3 +
            embedding["entropy"] * 100 * 0.2
        )

        return {
            "score": round(score, 2),
            "is_anomaly": score > 75,
            "meta": embedding
        }


# =========================================================
# 🧭 DEBUGGER ENGINE
# =========================================================

class WorkflowDebugger:

    breakpoints = []

    @classmethod
    def set_breakpoint(cls, model, state, condition=None):
        cls.breakpoints.append((model, state, condition))

    @classmethod
    def hit(cls, model, state, context=None):
        for m, s, cond in cls.breakpoints:
            if m == model and s == state:
                return cond(context) if callable(cond) else True
        return False


# =========================================================
# 🧠 WORKFLOW ENGINE (HARDENED CORE)
# =========================================================

class WorkflowEngine:

    # -------------------------
    # SAFE CONFIG
    # -------------------------
    @staticmethod
    def _cfg(entry):
        try:
            return registry.config(entry.model) or {}
        except Exception:
            return {}

    # -------------------------
    # DISCOVERY
    # -------------------------
    @classmethod
    def discover(cls, request):
        return [
            {"entry": e, "cfg": cls._cfg(e)}
            for e in registry.by_tag("workflow")
        ]

    # -------------------------
    # COMPILE
    # -------------------------
    @classmethod
    def compile(cls, entry, user=None):
        wf = cls._cfg(entry).get("workflow") or {}

        if not isinstance(wf, dict):
            raise ValueError(f"Invalid workflow config: {entry.model}")

        return {
            "status_field": wf.get("status_field", "status"),
            "graph": wf.get("graph") or {},
            "groups": wf.get("groups") or {},

            "resolver": wf.get("resolver"),
            "interceptors": wf.get("interceptors") or [],
            "validators": wf.get("validators") or [],

            "temporal": wf.get("temporal", True),
            "ui_graph": wf.get("ui_graph", True),

            "ordering": wf.get("ordering", "-id"),
            "recent_limit": wf.get("recent_limit", 10),
        }

    # -------------------------
    # STATE
    # -------------------------
    @classmethod
    def state(cls, obj, graph):
        resolver = graph.get("resolver")
        return resolver(obj) if callable(resolver) else getattr(obj, graph["status_field"], "UNKNOWN")

    # -------------------------
    # QUERY
    # -------------------------
    @classmethod
    def qs(cls, entry, request):
        cfg = cls._cfg(entry)
        return entry.queryset(entry.model, request, cfg) if entry.queryset else registry.resolve_queryset(entry.model, request, cfg)

    # -------------------------
    # INDEX
    # -------------------------
    @classmethod
    def index(cls, qs, graph):
        index = defaultdict(list)
        for obj in qs:
            index[cls.state(obj, graph)].append(obj)
        return index

    # -------------------------
    # BUCKETS (SAFE)
    # -------------------------
    @classmethod
    def buckets(cls, index, graph):
        graph_map = graph.get("graph") or {}
        groups = graph.get("groups") or {}

        if graph_map:
            return {k: len(index.get(k, [])) for k in graph_map}

        return {
            g: sum(len(index.get(s, [])) for s in states)
            for g, states in groups.items()
        }

    # -------------------------
    # DAG (DEDUP + STABLE ORDER)
    # -------------------------
    @classmethod
    def build_dag(cls, events):
        nodes = {}
        edges = []
        seen = set()

        for e in events or []:
            b, a = e.get("before"), e.get("after")

            if b:
                nodes.setdefault(b, {"id": b})
            if a:
                nodes.setdefault(a, {"id": a})

            key = (b, a, e.get("action"))
            if b and a and key not in seen:
                seen.add(key)
                edges.append({
                    "source": b,
                    "target": a,
                    "label": e.get("action"),
                })

        return {"nodes": list(nodes.values()), "edges": edges}

    # -------------------------
    # ANOMALY
    # -------------------------
    @classmethod
    def anomaly(cls, events):
        return AnomalyEngine.detect(AnomalyEngine.embed_path(events))

    # -------------------------
    # EVENT EMIT (IDEMPOTENT SAFE)
    # -------------------------
    @classmethod
    def emit(cls, user, obj, action, before, after, idempotency_key):

        payload = {
            "trace_id": str(uuid.uuid4()),
            "user": str(user),
            "model": obj.__class__.__name__,
            "id": str(obj.pk),
            "action": action,
            "before": before,
            "after": after,
            "ts": timezone.now().isoformat(),
        }

        try:
            event = EventStream.publish(
                "workflow.events",
                payload,
                idempotency_key=idempotency_key
            )

            if event:
                broadcast_event(event)

            return event

        except Exception as e:
            logger.error(f"[Workflow Emit Failed] {e}")
            return None

    # -------------------------
    # TEMPORAL
    # -------------------------
    @classmethod
    def schedule(cls, workflow_id, step, payload):
        try:
            return TemporalEngine.schedule(workflow_id, step, payload)
        except Exception as e:
            logger.error(f"[Temporal Error] {e}")
            return None

    # -------------------------
    # PROJECT
    # -------------------------
    @classmethod
    def project(cls, entry, request):

        qs = cls.qs(entry, request)
        graph = cls.compile(entry, request.user)

        index = cls.index(qs, graph)
        buckets = cls.buckets(index, graph)

        events = EventStream.replay(entry.model.__name__)
        dag = cls.build_dag(events)

        return {
            "label": entry.meta.get("label"),
            "key": entry.meta.get("key"),
            "graph": graph,

            "states": dict(index),
            "counts": buckets,

            "dag": dag,
            "dag_stream": events,

            "anomalies": cls.anomaly(events),

            "recent": [
                registry.resolve_row(o)
                for o in qs.order_by(graph["ordering"])[:graph["recent_limit"]]
            ],
        }

    # -------------------------
    # AGGREGATE
    # -------------------------
    @classmethod
    def aggregate(cls, request):
        models, totals = [], defaultdict(int)

        for wf in cls.discover(request):

            entry = wf["entry"]
            cfg = wf["cfg"]

            override = cfg.get("workflow_aggregator")

            if callable(override):
                models.append(override(entry.model, cls.qs(entry, request), request))
                continue

            data = cls.project(entry, request)
            models.append(data)

            for k, v in data["counts"].items():
                totals[k] += v

        return {
            "models": models,
            "totals": totals,
            "generated_at": timezone.now().isoformat(),
        }


# =========================================================
# ⚡ DASHBOARD VIEW
# =========================================================

class WorkflowDashboardView(WanjalaMixin, TemplateView):

    template_name = "core/workflow/dashboard.html"

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "dashboard": WorkflowEngine.aggregate(self.request),
            "sidebar": registry.sidebar(),
            "now": timezone.now(),
            "page_title": "Workflow Intelligence Hub",
        }

    # -------------------------
    # HTMX ROUTER (SAFE)
    # -------------------------
    def get(self, request, *args, **kwargs):

        if not self.is_htmx():
            return super().get(request, *args, **kwargs)

        section = request.GET.get("section")
        model = request.GET.get("model")

        routes = {
            "summary": self._summary,
            "models": self._models,
            "model": lambda: self._model(model),
            "dag": lambda: self._dag(model),
            "debug": lambda: self._debug(model),
        }

        handler = routes.get(section)
        return handler() if handler else HttpResponse(status=204)

    # -------------------------
    # RENDER
    # -------------------------
    def _render(self, tpl, ctx):
        return HttpResponse(render_to_string(
            f"core/workflow/partials/{tpl}",
            ctx,
            request=self.request
        ))

    def _summary(self):
        return self._render("summary.html", WorkflowEngine.aggregate(self.request))

    def _models(self):
        return self._render("models.html", WorkflowEngine.aggregate(self.request))

    def _model(self, key):
        entry = registry.get(key)
        if not entry:
            return HttpResponse(status=404)
        return self._render("model_detail.html", {"model": WorkflowEngine.project(entry, self.request)})

    def _dag(self, key):
        entry = registry.get(key)
        return self._render("dag.html", WorkflowEngine.project(entry, self.request))

    def _debug(self, key):
        entry = registry.get(key)
        qs = WorkflowEngine.qs(entry, self.request)
        graph = WorkflowEngine.compile(entry)
        return self._render("debugger.html", {
            "model": key,
            "states": WorkflowEngine.index(qs, graph),
            "breakpoints": WorkflowDebugger.breakpoints,
        })

    # -------------------------
    # ACTION PIPELINE
    # -------------------------
    def post(self, request, *args, **kwargs):

        model_key = request.POST.get("model")
        pk = request.POST.get("pk")
        action = request.POST.get("action")

        entry = registry.get(model_key)
        if not entry:
            return JsonResponse({"error": "Invalid model"}, status=400)

        obj = entry.model.objects.filter(pk=pk).first()
        if not obj:
            return JsonResponse({"error": "Not found"}, status=404)

        graph = WorkflowEngine.compile(entry)

        idempotency_key = request.headers.get(
            "Idempotency-Key",
            f"{model_key}:{pk}:{action}"
        )

        try:
            with transaction.atomic():

                before = WorkflowEngine.state(obj, graph)

                if WorkflowDebugger.hit(model_key, before, {"obj": obj}):
                    return JsonResponse({"error": "Breakpoint hit"}, status=409)

                for validator in graph.get("validators", []):
                    try:
                        validator(obj, action, request)
                    except Exception as e:
                        return JsonResponse({"error": str(e)}, status=400)

                for interceptor in graph.get("interceptors", []):
                    try:
                        interceptor({"request": request, "instance": obj, "action": action})
                    except Exception as e:
                        logger.warning(f"Interceptor failed: {e}")

                if callable(entry.transition_handler):
                    entry.transition_handler({"request": request, "instance": obj, "action": action})
                else:
                    obj.transition_to(action, performed_by=request.user)

                after = WorkflowEngine.state(obj, graph)

                event = WorkflowEngine.emit(
                    request.user,
                    obj,
                    action,
                    before,
                    after,
                    idempotency_key
                )

                if graph.get("temporal") and event:
                    WorkflowEngine.schedule(obj.pk, action, event)

            return JsonResponse({
                "success": True,
                "event": event,
                "before": before,
                "after": after
            })

        except Exception as e:
            traceback.print_exc()
            return JsonResponse({
                "error": str(e),
                "type": e.__class__.__name__,
            }, status=500)
