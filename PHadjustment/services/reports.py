"""Plant-scoped reporting for pH titration tests and their source jar tests."""

from __future__ import annotations

from math import isfinite

import numpy as np


def _stage(test):
    if test.needs_review:
        return "Needs review"
    if test.approved_at:
        return "Approved"
    if test.confirmed_at:
        return "Confirmed"
    if test.verified_at:
        return "Verified"
    return "In progress"


def serialize_ph_test(test):
    jars = list(test.results.all())
    optimal = next((jar for jar in jars if jar.is_optimal), None)
    if optimal is None:
        measured = [jar for jar in jars if jar.resulting_ph is not None]
        optimal = min(measured, key=lambda jar: abs(float(jar.resulting_ph) - 7.0)) if measured else None
    dose = test.established_dosage_ml
    if dose is None and optimal:
        dose = optimal.dosage_ml
    ph = float(optimal.resulting_ph) if optimal and optimal.resulting_ph is not None else None
    source = test.source_jar
    source_test = source.jar_test if source else None
    raw_water = source_test.raw_water if source_test else None
    raw_metrics = {}
    if raw_water:
        for measurement in raw_water.analyses.all():
            parameter = measurement.parameter.parameter
            raw_metrics[str(measurement.parameter_id)] = {"name": parameter.name, "unit": parameter.unit or "", "value": float(measurement.value)}
    dose = float(dose) if dose is not None else None
    if dose is not None and not isfinite(dose):
        dose = None
    raw_summary = "; ".join(
        f"{item['name']}: {item['value']:.3g}{(' ' + item['unit']) if item['unit'] else ''}"
        for item in sorted(raw_metrics.values(), key=lambda value: value["name"].casefold())
    )
    return {
        "id": test.pk, "date": test.test_date.isoformat(), "plant": str(test.treatment_plant),
        "analyst": (getattr(test.analyst, "get_full_name", lambda: "")() or getattr(test.analyst, "username", "—")) if test.analyst else "—",
        "dose": dose, "ph": ph, "deviation": round(ph - 7.0, 3) if ph is not None else None,
        "jar_count": len(jars), "optimal_jar": optimal.jar_number if optimal else None,
        "source_coagulant": str(source_test.coagulant) if source_test and source_test.coagulant_id else "—",
        "source_dose": float(source.dosage_mg_per_l) if source else None,
        "source_jar_number": source.jar_number if source else None,
        "source_date": source_test.test_date.isoformat() if source_test else "—",
        "raw_source": getattr(raw_water, "source_name", "") or "—", "raw_metrics": raw_metrics, "raw_summary": raw_summary,
        "stage": _stage(test), "remarks": test.remarks or "",
    }


def _trend(rows, field):
    ordered = sorted((row for row in rows if row[field] is not None), key=lambda row: (row["date"], row["id"]))
    timeline = [{"date": row["date"], "value": row[field]} for row in ordered]
    fit, slope = [], None
    if len(ordered) >= 3:
        x = np.asarray([np.datetime64(row["date"], "D").astype(int) for row in ordered], dtype=float)
        if np.unique(x).size > 1:
            y = np.asarray([row[field] for row in ordered], dtype=float)
            if len(x) > 500:
                indexes = np.linspace(0, len(x) - 1, 500, dtype=int)
                x, y = x[indexes], y[indexes]
            from scipy.stats import theilslopes

            slope, intercept, _, _ = theilslopes(y, x)
            slope = float(slope)
            fit = [{"date": ordered[0]["date"], "value": float(intercept + slope * x[0])},
                   {"date": ordered[-1]["date"], "value": float(intercept + slope * x[-1])}]
    return timeline, fit, round(slope, 6) if slope is not None and isfinite(slope) else None


