"""Permission and plant scoped result-card data for treatment dashboards."""

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from django.apps import apps
from django.db.models import Count


RESULT_DASHBOARD_SPECS = {
    "destw": [
        {
            "model": "WasteWaterAnalysis",
            "result_model": "WasteWaterParameterResult",
            "title": "Wastewater analysis",
            "sample_relation": "sample",
            "plant_path": "sample__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Date", "sample__sampling_date"),
                ("Time", "sample__sampling_time"),
                ("Sampling site", "sample__sampling_site__name"),
            ],
            "results_relation": "destw_parameter_results",
        },
        {
            "model": "WasteWaterPondAnalysis",
            "result_model": "WasteWaterPondParameterResult",
            "title": "Stabilization pond analysis",
            "sample_relation": "sample",
            "plant_path": "sample__site__pond__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Date", "sample__sampling_date"),
                ("Time", "sample__sampling_time"),
                ("Pond", "sample__site__pond__name"),
                ("Sampling site", "sample__site__site_name"),
            ],
            "results_relation": "destw_pond_parameter_results",
        },
    ],
    "kstw": [
        {
            "model": "WasteWaterAnalysis",
            "result_model": "WasteWaterParameterResult",
            "title": "Wastewater analysis",
            "sample_relation": "sample",
            "plant_path": "sample__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Date", "sample__sampling_date"),
                ("Time", "sample__sampling_time"),
                ("Sampling site", "sample__sampling_site__name"),
            ],
            "results_relation": "parameter_results",
        },
        {
            "model": "IndustrialSampleAnalysis",
            "result_model": "IndustrialSampleParameterResult",
            "title": "Industrial sample analysis",
            "sample_relation": "sample",
            "plant_path": "sample__assignment__shift__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Client", "sample__client_name"),
                ("Location", "sample__location"),
                ("Date", "sample__sampling_date"),
            ],
            "results_relation": "industrialsampleparameterresult_set",
        },
        {
            "model": "TreatmentPlantSampleAnalysis",
            "result_model": "TreatmentPlantSampleParameterResult",
            "title": "Treatment plant sample analysis",
            "sample_relation": "sample",
            "plant_path": "sample__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Sampling point", "sample__sampling_point_description"),
                ("Date", "sample__sampling_date"),
                ("Time", "sample__sampling_time"),
            ],
            "results_relation": "treatmentplantsampleparameterresult_set",
        },
        {
            "model": "ExhausterSampleAnalysis",
            "result_model": "ExhausterSampleParameterResult",
            "title": "Exhauster sample analysis",
            "sample_relation": "sample",
            "plant_path": "sample__assignment__shift__treatment_plant",
            "sample_fields": [
                ("Sample", "sample__reference_id"),
                ("Vehicle", "sample__exhauster_reg_number"),
                ("Driver", "sample__driver_name"),
                ("Date", "sample__sampling_date"),
            ],
            "results_relation": "exhaustersampleparameterresult_set",
        },
    ],
}

STATUS_ORDER = ("NEW", "ANALYSED", "VERIFIED", "CONFIRMED", "APPROVED")


def _get_attr(obj, path):
    for part in path.split("__"):
        if obj is None:
            return None
        obj = getattr(obj, part, None)
    return obj


def _format_value(value):
    if value is None or value == "":
        return "—"
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d %b %Y" if value.__class__.__name__ == "date" else "%H:%M")
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _can_view(user, model):
    return bool(user.is_superuser or user.has_perm(f"{model._meta.app_label}.view_{model._meta.model_name}"))


def permission_scoped_sidebar(request, registry, app_label):
    user = request.user
    grouped = registry.sidebar(app_label)
    if user.is_superuser:
        return grouped
    visible = {}
    for group, items in grouped.items():
        allowed = [
            item for item in items
            if user.has_perm(f"{app_label}.view_{item.get('model', '').lower()}")
        ]
        if allowed:
            visible[group] = allowed
    return visible


def _result_display(result):
    parameter = result.parameter
    value = getattr(result, "result", None)
    minimum = getattr(parameter, "nema_min_std", None)
    maximum = getattr(parameter, "nema_max_std", None)
    compliance = str(getattr(result, "quality_compliance", "") or "").strip()
    if not compliance and value is not None:
        try:
            numeric = Decimal(value)
            compliance = "Complying" if minimum <= numeric <= maximum else "Not Complying"
        except (InvalidOperation, TypeError):
            compliance = "Unclassified"
    failed = compliance.casefold() in {"not complying", "non-compliant", "fail", "failed"}
    unit = getattr(parameter, "unit", "") or "mg/L"
    limit = f"{minimum if minimum is not None else '—'} – {maximum if maximum is not None else '—'} {unit}"
    return {
        "name": str(getattr(parameter, "name", "Parameter")),
        "value": _format_value(value),
        "unit": str(unit),
        "limit": limit,
        "compliance": compliance or "Pending",
        "failed": failed,
    }


