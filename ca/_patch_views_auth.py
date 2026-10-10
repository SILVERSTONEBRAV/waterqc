from pathlib import Path
import re

p = Path(__file__).with_name("views.py")
text = p.read_text(encoding="utf-8")
text = text.replace("CaCaWanjalaMixin", "CaWanjalaMixin")

old_import = """from .mixins import CaWanjalaMixin

from .forms import (
    ChemicalBatchForm,
    ChemicalSpecificationFilterForm,
    TestResultFilterForm,
)
from .models import (
    BatchTestResult,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
    ChemicalSpecification,
    ChecklistForWaterTreatmentChemicalAnalysis,
)"""

new_import = """from core.engine.super_user import SuperUserEngine

from .forms import (
    ChemicalBatchForm,
    ChemicalSpecificationFilterForm,
    TestResultFilterForm,
)
from .mixins import CaWanjalaMixin
from .models import (
    BatchTestResult,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalCoA,
    ChemicalSpecification,
    ChecklistForWaterTreatmentChemicalAnalysis,
)"""

if old_import not in text:
    raise SystemExit("import block missing")
text = text.replace(old_import, new_import, 1)

helpers_old = """def _user_plant_id(user):
    return getattr(user, \"assigned_treatment_plant_id\", None)


def _is_superuser(user):
    return bool(user and user.is_superuser)


def _require_permission(user, permission):
    if _is_superuser(user):
        return

    if not user.has_perm(permission):
        raise PermissionDenied(
            \"You do not have permission to perform this action.\"
        )


def _require_plant(user):
    if _is_superuser(user):
        return None

    plant_id = _user_plant_id(user)

    if plant_id is None:
        raise PermissionDenied(
            \"Your account is not assigned to a treatment plant.\"
        )

    return plant_id


def _scope_queryset(queryset, user, field=\"treatment_plant_id\"):
    if _is_superuser(user):
        return queryset

    plant_id = _require_plant(user)

    return queryset.filter(
        **{field: plant_id}
    )"""

helpers_new = """def _scope_queryset(queryset, user, field=\"treatment_plant_id\", plant_id=None):
    \"\"\"Plant-scope a queryset using Wanjala/SuperUser rules.\"\"\"
    if SuperUserEngine.is_superuser(user):
        if plant_id is None:
            return queryset
        return queryset.filter(**{field: plant_id})

    assigned = getattr(user, \"assigned_treatment_plant_id\", None)
    if assigned is None:
        raise PermissionDenied(
            \"Your account is not assigned to a treatment plant.\"
        )
    return queryset.filter(**{field: assigned})"""

if helpers_old not in text:
    raise SystemExit("helpers block missing")
text = text.replace(helpers_old, helpers_new, 1)

text = re.sub(
    r"\ndef request_has_permission\(\n    request,\n    permission,\n\):\n"
    r"    if not permission:\n        return True\n\n"
    r"    try:\n        if request\.user\.is_superuser:\n            return True\n\n"
    r"        return bool\(\n            request\.user\.has_perm\(permission\)\n        \)\n"
    r"    except AttributeError:\n        return False\n",
    "\n",
    text,
    count=1,
)

# Update queryset helpers to accept optional plant_id
for fn in (
    "_process_queryset",
    "_batch_queryset",
    "_request_queryset",
    "_result_queryset",
    "_analysis_input_queryset",
    "_coa_queryset",
    "_checklist_queryset",
    "_process_display_queryset",
    "_batch_display_queryset",
    "_request_display_queryset",
    "_result_display_queryset",
    "_coa_display_queryset",
    "_specification_queryset",
):
    text = text.replace(f"def {fn}(user):", f"def {fn}(user, plant_id=None):")

text = text.replace(
    """def _specification_queryset(user, plant_id=None):
    queryset = (
        ChemicalSpecification.objects
        .select_related(
            \"chemical\",
            \"method\",
            \"treatment_plant\",
        )
        .order_by(
            \"chemical__name\",
            \"parameter_name\",
            \"-version\",
        )
    )

    if _is_superuser(user):
        return queryset

    plant_id = _require_plant(user)

    return queryset.filter(
        Q(treatment_plant_id=plant_id)
        | Q(treatment_plant__isnull=True)
    )""",
    """def _specification_queryset(user, plant_id=None):
    queryset = (
        ChemicalSpecification.objects
        .select_related(
            \"chemical\",
            \"method\",
            \"treatment_plant\",
        )
        .order_by(
            \"chemical__name\",
            \"parameter_name\",
            \"-version\",
        )
    )

    if SuperUserEngine.is_superuser(user):
        if plant_id is None:
            return queryset
        return queryset.filter(
            Q(treatment_plant_id=plant_id)
            | Q(treatment_plant__isnull=True)
        )

    assigned = getattr(user, \"assigned_treatment_plant_id\", None)
    if assigned is None:
        raise PermissionDenied(
            \"Your account is not assigned to a treatment plant.\"
        )

    return queryset.filter(
        Q(treatment_plant_id=assigned)
        | Q(treatment_plant__isnull=True)
    )""",
)

