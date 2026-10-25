from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, time
from math import ceil, isfinite

import numpy as np
from django.db.models import Count, Prefetch
from django.utils import timezone

from jartest.models import JarTest, RawWater, RawWaterAnalysis
from qc.models import RawWaterResult, SamplingSchedule, WaterAnalysis
from t.models import CoagulatedWaterLimit, RawWaterLimit


MIN_TRAINING_TESTS = 5


class ScipyHuberRidge:
    """L2-regularized Huber regression fitted with SciPy's L-BFGS optimizer."""

    def __init__(self, alpha=1.5):
        self.alpha = alpha

    def fit(self, features, outcomes):
        from scipy.optimize import minimize

        features = np.asarray(features, dtype=float)
        outcomes = np.asarray(outcomes, dtype=float).reshape(-1)
        if features.ndim != 2 or features.shape[0] != outcomes.size:
            raise ValueError("Features and dosage outcomes are not aligned.")

        feature_count = features.shape[1]
        center = float(np.median(outcomes))
        mad = float(np.median(np.abs(outcomes - center)))
        huber_delta = max(1.345 * 1.4826 * mad, 0.25)
        initial = np.zeros(feature_count + 1, dtype=float)
        initial[-1] = center

        def objective(parameters):
            coefficients = parameters[:-1]
            residuals = features @ coefficients + parameters[-1] - outcomes
            absolute = np.abs(residuals)
            losses = np.where(
                absolute <= huber_delta,
                0.5 * np.square(residuals),
                huber_delta * (absolute - 0.5 * huber_delta),
            )
            value = float(losses.sum() + 0.5 * self.alpha * np.dot(coefficients, coefficients))
            influence = np.clip(residuals, -huber_delta, huber_delta)
            gradient = np.concatenate((
                features.T @ influence + self.alpha * coefficients,
                np.asarray([influence.sum()]),
            ))
            return value, gradient

        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            jac=True,
            options={"maxiter": 500, "ftol": 1e-10},
        )
        if not np.isfinite(result.x).all():
            raise ValueError("SciPy robust regression did not produce a finite fit.")
        self.coef_ = result.x[:-1]
        self.intercept_ = float(result.x[-1])
        return self

    def predict(self, features):
        features = np.asarray(features, dtype=float)
        return features @ self.coef_ + self.intercept_


