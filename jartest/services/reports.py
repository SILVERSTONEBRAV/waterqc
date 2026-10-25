"""Filtered jar-test reports and statistical summaries for the dashboard."""

from __future__ import annotations

from math import isfinite

import numpy as np

THEIL_SEN_MAX_POINTS = 500


def _evenly_sample(items, limit=THEIL_SEN_MAX_POINTS):
    """Keep deterministic coverage while bounding the cost of pairwise robust fits."""
    if len(items) <= limit:
        return items
    indices = np.linspace(0, len(items) - 1, limit, dtype=int)
    return [items[index] for index in indices]


def _raw_water_metrics(raw_water):
    metrics = {"turbidity": None, "color": None, "ph": None}
    if not raw_water:
        return metrics

    for analysis in raw_water.analyses.all():
        parameter = getattr(analysis, "parameter", None)
        parameter = getattr(parameter, "parameter", None)
        name = str(getattr(parameter, "name", "")).casefold()
        value = float(analysis.value)
        if not isfinite(value):
            continue
        if "turb" in name:
            metrics["turbidity"] = value
        elif "color" in name or "colour" in name:
            metrics["color"] = value
        elif "ph" in name and "alpha" not in name:
            metrics["ph"] = value
    return metrics


def _review_stage(test):
    if test.needs_review:
        return "Needs review"
    if test.approved_at:
        return "Approved"
    if test.confirmed_at:
        return "Confirmed"
    if test.verified_at:
        return "Verified"
    return "In progress"


def serialize_report_test(test, parameter_id=None):
    """Return the report-table fields for a single test, including linked water data."""
    raw = _raw_water_metrics(test.raw_water)
    dose = float(test.established_dosage_mg_per_l) if test.established_dosage_mg_per_l is not None else None
    if dose is not None and not isfinite(dose):
        dose = None
    raw_parameters = {}
    if test.raw_water_id:
        for analysis in test.raw_water.analyses.all():
            value = float(analysis.value)
            if not isfinite(value):
                continue
            parameter = getattr(analysis.parameter, "parameter", None)
            key = str(analysis.parameter_id)
            raw_parameters[key] = {
                "name": str(getattr(parameter, "name", "Raw-water parameter")),
                "unit": str(getattr(parameter, "unit", "") or ""),
                "value": value,
            }
    selected = raw_parameters.get(str(parameter_id)) if parameter_id else None
    return {
        "id": test.pk,
        "date": test.test_date.isoformat(),
        "plant": str(test.treatment_plant),
        "coagulant": str(test.coagulant),
        "coagulant_id": test.coagulant_id,
        "analyst": getattr(test.analyst, "username", "—") or "—",
        "dose": dose,
        "stage": _review_stage(test),
        "jar_count": len(test.jar_results.all()),
        "raw_source": getattr(test.raw_water, "source_name", "") or "—",
        "turbidity": raw["turbidity"],
        "color": raw["color"],
        "ph": raw["ph"],
        "selected_parameter_value": selected["value"] if selected else None,
        "raw_parameters": raw_parameters,
        "remarks": test.remarks or "",
    }


