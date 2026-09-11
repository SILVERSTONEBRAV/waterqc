# qc/utils.py

from __future__ import annotations

import json
from typing import Dict, List, Type, Any, Optional

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet

from t.models import (
    TreatmentPlant,
    TreatedWaterLimit,
    MicrobialLimit,
    HeavyMetalLimit,
    RawWaterLimit,
    ClarifiedWaterLimit,
    CoagulatedWaterLimit,
    FilteredWaterLimit,
)

# ==========================================================
# 🔧 LIMIT MODEL REGISTRY (EXTENSIBLE)
# ==========================================================

LIMIT_MODELS: Dict[str, Type[Model]] = {
    "Treated Water": TreatedWaterLimit,
    "Microbial": MicrobialLimit,
    "Heavy Metal": HeavyMetalLimit,
    "Raw Water": RawWaterLimit,
    "Clarified Water": ClarifiedWaterLimit,
    "Coagulated Water": CoagulatedWaterLimit,
    "Filtered Water": FilteredWaterLimit,
}


# ==========================================================
# 🧱 CORE SERIALIZER
# ==========================================================

def format_limit(instance: Model, limit_type: str) -> Dict[str, Any]:
    """
    Standardized serializer for all limit models.
    Assumes uniform fields: parameter, min_value, max_value, treatment_plant.
    """
    return {
        "parameter": getattr(instance, "parameter", None),
        "min_value": getattr(instance, "min_value", None),
        "max_value": getattr(instance, "max_value", None),
        "limit_type": limit_type,
        "treatment_plant": getattr(instance.treatment_plant, "name", None),
        "treatment_plant_id": getattr(instance.treatment_plant, "id", None),
    }


# ==========================================================
# 🚀 GENERIC QUERY ENGINE (REDUCES DUPLICATION)
# ==========================================================

def _iter_limits(
    plant: Optional[TreatmentPlant] = None
) -> List[Dict[str, Any]]:
    """
    Internal generator for all limits across all models.
    Optionally filters by plant.
    """
    results: List[Dict[str, Any]] = []

    for limit_type, model in LIMIT_MODELS.items():
        qs: QuerySet = model.objects.select_related("treatment_plant")

        if plant is not None:
            qs = qs.filter(treatment_plant=plant)

        for obj in qs.iterator():
            results.append(format_limit(obj, limit_type))

    return results


# ==========================================================
# 📊 GLOBAL QUERIES
# ==========================================================

def list_all_parameters_and_limits() -> List[Dict[str, Any]]:
    """
    Returns flattened list of all limits across all plants and types.
    """
    return _iter_limits()


def get_limits_by_treatment_plant(plant_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Grouped limits by limit type for a single plant.
    """
    plant = TreatmentPlant.objects.filter(id=plant_id).only("id", "name").first()
    if not plant:
        return {}

    result: Dict[str, List[Dict[str, Any]]] = {}

    for limit_type, model in LIMIT_MODELS.items():
        qs = (
            model.objects
            .select_related("treatment_plant")
            .filter(treatment_plant_id=plant.id)
        )

        items = [format_limit(obj, limit_type) for obj in qs]
        if items:
            result[limit_type] = items

    return result


def get_parameters_by_treatment_plant(plant_id: int) -> List[str]:
    """
    Unique parameter list across all limit models for a plant.
    """
    plant = TreatmentPlant.objects.filter(id=plant_id).only("id").first()
    if not plant:
        return []

    params = set()

    for model in LIMIT_MODELS.values():
        qs = (
            model.objects
            .filter(treatment_plant_id=plant.id)
            .values_list("parameter", flat=True)
            .distinct()
        )
        params.update(qs)

    return sorted(params)


def get_parameter_limit_detail(
    plant_id: int,
    parameter_name: str
) -> List[Dict[str, Any]]:
    """
    Fetch limit definition(s) for a specific parameter in a plant.
    Case-insensitive parameter match.
    """
    plant = TreatmentPlant.objects.filter(id=plant_id).only("id").first()
    if not plant:
        return []

    results: List[Dict[str, Any]] = []

    for limit_type, model in LIMIT_MODELS.items():
        qs = model.objects.filter(
            treatment_plant_id=plant.id,
            parameter__iexact=parameter_name,
        ).select_related("treatment_plant")

        results.extend(format_limit(obj, limit_type) for obj in qs)

    return results


def get_all_plants_with_their_parameters() -> List[Dict[str, Any]]:
    """
    Returns all plants with distinct parameter lists.
    Optimized: avoids repeated DB calls per plant.
    """
    plants = TreatmentPlant.objects.all().only("id", "name")

    # prefetch all data once (avoids N+1 explosion)
    all_limits = _iter_limits()

    plant_map: Dict[int, set] = {p.id: set() for p in plants}

    # map parameters to plants
    for item in all_limits:
        pid = item.get("treatment_plant_id")
        param = item.get("parameter")
        if pid and param:
            plant_map.setdefault(pid, set()).add(param)

    return [
        {
            "treatment_plant": plant.name,
            "parameters": sorted(list(plant_map.get(plant.id, set()))),
        }
        for plant in plants
    ]


# ==========================================================
# 📤 EXPORTERS
# ==========================================================

def export_limits_json(pretty: bool = True) -> str:
    """
    Export all limits system-wide as JSON.
    """
    data = list_all_parameters_and_limits()
    return json.dumps(
        data,
        cls=DjangoJSONEncoder,
        indent=2 if pretty else None
    )


def export_limits_by_plant_json(plant_id: int, pretty: bool = True) -> str:
    """
    Export plant-specific limits as JSON.
    """
    data = get_limits_by_treatment_plant(plant_id)
    return json.dumps(
        data,
        cls=DjangoJSONEncoder,
        indent=2 if pretty else None
    )


# ==========================================================
# 🧪 OPTIONAL: PERFORMANCE HELPERS
# ==========================================================

def get_limit_model_names() -> List[str]:
    """
    Debug / introspection helper.
    """
    return list(LIMIT_MODELS.keys())


def count_all_limits() -> Dict[str, int]:
    """
    Returns count per limit category.
    """
    return {
        name: model.objects.count()
        for name, model in LIMIT_MODELS.items()
    }