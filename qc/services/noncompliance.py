"""Cross-water-type non-compliance case normalization and dashboard analytics."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from filtered_water.models import FilteredWaterResults
from heavy_metal.models import HeavyMetalNonConformity
from microbial.models import MicrobialNonConformity
from qc.models import NonConformity, SamplingSchedule
from qc.services.advanced_reports import RESULT_CONFIG
from t.models import FilteredWaterLimit, HeavyMetalLimit, MicrobialLimit


NONCOMPLIANCE_TYPES = (
    (SamplingSchedule.RAW, "Raw water"),
    (SamplingSchedule.COAGULATED, "Coagulated water"),
    (SamplingSchedule.CLARIFIED, "Clarified water"),
    (SamplingSchedule.TREATED, "Treated water"),
    ("filtered_water", "Filtered water"),
    ("microbial", "Microbial analysis"),
    ("heavy_metal", "Heavy metal analysis"),
)


def _local_bounds(start_date, end_date):
    tz = timezone.get_current_timezone()
    return (
        timezone.make_aware(datetime.combine(start_date, time.min), tz),
        timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), tz),
    )


def _risk_band(value):
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 8:
        return "Critical"
    if score >= 6:
        return "High"
    if score >= 3:
        return "Moderate"
    return "Low"


def _normalize(instance, water_type, source, analysis, *, parameter_name=None, observed=None, minimum=None, maximum=None, deviation=None, risk_score=None, status=None, resolved_at=None, auto_detected=True, corrective_action="", preventive_action="", root_cause=""):
    created_at = getattr(analysis, "timestamp", None) if source == "filtered_derived" else getattr(instance, "created_at", None)
    recorded_at = timezone.localtime(created_at) if created_at and timezone.is_aware(created_at) else created_at
    analysis_date = getattr(analysis, "analysis_date", None)
    if analysis_date is None:
        analysis_date = getattr(analysis, "timestamp", None)
        if analysis_date and timezone.is_aware(analysis_date):
            analysis_date = timezone.localtime(analysis_date)
        if analysis_date:
            analysis_date = analysis_date.date()
    try:
        reference = analysis.reference_id
    except AttributeError:
        reference = str(getattr(analysis, "uuid", ""))
    phase = getattr(getattr(analysis, "treatment_plant_phase", None), "name", "—") or "—"
    sample_time = ""
    for path in ("sampling_time", "analysis_time"):
        relation = getattr(analysis, path, None)
        if relation is not None:
            sample_time = getattr(getattr(relation, "time", None), "strftime", lambda _fmt: "")("%H:%M")
            if sample_time:
                break
    try:
        if not hasattr(analysis, "sampling_time"):
            sample_time = analysis.analysis_time.time.strftime("%H:%M")
    except (AttributeError, TypeError):
        pass
    if status is None:
        status = getattr(instance, "status", "derived")
    try:
        cause_names = [cause.name for cause in instance.causes.all()]
    except (AttributeError, TypeError):
        cause_names = []
    try:
        log_history = " · ".join(
            f"{log.created_at:%Y-%m-%d %H:%M} {log.action}: {log.remarks or ''}".strip()
            for log in instance.logs.all()
        )
    except (AttributeError, TypeError):
        log_history = ""
    return {
        "id": f"{source}:{instance.pk}",
        "source_id": instance.pk,
        "source": source,
        "source_label": "Recorded case" if source != "filtered_derived" else "Derived limit exceedance",
        "water_type": water_type,
        "water_type_label": dict(NONCOMPLIANCE_TYPES).get(water_type, water_type.replace("_", " ").title()),
        "date": recorded_at.date().isoformat() if recorded_at else str(analysis_date or ""),
        "recorded_at": recorded_at.isoformat() if recorded_at else "",
        "sample_date": analysis_date.isoformat() if hasattr(analysis_date, "isoformat") else str(analysis_date or ""),
        "time": sample_time,
        "reference": reference,
        "phase": phase,
        "parameter": parameter_name or getattr(instance, "parameter_name", "Unknown parameter"),
        "unit": getattr(getattr(getattr(instance, "parameter", None), "parameter", None), "unit", "") or "",
        "observed_value": _finite(observed if observed is not None else getattr(instance, "observed_value", None)),
        "minimum_limit": _finite(minimum if minimum is not None else getattr(instance, "min_limit", None)),
        "maximum_limit": _finite(maximum if maximum is not None else getattr(instance, "max_limit", None)),
        "deviation": _finite(deviation if deviation is not None else getattr(instance, "deviation", None)),
        "risk_score": _finite(risk_score if risk_score is not None else getattr(instance, "risk_score", 0)) or 0.0,
        "risk_band": _risk_band(risk_score if risk_score is not None else getattr(instance, "risk_score", 0)),
        "status": str(status),
        "status_label": str(status).replace("_", " ").title(),
        "escalation_level": int(getattr(instance, "escalation_level", 0) or 0),
        "auto_detected": bool(auto_detected),
        "resolved_at": timezone.localtime(resolved_at).isoformat() if resolved_at and timezone.is_aware(resolved_at) else resolved_at.isoformat() if resolved_at else "",
        "corrective_action": corrective_action or "",
        "preventive_action": preventive_action or "",
        "root_cause": root_cause or "",
        "causes": "; ".join(cause_names),
        "causes_list": cause_names,
        "log_history": log_history,
    }


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _parameter_units(plant, water_type):
    if water_type == "filtered_water":
        model = FilteredWaterLimit
    elif water_type == "microbial":
        model = MicrobialLimit
    elif water_type == "heavy_metal":
        model = HeavyMetalLimit
    else:
        model = RESULT_CONFIG.get(water_type, {}).get("limit_model")
    if not model or not plant:
        return {}
    return dict(model.objects.filter(treatment_plant=plant).values_list("parameter__name", "parameter__unit"))


def load_noncompliance_cases(*, plant, start_date: date, end_date: date, water_type: str, status="", severity="", search="", sort="date", direction="desc"):
    """Load one water-type slice, retaining recorded and derived cases as distinct sources."""
    if not plant:
        return []
    start, end_exclusive = _local_bounds(start_date, end_date)
    cases = []
    if water_type in {SamplingSchedule.RAW, SamplingSchedule.COAGULATED, SamplingSchedule.CLARIFIED, SamplingSchedule.TREATED}:
        queryset = NonConformity.objects.filter(
            analysis__treatment_plant=plant,
            analysis__analysis_time__schedule__water_type=water_type,
            created_at__gte=start,
            created_at__lt=end_exclusive,
        ).select_related(
            "analysis", "analysis__analysis_time", "analysis__analysis_time__schedule",
            "analysis__treatment_plant", "triggered_by", "reviewed_by",
        ).prefetch_related("causes", "logs")
        if search:
            queryset = queryset.filter(
                Q(parameter_name__icontains=search)
                | Q(analysis__reference_id__icontains=search)
                | Q(corrective_action__icontains=search)
                | Q(preventive_action__icontains=search)
                | Q(root_cause__icontains=search)
                | Q(causes__name__icontains=search)
                | Q(logs__remarks__icontains=search)
            ).distinct()
        for item in queryset.iterator(chunk_size=1000):
            cases.append(_normalize(
                item, water_type, "qc", item.analysis,
                corrective_action=item.corrective_action,
                preventive_action=item.preventive_action,
                root_cause=item.root_cause,
            ))
    elif water_type == "microbial":
        queryset = MicrobialNonConformity.objects.filter(
            analysis__treatment_plant=plant, created_at__gte=start, created_at__lt=end_exclusive,
        ).select_related("analysis", "analysis__treatment_plant_phase", "analysis__sampling_time").prefetch_related("logs")
        if search:
            queryset = queryset.filter(
                Q(parameter_name__icontains=search)
                | Q(analysis__reference_id__icontains=search)
                | Q(logs__remarks__icontains=search)
            ).distinct()
        for item in queryset.iterator(chunk_size=1000):
            cases.append(_normalize(item, water_type, "microbial", item.analysis))
    elif water_type == "heavy_metal":
        queryset = HeavyMetalNonConformity.objects.filter(
            analysis__treatment_plant=plant, created_at__gte=start, created_at__lt=end_exclusive,
        ).select_related("analysis", "analysis__treatment_plant_phase", "analysis__sampling_time").prefetch_related("causes", "logs")
        if search:
            queryset = queryset.filter(
                Q(parameter_name__icontains=search)
                | Q(analysis__reference_id__icontains=search)
                | Q(corrective_action__icontains=search)
                | Q(preventive_action__icontains=search)
                | Q(root_cause__icontains=search)
                | Q(causes__name__icontains=search)
                | Q(logs__remarks__icontains=search)
            ).distinct()
        for item in queryset.iterator(chunk_size=1000):
            cases.append(_normalize(
                item, water_type, "heavy_metal", item.analysis,
                corrective_action=item.corrective_action,
                preventive_action=item.preventive_action,
                root_cause=item.root_cause,
            ))
    elif water_type == "filtered_water":
        queryset = FilteredWaterResults.objects.filter(
            analysis__treatment_plant=plant,
            analysis__timestamp__gte=start,
            analysis__timestamp__lt=end_exclusive,
            result_value__isnull=False,
        ).select_related(
            "analysis", "analysis__treatment_plant_phase", "water_filter",
            "parameter", "parameter__parameter",
        ).order_by("analysis__timestamp", "pk")
        if search:
            queryset = queryset.filter(
                Q(analysis__uuid__icontains=search)
                | Q(parameter__parameter__name__icontains=search)
                | Q(water_filter__name__icontains=search)
                | Q(analysis__remarks__icontains=search)
            )
        for item in queryset.iterator(chunk_size=1000):
            value = _finite(item.result_value)
            minimum = _finite(item.parameter.min_value)
            maximum = _finite(item.parameter.max_value)
            if value is None or (minimum is None and maximum is None):
                continue
            if (minimum is None or value >= minimum) and (maximum is None or value <= maximum):
                continue
            boundary = minimum if minimum is not None and value < minimum else maximum
            deviation = abs(value - boundary) if boundary is not None else 0.0
            scale = max(abs(maximum or minimum or 0), 1.0)
            risk = min(10.0, 1.0 + deviation / scale * 5.0)
            case = _normalize(
                item, water_type, "filtered_derived", item.analysis,
                parameter_name=item.parameter.parameter.name,
                observed=value, minimum=minimum, maximum=maximum, deviation=deviation,
                risk_score=risk, status="derived", auto_detected=True,
            )
            case["water_filter"] = getattr(item.water_filter, "name", "")
            case["unit"] = item.parameter.parameter.unit
            cases.append(case)

    if status:
        cases = [case for case in cases if case["status"] == status]
    if severity:
        cases = [case for case in cases if case["risk_band"].casefold() == severity.casefold()]
    parameter_units = _parameter_units(plant, water_type)
    for case in cases:
        case["unit"] = case.get("unit") or parameter_units.get(case["parameter"], "")
    sort_key = {
        "date": "date", "risk": "risk_score", "deviation": "deviation",
        "status": "status", "parameter": "parameter", "reference": "reference",
    }.get(sort, "date")
    def sort_value(case):
        value = case.get(sort_key)
        if value is None:
            return (1, "")
        if isinstance(value, (int, float)):
            return (0, float(value))
        return (0, str(value).casefold())
    cases.sort(key=sort_value, reverse=direction != "asc")
    return cases


def analyze_noncompliance(cases, group_by="day", start_date=None, end_date=None):
    """Descriptive case, risk, aging and recurrence analytics; no exposure rate is inferred."""
    import numpy as np
    import pandas as pd
    from scipy import stats

    frame = pd.DataFrame(cases)
    if frame.empty:
        return {
            "total": 0, "open": 0, "under_review": 0, "closed": 0, "derived": 0,
            "risk_mean": None, "risk_median": None, "resolution_median_days": None,
            "status_counts": [], "risk_counts": [], "top_parameters": [],
            "periods": [], "trend": None, "correlation": None, "critical_high": 0,
            "aging_buckets": [], "active_age_median_days": None, "top_causes": [],
            "method_note": "Case counts are not normalized by sampling volume. Dashboard risk bands are computed from stored scores: low <3, moderate 3–<6, high 6–<8, critical ≥8. Filtered-water events are derived limit exceedances, not persisted non-conformity records; their heuristic score is min(10, 1 + 5 × absolute deviation / max(|limit|, 1)).",
        }
    frame["risk_score"] = pd.to_numeric(frame["risk_score"], errors="coerce").fillna(0)
    frame["deviation"] = pd.to_numeric(frame["deviation"], errors="coerce")
    frame["recorded_date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["resolved_date"] = pd.to_datetime(frame["resolved_at"], errors="coerce", utc=True)
    closed = frame[(frame["status"] == "closed") & frame["resolved_date"].notna() & frame["recorded_date"].notna()]
    if len(closed):
        recorded_utc = pd.to_datetime(closed["recorded_at"], errors="coerce", utc=True)
        resolution_days = (closed["resolved_date"] - recorded_utc).dt.total_seconds().div(86400).dropna()
    else:
        resolution_days = pd.Series(dtype=float)
    status_counts = frame["status_label"].value_counts().rename_axis("label").reset_index(name="count").to_dict("records")
    risk_order = ["Critical", "High", "Moderate", "Low"]
    risk_counts = frame["risk_band"].value_counts().reindex(risk_order, fill_value=0).rename_axis("label").reset_index(name="count").to_dict("records")
    top_parameters = frame.groupby("parameter", dropna=False).agg(
        cases=("id", "count"), median_risk=("risk_score", "median"),
        mean_deviation=("deviation", "mean"),
    ).sort_values(["cases", "median_risk"], ascending=False).head(12).reset_index().to_dict("records")
    top_causes = []
    if "causes_list" in frame:
        cause_counts = frame["causes_list"].explode().dropna().value_counts().head(10)
        top_causes = [{"cause": str(cause), "cases": int(count)} for cause, count in cause_counts.items()]
    today = pd.Timestamp(timezone.localdate())
    active = frame[frame["status"].isin(["open", "under_review"])].copy()
    active_ages = (today - active["recorded_date"].dt.normalize()).dt.days.clip(lower=0).dropna().astype(int)
    age_bands = [("0–7 days", 0, 7), ("8–30 days", 8, 30), ("31–90 days", 31, 90), ("Over 90 days", 91, float("inf"))]
    aging_buckets = [{"label": label, "count": int(((active_ages >= lower) & (active_ages <= upper)).sum())} for label, lower, upper in age_bands]
    frequency = {"day": "D", "week": "W-MON", "month": "MS", "quarter": "QS", "half_year": "2QS", "year": "YS"}.get(group_by, "D")
    daily = frame.dropna(subset=["recorded_date"]).set_index("recorded_date")["id"].resample(frequency).count()
    if start_date and end_date:
        anchor = pd.Timestamp(start_date)
        if group_by == "week":
            anchor += pd.Timedelta(days=(7 - anchor.weekday()) % 7)
        elif group_by == "month":
            anchor = anchor.replace(day=1)
        elif group_by == "quarter":
            anchor = anchor.replace(month=((anchor.month - 1) // 3) * 3 + 1, day=1)
        elif group_by == "half_year":
            anchor = anchor.replace(month=1 if anchor.month <= 6 else 7, day=1)
        elif group_by == "year":
            anchor = anchor.replace(month=1, day=1)
        calendar_end = pd.Timestamp(end_date)
        if group_by == "week":
            calendar_end += pd.Timedelta(days=(7 - calendar_end.weekday()) % 7)
        calendar = pd.date_range(start=anchor, end=calendar_end, freq=frequency)
        if len(calendar):
            daily = daily.reindex(calendar, fill_value=0)
    def period_label(timestamp):
        if group_by == "day":
            return timestamp.strftime("%d %b %Y")
        if group_by == "week":
            return f"Week ending {timestamp.strftime('%d %b %Y')}"
        if group_by == "month":
            return timestamp.strftime("%b %Y")
        if group_by == "quarter":
            return f"Q{timestamp.quarter} {timestamp.year}"
        if group_by == "half_year":
            return f"H{1 if timestamp.month <= 6 else 2} {timestamp.year}"
        return timestamp.strftime("%Y")
    periods = [{"date": timestamp.strftime("%Y-%m-%d"), "label": period_label(timestamp), "cases": int(count)} for timestamp, count in daily.items()]
    trend = None
    if len(daily) >= 3 and daily.nunique() > 1:
        slope = stats.theilslopes(daily.to_numpy(dtype=float), np.arange(len(daily), dtype=float))
        trend = {"slope_per_period": float(slope.slope), "intercept": float(slope.intercept), "low": float(slope.low_slope), "high": float(slope.high_slope), "periods": int(len(daily)), "method": "Theil–Sen slope of recorded case counts"}
    pair = frame[["risk_score", "deviation"]].dropna()
    correlation = None
    if len(pair) >= 5 and pair["risk_score"].nunique() > 1 and pair["deviation"].nunique() > 1:
        result = stats.spearmanr(pair["risk_score"], pair["deviation"])
        correlation = {"rho": float(result.statistic), "p_value": float(result.pvalue), "n": int(len(pair)), "interpretation": "Exploratory association; risk scores are calculated from recorded deviations in some source workflows."}
    return {
        "total": int(len(frame)),
        "open": int((frame["status"] == "open").sum()),
        "under_review": int((frame["status"] == "under_review").sum()),
        "closed": int((frame["status"] == "closed").sum()),
        "derived": int((frame["status"] == "derived").sum()),
        "risk_mean": float(frame["risk_score"].mean()),
        "risk_median": float(frame["risk_score"].median()),
        "critical_high": int(frame["risk_band"].isin(["Critical", "High"]).sum()),
        "resolution_median_days": float(resolution_days.median()) if len(resolution_days) else None,
        "active_age_median_days": float(active_ages.median()) if len(active_ages) else None,
        "aging_buckets": aging_buckets,
        "top_causes": top_causes,
        "status_counts": status_counts,
        "risk_counts": risk_counts,
        "top_parameters": top_parameters,
        "periods": periods,
        "trend": trend,
        "correlation": correlation,
        "group_by": group_by,
        "method_note": "Case counts are not normalized by sampling volume. Dashboard risk bands are computed from stored scores: low <3, moderate 3–<6, high 6–<8, critical ≥8. Filtered-water events are derived limit exceedances, not persisted non-conformity records; their heuristic score is min(10, 1 + 5 × absolute deviation / max(|limit|, 1)).",
    }
