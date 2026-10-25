"""Data preparation and statistical analysis for the QC reporting workspace."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone
from filtered_water.models import FilteredWaterAnalysis, FilteredWaterResults
from heavy_metal.models import HeavyMetalAnalysis, HeavyMetalParameter as HeavyMetalResult
from microbial.models import MicrobialAnalysis, MicrobialParameterResult

from qc.models import (
    ClarifiedWaterResult,
    CoagulatedWaterResult,
    RawWaterResult,
    SamplingSchedule,
    TreatedWaterResult,
    WaterAnalysis,
)
from t.models import (
    ClarifiedWaterLimit,
    CoagulatedWaterLimit,
    FilteredWaterLimit,
    HeavyMetalLimit,
    MicrobialLimit,
    RawWaterLimit,
    TreatmentPlant,
    TreatmentPlantPhase,
    TreatedWaterLimit,
)


WATER_TYPES = (
    (SamplingSchedule.RAW, "Raw water"),
    (SamplingSchedule.COAGULATED, "Coagulated water"),
    (SamplingSchedule.CLARIFIED, "Clarified water"),
    (SamplingSchedule.TREATED, "Treated water"),
    ("filtered_water", "Filtered water"),
    ("microbial", "Microbial analysis"),
    ("heavy_metal", "Heavy metal analysis"),
)

RESULT_CONFIG = {
    SamplingSchedule.RAW: {
        "title": "Raw water",
        "result_model": RawWaterResult,
        "limit_model": RawWaterLimit,
        "color": "#06b6d4",
    },
    SamplingSchedule.COAGULATED: {
        "title": "Coagulated water",
        "result_model": CoagulatedWaterResult,
        "limit_model": CoagulatedWaterLimit,
        "color": "#8b5cf6",
    },
    SamplingSchedule.CLARIFIED: {
        "title": "Clarified water",
        "result_model": ClarifiedWaterResult,
        "limit_model": ClarifiedWaterLimit,
        "color": "#f59e0b",
    },
    SamplingSchedule.TREATED: {
        "title": "Treated water",
        "result_model": TreatedWaterResult,
        "limit_model": TreatedWaterLimit,
        "color": "#10b981",
    },
}

PERIOD_LENGTHS = {
    "day": 1,
    "week": 7,
    "month": 30,
    "quarter": 91,
    "half_year": 182,
    "year": 365,
}

GROUP_RULES = {
    "day": "D",
    "week": "W-MON",
    "month": "MS",
    "quarter": "QS",
    "half_year": "2QS",
    "year": "YS",
}

SORT_FIELDS = {
    "date": "timestamp",
    "water_type": "water_type",
    "parameter": "parameter",
    "value": "value",
    "status": "status",
    "phase": "phase",
    "reference": "reference",
}


def _float(value: Any, default=None):
    try:
        if value is None:
            return default
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _as_decimal_text(value):
    return "" if value is None else str(value)


def _is_compliant(value, minimum, maximum):
    if value is None or (minimum is None and maximum is None):
        return None
    return (minimum is None or value >= minimum) and (maximum is None or value <= maximum)


def load_result_rows(
    *,
    plant: TreatmentPlant,
    start_date: date,
    end_date: date,
    water_type: str = "all",
    parameter_name: str = "",
    phase_id: str = "",
    search: str = "",
):
    """Load normalized result rows with plant, date, and user-selected filters applied."""
    rows = []
    if not plant:
        return rows

    if water_type == "filtered_water":
        local_start = timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone())
        local_end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), timezone.get_current_timezone())
        queryset = FilteredWaterResults.objects.filter(
            analysis__treatment_plant=plant,
            analysis__timestamp__gte=local_start,
            analysis__timestamp__lt=local_end,
            analysis__state__in=("analysed", "verified"),
        ).select_related(
            "analysis__treatment_plant", "analysis__treatment_plant_phase",
            "water_filter", "parameter__parameter",
        ).order_by("analysis__timestamp", "water_filter__name", "pk")
        if parameter_name:
            queryset = queryset.filter(parameter__parameter__name=parameter_name)
        if phase_id:
            queryset = queryset.filter(analysis__treatment_plant_phase_id=phase_id)
        if search:
            queryset = queryset.filter(
                Q(analysis__uuid__icontains=search)
                | Q(parameter__parameter__name__icontains=search)
                | Q(water_filter__name__icontains=search)
                | Q(analysis__treatment_plant_phase__name__icontains=search)
                | Q(analysis__remarks__icontains=search)
            )
        for result in queryset.iterator(chunk_size=2000):
            analysis = result.analysis
            timestamp = timezone.localtime(analysis.timestamp)
            parameter = result.parameter.parameter
            value = _float(result.result_value)
            minimum = _float(result.parameter.min_value)
            maximum = _float(result.parameter.max_value)
            compliant = _is_compliant(value, minimum, maximum)
            rows.append({
                "id": result.pk, "analysis_id": analysis.pk,
                "sample_id": f"filtered:{analysis.pk}:{result.water_filter_id}",
                "reference": str(analysis.uuid), "plant": analysis.treatment_plant.name,
                "water_type": "filtered_water", "water_type_label": "Filtered water",
                "date": timestamp.date().isoformat(), "time": timestamp.strftime("%H:%M"),
                "timestamp": timestamp, "shift": "", "phase": analysis.treatment_plant_phase.name,
                "filter_name": result.water_filter.name, "state": analysis.state,
                "parameter": parameter.name, "unit": parameter.unit,
                "value": value, "value_text": _as_decimal_text(result.result_value),
                "minimum": minimum, "maximum": maximum,
                "minimum_text": _as_decimal_text(result.parameter.min_value),
                "maximum_text": _as_decimal_text(result.parameter.max_value),
                "status": "Missing" if value is None else "No limit configured" if compliant is None else "Within limits" if compliant else "Out of range",
                "compliant": compliant, "remarks": analysis.remarks or "",
            })
    elif water_type in {"microbial", "heavy_metal"}:
        is_microbial = water_type == "microbial"
        model = MicrobialParameterResult if is_microbial else HeavyMetalResult
        state_filter = ("analysed", "verified", "confirmed", "approved")
        queryset = model.objects.filter(
            analysis__treatment_plant=plant,
            analysis__analysis_date__range=(start_date, end_date),
            analysis__state__in=state_filter,
        ).select_related(
            "analysis__treatment_plant", "analysis__treatment_plant_phase",
            "analysis__sampling_time", "analysis__shift", "parameter__parameter",
        ).order_by("analysis__analysis_date", "analysis__sampling_time__time", "pk")
        if parameter_name:
            queryset = queryset.filter(parameter__parameter__name=parameter_name)
        if phase_id:
            queryset = queryset.filter(analysis__treatment_plant_phase_id=phase_id)
        if search:
            search_query = (
                Q(analysis__reference_id__icontains=search)
                | Q(parameter__parameter__name__icontains=search)
                | Q(analysis__treatment_plant_phase__name__icontains=search)
                | Q(analysis__remarks__icontains=search)
            )
            if is_microbial:
                search_query |= Q(analysis__method__name__icontains=search)
            queryset = queryset.filter(search_query)
        label = "Microbial analysis" if is_microbial else "Heavy metal analysis"
        for result in queryset.iterator(chunk_size=2000):
            analysis = result.analysis
            sampling_time = analysis.sampling_time.time
            timestamp = datetime.combine(analysis.analysis_date, sampling_time)
            if timezone.is_aware(timezone.now()):
                timestamp = timezone.make_aware(timestamp, timezone.get_current_timezone())
            parameter = result.parameter.parameter
            entry_status = getattr(result, "entry_status", "recorded")
            value_is_recorded = entry_status == "recorded"
            value = _float(result.value) if value_is_recorded else None
            minimum = _float(result.parameter.min_value)
            maximum = _float(result.parameter.max_value)
            compliant = _is_compliant(value, minimum, maximum)
            status = (
                "Pending entry" if entry_status == "pending"
                else "Verify historical value" if entry_status == "legacy_unverified"
                else "Missing" if value is None
                else "No limit configured" if compliant is None
                else "Within limits" if compliant else "Out of range"
            )
            rows.append({
                "id": result.pk, "analysis_id": analysis.pk,
                "sample_id": f"{water_type}:{analysis.pk}",
                "reference": analysis.reference_id, "plant": analysis.treatment_plant.name,
                "water_type": water_type, "water_type_label": label,
                "date": analysis.analysis_date.isoformat(), "time": sampling_time.strftime("%H:%M"),
                "timestamp": timestamp, "shift": str(analysis.shift) if analysis.shift else "",
                "phase": analysis.treatment_plant_phase.name, "filter_name": "", "state": analysis.state,
                "parameter": parameter.name, "unit": parameter.unit,
                "value": value, "value_text": _as_decimal_text(result.value) if value_is_recorded else "",
                "entry_status": entry_status,
                "entry_status_label": "Recorded" if value_is_recorded else "Pending entry" if entry_status == "pending" else "Verify historical value",
                "minimum": minimum, "maximum": maximum,
                "minimum_text": _as_decimal_text(result.parameter.min_value),
                "maximum_text": _as_decimal_text(result.parameter.max_value),
                "status": status,
                "compliant": compliant, "remarks": analysis.remarks or "",
            })
    elif water_type in RESULT_CONFIG:
        config = RESULT_CONFIG[water_type]
        model = config["result_model"]
        queryset = (
            model.objects.filter(
                analysis__treatment_plant=plant,
                analysis__analysis_date__range=(start_date, end_date),
                analysis__analysis_time__schedule__water_type=water_type,
            )
            .select_related(
                "analysis__treatment_plant",
                "analysis__analysis_time__schedule",
                "analysis__shift",
                "parameter__parameter",
                "phase",
            )
            .order_by("analysis__analysis_date", "analysis__analysis_time__time", "pk")
        )
        if parameter_name:
            queryset = queryset.filter(parameter__parameter__name=parameter_name)
        if phase_id and water_type != SamplingSchedule.RAW:
            queryset = queryset.filter(phase_id=phase_id)
        if search:
            queryset = queryset.filter(
                Q(analysis__reference_id__icontains=search)
                | Q(parameter__parameter__name__icontains=search)
                | Q(phase__name__icontains=search)
                | Q(analysis__remarks__icontains=search)
            )

        config = RESULT_CONFIG[water_type]
        for result in queryset.iterator(chunk_size=2000):
            analysis = result.analysis
            sampling_time = analysis.analysis_time.time
            sampled_at = datetime.combine(analysis.analysis_date, sampling_time)
            if timezone.is_aware(timezone.now()):
                sampled_at = timezone.make_aware(sampled_at, timezone.get_current_timezone())

            parameter = result.parameter.parameter
            numeric_value = _float(result.value)
            minimum = _float(result.parameter.min_value)
            maximum = _float(result.parameter.max_value)
            compliant = _is_compliant(numeric_value, minimum, maximum)
            status = (
                "Missing" if numeric_value is None
                else "No limit configured" if compliant is None
                else "Within limits" if compliant
                else "Out of range"
            )

            rows.append({
                "id": result.pk,
                "analysis_id": analysis.pk,
                "sample_id": f"qc:{analysis.pk}:{result.phase_id or 'raw'}",
                "reference": analysis.reference_id,
                "plant": analysis.treatment_plant.name,
                "water_type": water_type,
                "water_type_label": config["title"],
                "date": analysis.analysis_date.isoformat(),
                "time": sampling_time.strftime("%H:%M"),
                "timestamp": sampled_at,
                "shift": str(analysis.shift) if analysis.shift else "",
                "phase": result.phase.name if result.phase else "—",
                "filter_name": "",
                "state": "",
                "parameter": parameter.name,
                "unit": parameter.unit,
                "value": numeric_value,
                "value_text": _as_decimal_text(result.value),
                "minimum": minimum,
                "maximum": maximum,
                "minimum_text": _as_decimal_text(result.parameter.min_value),
                "maximum_text": _as_decimal_text(result.parameter.max_value),
                "status": status,
                "compliant": compliant,
                "remarks": analysis.remarks or "",
            })

    if search:
        needle = search.casefold()
        rows = [row for row in rows if needle in " ".join(
            str(row.get(field, "")) for field in (
                "reference", "plant", "water_type_label", "date", "time", "shift",
                "phase", "filter_name", "parameter", "unit", "value_text", "status", "state", "remarks",
            )
        ).casefold()]
    return rows


def parameter_options(plant: TreatmentPlant, water_type="all"):
    """Return unique parameter names configured for the selected plant and water type."""
    if not plant:
        return []
    options = {}
    if water_type in RESULT_CONFIG:
        limit_models = (RESULT_CONFIG[water_type]["limit_model"],)
    elif water_type == "filtered_water":
        limit_models = (FilteredWaterLimit,)
    elif water_type == "microbial":
        limit_models = (MicrobialLimit,)
    elif water_type == "heavy_metal":
        limit_models = (HeavyMetalLimit,)
    else:
        limit_models = tuple(config["limit_model"] for config in RESULT_CONFIG.values())
    for limit_model in limit_models:
        query = limit_model.objects.filter(treatment_plant=plant).select_related("parameter")
        for limit in query.order_by("parameter__name"):
            parameter = limit.parameter
            options[parameter.name] = {"name": parameter.name, "unit": parameter.unit}
    return sorted(options.values(), key=lambda item: item["name"].casefold())


def count_analysis_records(*, plant, start_date, end_date, water_type, parameter_name="", phase_id="", search=""):
    """Count source analyses in the selected scope independently of result rows."""
    if not plant:
        return 0
    if water_type == "filtered_water":
        queryset = FilteredWaterAnalysis.objects.filter(
            treatment_plant=plant,
            timestamp__gte=timezone.make_aware(datetime.combine(start_date, time.min), timezone.get_current_timezone()),
            timestamp__lt=timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min), timezone.get_current_timezone()),
        )
        if phase_id:
            queryset = queryset.filter(treatment_plant_phase_id=phase_id)
        if search:
            queryset = queryset.filter(Q(uuid__icontains=search) | Q(remarks__icontains=search))
        if parameter_name:
            queryset = queryset.filter(results__parameter__parameter__name=parameter_name)
        return queryset.values("pk").distinct().count()
    if water_type == "microbial":
        queryset = MicrobialAnalysis.objects.filter(
            treatment_plant=plant, analysis_date__range=(start_date, end_date)
        )
        if phase_id:
            queryset = queryset.filter(treatment_plant_phase_id=phase_id)
        if search:
            queryset = queryset.filter(Q(reference_id__icontains=search) | Q(remarks__icontains=search))
        if parameter_name:
            queryset = queryset.filter(
                pk__in=MicrobialParameterResult.objects.filter(
                    analysis__in=queryset,
                    parameter__parameter__name=parameter_name,
                ).values("analysis_id")
            )
        return queryset.distinct().count()
    if water_type == "heavy_metal":
        queryset = HeavyMetalAnalysis.objects.filter(
            treatment_plant=plant, analysis_date__range=(start_date, end_date)
        )
        if phase_id:
            queryset = queryset.filter(treatment_plant_phase_id=phase_id)
        if search:
            queryset = queryset.filter(Q(reference_id__icontains=search) | Q(remarks__icontains=search))
        if parameter_name:
            queryset = queryset.filter(
                pk__in=HeavyMetalResult.objects.filter(
                    analysis__in=queryset,
                    parameter__parameter__name=parameter_name,
                ).values("analysis_id")
            )
        return queryset.distinct().count()

    queryset = WaterAnalysis.objects.filter(
        treatment_plant=plant,
        analysis_date__range=(start_date, end_date),
        analysis_time__schedule__water_type=water_type,
    )
    if search:
        queryset = queryset.filter(Q(reference_id__icontains=search) | Q(remarks__icontains=search))
    result_model = RESULT_CONFIG.get(water_type, {}).get("result_model")
    if result_model and (parameter_name or phase_id):
        result_query = result_model.objects.filter(analysis__in=queryset)
        if parameter_name:
            result_query = result_query.filter(parameter__parameter__name=parameter_name)
        if phase_id and water_type != SamplingSchedule.RAW:
            result_query = result_query.filter(phase_id=phase_id)
        queryset = queryset.filter(pk__in=result_query.values("analysis_id"))
    return queryset.distinct().count()


def phase_options(plant: TreatmentPlant):
    if not plant:
        return []
    return list(TreatmentPlantPhase.objects.filter(treatment_plant=plant).order_by("name").values("id", "name"))


def parameter_summaries(rows):
    import numpy as np
    import pandas as pd
    from scipy import stats

    if not rows:
        return []
    df = pd.DataFrame(rows)
    summaries = []
    for (name, unit), group in df.groupby(["parameter", "unit"], dropna=False, sort=True):
        values = pd.to_numeric(group["value"], errors="coerce").dropna().to_numpy(dtype=float)
        count = int(values.size)
        if count:
            mean = float(np.mean(values))
            std = float(np.std(values, ddof=1)) if count > 1 else 0.0
            sem = std / math.sqrt(count) if count else 0.0
            critical = float(stats.t.ppf(0.975, count - 1)) if count > 1 else 0.0
            ci_low, ci_high = (mean - critical * sem, mean + critical * sem) if count > 1 else (None, None)
            percentiles = np.percentile(values, [5, 25, 50, 75, 95])
            skew = float(stats.skew(values, bias=False)) if count > 2 else None
            kurtosis = float(stats.kurtosis(values, bias=False)) if count > 3 else None
        else:
            mean = std = ci_low = ci_high = skew = kurtosis = None
            percentiles = [None] * 5
        # Boolean comparisons ignore missing values without coercing the column
        # through fillna(), which pandas is deprecating for mixed object dtypes.
        compliant_count = int(group["compliant"].eq(True).sum())
        evaluated = int(group["compliant"].notna().sum())
        sample_groups = group.groupby("sample_id", dropna=False)
        sample_statuses = [_sample_compliance(part) for _, part in sample_groups]
        collected_samples = len(sample_statuses)
        complying_samples = sum(status is True for status in sample_statuses)
        evaluated_samples = sum(status is not None for status in sample_statuses)
        summaries.append({
            "parameter": str(name),
            "unit": str(unit or ""),
            "n": count,
            "result_count": int(len(group)),
            "missing": int((group["status"] == "Missing").sum()),
            "pending": int(group["status"].isin(["Pending entry", "Verify historical value"]).sum()),
            "not_evaluated": int(((group["value"].notna()) & (group["compliant"].isna())).sum()),
            "mean": _float(mean),
            "median": _float(percentiles[2]),
            "std": _float(std),
            "cv": _float((std / abs(mean) * 100) if mean else None),
            "min": _float(np.min(values)) if count else None,
            "p05": _float(percentiles[0]),
            "q1": _float(percentiles[1]),
            "q3": _float(percentiles[3]),
            "p95": _float(percentiles[4]),
            "max": _float(np.max(values)) if count else None,
            "ci_low": _float(ci_low),
            "ci_high": _float(ci_high),
            "skewness": _float(skew),
            "kurtosis": _float(kurtosis),
            "out_of_range": int((group["compliant"] == False).sum()),
            "compliant": compliant_count,
            "compliance_rate": round(compliant_count / evaluated * 100, 2) if evaluated else None,
            "samples_collected": collected_samples,
            "samples_complying": complying_samples,
            "sample_compliance_rate": round(complying_samples / evaluated_samples * 100, 2) if evaluated_samples else None,
            "lower_limit": next((row["minimum"] for row in group.to_dict("records") if row["minimum"] is not None), None),
            "upper_limit": next((row["maximum"] for row in group.to_dict("records") if row["maximum"] is not None), None),
        })
    return summaries


def _sample_compliance(sample_rows):
    """A sample complies only when every reported result has an applicable limit and passes."""
    import pandas as pd

    if isinstance(sample_rows, pd.DataFrame):
        if sample_rows.empty:
            return None
        statuses = sample_rows["compliant"].tolist()
    else:
        if not sample_rows:
            return None
        statuses = [row.get("compliant") for row in sample_rows]

    # Convert pandas/NumPy scalar booleans and NaN/pd.NA to stable Python values.
    statuses = [None if pd.isna(status) else bool(status) for status in statuses]
    if not statuses:
        return None
    if any(status is False for status in statuses):
        return False
    if all(status is True for status in statuses):
        return True
    return None


def sample_summary(rows, samples_collected=None):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["sample_id"], []).append(row)
    statuses = [_sample_compliance(sample_rows) for sample_rows in grouped.values()]
    evaluated = sum(status is not None for status in statuses)
    samples_with_results = len(grouped)
    collected = max(samples_with_results, int(samples_collected or 0))
    incomplete = sum(status is None for status in statuses) + max(0, collected - samples_with_results)
    return {
        "samples_collected": collected,
        "samples_with_results": samples_with_results,
        "samples_complying": sum(status is True for status in statuses),
        "samples_out_of_range": sum(status is False for status in statuses),
        "samples_not_fully_evaluated": incomplete,
        "samples_evaluated": evaluated,
        "sample_compliance_rate": round(sum(status is True for status in statuses) / evaluated * 100, 1) if evaluated else None,
    }


def daily_parameter_summaries(rows):
    """Daily descriptive rollups per parameter, retaining sample and result denominators."""
    import numpy as np
    import pandas as pd

    if not rows:
        return []
    frame = pd.DataFrame(rows)
    output = []
    for (day, parameter, unit), group in frame.groupby(["date", "parameter", "unit"], dropna=False, sort=True):
        values = pd.to_numeric(group["value"], errors="coerce").dropna().to_numpy(dtype=float)
        per_sample = group.groupby("sample_id", dropna=False)
        sample_statuses = [_sample_compliance(part.to_dict("records")) for _, part in per_sample]
        evaluated_samples = sum(status is not None for status in sample_statuses)
        evaluated_results = int(group["compliant"].notna().sum())
        within = int((group["compliant"] == True).sum())
        out_of_range = int((group["compliant"] == False).sum())
        output.append({
            "date": str(day), "parameter": str(parameter), "unit": str(unit or ""),
            "samples_collected": int(group["sample_id"].nunique()),
            "samples_complying": sum(status is True for status in sample_statuses),
            "samples_out_of_range": sum(status is False for status in sample_statuses),
            "samples_evaluated": evaluated_samples,
            "sample_compliance_rate": round(sum(status is True for status in sample_statuses) / evaluated_samples * 100, 1) if evaluated_samples else None,
            "result_count": int(len(group)), "measured_count": int(values.size),
            "minimum": _float(np.min(values)) if values.size else None,
            "maximum": _float(np.max(values)) if values.size else None,
            "mean": _float(np.mean(values)) if values.size else None,
            "median": _float(np.median(values)) if values.size else None,
            "std": _float(np.std(values, ddof=1)) if values.size > 1 else (0.0 if values.size else None),
            "within_limits": within, "out_of_range": out_of_range,
            "missing": int((group["status"] == "Missing").sum()),
            "pending": int(group["status"].isin(["Pending entry", "Verify historical value"]).sum()),
            "no_limits": int((group["status"] == "No limit configured").sum()),
            "result_compliance_rate": round(within / evaluated_results * 100, 1) if evaluated_results else None,
        })
    output.sort(key=lambda item: (item["date"], item["parameter"]), reverse=True)
    return output


def multivariate_analysis(rows):
    """Pairwise parameter association and standardized PCA for matched samples."""
    import numpy as np
    import pandas as pd
    from scipy import stats

    empty = {
        "parameters": [], "sample_count": 0, "correlations": [],
        "pearson_matrix": [], "spearman_matrix": [], "sample_size_matrix": [],
        "pca": {"available": False, "reason": "No parameter data is available.", "scores": [], "loadings": [], "explained_variance": []},
    }
    if not rows:
        return empty

    frame = pd.DataFrame(rows)
    frame["numeric_value"] = pd.to_numeric(frame["value"], errors="coerce")
    pivot = frame.pivot_table(index="sample_id", columns="parameter", values="numeric_value", aggfunc="mean")
    pivot = pivot.replace([np.inf, -np.inf], np.nan).dropna(how="all")
    parameters = [
        column for column in pivot.columns
        if int(pivot[column].notna().sum()) >= 3 and int(pivot[column].dropna().nunique()) > 1
    ]
    pivot = pivot[parameters]
    labels = [str(value) for value in pivot.columns]
    width = len(labels)
    pearson = [[None for _ in range(width)] for _ in range(width)]
    spearman = [[None for _ in range(width)] for _ in range(width)]
    pair_sizes = [[0 for _ in range(width)] for _ in range(width)]
    pearson_pairs = []
    spearman_pairs = []
    for index in range(width):
        pearson[index][index] = 1.0
        spearman[index][index] = 1.0
        pair_sizes[index][index] = int(pivot.iloc[:, index].notna().sum())
        for other in range(index + 1, width):
            paired = pivot.iloc[:, [index, other]].dropna()
            count = len(paired)
            pair_sizes[index][other] = pair_sizes[other][index] = count
            if count < 3:
                continue
            left = paired.iloc[:, 0].to_numpy(dtype=float)
            right = paired.iloc[:, 1].to_numpy(dtype=float)
            if np.std(left) == 0 or np.std(right) == 0:
                continue
            pearson_result = stats.pearsonr(left, right)
            spearman_result = stats.spearmanr(left, right)
            pearson[index][other] = pearson[other][index] = _float(pearson_result.statistic)
            spearman[index][other] = spearman[other][index] = _float(spearman_result.statistic)
            pearson_pairs.append({"left": labels[index], "right": labels[other], "r": _float(pearson_result.statistic), "p_value": _float(pearson_result.pvalue), "n": count})
            spearman_pairs.append({"left": labels[index], "right": labels[other], "rho": _float(spearman_result.statistic), "p_value": _float(spearman_result.pvalue), "n": count})

    if pearson_pairs:
        from statsmodels.stats.multitest import multipletests
        adjusted = multipletests([item["p_value"] for item in pearson_pairs], method="fdr_bh")
        for item, value in zip(pearson_pairs, adjusted[1]):
            item["fdr_q_value"] = _float(value)
        adjusted = multipletests([item["p_value"] for item in spearman_pairs], method="fdr_bh")
        for item, value in zip(spearman_pairs, adjusted[1]):
            item["fdr_q_value"] = _float(value)

    pearson_pairs.sort(key=lambda item: abs(item["r"] or 0), reverse=True)
    spearman_pairs.sort(key=lambda item: abs(item["rho"] or 0), reverse=True)
    pca = {"available": False, "reason": "At least two varying parameters and three matched samples are needed for PCA.", "scores": [], "loadings": [], "explained_variance": []}
    if width >= 2 and len(pivot) >= 3:
        from sklearn.decomposition import PCA
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler

        # Keep the most complete variables if a very wide assay is selected.
        selected_columns = sorted(parameters, key=lambda column: (-int(pivot[column].notna().sum()), str(column).casefold()))[:20]
        matrix = pivot[selected_columns]
        imputed = SimpleImputer(strategy="median").fit_transform(matrix)
        scaled = StandardScaler().fit_transform(imputed)
        component_count = min(5, len(matrix), len(selected_columns))
        model = PCA(n_components=component_count, svd_solver="full")
        coordinates = model.fit_transform(scaled)
        positions = np.linspace(0, len(matrix) - 1, min(len(matrix), 1200)).astype(int)
        pca = {
            "available": True,
            "reason": "Median imputation was applied to missing cells before standardization.",
            "samples_used": int(len(matrix)),
            "variables_used": [str(value) for value in selected_columns],
            "explained_variance": [_float(value) for value in model.explained_variance_ratio_],
            "scores": [{"sample_id": str(matrix.index[position]), "pc1": _float(coordinates[position, 0]), "pc2": _float(coordinates[position, 1])} for position in positions],
            "loadings": [{"parameter": str(column), "pc1": _float(model.components_[0, position]), "pc2": _float(model.components_[1, position])} for position, column in enumerate(selected_columns)],
        }

    return {
        "parameters": labels,
        "sample_count": int(len(pivot)),
        "correlations": pearson_pairs,
        "spearman_correlations": spearman_pairs,
        "pearson_matrix": pearson,
        "spearman_matrix": spearman,
        "sample_size_matrix": pair_sizes,
        "pca": pca,
    }


def _downsample(frame, max_points=1800):
    if len(frame) <= max_points:
        return frame
    take = np_linspace_indices(len(frame), max_points)
    return frame.iloc[take]


def _period_label(timestamp, group_by):
    if group_by == "day":
        return timestamp.strftime("%d %b %Y")
    if group_by == "week":
        return f"W{timestamp.isocalendar().week:02d} · {timestamp.strftime('%d %b')}"
    if group_by == "month":
        return timestamp.strftime("%b %Y")
    if group_by == "quarter":
        return f"Q{timestamp.quarter} {timestamp.year}"
    if group_by == "half_year":
        return f"H{1 if timestamp.month <= 6 else 2} {timestamp.year}"
    return timestamp.strftime("%Y")


def np_linspace_indices(length, count):
    # Avoid importing NumPy solely for small chart payloads.
    if count >= length:
        return list(range(length))
    step = (length - 1) / (count - 1)
    return sorted({round(index * step) for index in range(count)})


def build_analytics(rows, previous_rows, focus_parameter="", group_by="day"):
    """Build parameter-focused statistics and compact chart payloads."""
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from scipy import stats

    if not rows:
        return {
            "focus_parameter": focus_parameter or "—",
            "metrics": [], "series": {}, "comparisons": [], "distribution": {},
            "by_group": [], "forecast": [], "anomalies": [], "diagnostics": [],
            "forecast_validation": {"points": 0, "mae": None, "rmse": None, "interval_method": "Not available"},
            "group_by": group_by,
        }

    all_frame = pd.DataFrame(rows)
    if not focus_parameter:
        counts = all_frame["parameter"].value_counts()
        focus_parameter = str(counts.index[0]) if not counts.empty else ""
    frame = all_frame[all_frame["parameter"] == focus_parameter].copy()
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    measured = frame.dropna(subset=["value"]).copy()
    values = measured["value"].to_numpy(dtype=float)
    n = len(values)
    unit = str(frame["unit"].iloc[0]) if len(frame) else ""

    metrics = []
    if n:
        mean = float(np.mean(values))
        std = float(np.std(values, ddof=1)) if n > 1 else 0.0
        sem = std / math.sqrt(n) if n > 1 else 0.0
        ci_critical = float(stats.t.ppf(0.975, n - 1)) if n > 1 else 0.0
        q1, median, q3 = [float(v) for v in np.percentile(values, [25, 50, 75])]
        iqr = q3 - q1
        mad = float(np.median(np.abs(values - median)))
        compliant_values = frame["compliant"].dropna()
        in_range = int((compliant_values == True).sum())
        out_range = int((compliant_values == False).sum())
        evaluated = len(compliant_values)
        metrics = [
            {"label": "Measured results", "value": f"{n:,}", "detail": f"{int(frame['status'].isin(['Pending entry', 'Verify historical value']).sum()):,} pending or unverified · {int((frame['status'] == 'Missing').sum()):,} missing"},
            {"label": "Mean ± 95% CI", "value": f"{mean:.4g} {unit}", "detail": f"{mean-ci_critical*sem:.4g} to {mean+ci_critical*sem:.4g}" if n > 1 else "95% CI unavailable with fewer than two observations"},
            {"label": "Median · IQR", "value": f"{median:.4g} {unit}", "detail": f"IQR {iqr:.4g}"},
            {"label": "Standard deviation", "value": f"{std:.4g} {unit}", "detail": f"CV {_float(std/abs(mean)*100, 0):.2f}%" if mean else "CV unavailable when mean is zero"},
            {"label": "Compliance", "value": f"{(in_range/evaluated*100):.1f}%" if evaluated else "—", "detail": f"{in_range:,} within · {out_range:,} out of range"},
            {"label": "Observed range", "value": f"{np.min(values):.4g} – {np.max(values):.4g}", "detail": f"P05 {np.percentile(values,5):.4g} · P95 {np.percentile(values,95):.4g} {unit}"},
        ]
    else:
        mean = std = median = q1 = q3 = mad = None
        in_range = out_range = evaluated = 0

    timestamps = measured["timestamp"]
    x_days = (timestamps - timestamps.min()).dt.total_seconds().to_numpy() / 86400 if n else np.array([])
    trend = {"slope_per_day": None, "p_value": None, "r_squared": None, "ci_low": None, "ci_high": None, "robust_slope": None, "method": "Daily median regression with HAC errors and Theil–Sen slope"}
    predictions = []
    trend_residuals = values - np.mean(values) if n else np.array([])
    daily_signal = measured.set_index("timestamp")["value"].resample("D").median().dropna()
    daily_values = daily_signal.to_numpy(dtype=float)
    daily_x = (daily_signal.index - daily_signal.index.min()).total_seconds().to_numpy(dtype=float) / 86400 if len(daily_signal) else np.array([])
    if len(daily_signal) >= 3 and np.unique(daily_x).size >= 2:
        design = sm.add_constant(daily_x)
        fitted = sm.OLS(daily_values, design, missing="drop").fit(
            cov_type="HAC", cov_kwds={"maxlags": min(7, max(1, int(math.sqrt(len(daily_values)))))},
        )
        trend_residuals = np.asarray(fitted.resid)
        trend.update({
            "slope_per_day": _float(fitted.params[1]),
            "p_value": _float(fitted.pvalues[1]),
            "r_squared": _float(fitted.rsquared),
            "ci_low": _float(fitted.conf_int()[1][0]),
            "ci_high": _float(fitted.conf_int()[1][1]),
            "independent_days": int(len(daily_values)),
        })
        predicted = fitted.predict(sm.add_constant(x_days))
        sample = _downsample(measured.reset_index(drop=True), 1800)
        sample_positions = sample.index.to_numpy()
        predictions = [_float(predicted[pos]) for pos in sample_positions]
        if len(daily_values) <= 5000:
            slope = stats.theilslopes(daily_values, daily_x)
            trend["robust_slope"] = _float(slope.slope)
        else:
            sample_idx = np.linspace(0, len(daily_values) - 1, 5000).astype(int)
            slope = stats.theilslopes(daily_values[sample_idx], daily_x[sample_idx])
            trend["robust_slope"] = _float(slope.slope)

    frequency = GROUP_RULES.get(group_by, "D")
    if n:
        time_frame = measured.set_index("timestamp")
        time_frame = time_frame.copy()
        time_frame["compliance_numeric"] = time_frame["compliant"].map({True: 1.0, False: 0.0})
        grouped = time_frame.resample(frequency).agg(
            mean=("value", "mean"), median=("value", "median"), n=("value", "count"),
            compliant=("compliance_numeric", "mean"),
            within=("compliance_numeric", lambda values: int((values == 1).sum())),
            out=("compliance_numeric", lambda values: int((values == 0).sum())),
            evaluated=("compliance_numeric", "count"),
        ).dropna(subset=["mean"], how="all")
        grouped.index = pd.to_datetime(grouped.index)
        by_group = [{
            "period": timestamp.strftime("%Y-%m-%d"),
            "label": _period_label(timestamp, group_by),
            "mean": _float(row["mean"]),
            "median": _float(row["median"]),
            "n": int(row["n"]),
            "evaluated": int(row["evaluated"]),
            "within": int(row["within"]),
            "out": int(row["out"]),
            "compliance_rate": _float(row["compliant"] * 100),
        } for timestamp, row in grouped.iterrows()]
    else:
        grouped = pd.DataFrame()
        by_group = []

    comparison = []
    previous = pd.DataFrame(previous_rows or [])
    if len(previous):
        previous = previous[previous["parameter"] == focus_parameter]
        previous["timestamp"] = pd.to_datetime(previous["timestamp"], errors="coerce")
        previous["value"] = pd.to_numeric(previous["value"], errors="coerce")
        previous_daily = previous.dropna(subset=["timestamp", "value"]).set_index("timestamp")["value"].resample("D").median().dropna().to_numpy(dtype=float)
        if len(daily_values) >= 2 and len(previous_daily) >= 2:
            welch = stats.ttest_ind(daily_values, previous_daily, equal_var=False, nan_policy="omit")
            mann_whitney = stats.mannwhitneyu(daily_values, previous_daily, alternative="two-sided", method="auto")
            prior_mean = float(np.mean(previous_daily))
            daily_mean = float(np.mean(daily_values))
            daily_std = float(np.std(daily_values, ddof=1))
            previous_std = float(np.std(previous_daily, ddof=1))
            pooled = math.sqrt(((len(daily_values)-1)*daily_std**2 + (len(previous_daily)-1)*previous_std**2)/(len(daily_values)+len(previous_daily)-2)) if len(daily_values)+len(previous_daily)>2 else 0
            effect = (daily_mean-prior_mean)/pooled if pooled else None
            comparison = [{
                "label": "Selected period", "n": int(len(daily_values)), "result_count": n, "mean": daily_mean, "median": float(np.median(daily_values)),
                "compliance_rate": (in_range/evaluated*100) if evaluated else None,
            }, {
                "label": "Previous equivalent period", "n": int(len(previous_daily)), "result_count": int(previous["value"].notna().sum()), "mean": prior_mean,
                "median": float(np.median(previous_daily)),
                "compliance_rate": float(previous["compliant"].dropna().mean()*100) if previous["compliant"].notna().any() else None,
                "difference": daily_mean-prior_mean,
                "change_percent": ((daily_mean-prior_mean)/abs(prior_mean)*100) if prior_mean else None,
                "welch_p_value": _float(welch.pvalue),
                "mann_whitney_p_value": _float(mann_whitney.pvalue),
                "rank_biserial_effect": _float(2*mann_whitney.statistic/(len(daily_values)*len(previous_daily))-1),
                "cohens_d": _float(effect),
            }]

    # When the all-water view combines stages with different configured limits,
    # avoid drawing one stage's specification as though it applied to every row.
    lower_values = frame["minimum"].dropna().unique().tolist() if len(frame) else []
    upper_values = frame["maximum"].dropna().unique().tolist() if len(frame) else []
    lower = lower_values[0] if len(lower_values) == 1 else None
    upper = upper_values[0] if len(upper_values) == 1 else None
    status_counts = frame["status"].value_counts().to_dict() if len(frame) else {}
    distribution = {
        "values": [_float(v) for v in _downsample(measured.reset_index(drop=True), 5000)["value"].tolist()],
        "compliant": int(status_counts.get("Within limits", 0)),
        "out_of_range": int(status_counts.get("Out of range", 0)),
        "missing": int(status_counts.get("Missing", 0)),
        "pending": int(status_counts.get("Pending entry", 0)),
        "legacy_unverified": int(status_counts.get("Verify historical value", 0)),
        "not_evaluated": int(status_counts.get("No limit configured", 0)),
    }

    phase_boxes = []
    group_field = "water_type_label" if frame["water_type"].nunique() > 1 else "phase"
    stage_comparison = []
    independent_groups = []
    for label, group in frame.groupby(group_field, dropna=False, sort=True):
        group_values = pd.to_numeric(group["value"], errors="coerce").dropna()
        if len(group_values):
            phase_boxes.append({"label": str(label), "values": [_float(v) for v in _downsample(group_values.reset_index(drop=True).to_frame(name="value"), 1500)["value"].tolist()]})
            group_in_range = int((group["compliant"] == True).sum())
            group_evaluated = int(group["compliant"].notna().sum())
            group_std = float(group_values.std(ddof=1)) if len(group_values) > 1 else 0.0
            group_sem = group_std / math.sqrt(len(group_values)) if len(group_values) > 1 else 0.0
            group_critical = float(stats.t.ppf(0.975, len(group_values)-1)) if len(group_values) > 1 else 0.0
            stage_comparison.append({
                "label": str(label), "n": int(len(group_values)), "mean": float(group_values.mean()),
                "median": float(group_values.median()), "std": group_std,
                "compliance_rate": (group_in_range/group_evaluated*100) if group_evaluated else None,
                "ci_low": float(group_values.mean() - group_critical*group_sem) if len(group_values) > 1 else None,
                "ci_high": float(group_values.mean() + group_critical*group_sem) if len(group_values) > 1 else None,
            })
            independent_groups.append(group_values.to_numpy(dtype=float))
    stage_test = None
    if len(independent_groups) >= 2:
        try:
            test_result = stats.kruskal(*independent_groups, nan_policy="omit")
            stage_test = {"name": "Kruskal–Wallis stage comparison", "statistic": _float(test_result.statistic), "p_value": _float(test_result.pvalue), "groups": len(independent_groups), "interpretation": "Evidence of a distributional difference between stages" if test_result.pvalue < 0.05 else "No strong evidence of a distributional difference"}
        except Exception:
            stage_test = None

    anomaly_rows = []
    anomaly_count = 0
    if n >= 10:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import RobustScaler
        hours = measured["timestamp"].dt.hour.to_numpy(dtype=float)
        hour_angle = hours * (2 * np.pi / 24)
        features = np.column_stack([values, np.sin(hour_angle), np.cos(hour_angle)])
        if len(features) > 50000:
            sample_positions = np.linspace(0, len(features) - 1, 50000).astype(int)
            anomaly_source = measured.iloc[sample_positions]
            features = features[sample_positions]
        else:
            anomaly_source = measured
        scaled_features = RobustScaler().fit_transform(features)
        model = IsolationForest(contamination="auto", n_estimators=160, random_state=41, n_jobs=1)
        flags = model.fit_predict(scaled_features)
        anomaly_count = int(np.sum(flags == -1))
        anomaly_frame = anomaly_source.iloc[np.flatnonzero(flags == -1)]
        anomaly_rows = [{
            "date": row["date"], "time": row["time"], "parameter": row["parameter"],
            "value": _float(row["value"]), "unit": row["unit"],
            "phase": row["phase"], "reference": row["reference"],
        } for _, row in anomaly_frame.head(100).iterrows()]

    diagnostics = []
    if n >= 8:
        try:
            normality = stats.normaltest(values)
            diagnostics.append({"name": "D’Agostino–Pearson normality", "statistic": _float(normality.statistic), "p_value": _float(normality.pvalue), "interpretation": "Evidence against normality" if normality.pvalue < 0.05 else "No strong evidence against normality"})
        except Exception:
            pass
    # ADF assumes equally spaced observations. Use the configured regular period
    # means, rather than applying it to irregular raw sampling timestamps.
    stationary_values = np.array([])
    if len(grouped) >= 20:
        try:
            stationary_series = grouped["mean"].astype(float).asfreq(frequency).interpolate(limit=1).dropna()
            stationary_values = stationary_series.to_numpy(dtype=float)
        except Exception:
            stationary_values = np.array([])
    if len(stationary_values) >= 20 and np.std(stationary_values) > 0:
        try:
            from statsmodels.tsa.stattools import adfuller
            adf_values = stationary_values if len(stationary_values) <= 10000 else stationary_values[np.linspace(0, len(stationary_values) - 1, 10000).astype(int)]
            adf = adfuller(adf_values, autolag="AIC")
            diagnostics.append({"name": "Augmented Dickey–Fuller stationarity", "statistic": _float(adf[0]), "p_value": _float(adf[1]), "interpretation": "Stationary signal indicated in regular period means" if adf[1] < 0.05 else "Trend / unit-root signal may remain in regular period means"})
        except Exception:
            pass
    if n >= 4:
        try:
            from statsmodels.stats.stattools import durbin_watson
            diagnostics.append({"name": "Durbin–Watson residual independence", "statistic": _float(durbin_watson(trend_residuals)), "p_value": None, "interpretation": "Values near 2 suggest weak first-order autocorrelation"})
        except Exception:
            pass
    if n >= 10:
        iqr_low, iqr_high = q1 - 1.5 * (q3-q1), q3 + 1.5 * (q3-q1)
        mad_z = np.abs(values - median) / (1.4826 * mad) if mad else np.zeros_like(values)
        diagnostics.extend([
            {"name": "IQR screening flags", "statistic": int(np.sum((values < iqr_low) | (values > iqr_high))), "p_value": None, "interpretation": f"Fences {iqr_low:.4g} to {iqr_high:.4g} {unit}"},
            {"name": "Robust MAD screening flags", "statistic": int(np.sum(mad_z > 3.5)), "p_value": None, "interpretation": "Robust modified z-score threshold: 3.5"},
            {"name": "Isolation Forest flags", "statistic": anomaly_count, "p_value": None, "interpretation": "Unsupervised screening on value and sample hour; review source records"},
        ])

    forecast = []
    forecast_validation = {"points": 0, "mae": None, "rmse": None, "interval_method": "Not available"}
    if len(grouped) >= 8:
        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing
            series = grouped["mean"].astype(float).asfreq(frequency)
            series = series.interpolate(limit_direction="both")
            fitted = ExponentialSmoothing(series, trend="add", damped_trend=True, initialization_method="estimated").fit(optimized=True)
            horizon = {"day": 7, "week": 6, "month": 6, "quarter": 4, "half_year": 2, "year": 3}.get(group_by, 6)
            forecast_values = fitted.forecast(horizon)
            validation_errors = []
            first_origin = max(4, len(series) - 40)
            for origin in range(first_origin, len(series)):
                train = series.iloc[:origin]
                try:
                    origin_fit = ExponentialSmoothing(train, trend="add", damped_trend=True, initialization_method="estimated").fit(optimized=True)
                    validation_errors.append(float(series.iloc[origin] - origin_fit.forecast(1).iloc[0]))
                except Exception:
                    continue
            if len(validation_errors) >= 5:
                error_values = np.asarray(validation_errors, dtype=float)
                residual_sigma = float(np.std(error_values, ddof=1))
                forecast_validation = {
                    "points": int(len(error_values)),
                    "mae": _float(np.mean(np.abs(error_values))),
                    "rmse": _float(math.sqrt(np.mean(error_values ** 2))),
                    "interval_method": "Approximate band calibrated from rolling-origin one-step errors; width grows with forecast horizon",
                }
            else:
                residual_sigma = float(np.std(fitted.resid, ddof=1)) if len(fitted.resid) > 1 else 0.0
                forecast_validation = {
                    "points": int(len(validation_errors)),
                    "mae": _float(np.mean(np.abs(validation_errors))) if validation_errors else None,
                    "rmse": _float(math.sqrt(np.mean(np.square(validation_errors)))) if validation_errors else None,
                    "interval_method": "Approximate in-sample residual band; too few rolling-origin errors for calibration",
                }
            for step, (timestamp, value) in enumerate(forecast_values.items(), start=1):
                spread = 1.96 * residual_sigma * math.sqrt(step)
                forecast.append({"period": timestamp.strftime("%Y-%m-%d"), "mean": _float(value), "low": _float(value - spread), "high": _float(value + spread), "step": step})
        except Exception:
            forecast = []

    trend_frame = measured.reset_index(drop=True)
    trend_sample = _downsample(trend_frame, 1800)
    trend_line = predictions if len(predictions) == len(trend_sample) else []
    rolling_all = trend_frame["value"].rolling(window=max(3, min(12, int(math.sqrt(max(n, 1))))), min_periods=1).mean()
    heatmap_group = "water_type_label" if frame["water_type"].nunique() > 1 else "phase"
    heatmap_x = []
    heatmap_y = []
    heatmap_z = []
    heatmap_table = []
    if n and heatmap_group in frame:
        comparable = frame.copy()
        comparable["compliance_numeric"] = comparable["compliant"].map({True: 100.0, False: 0.0})
        heatmap_labels = []
        heatmap_matrix = []
        for label, part in comparable.groupby(heatmap_group, dropna=False, sort=True):
            if str(label) in {"—", "nan", "None", ""} and heatmap_group == "phase":
                label = "Unphased"
            bucketed = part.set_index("timestamp").resample(frequency).agg(
                rate=("compliance_numeric", "mean"),
            )
            if len(grouped):
                bucketed = bucketed.reindex(grouped.index)
            if not bucketed["rate"].notna().any():
                continue
            if not heatmap_x:
                heatmap_x = [stamp.strftime("%Y-%m-%d") for stamp in bucketed.index]
            heatmap_labels.append(str(label))
            heatmap_matrix.append([_float(value) for value in bucketed["rate"].tolist()])
        heatmap_y = heatmap_labels
        heatmap_z = heatmap_matrix
        heatmap_table = [{
            "label": label,
            "values": [{"period": period_label, "compliance": value} for period_label, value in zip(heatmap_x, row)],
        } for label, row in zip(heatmap_y, heatmap_z)]
    series = {
        "x": [pd.Timestamp(value).strftime("%Y-%m-%d %H:%M") for value in trend_sample["timestamp"].tolist()],
        "y": [_float(value) for value in trend_sample["value"].tolist()],
        "status": trend_sample["status"].tolist(),
        "reference": trend_sample["reference"].tolist(),
        "table_rows": [{
            "timestamp": pd.Timestamp(stamp).strftime("%Y-%m-%d %H:%M"),
            "value": _float(value),
            "reference": reference,
            "status": status,
            "rolling": _float(rolling_value),
        } for stamp, value, reference, status, rolling_value in zip(
            trend_sample["timestamp"].tolist(),
            trend_sample["value"].tolist(),
            trend_sample["reference"].tolist(),
            trend_sample["status"].tolist(),
            rolling_all.iloc[trend_sample.index].tolist() if n else [],
        )],
        "trend": trend_line,
        "rolling": [_float(value) for value in rolling_all.iloc[trend_sample.index].tolist()] if n else [],
        "lower_limit": lower,
        "upper_limit": upper,
        "unit": unit,
        "periods": [item["period"] for item in by_group],
        "period_labels": [item["label"] for item in by_group],
        "period_mean": [item["mean"] for item in by_group],
        "period_median": [item["median"] for item in by_group],
        "period_n": [item["n"] for item in by_group],
        "period_compliance": [item["compliance_rate"] for item in by_group],
        "period_within": [item["within"] for item in by_group],
        "period_out": [item["out"] for item in by_group],
        "phase_boxes": phase_boxes,
        "stage_comparison": stage_comparison,
        "heatmap_x": heatmap_x,
        "heatmap_y": heatmap_y,
        "heatmap_z": heatmap_z,
        "heatmap_table": heatmap_table,
        "forecast": forecast,
        "forecast_validation": forecast_validation,
        "trend_stats": trend,
    }

    return {
        "focus_parameter": focus_parameter or "—",
        "unit": unit,
        "metrics": metrics,
        "series": series,
        "comparisons": comparison,
        "stage_comparison": stage_comparison,
        "stage_test": stage_test,
        "distribution": distribution,
        "by_group": by_group,
        "forecast": forecast,
        "forecast_validation": forecast_validation,
        "anomalies": anomaly_rows,
        "anomaly_count": anomaly_count,
        "diagnostics": diagnostics,
        "trend": trend,
        "group_by": group_by,
        "rows_analyzed": int(n),
        "water_type_counts": all_frame["water_type_label"].value_counts().to_dict(),
    }


def json_safe(value):
    """Convert analysis output to strict JSON compatible values."""
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def rows_for_export(rows):
    fields = (
        ("reference", "Sample reference"), ("sample_id", "Sample key"),
        ("plant", "Treatment plant"), ("water_type_label", "Water type"),
        ("date", "Sample date"), ("time", "Sample time"), ("shift", "Shift"),
        ("phase", "Treatment phase"), ("filter_name", "Water filter"),
        ("state", "Analysis state"), ("parameter", "Parameter"),
        ("unit", "Unit"), ("value_text", "Result"),
        ("minimum_text", "Minimum limit"), ("maximum_text", "Maximum limit"),
        ("status", "Compliance status"), ("entry_status_label", "Entry status"), ("remarks", "Remarks"),
    )
    data = [[label for _, label in fields]]
    data.extend([[str(row.get(key, "") or "") for key, _ in fields] for row in rows])
    return fields, data


def image_report(rows, analytics, image_format="png"):
    """Render a publication-style four-panel figure to PNG or SVG."""
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns

    sns.set_theme(style="whitegrid", context="notebook")
    palette = ["#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#ec4899"]
    name = analytics.get("focus_parameter", "Parameter")
    frame = pd.DataFrame([row for row in rows if row.get("parameter") == name and row.get("value") is not None])
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), dpi=180, constrained_layout=True)
    fig.suptitle(f"QCA Advanced Analytics · {name}", fontsize=17, fontweight="bold", color="#10223a")
    if frame.empty:
        for ax in axes.flat:
            ax.text(.5, .5, "No measured results in this selection", ha="center", va="center")
            ax.set_axis_off()
    else:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame.sort_values("timestamp")
        values = frame["value"].astype(float)
        axes[0, 0].plot(frame["timestamp"], values, color=palette[0], alpha=.45, linewidth=.8, label="Measured")
        rolling = values.rolling(max(3, min(12, int(np.sqrt(len(values))))), min_periods=1).mean()
        axes[0, 0].plot(frame["timestamp"], rolling, color=palette[1], linewidth=2.2, label="Rolling mean")
        for key, color, label in (("lower_limit", "#ef4444", "Lower limit"), ("upper_limit", "#ef4444", "Upper limit")):
            limit = analytics.get("series", {}).get(key)
            if limit is not None:
                axes[0, 0].axhline(limit, color=color, linestyle="--", linewidth=1.4, label=label)
        axes[0, 0].set_title("Observed process trend")
        axes[0, 0].set_ylabel(analytics.get("unit", "Result"))
        axes[0, 0].legend(frameon=False, fontsize=8)

        sns.histplot(values, kde=True, ax=axes[0, 1], color=palette[2], bins="auto", stat="density")
        axes[0, 1].set_title("Distribution and density")
        axes[0, 1].set_xlabel(f"Result ({analytics.get('unit','')})")

        labels = ["Within limits", "Out of range", "Missing", "Pending entry", "Historical value to verify", "No limit configured"]
        distribution = analytics.get("distribution", {})
        counts = [distribution.get("compliant", 0), distribution.get("out_of_range", 0), distribution.get("missing", 0), distribution.get("pending", 0), distribution.get("legacy_unverified", 0), distribution.get("not_evaluated", 0)]
        axes[1, 0].pie(counts, labels=labels, colors=["#009e73", "#d55e00", "#64748b", "#cc79a7", "#a85585", "#56b4e9"], startangle=90, counterclock=False, wedgeprops={"width": .38, "edgecolor": "white"}, autopct=lambda p: f"{p:.1f}%" if p >= 3 else "")
        axes[1, 0].set_title("Limit compliance composition")

        comparison_field = "water_type_label" if frame["water_type"].nunique() > 1 else "phase"
        if frame[comparison_field].nunique() > 1:
            sns.boxplot(data=frame, x=comparison_field, y="value", hue=comparison_field, palette=palette, ax=axes[1, 1])
            legend = axes[1, 1].get_legend()
            if legend:
                legend.remove()
            axes[1, 1].tick_params(axis="x", rotation=25)
        else:
            sns.boxplot(y=values, color=palette[4], ax=axes[1, 1], width=.35)
        axes[1, 1].set_title("Robust spread by stage / phase" if frame[comparison_field].nunique() > 1 else "Robust spread · IQR")
        axes[1, 1].set_ylabel(f"Result ({analytics.get('unit','')})")
    fig.text(.01, .005, "Screening and model outputs support review; they do not replace laboratory validation or regulatory interpretation.", fontsize=8, color="#64748b")
    output = __import__("io").BytesIO()
    fig.savefig(output, format=image_format, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    output.seek(0)
    return output