def build_result_dashboard(request, app_label):
    """Build compact analysis cards without crossing plant or permission scope."""
    user = request.user
    selected_plant = None
    available_plants = []
    if user.is_superuser:
        Plant = apps.get_model("t", "TreatmentPlant")
        available_plants = list(Plant.objects.order_by("name").values("id", "name"))
        plant_id = request.GET.get("plant")
        if plant_id and str(plant_id).isdigit():
            selected_plant = Plant.objects.filter(pk=int(plant_id)).first()
    else:
        selected_plant = getattr(user, "assigned_treatment_plant", None)

    cards = []
    status_totals = Counter()
    available_types = []
    total_analyses = 0
    failure_count = 0
    pending_count = 0

    for spec in RESULT_DASHBOARD_SPECS.get(app_label, ()):
        try:
            Analysis = apps.get_model(app_label, spec["model"])
            Result = apps.get_model(app_label, spec["result_model"])
        except LookupError:
            continue
        if not _can_view(user, Analysis):
            continue
        can_view_results = _can_view(user, Result)

        available_types.append(spec["title"])
        qs = Analysis.objects.all()
        field_names = {field.name for field in Analysis._meta.fields}
        if "is_deleted" in field_names:
            qs = qs.filter(is_deleted=False)
        sample_model = Analysis._meta.get_field(spec["sample_relation"]).related_model
        if any(field.name == "is_deleted" for field in sample_model._meta.fields):
            qs = qs.filter(**{f"{spec['sample_relation']}__is_deleted": False})

        if selected_plant is not None:
            qs = qs.filter(**{spec["plant_path"]: selected_plant})
        elif not user.is_superuser:
            # A user without an assigned plant must not inherit another plant's data.
            qs = qs.none()

        for row in qs.values("status").annotate(total=Count("pk")):
            state = row.get("status") or "NEW"
            status_totals[state] += row["total"]
        total_analyses += qs.count()
        result_qs = Result.objects.all()
        if any(field.name == "is_deleted" for field in Result._meta.fields):
            result_qs = result_qs.filter(is_deleted=False)
        if can_view_results:
            failure_count += result_qs.filter(
                analysis_id__in=qs.values("pk"),
                quality_compliance__iexact="Not Complying",
            ).count()

        analyses = list(
            qs.select_related(spec["sample_relation"])
            .order_by("-analysis_datetime", "-pk")[:8]
        )
        result_map = defaultdict(list)
        if analyses and can_view_results:
            for result in (
                result_qs.filter(analysis_id__in=[item.pk for item in analyses])
                .select_related("parameter")
                .order_by("parameter__name")
            ):
                result_map[result.analysis_id].append(_result_display(result))

        for analysis in analyses:
            sample = getattr(analysis, spec["sample_relation"], None)
            results = result_map.get(analysis.pk, [])
            failures = sum(item["failed"] for item in results)
            plant = _get_attr(analysis, spec["plant_path"])
            status = getattr(analysis, "status", "NEW") or "NEW"
            card = {
                "title": spec["title"],
                "sample_title": str(sample or "Sample"),
                "reference": str(_get_attr(analysis, spec["sample_relation"] + "__reference_id") or f"#{analysis.pk}"),
                "status": status,
                "status_label": analysis.get_status_display() if hasattr(analysis, "get_status_display") else status.replace("_", " ").title(),
                "stage_index": STATUS_ORDER.index(status) if status in STATUS_ORDER else 0,
                "plant_name": getattr(plant, "name", "—") or "—",
                "sample_fields": [
                    {"label": label, "value": _format_value(_get_attr(analysis, path))}
                    for label, path in spec["sample_fields"]
                ],
                "results": results[:6],
                "result_count": len(results),
                "results_permitted": can_view_results,
                "failure_count": failures,
                "analyst": getattr(getattr(analysis, "analysed_by", None), "get_full_name", lambda: "")()
                    or getattr(getattr(analysis, "analysed_by", None), "username", "Unassigned"),
                "analysis_datetime": getattr(analysis, "analysis_datetime", None),
                "detail_url": f"/{app_label}/{Analysis._meta.model_name}/{analysis.pk}/detail/",
            }
            cards.append(card)

    cards.sort(key=lambda item: item["analysis_datetime"] or 0, reverse=True)
    stage_cards = [
        {"key": state, "label": state.replace("_", " ").title(), "count": status_totals[state]}
        for state in STATUS_ORDER
    ]
    pending_count = sum(count for state, count in status_totals.items() if state != "APPROVED")
    return {
        "dashboard_title": "Desalination Works" if app_label == "destw" else "Kariobangi South Treatment Works",
        "dashboard_subtitle": "Treatment process analyses, result compliance and review stages",
        "plant": selected_plant,
        "available_plants": available_plants,
        "cards": cards,
        "stage_cards": stage_cards,
        "summary_cards": [
            {"label": "Analyses", "value": total_analyses, "icon": "fa-vial", "tone": "blue"},
            {"label": "Awaiting approval", "value": pending_count, "icon": "fa-hourglass-half", "tone": "orange"},
            {"label": "Out of range", "value": failure_count, "icon": "fa-triangle-exclamation", "tone": "red"},
            {"label": "Workflow types", "value": len(available_types), "icon": "fa-layer-group", "tone": "green"},
        ],
        "available_analysis_types": available_types,
        "has_analysis_permission": bool(available_types),
        "has_plant_scope": bool(selected_plant or user.is_superuser),
    }