def build_report_payload(queryset, selected_parameter_id=None):
    """Serialize a filtered report set and its descriptive/statistical graphics."""
    rows = [serialize_report_test(test, selected_parameter_id) for test in queryset]

    dose_rows = [row for row in rows if row["dose"] is not None and isfinite(row["dose"])]
    doses = np.asarray([row["dose"] for row in dose_rows], dtype=float)
    summary = {
        "records": len(rows),
        "with_dose": len(dose_rows),
        "approved": sum(row["stage"] == "Approved" for row in rows),
        "median": None,
        "mean": None,
        "stdev": None,
        "q1": None,
        "q3": None,
        "min": None,
        "max": None,
        "trend_per_day": None,
        "turbidity_rho": None,
        "turbidity_p": None,
    }
    timeline = []
    histogram = {"centers": [], "counts": []}
    control = {"center": None, "lower": None, "upper": None}
    associations = []
    grouped_doses = []

    if doses.size:
        q1, median, q3 = np.quantile(doses, [0.25, 0.5, 0.75])
        summary.update({
            "median": round(float(median), 3),
            "mean": round(float(np.mean(doses)), 3),
            "stdev": round(float(np.std(doses, ddof=1)), 3) if doses.size > 1 else 0.0,
            "q1": round(float(q1), 3),
            "q3": round(float(q3), 3),
            "min": round(float(np.min(doses)), 3),
            "max": round(float(np.max(doses)), 3),
        })
        mad = float(np.median(np.abs(doses - median)))
        robust_sigma = 1.4826 * mad
        control = {
            "center": float(median),
            "lower": max(0.0, float(median - 3 * robust_sigma)),
            "upper": float(median + 3 * robust_sigma),
        }

        ordered = sorted(dose_rows, key=lambda row: (row["date"], row["id"]))
        dates = np.asarray([np.datetime64(row["date"], "D").astype(int) for row in ordered], dtype=float)
        values = np.asarray([row["dose"] for row in ordered], dtype=float)
        timeline = [{"date": row["date"], "dose": row["dose"]} for row in ordered]
        if len(ordered) >= 3 and np.unique(dates).size >= 2:
            from scipy.stats import theilslopes

            trend_indices = np.linspace(0, len(ordered) - 1, min(len(ordered), THEIL_SEN_MAX_POINTS), dtype=int)
            slope, intercept, _, _ = theilslopes(values[trend_indices], dates[trend_indices])
            summary["trend_per_day"] = round(float(slope), 5)
            timeline_fit = [
                {"date": ordered[index]["date"], "dose": float(intercept + slope * dates[index])}
                for index in (0, len(ordered) - 1)
            ]
        else:
            timeline_fit = []

        bin_count = min(12, max(3, int(np.sqrt(doses.size))))
        counts, edges = np.histogram(doses, bins=bin_count)
        histogram = {
            "centers": [round(float((edges[i] + edges[i + 1]) / 2), 3) for i in range(len(counts))],
            "counts": [int(value) for value in counts],
        }
        control["fit"] = timeline_fit

        from scipy.stats import spearmanr

        parameter_catalog = {}
        for row in dose_rows:
            for parameter_id, measurement in row["raw_parameters"].items():
                parameter_catalog[parameter_id] = {
                    "label": measurement["name"],
                    "unit": measurement["unit"],
                }
        for parameter_id, descriptor in sorted(parameter_catalog.items(), key=lambda item: item[1]["label"].casefold()):
            pairs = [
                (row["raw_parameters"][parameter_id]["value"], row["dose"], row)
                for row in dose_rows if parameter_id in row["raw_parameters"]
            ]
            correlation = None
            trend = []
            if len(pairs) >= 4 and len({pair[0] for pair in pairs}) > 1:
                rho, p_value = spearmanr([pair[0] for pair in pairs], [pair[1] for pair in pairs])
                if isfinite(float(rho)):
                    correlation = {"rho": round(float(rho), 3), "p": round(float(p_value), 4) if isfinite(float(p_value)) else None}
                    if "turb" in descriptor["label"].casefold():
                        summary["turbidity_rho"] = correlation["rho"]
                        summary["turbidity_p"] = correlation["p"]
            if len(pairs) >= 3 and len({pair[0] for pair in pairs}) >= 3:
                from scipy.stats import theilslopes

                trend_pairs = _evenly_sample(sorted(pairs, key=lambda pair: pair[0]))
                x_values = np.asarray([pair[0] for pair in trend_pairs], dtype=float)
                y_values = np.asarray([pair[1] for pair in trend_pairs], dtype=float)
                slope, intercept, _, _ = theilslopes(y_values, x_values)
                trend = [
                    {"x": float(x_values.min()), "y": float(intercept + slope * x_values.min())},
                    {"x": float(x_values.max()), "y": float(intercept + slope * x_values.max())},
                ]
            associations.append({
                "parameter": f"raw:{parameter_id}",
                "label": descriptor["label"],
                "unit": descriptor["unit"],
                "points": [{"x": float(value), "y": dose, "date": row["date"]} for value, dose, row in pairs],
                "correlation": correlation,
                "trend": trend,
            })

    groups = {}
    for row in dose_rows:
        groups.setdefault(row["coagulant"], []).append(row["dose"])
    for name, values in sorted(groups.items()):
        grouped_doses.append({"name": name, "doses": values})

    group_test = None
    valid_groups = [values for values in groups.values() if len(values) >= 2]
    if len(valid_groups) >= 2:
        from scipy.stats import kruskal

        try:
            statistic, p_value = kruskal(*valid_groups)
            if isfinite(float(statistic)) and isfinite(float(p_value)):
                group_test = {"name": "Kruskal–Wallis", "statistic": round(float(statistic), 3), "p": round(float(p_value), 4)}
        except ValueError:
            # SciPy cannot compare groups when every observed dose is identical.
            group_test = None

    return {
        "rows": rows,
        "summary": summary,
        "timeline": timeline,
        "histogram": histogram,
        "control": control,
        "associations": associations,
        "groups": grouped_doses,
        "group_test": group_test,
    }