def _float(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def parameter_catalog(plant):
    """Return the plant's physical/chemical raw-water fields by parameter id."""
    catalog = {}
    sources = (
        (RawWaterLimit, "QC raw water"),
        (CoagulatedWaterLimit, "Jar-test raw water"),
    )
    for limit_model, source in sources:
        limits = limit_model.objects.filter(treatment_plant=plant).select_related("parameter")
        for limit in limits:
            parameter = limit.parameter
            if not parameter or parameter.pk is None:
                continue
            row = catalog.setdefault(parameter.pk, {
                "id": parameter.pk,
                "name": parameter.name,
                "unit": parameter.unit or "",
                "sources": set(),
                "priority": _parameter_priority(parameter.name),
            })
            row["sources"].add(source)
            if not row["unit"]:
                row["unit"] = parameter.unit or ""
    return sorted(
        ({**row, "sources": sorted(row["sources"])} for row in catalog.values()),
        key=lambda row: (row["priority"], row["name"].casefold()),
    )


def _parameter_priority(name):
    label = str(name or "").casefold()
    ordered = ("turb", "ph", "alkal", "color", "colour", "temp", "conduct", "toc", "organic")
    for index, token in enumerate(ordered):
        if token in label:
            return index
    return len(ordered)


def _parameter_id_from_limit(limit):
    return getattr(limit, "parameter_id", None)


def _analysis_timestamp(analysis):
    sampled_time = getattr(getattr(analysis, "analysis_time", None), "time", None)
    if not sampled_time:
        sampled_time = time.min
    local_dt = datetime.combine(analysis.analysis_date, sampled_time)
    if timezone.is_naive(local_dt):
        return timezone.make_aware(local_dt, timezone.get_current_timezone())
    return local_dt


def _analysis_value_map(results):
    values = {}
    for result in results:
        key = _parameter_id_from_limit(result.parameter)
        value = _float(result.value)
        if key is not None and value is not None:
            values[key] = value
    return values


def _raw_water_value_map(raw_water):
    values = {}
    if not raw_water:
        return values
    for result in raw_water.analyses.all():
        key = _parameter_id_from_limit(result.parameter)
        value = _float(result.value)
        if key is not None and value is not None:
            values[key] = value
    return values


def _collect_qc_samples(plant, through_date):
    results = list(
        RawWaterResult.objects.filter(
            analysis__treatment_plant=plant,
            analysis__analysis_time__schedule__water_type=SamplingSchedule.RAW,
            analysis__analysis_date__lte=through_date,
        ).select_related(
            "analysis__analysis_time__schedule",
            "parameter__parameter",
        ).order_by(
            "analysis__analysis_date",
            "analysis__analysis_time__time",
            "analysis_id",
            "id",
        )
    )
    grouped = {}
    for result in results:
        analysis = result.analysis
        sample = grouped.setdefault(analysis.pk, {
            "analysis": analysis,
            "at": _analysis_timestamp(analysis),
            "values": {},
        })
        key = _parameter_id_from_limit(result.parameter)
        value = _float(result.value)
        if key is not None and value is not None:
            sample["values"][key] = value
    return sorted(grouped.values(), key=lambda sample: (sample["at"], sample["analysis"].pk))


def _collect_jar_raw_samples(plant, through_time):
    rows = list(
        RawWater.objects.filter(
            treatment_plant=plant,
            sampled_at__lte=through_time,
            analyses__isnull=False,
        ).distinct().prefetch_related(
            Prefetch(
                "analyses",
                queryset=RawWaterAnalysis.objects.select_related("parameter__parameter"),
            )
        ).order_by("sampled_at", "id")
    )
    samples = []
    for raw_water in rows:
        values = _raw_water_value_map(raw_water)
        if values:
            samples.append({"at": raw_water.sampled_at, "id": raw_water.pk, "values": values})
    return samples


def latest_prior_sample(plant, before=None):
    """Newest measured raw-water record from the jar-test or QC models."""
    if not plant:
        return None
    cutoff = before or timezone.now()
    if timezone.is_naive(cutoff):
        cutoff = timezone.make_aware(cutoff, timezone.get_current_timezone())
    latest_raw = RawWater.objects.filter(
        treatment_plant=plant,
        sampled_at__lt=cutoff,
        analyses__isnull=False,
    ).distinct().prefetch_related(
        Prefetch("analyses", queryset=RawWaterAnalysis.objects.select_related("parameter__parameter"))
    ).order_by("-sampled_at", "-id").first()
    raw_sample = None
    if latest_raw:
        raw_sample = {
            "at": latest_raw.sampled_at,
            "values": _raw_water_value_map(latest_raw),
            "source": "Jar-test raw-water record",
        }

    latest_result = RawWaterResult.objects.filter(
        analysis__treatment_plant=plant,
        analysis__analysis_time__schedule__water_type=SamplingSchedule.RAW,
        analysis__analysis_date__lte=timezone.localtime(cutoff).date(),
    ).select_related(
        "analysis__analysis_time__schedule",
        "parameter__parameter",
    ).order_by(
        "-analysis__analysis_date", "-analysis__analysis_time__time", "-id",
    ).first()
    qc_sample = None
    if latest_result:
        analysis = latest_result.analysis
        related = RawWaterResult.objects.filter(analysis=analysis).select_related("parameter__parameter")
        qc_sample = {
            "at": _analysis_timestamp(analysis),
            "analysis": analysis,
            "values": _analysis_value_map(related),
        }
        if qc_sample["at"] >= cutoff:
            qc_sample = None
    if qc_sample and (raw_sample is None or qc_sample["at"] > raw_sample["at"]):
        return {
            "date": timezone.localtime(qc_sample["at"]).strftime("%Y-%m-%d %H:%M"),
            "values": {str(key): value for key, value in qc_sample["values"].items()},
            "source": f"QC analysis {getattr(qc_sample['analysis'], 'reference_id', '')}".strip(),
        }
    if raw_sample:
        return {
            "date": timezone.localtime(raw_sample["at"]).strftime("%Y-%m-%d %H:%M"),
            "values": {str(key): value for key, value in raw_sample["values"].items()},
            "source": raw_sample["source"],
        }
    return None


def _history_tests(plant, coagulant, through_date=None):
    through_date = through_date or timezone.localdate()
    return list(
        JarTest.objects.annotate(_jar_count=Count("jar_results", distinct=True)).filter(
            treatment_plant=plant,
            coagulant=coagulant,
            test_date__lte=through_date,
            _jar_count=6,
            established_dosage_mg_per_l__isnull=False,
            verified_at__isnull=False,
            confirmed_at__isnull=False,
            approved_at__isnull=False,
            needs_review=False,
        ).select_related(
            "raw_water", "coagulant", "treatment_plant",
        ).prefetch_related(
            Prefetch(
                "raw_water__analyses",
                queryset=RawWaterAnalysis.objects.select_related("parameter__parameter"),
            )
        ).order_by("test_date", "id")
    )


def _record_feature_rows(plant, coagulant, through_date=None):
    tests = _history_tests(plant, coagulant, through_date=through_date)
    if not tests:
        return tests, []
    through_date = max(timezone.localtime(test.raw_water.sampled_at).date() for test in tests if test.raw_water_id)
    through_time = max(test.raw_water.sampled_at for test in tests if test.raw_water_id)
    qc_samples = _collect_qc_samples(plant, through_date)
    jar_samples = _collect_jar_raw_samples(plant, through_time)
    qc_times = [row["at"] for row in qc_samples]
    jar_times = [row["at"] for row in jar_samples]

    rows = []
    for test in tests:
        raw_water = test.raw_water
        raw_water_id = test.raw_water_id
        sampled_at = raw_water.sampled_at if raw_water_id else timezone.make_aware(
            datetime.combine(test.test_date, time.min), timezone.get_current_timezone()
        )
        if timezone.is_naive(sampled_at):
            sampled_at = timezone.make_aware(sampled_at, timezone.get_current_timezone())
        observed_before = sampled_at
        created_at = getattr(test, "created_at", None)
        if created_at:
            if timezone.is_naive(created_at):
                created_at = timezone.make_aware(created_at, timezone.get_current_timezone())
            if timezone.localtime(created_at).date() == timezone.localtime(sampled_at).date() and created_at > sampled_at:
                # JarTest stores a date, while its linked raw-water record often
                # carries midnight. On that same calendar day, use the record's
                # creation time as the latest defensible QC cutoff.
                observed_before = created_at
        current = _raw_water_value_map(raw_water)

        # Use QC only where this exact JarTest raw-water sample has no value.
        qc_index = bisect_right(qc_times, observed_before) - 1
        matched_qc = qc_samples[qc_index] if qc_index >= 0 else None
        if matched_qc:
            for key, value in matched_qc["values"].items():
                current.setdefault(key, value)

        jar_index = bisect_left(jar_times, sampled_at) - 1
        prior_jar = None
        while jar_index >= 0:
            prior = jar_samples[jar_index]
            if prior["id"] != raw_water_id:
                prior_jar = prior
                break
            jar_index -= 1
        previous = dict(prior_jar["values"]) if prior_jar else {}

        if matched_qc:
            prior_qc_index = qc_index - 1
        else:
            prior_qc_index = bisect_left(qc_times, observed_before) - 1
        prior_qc = qc_samples[prior_qc_index] if prior_qc_index >= 0 else None
        if prior_qc:
            for key, value in prior_qc["values"].items():
                previous.setdefault(key, value)

        features = {}
        for key in set(current) | set(previous):
            current_value = current.get(key)
            previous_value = previous.get(key)
            if current_value is not None:
                features[f"current_{key}"] = current_value
            if previous_value is not None:
                features[f"previous_{key}"] = previous_value
            if current_value is not None and previous_value is not None:
                features[f"change_{key}"] = current_value - previous_value

        rows.append({
            "test": test,
            "date": test.test_date,
            "dose": float(test.established_dosage_mg_per_l),
            "current": current,
            "previous": previous,
            "features": features,
            "qc_reference": getattr(matched_qc["analysis"], "reference_id", None) if matched_qc else None,
            "previous_reference": getattr(prior_qc["analysis"], "reference_id", None) if prior_qc else None,
        })
    return tests, rows


def _feature_schema(rows, catalog):
    if not rows:
        return []
    n = len(rows)
    min_coverage = max(3, ceil(n * 0.45))
    catalog_by_id = {item["id"]: item for item in catalog}
    features = []
    for parameter_id, parameter in catalog_by_id.items():
        current_values = [row["current"].get(parameter_id) for row in rows]
        present = [value for value in current_values if value is not None]
        if len(present) < min_coverage or len(set(round(value, 6) for value in present)) < 2:
            continue
        features.append({
            "key": f"current_{parameter_id}",
            "parameter_id": parameter_id,
            "name": parameter["name"],
            "unit": parameter["unit"],
            "kind": "current",
            "label": f"Current {parameter['name']}",
            "coverage": len(present),
        })
        previous_values = [row["previous"].get(parameter_id) for row in rows]
        valid_previous = [value for value in previous_values if value is not None]
        if len(valid_previous) >= min_coverage and len(set(round(value, 6) for value in valid_previous)) > 1:
            features.append({
                "key": f"previous_{parameter_id}",
                "parameter_id": parameter_id,
                "name": parameter["name"],
                "unit": parameter["unit"],
                "kind": "previous",
                "label": f"Previous {parameter['name']}",
                "coverage": len(valid_previous),
            })
            change_values = [
                row["current"].get(parameter_id) - row["previous"].get(parameter_id)
                for row in rows
                if row["current"].get(parameter_id) is not None and row["previous"].get(parameter_id) is not None
            ]
            if len(set(round(value, 6) for value in change_values)) > 1:
                features.append({
                    "key": f"change_{parameter_id}",
                    "parameter_id": parameter_id,
                    "name": parameter["name"],
                    "unit": parameter["unit"],
                    "kind": "change",
                    "label": f"Change in {parameter['name']}",
                    "coverage": len(change_values),
                })
    return features


def _matrix(rows, schema, current_inputs=None, previous_inputs=None):
    matrix = []
    for row in rows:
        matrix.append([row["features"].get(feature["key"]) for feature in schema])
    if current_inputs is not None:
        values = []
        for feature in schema:
            parameter_id = feature["parameter_id"]
            current = current_inputs.get(parameter_id)
            previous = previous_inputs.get(parameter_id)
            if feature["kind"] == "current":
                values.append(current)
            elif feature["kind"] == "previous":
                values.append(previous)
            else:
                values.append(current - previous if current is not None and previous is not None else None)
        matrix.append(values)
    return matrix


def _numeric_matrix(matrix):
    return np.asarray([
        [np.nan if value is None else float(value) for value in row]
        for row in matrix
    ], dtype=float)


def _correlations(rows, schema):
    from scipy.stats import spearmanr

    results = []
    for feature in schema:
        pairs = [
            (row["features"].get(feature["key"]), row["dose"])
            for row in rows
            if row["features"].get(feature["key"]) is not None
        ]
        if len(pairs) < 4 or len({x for x, _ in pairs}) < 2:
            continue
        rho, p_value = spearmanr([pair[0] for pair in pairs], [pair[1] for pair in pairs])
        if isfinite(float(rho)):
            results.append({
                "label": feature["label"],
                "name": feature["name"],
                "kind": feature["kind"],
                "rho": round(float(rho), 3),
                "p_value": round(float(p_value), 4) if isfinite(float(p_value)) else None,
                "n": len(pairs),
            })
    return sorted(results, key=lambda row: abs(row["rho"]), reverse=True)


def build_dashboard_analytics(plant, coagulant, sample_at=None):
    catalog = parameter_catalog(plant) if plant else []
    if not plant or not coagulant:
        return {
            "catalog": catalog,
            "history": [],
            "correlations": [],
            "features": [],
            "summary": {"count": 0, "median": None, "mean": None, "stdev": None, "q1": None, "q3": None, "min": None, "max": None},
            "prior_sample": None,
            "has_model": False,
        }
    requested_date = timezone.localtime(sample_at).date() if sample_at else timezone.localdate()
    through_date = min(requested_date, timezone.localdate())
    _, rows = _record_feature_rows(plant, coagulant, through_date=through_date)
    doses = [row["dose"] for row in rows]
    summary = {"count": len(doses), "median": None, "mean": None, "stdev": None, "q1": None, "q3": None, "min": None, "max": None}
    if doses:
        summary.update({
            "median": round(float(np.median(doses)), 2),
            "mean": round(float(np.mean(doses)), 2),
            "stdev": round(float(np.std(doses, ddof=1)), 2) if len(doses) > 1 else 0,
            "q1": round(float(np.quantile(doses, 0.25)), 2),
            "q3": round(float(np.quantile(doses, 0.75)), 2),
            "min": round(min(doses), 2),
            "max": round(max(doses), 2),
        })
    schema = _feature_schema(rows, catalog)
    history = []
    for row in rows:
        current = row["current"]
        raw = {str(key): value for key, value in current.items()}
        history.append({
            "date": row["date"].isoformat(),
            "dose": row["dose"],
            "raw": raw,
            "qc_reference": row["qc_reference"],
        })

    previous_raw = latest_prior_sample(plant, before=sample_at)

    return {
        "catalog": catalog,
        "history": history,
        "correlations": _correlations(rows, schema),
        "features": schema,
        "summary": summary,
        "prior_sample": previous_raw,
        "has_model": len(rows) >= MIN_TRAINING_TESTS and len(schema) >= 1,
    }


def predict_dosage(plant, coagulant, current_inputs, sample_at=None):
    """Fit and calibrate a small-data regression against approved outcomes."""
    catalog = parameter_catalog(plant)
    requested_date = timezone.localtime(sample_at).date() if sample_at else timezone.localdate()
    through_date = min(requested_date, timezone.localdate())
    _, rows = _record_feature_rows(plant, coagulant, through_date=through_date)
    schema = _feature_schema(rows, catalog)
    clean_inputs = {int(key): _float(value) for key, value in current_inputs.items()}
    clean_inputs = {key: value for key, value in clean_inputs.items() if key in {row["id"] for row in catalog} and value is not None}

    if len(rows) < MIN_TRAINING_TESTS:
        return {
            "ok": False,
            "status": "insufficient_history",
            "message": f"Only {len(rows)} complete, approved jar test(s) match this plant and coagulant. At least {MIN_TRAINING_TESTS} are required before a dosage estimate is shown.",
            "sample_count": len(rows),
            "features": schema,
            "history": _serializable_history(rows),
            "summary": _dose_summary([row["dose"] for row in rows]),
            "correlations": _correlations(rows, schema),
        }
    if not schema:
        return {
            "ok": False,
            "status": "insufficient_raw_water",
            "message": "The completed tests do not contain enough varying, comparable raw-water measurements to fit a defensible predictor.",
            "sample_count": len(rows),
            "features": [],
            "history": _serializable_history(rows),
            "summary": _dose_summary([row["dose"] for row in rows]),
            "correlations": [],
        }

    used_parameter_ids = {feature["parameter_id"] for feature in schema if feature["kind"] == "current"}
    missing_ids = [parameter_id for parameter_id in used_parameter_ids if parameter_id not in clean_inputs]
    required_count = min(len(used_parameter_ids), max(3, ceil(len(used_parameter_ids) * 0.6)))
    if len(used_parameter_ids) - len(missing_ids) < required_count:
        labels = [item["name"] for item in catalog if item["id"] in missing_ids]
        return {
            "ok": False,
            "status": "missing_inputs",
            "message": f"Enter at least {required_count} of the {len(used_parameter_ids)} historically informative raw-water parameters to estimate dosage.",
            "required_parameters": labels,
            "sample_count": len(rows),
            "features": schema,
            "history": _serializable_history(rows),
            "summary": _dose_summary([row["dose"] for row in rows]),
            "correlations": _correlations(rows, schema),
        }

    previous_inputs = {}
    prior_sample = latest_prior_sample(plant, before=sample_at)
    if prior_sample:
        previous_inputs = {
            int(key): _float(value)
            for key, value in prior_sample.get("values", {}).items()
        }
    x = _numeric_matrix(_matrix(rows, schema))
    y = np.asarray([row["dose"] for row in rows], dtype=float)
    input_x = _numeric_matrix(_matrix([], schema, clean_inputs, previous_inputs))
    input_coverage = float(np.isfinite(input_x).sum() / max(1, input_x.shape[1]))

    from sklearn.ensemble import ExtraTreesRegressor, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error
    from sklearn.model_selection import LeaveOneOut, TimeSeriesSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    n = len(rows)
    if n >= 9:
        splitter = TimeSeriesSplit(n_splits=min(5, max(2, n - 5)))
        folds = list(splitter.split(x))
        validation_method = "expanding-window temporal validation"
    else:
        folds = list(LeaveOneOut().split(x))
        validation_method = "leave-one-test-out validation"

    estimators = {
        "SciPy Huber robust regression": make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            ScipyHuberRidge(alpha=1.5),
        ),
        "Regularized linear model": make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=3.0)
        ),
        "Extra-trees regression": make_pipeline(
            SimpleImputer(strategy="median"),
            ExtraTreesRegressor(
                n_estimators=160,
                min_samples_leaf=max(1, ceil(n * 0.08)),
                max_features=0.9,
                random_state=41,
                n_jobs=1,
            ),
        ),
        "Random-forest regression": make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestRegressor(
                n_estimators=160,
                min_samples_leaf=max(1, ceil(n * 0.1)),
                max_features=0.9,
                random_state=73,
                n_jobs=1,
            ),
        ),
    }
    validation = {}
    for name, estimator in estimators.items():
        predictions = np.full(n, np.nan)
        for train_index, test_index in folds:
            if len(train_index) < 2:
                continue
            try:
                estimator.fit(x[train_index], y[train_index])
                predictions[test_index] = estimator.predict(x[test_index])
            except (ValueError, TypeError, FloatingPointError):
                continue
        valid = np.isfinite(predictions)
        if valid.sum():
            validation[name] = {
                "mae": float(mean_absolute_error(y[valid], predictions[valid])),
                "predictions": predictions,
                "n": int(valid.sum()),
            }
    baseline = np.full(n, np.nan)
    for train_index, test_index in folds:
        if len(train_index):
            baseline[test_index] = float(np.median(y[train_index]))
    valid_baseline = np.isfinite(baseline)
    baseline_mae = float(mean_absolute_error(y[valid_baseline], baseline[valid_baseline])) if valid_baseline.sum() else float("inf")

    if not validation:
        return {
            "ok": False,
            "status": "model_fit_failed",
            "message": "The historical feature matrix is too sparse for a stable fit. Review the raw-water analyses linked to completed tests.",
            "sample_count": n,
            "features": schema,
            "history": _serializable_history(rows),
            "summary": _dose_summary(y.tolist()),
            "correlations": _correlations(rows, schema),
        }
    best_name = min(validation, key=lambda name: validation[name]["mae"])
    best_mae = validation[best_name]["mae"]
    if baseline_mae <= best_mae * 0.95:
        estimator_name = "Historical median (validated baseline)"
        point_estimate = float(np.median(y))
        residuals = np.abs(y[valid_baseline] - baseline[valid_baseline])
        validation_mae = baseline_mae
    else:
        estimator_name = best_name
        estimator = estimators[best_name]
        estimator.fit(x, y)
        point_estimate = float(estimator.predict(input_x)[0])
        predictions = validation[best_name]["predictions"]
        valid = np.isfinite(predictions)
        residuals = np.abs(y[valid] - predictions[valid])
        validation_mae = best_mae

    dose_min, dose_max = float(np.min(y)), float(np.max(y))
    bounded_estimate = min(dose_max, max(dose_min, point_estimate))
    out_of_domain = []
    feature_ranges = {}
    for feature in schema:
        values = [row["features"].get(feature["key"]) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            continue
        feature_ranges[feature["key"]] = [float(min(values)), float(max(values))]
        if feature["kind"] == "current":
            value = clean_inputs.get(feature["parameter_id"])
            if value is not None and (value < min(values) or value > max(values)):
                out_of_domain.append({"name": feature["name"], "value": value, "min": min(values), "max": max(values)})

    neighbor_data = _nearest_cases(rows, schema, clean_inputs, previous_inputs, x)
    neighbor_spread = float(np.quantile([abs(item["dose"] - bounded_estimate) for item in neighbor_data], 0.8)) if neighbor_data else 0
    calibrated_error = float(np.quantile(residuals, 0.9, method="higher")) if len(residuals) else 0
    half_width = max(calibrated_error, neighbor_spread, 0.5)
    low = max(dose_min, bounded_estimate - half_width)
    high = min(dose_max, bounded_estimate + half_width)
    relative_mae = validation_mae / max(float(np.std(y, ddof=1)) if n > 1 else 1, 0.1)
    confidence = "high" if n >= 20 and relative_mae < 0.65 and input_coverage >= 0.75 and not out_of_domain else "moderate" if n >= 10 and relative_mae < 1.0 and input_coverage >= 0.5 and not out_of_domain else "low"

    return {
        "ok": True,
        "status": "estimated",
        "estimate": round(bounded_estimate, 2),
        "interval": {"low": round(low, 2), "high": round(high, 2), "coverage": "calibrated historical error band; not a guaranteed interval"},
        "confidence": confidence,
        "input_coverage": round(input_coverage, 2),
        "sample_count": n,
        "coagulant": coagulant.name,
        "model": estimator_name,
        "validation": {
            "method": validation_method,
            "mae": round(float(validation_mae), 2),
            "median_baseline_mae": round(float(baseline_mae), 2),
            "validation_cases": min(item["n"] for item in validation.values()),
            "model_scores": [
                {"model": name, "mae": round(item["mae"], 2), "n": item["n"]}
                for name, item in sorted(validation.items(), key=lambda item: item[1]["mae"])
            ],
        },
        "dose_range": {"min": round(dose_min, 2), "max": round(dose_max, 2)},
        "out_of_domain": out_of_domain,
        "feature_ranges": feature_ranges,
        "features": schema,
        "history": _serializable_history(rows),
        "summary": _dose_summary(y.tolist()),
        "correlations": _correlations(rows, schema),
        "nearest_cases": neighbor_data,
        "prior_sample": prior_sample,
    }


def _nearest_cases(rows, schema, current_inputs, previous_inputs, x):
    if not rows or not schema:
        return []
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import StandardScaler

    filled = SimpleImputer(strategy="median").fit_transform(x)
    standardized = StandardScaler().fit_transform(filled)
    target = _numeric_matrix(_matrix([], schema, current_inputs, previous_inputs))
    target = SimpleImputer(strategy="median").fit(x).transform(target)
    target = StandardScaler().fit(filled).transform(target)[0]
    distances = np.linalg.norm(standardized - target, axis=1)
    indexes = np.argsort(distances)[: min(5, len(rows))]
    return [
        {
            "date": rows[index]["date"].isoformat(),
            "dose": round(rows[index]["dose"], 2),
            "distance": round(float(distances[index]), 2),
            "raw": {str(key): value for key, value in rows[index]["current"].items()},
        }
        for index in indexes
    ]


def _dose_summary(doses):
    if not doses:
        return {"count": 0, "median": None, "mean": None, "stdev": None, "q1": None, "q3": None, "min": None, "max": None}
    return {
        "count": len(doses),
        "median": round(float(np.median(doses)), 2),
        "mean": round(float(np.mean(doses)), 2),
        "stdev": round(float(np.std(doses, ddof=1)), 2) if len(doses) > 1 else 0,
        "q1": round(float(np.quantile(doses, 0.25)), 2),
        "q3": round(float(np.quantile(doses, 0.75)), 2),
        "min": round(float(min(doses)), 2),
        "max": round(float(max(doses)), 2),
    }


def _serializable_history(rows):
    return [
        {
            "date": row["date"].isoformat(),
            "dose": round(row["dose"], 2),
            "raw": {str(key): value for key, value in row["current"].items()},
            "qc_reference": row["qc_reference"],
        }
        for row in rows
    ]