def _association(rows, x_field, y_field):
    pairs = [(row[x_field], row[y_field], row) for row in rows if row[x_field] is not None and row[y_field] is not None]
    correlation, fit = None, []
    points = [{"x": x, "y": y, "date": row["date"], "id": row["id"]} for x, y, row in pairs]
    if len(pairs) >= 4 and len({pair[0] for pair in pairs}) > 1 and len({pair[1] for pair in pairs}) > 1:
        from scipy.stats import spearmanr

        rho, p_value = spearmanr([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if isfinite(float(rho)):
            correlation = {"rho": round(float(rho), 3), "p": round(float(p_value), 4) if isfinite(float(p_value)) else None}
    if len(pairs) >= 3 and len({pair[0] for pair in pairs}) >= 3:
        from scipy.stats import theilslopes

        sample = pairs if len(pairs) <= 500 else [pairs[index] for index in np.linspace(0, len(pairs) - 1, 500, dtype=int)]
        xs, ys = np.asarray([pair[0] for pair in sample]), np.asarray([pair[1] for pair in sample])
        slope, intercept, _, _ = theilslopes(ys, xs)
        fit = [{"x": float(xs.min()), "y": float(intercept + slope * xs.min())},
               {"x": float(xs.max()), "y": float(intercept + slope * xs.max())}]
    return {"points": points, "fit": fit, "correlation": correlation}


def build_report_payload(queryset, parameter_id=None):
    rows = [serialize_ph_test(test) for test in queryset]
    doses = np.asarray([row["dose"] for row in rows if row["dose"] is not None], dtype=float)
    ph_values = np.asarray([row["ph"] for row in rows if row["ph"] is not None], dtype=float)
    timeline, fit, trend = _trend(rows, "dose")
    ph_timeline, ph_fit, _ = _trend(rows, "ph")
    summary = {"records": len(rows), "with_dose": int(doses.size), "approved": sum(row["stage"] == "Approved" for row in rows),
               "median": None, "mean": None, "stdev": None, "q1": None, "q3": None, "min": None, "max": None,
               "median_ph": None, "trend_per_day": trend, "rho": None, "p": None}
    if doses.size:
        q1, median, q3 = np.quantile(doses, [0.25, 0.5, 0.75])
        summary.update({"median": round(float(median), 3), "mean": round(float(np.mean(doses)), 3),
                        "stdev": round(float(np.std(doses, ddof=1)), 3) if doses.size > 1 else 0.0,
                        "q1": round(float(q1), 3), "q3": round(float(q3), 3),
                        "min": round(float(doses.min()), 3), "max": round(float(doses.max()), 3)})
    if ph_values.size:
        summary["median_ph"] = round(float(np.median(ph_values)), 3)
    response = _association(rows, "dose", "ph")
    if response["correlation"]:
        summary["rho"], summary["p"] = response["correlation"]["rho"], response["correlation"]["p"]
    raw_catalog = {}
    for row in rows:
        raw_catalog.update(row["raw_metrics"])
    raw_parameters = [{"id": key, **value} for key, value in sorted(raw_catalog.items(), key=lambda item: item[1]["name"].casefold())]
    valid_parameter_ids = {item["id"] for item in raw_parameters}
    selected_parameter = str(parameter_id) if parameter_id and str(parameter_id) in valid_parameter_ids else (raw_parameters[0]["id"] if raw_parameters else "")
    raw_associations = []
    for descriptor in raw_parameters:
        parameter_key = descriptor["id"]
        for row in rows:
            row[f"raw:{parameter_key}"] = row["raw_metrics"].get(parameter_key, {}).get("value")
        raw_associations.append({"id": parameter_key, "name": descriptor["name"], "unit": descriptor["unit"], **_association(rows, f"raw:{parameter_key}", "dose")})
    raw_response = next((item for item in raw_associations if item["id"] == selected_parameter), {"points": [], "fit": [], "correlation": None})
    def histogram(values):
        if not len(values):
            return {"centers": [], "counts": []}
        counts, edges = np.histogram(values, bins=min(12, max(3, int(np.sqrt(len(values))))))
        return {"centers": [round(float((edges[i] + edges[i + 1]) / 2), 3) for i in range(len(counts))], "counts": [int(n) for n in counts]}
    groups = {}
    for row in rows:
        if row["dose"] is not None:
            groups.setdefault(row["source_coagulant"], []).append(row["dose"])
    group_test = None
    eligible = [values for values in groups.values() if len(values) >= 2]
    if len(eligible) >= 2:
        from scipy.stats import kruskal

        try:
            stat, p_value = kruskal(*eligible)
            if isfinite(float(stat)) and isfinite(float(p_value)):
                group_test = {"name": "Kruskal–Wallis", "statistic": round(float(stat), 3), "p": round(float(p_value), 4)}
        except ValueError:
            pass
    return {"rows": rows, "summary": summary, "dose_timeline": timeline, "dose_fit": fit,
            "ph_timeline": ph_timeline, "ph_fit": ph_fit, "dose_histogram": histogram(doses),
            "ph_histogram": histogram(ph_values), "dose_ph": response, "raw_dose": raw_response,
            "raw_parameters": raw_parameters, "raw_associations": raw_associations, "selected_parameter": selected_parameter,
            "groups": [{"name": name, "doses": values} for name, values in sorted(groups.items())], "group_test": group_test}