# Pass plant_id through nested queryset helpers where _scope_queryset is called
replacements = [
    (
        """def _process_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisProcess.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
    )""",
        """def _process_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisProcess.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
        plant_id=plant_id,
    )""",
    ),
    (
        """def _batch_queryset(user, plant_id=None):
    queryset = ChemicalBatch.objects.all()

    return _scope_queryset(
        queryset,
        user,
    )""",
        """def _batch_queryset(user, plant_id=None):
    queryset = ChemicalBatch.objects.all()

    return _scope_queryset(
        queryset,
        user,
        plant_id=plant_id,
    )""",
    ),
    (
        """def _request_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisRequest.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
    )""",
        """def _request_queryset(user, plant_id=None):
    queryset = ChemicalAnalysisRequest.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
        plant_id=plant_id,
    )""",
    ),
    (
        """def _result_queryset(user, plant_id=None):
    queryset = BatchTestResult.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
    )""",
        """def _result_queryset(user, plant_id=None):
    queryset = BatchTestResult.objects.all()

    return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
        plant_id=plant_id,
    )""",
    ),
]

for old, new in replacements:
    if old not in text:
        raise SystemExit(f"missing block:\n{old[:80]}")
    text = text.replace(old, new, 1)

# Remaining scope helpers that still lack plant_id kwarg
text = text.replace(
    """return _scope_queryset(
        queryset,
        user,
        \"test_result__batch__treatment_plant_id\",
    )""",
    """return _scope_queryset(
        queryset,
        user,
        \"test_result__batch__treatment_plant_id\",
        plant_id=plant_id,
    )""",
    1,
)
text = text.replace(
    """return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
    )


def _coa_display_queryset""",
    """return _scope_queryset(
        queryset,
        user,
        \"batch__treatment_plant_id\",
        plant_id=plant_id,
    )


def _coa_display_queryset""",
    1,
)
text = text.replace(
    """return _scope_queryset(
        queryset,
        user,
        \"chemical_analysis_request__batch__treatment_plant_id\",
    )""",
    """return _scope_queryset(
        queryset,
        user,
        \"chemical_analysis_request__batch__treatment_plant_id\",
        plant_id=plant_id,
    )""",
    1,
)

# Nested display helpers should forward plant_id
for name in (
    "_process_display_queryset",
    "_batch_display_queryset",
    "_request_display_queryset",
    "_result_display_queryset",
    "_coa_display_queryset",
):
    base = name.replace("_display", "")
    # e.g. _process_queryset(user) -> _process_queryset(user, plant_id=plant_id)
    text = text.replace(
        f"{base}(user)",
        f"{base}(user, plant_id=plant_id)",
    )

# Remove manual _require_permission calls — CaWanjalaMixin.dispatch enforces view perms
text = re.sub(
    r"\n\s*_require_permission\(\n(?:.|\n)*?\n\s*\)\n",
    "\n",
    text,
)

# Replace _require_plant(user) usages in forms
text = text.replace(
    """        if not user.is_superuser:
            form.instance.treatment_plant_id = (
                _require_plant(user)
            )""",
    """        if not SuperUserEngine.is_superuser(user):
            form.instance.treatment_plant_id = (
                getattr(user, \"assigned_treatment_plant_id\", None)
            )
            if form.instance.treatment_plant_id is None:
                raise PermissionDenied(
                    \"Your account is not assigned to a treatment plant.\"
                )""",
)

text = text.replace(
    """        if not user.is_superuser:
            plant_id = _require_plant(user)

            if (
                form.instance.treatment_plant_id
                != plant_id
            ):
                raise PermissionDenied(
                    \"The chemical batch belongs to another treatment plant.\"
                )""",
    """        if not SuperUserEngine.is_superuser(user):
            plant_id = getattr(user, \"assigned_treatment_plant_id\", None)

            if plant_id is None:
                raise PermissionDenied(
                    \"Your account is not assigned to a treatment plant.\"
                )

            if form.instance.treatment_plant_id != plant_id:
                raise PermissionDenied(
                    \"The chemical batch belongs to another treatment plant.\"
                )""",
)

# request_has_permission references in context -> SuperUserEngine / has_perm
text = text.replace(
    "request_has_permission(\n                        request,",
    "(\n                        SuperUserEngine.is_superuser(request.user)\n                        or request.user.has_perm(",
)

# That might be too fragile - check remaining markers after write

p.write_text(text, encoding="utf-8")
print("patched views.py")
print("leftover _require_permission", text.count("_require_permission"))
print("leftover _require_plant", text.count("_require_plant"))
print("leftover _is_superuser", text.count("_is_superuser"))
print("leftover request_has_permission", text.count("request_has_permission"))
print("CaCa", text.count("CaCaWanjalaMixin"))
