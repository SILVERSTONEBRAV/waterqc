"""Plant-scoped statistical reporting for breakpoint chlorine demand tests."""

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


def serialize_chlorine_test(test):
    jars = list(test.jar_results.all())
    optimal = next((jar for jar in jars if jar.is_optimal), None)
    if optimal is None:
        measured = [jar for jar in jars if jar.residual_chlorine is not None]
        optimal = min(measured, key=lambda jar: abs(float(jar.residual_chlorine) - 0.2)) if measured else None
    dose = test.established_dosage_mg_per_l
    if dose is None and optimal:
        dose = optimal.dosage_mg_per_l
    dose = float(dose) if dose is not None else None
    residual = float(optimal.residual_chlorine) if optimal and optimal.residual_chlorine is not None else None
    if dose is not None and not isfinite(dose):
        dose = None
    if residual is not None and not isfinite(residual):
        residual = None
    return {
        "id": test.pk,
        "date": test.test_date.isoformat(),
        "plant": str(test.treatment_plant),
        "analyst": (getattr(test.analyst, "get_full_name", lambda: "")() or getattr(test.analyst, "username", "—")) if test.analyst else "—",
        "dose": dose,
        "residual": residual,
        "consumed": max(0.0, dose - residual) if dose is not None and residual is not None else None,
        "jar_count": len(jars),
        "optimal_jar": optimal.jar_number if optimal else None,
        "stage": _stage(test),
        "remarks": test.remarks or "",
    }


def _trend(rows, field):
    values = [row for row in rows if row[field] is not None]
    ordered = sorted(values, key=lambda row: (row["date"], row["id"]))
    timeline = [{"date": row["date"], "value": row[field]} for row in ordered]
    fit = []
    slope = None
    if len(ordered) >= 3:
        x = np.asarray([np.datetime64(row["date"], "D").astype(int) for row in ordered], dtype=float)
        if np.unique(x).size > 1:
            if len(x) > 500:
                indexes = np.linspace(0, len(x) - 1, 500, dtype=int)
                x, y = x[indexes], np.asarray([row[field] for row in ordered], dtype=float)[indexes]
            else:
                y = np.asarray([row[field] for row in ordered], dtype=float)
            from scipy.stats import theilslopes

            slope, intercept, _, _ = theilslopes(y, x)
            slope = float(slope)
            fit = [{"date": ordered[index]["date"], "value": float(intercept + slope * x_value)}
                   for index, x_value in ((0, x[0]), (-1, x[-1]))]
    return timeline, fit, round(slope, 6) if slope is not None and isfinite(slope) else None


def _correlation(rows, x_field, y_field):
    pairs = [(row[x_field], row[y_field], row) for row in rows if row[x_field] is not None and row[y_field] is not None]
    points = [{"x": x, "y": y, "date": row["date"], "id": row["id"]} for x, y, row in pairs]
    correlation, fit = None, []
    if len(pairs) >= 4 and len({pair[0] for pair in pairs}) > 1 and len({pair[1] for pair in pairs}) > 1:
        from scipy.stats import spearmanr

        rho, p_value = spearmanr([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if isfinite(float(rho)):
            correlation = {"rho": round(float(rho), 3), "p": round(float(p_value), 4) if isfinite(float(p_value)) else None}
    if len(pairs) >= 3 and len({pair[0] for pair in pairs}) >= 3:
        from scipy.stats import theilslopes

        sample = pairs if len(pairs) <= 500 else [pairs[index] for index in np.linspace(0, len(pairs) - 1, 500, dtype=int)]
        xs = np.asarray([pair[0] for pair in sample], dtype=float)
        ys = np.asarray([pair[1] for pair in sample], dtype=float)
        slope, intercept, _, _ = theilslopes(ys, xs)
        fit = [{"x": float(xs.min()), "y": float(intercept + slope * xs.min())},
               {"x": float(xs.max()), "y": float(intercept + slope * xs.max())}]
    return {"points": points, "fit": fit, "correlation": correlation}


def build_report_payload(queryset):
    rows = [serialize_chlorine_test(test) for test in queryset]
    doses = np.asarray([row["dose"] for row in rows if row["dose"] is not None], dtype=float)
    residuals = np.asarray([row["residual"] for row in rows if row["residual"] is not None], dtype=float)
    summary = {"records": len(rows), "with_dose": int(doses.size), "approved": sum(row["stage"] == "Approved" for row in rows),
               "median": None, "mean": None, "stdev": None, "q1": None, "q3": None, "min": None, "max": None,
               "median_residual": None, "trend_per_day": None, "residual_rho": None, "residual_p": None}
    timeline, fit, trend = _trend(rows, "dose")
    residual_timeline, residual_fit, _ = _trend(rows, "residual")
    if doses.size:
        q1, median, q3 = np.quantile(doses, [0.25, 0.5, 0.75])
        summary.update({"median": round(float(median), 3), "mean": round(float(np.mean(doses)), 3),
                        "stdev": round(float(np.std(doses, ddof=1)), 3) if doses.size > 1 else 0.0,
                        "q1": round(float(q1), 3), "q3": round(float(q3), 3),
                        "min": round(float(np.min(doses)), 3), "max": round(float(np.max(doses)), 3), "trend_per_day": trend})
    if residuals.size:
        summary["median_residual"] = round(float(np.median(residuals)), 3)
    response = _correlation(rows, "dose", "residual")
    if response["correlation"]:
        summary["residual_rho"] = response["correlation"]["rho"]
        summary["residual_p"] = response["correlation"]["p"]
    def histogram(values):
        if not len(values):
            return {"centers": [], "counts": []}
        counts, edges = np.histogram(values, bins=min(12, max(3, int(np.sqrt(len(values))))))
        return {"centers": [round(float((edges[i] + edges[i + 1]) / 2), 3) for i in range(len(counts))], "counts": [int(n) for n in counts]}
    return {"rows": rows, "summary": summary,
            "dose_timeline": timeline, "dose_fit": fit, "residual_timeline": residual_timeline, "residual_fit": residual_fit,
            "dose_histogram": histogram(doses), "residual_histogram": histogram(residuals), "dose_residual": response}
