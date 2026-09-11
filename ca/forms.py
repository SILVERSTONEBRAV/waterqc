from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from t.models import TreatmentPlant
from weeklytasks.models import DailyTaskAssignment, WeeklyDutyTask

from .models import (
    BatchTestResult,
    Chemical,
    ChemicalAnalysisInput,
    ChemicalAnalysisProcess,
    ChemicalAnalysisRequest,
    ChemicalBatch,
    ChemicalLocation,
    ChemicalSpecification,
    ChecklistForWaterTreatmentChemicalAnalysis,
    Supplier,
)


User = get_user_model()

FORM_CONTROL_CLASS = (
    "block w-full rounded-lg border border-gray-300 bg-white "
    "px-3 py-2 text-sm text-gray-900 shadow-sm "
    "focus:border-primary-500 focus:ring-primary-500"
)

CHECKBOX_CLASS = (
    "h-4 w-4 rounded border-gray-300 text-primary-600 "
    "focus:ring-primary-500"
)

CHEMICAL_ANALYSIS_TASK_NAME = "Water Treatment Chemical Analysis"


def apply_field_classes(form: forms.BaseForm) -> None:
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", CHECKBOX_CLASS)
        else:
            widget.attrs.setdefault("class", FORM_CONTROL_CLASS)


def scoped_user_queryset(
    treatment_plant=None,
    *,
    section=None,
):
    queryset = User.objects.filter(
        is_active=True,
    )

    if treatment_plant is not None:
        treatment_plant_id = getattr(
            treatment_plant,
            "pk",
            treatment_plant,
        )
        queryset = queryset.filter(
            assigned_treatment_plant_id=treatment_plant_id,
        )

    if section is not None:
        section_id = getattr(
            section,
            "pk",
            section,
        )
        queryset = queryset.filter(
            section_id=section_id,
        )

    return queryset.order_by(
        "first_name",
        "last_name",
        "username",
    )


def chemical_analysis_task_queryset(
    *,
    treatment_plant=None,
    section=None,
    assignment_date=None,
    current_time=None,
):
    assignment_date = (
        assignment_date
        or timezone.localdate()
    )

    if current_time is None:
        current_time = timezone.localtime().time()

    queryset = (
        DailyTaskAssignment.objects
        .filter(
            task__task_template__name__iexact=CHEMICAL_ANALYSIS_TASK_NAME,
            task__task_template__is_active=True,
            task__week__start_date__lte=assignment_date,
            task__week__end_date__gte=assignment_date,
            date=assignment_date,
            user__is_active=True,
            shift__is_deleted=False,
            shift__start_time__lte=current_time,
            shift__end_time__gt=current_time,
        )
    )

    if treatment_plant is not None:
        treatment_plant_id = getattr(
            treatment_plant,
            "pk",
            treatment_plant,
        )
        queryset = queryset.filter(
            task__treatment_plant_id=treatment_plant_id,
            user__assigned_treatment_plant_id=treatment_plant_id,
        )

    if section is not None:
        section_id = getattr(
            section,
            "pk",
            section,
        )
        queryset = queryset.filter(
            task__section_id=section_id,
            user__section_id=section_id,
        )

    return queryset


def chemical_analysis_analyst_queryset(
    *,
    treatment_plant=None,
    section=None,
    assignment_date=None,
    current_time=None,
):
    user_ids = (
        chemical_analysis_task_queryset(
            treatment_plant=treatment_plant,
            section=section,
            assignment_date=assignment_date,
            current_time=current_time,
        )
        .values_list(
            "user_id",
            flat=True,
        )
        .distinct()
    )

    return (
        User.objects
        .filter(
            pk__in=user_ids,
            is_active=True,
        )
        .order_by(
            "first_name",
            "last_name",
            "username",
        )
    )


def qa_user_queryset(
    treatment_plant=None,
):
    queryset = User.objects.filter(
        is_active=True,
    ).filter(
        Q(
            groups__permissions__codename="review_chemical_analysis",
            groups__permissions__content_type__app_label="ca",
        )
        | Q(
            user_permissions__codename="review_chemical_analysis",
            user_permissions__content_type__app_label="ca",
        )
    )

    if treatment_plant is not None:
        queryset = queryset.filter(
            assigned_treatment_plant_id=getattr(
                treatment_plant,
                "pk",
                treatment_plant,
            )
        )

    return (
        queryset
        .distinct()
        .order_by(
            "first_name",
            "last_name",
            "username",
        )
    )


def approver_queryset(
    treatment_plant=None,
):
    queryset = User.objects.filter(
        is_active=True,
    ).filter(
        Q(
            groups__permissions__codename="approve_chemical_coa",
            groups__permissions__content_type__app_label="ca",
        )
        | Q(
            user_permissions__codename="approve_chemical_coa",
            user_permissions__content_type__app_label="ca",
        )
    )

    if treatment_plant is not None:
        queryset = queryset.filter(
            assigned_treatment_plant_id=getattr(
                treatment_plant,
                "pk",
                treatment_plant,
            )
        )

    return (
        queryset
        .distinct()
        .order_by(
            "first_name",
            "last_name",
            "username",
        )
    )


def _input_definition_name(definition: Any) -> str:
    if isinstance(definition, str):
        return definition.strip()

    if isinstance(definition, dict):
        return str(
            definition.get("name")
            or definition.get("key")
            or definition.get("field")
            or ""
        ).strip()

    return str(
        getattr(
            definition,
            "name",
            getattr(
                definition,
                "key",
                getattr(
                    definition,
                    "field",
                    "",
                ),
            ),
        )
        or ""
    ).strip()


def _input_definition_value(
    definition: Any,
    key: str,
    default=None,
):
    if isinstance(definition, dict):
        return definition.get(key, default)

    return getattr(
        definition,
        key,
        default,
    )


def _normalise_input_definitions(
    definitions: Any,
) -> list[dict[str, Any]]:
    if not definitions:
        return []

    if isinstance(definitions, str):
        definitions = [
            item.strip()
            for item in definitions.split(",")
            if item.strip()
        ]

    if isinstance(definitions, dict):
        definitions = [
            {
                "name": key,
                **(
                    value
                    if isinstance(value, dict)
                    else {"label": value}
                ),
            }
            for key, value in definitions.items()
        ]

    normalised = []

    for definition in definitions:
        name = _input_definition_name(definition)

        if not name:
            continue

        normalised.append(
            {
                "name": name,
                "label": (
                    _input_definition_value(
                        definition,
                        "label",
                        name.replace("_", " ").title(),
                    )
                    or name.replace("_", " ").title()
                ),
                "required": bool(
                    _input_definition_value(
                        definition,
                        "required",
                        True,
                    )
                ),
                "type": (
                    _input_definition_value(
                        definition,
                        "type",
                        "number",
                    )
                    or "number"
                ),
                "min_value": _input_definition_value(
                    definition,
                    "min_value",
                ),
                "max_value": _input_definition_value(
                    definition,
                    "max_value",
                ),
            }
        )

    return normalised


def _coerce_numeric(value):
    if value in (
        None,
        "",
    ):
        return None

    try:
        return Decimal(str(value))
    except (
        TypeError,
        ValueError,
        ArithmeticError,
    ) as exc:
        raise ValidationError(
            "The value must be numeric."
        ) from exc


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = (
            "name",
            "contact_info",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Supplier name",
                }
            ),
            "contact_info": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Contact information",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_name(self):
        value = (
            self.cleaned_data
            .get("name")
            or ""
        ).strip()

        if not value:
            raise ValidationError(
                "Supplier name is required."
            )

        queryset = Supplier.objects.filter(
            name__iexact=value,
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise ValidationError(
                "A supplier with this name already exists."
            )

        return value


class ChemicalForm(forms.ModelForm):
    class Meta:
        model = Chemical
        fields = (
            "name",
            "code",
            "description",
            "grade",
            "hydrometer_formula",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Chemical name",
                }
            ),
            "code": forms.TextInput(
                attrs={
                    "placeholder": "Chemical code",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Chemical description",
                }
            ),
            "grade": forms.TextInput(
                attrs={
                    "placeholder": "Chemical grade",
                }
            ),
            "hydrometer_formula": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": (
                        "Example: (reading * 1.05 + 2)"
                    ),
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_name(self):
        value = (
            self.cleaned_data
            .get("name")
            or ""
        ).strip()

        if not value:
            raise ValidationError(
                "Chemical name is required."
            )

        queryset = Chemical.objects.filter(
            name__iexact=value,
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise ValidationError(
                "A chemical with this name already exists."
            )

        return value

    def clean_code(self):
        value = (
            self.cleaned_data
            .get("code")
            or ""
        ).strip().upper()

        if not value:
            raise ValidationError(
                "Chemical code is required."
            )

        queryset = Chemical.objects.filter(
            code__iexact=value,
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise ValidationError(
                "A chemical with this code already exists."
            )

        return value


class ChemicalLocationForm(forms.ModelForm):
    class Meta:
        model = ChemicalLocation
        fields = (
            "name",
            "treatment_plant",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Chemical storage or analysis location",
                }
            ),
        }

    def __init__(
        self,
        *args,
        treatment_plant=None,
        **kwargs,
    ):
        self.treatment_plant = treatment_plant
        super().__init__(*args, **kwargs)

        self.fields[
            "treatment_plant"
        ].queryset = TreatmentPlant.objects.order_by(
            "name",
        )

        if treatment_plant is not None:
            self.fields[
                "treatment_plant"
            ].initial = treatment_plant

        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        name = (
            cleaned.get("name")
            or ""
        ).strip()

        plant = cleaned.get(
            "treatment_plant"
        )

        if not name:
            self.add_error(
                "name",
                "Location name is required.",
            )

        if name and plant:
            queryset = ChemicalLocation.objects.filter(
                name__iexact=name,
                treatment_plant=plant,
            )

            if self.instance.pk:
                queryset = queryset.exclude(
                    pk=self.instance.pk,
                )

            if queryset.exists():
                self.add_error(
                    "name",
                    "This chemical location already exists "
                    "for the selected treatment plant.",
                )

        return cleaned


class ChemicalSpecificationForm(forms.ModelForm):
    class Meta:
        model = ChemicalSpecification
        fields = (
            "chemical",
            "treatment_plant",
            "parameter_name",
            "version",
            "min_limit",
            "max_limit",
            "unit",
            "is_required",
            "method",
        )
        widgets = {
            "min_limit": forms.NumberInput(
                attrs={
                    "step": "any",
                }
            ),
            "max_limit": forms.NumberInput(
                attrs={
                    "step": "any",
                }
            ),
            "version": forms.NumberInput(
                attrs={
                    "min": "1",
                }
            ),
        }

    def __init__(
        self,
        *args,
        treatment_plant=None,
        **kwargs,
    ):
        self.treatment_plant = treatment_plant
        super().__init__(*args, **kwargs)

        self.fields[
            "chemical"
        ].queryset = Chemical.objects.order_by(
            "name",
        )

        self.fields[
            "treatment_plant"
        ].queryset = TreatmentPlant.objects.order_by(
            "name",
        )

        if treatment_plant is not None:
            self.fields[
                "treatment_plant"
            ].initial = treatment_plant

        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        minimum = cleaned.get(
            "min_limit"
        )
        maximum = cleaned.get(
            "max_limit"
        )

        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
            self.add_error(
                "max_limit",
                "Maximum limit cannot be lower than minimum limit.",
            )

        return cleaned


class ChemicalRemarkForm(forms.Form):
    remark = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Remark",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_remark(self):
        value = (
            self.cleaned_data
            .get("remark")
            or ""
        ).strip()

        if not value:
            raise ValidationError(
                "A remark is required."
            )

        return value


class PackagingForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm packaging completion",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Packaging remarks",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class ChemicalBatchForm(forms.ModelForm):
    class Meta:
        model = ChemicalBatch
        fields = (
            "delivery_note_number",
            "batch_number",
            "chemical",
            "supplier",
            "treatment_plant",
            "quantity_received",
            "unit",
            "remarks",
        )
        widgets = {
            "delivery_note_number": forms.TextInput(
                attrs={
                    "placeholder": "Delivery note number",
                }
            ),
            "batch_number": forms.TextInput(
                attrs={
                    "placeholder": "Supplier/manufacturer batch number",
                }
            ),
            "quantity_received": forms.NumberInput(
                attrs={
                    "min": "0.0001",
                    "step": "any",
                }
            ),
            "unit": forms.TextInput(
                attrs={
                    "placeholder": "kg",
                }
            ),
            "remarks": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Receiving remarks",
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        self.user = user
        super().__init__(*args, **kwargs)

        self.fields[
            "chemical"
        ].queryset = Chemical.objects.order_by(
            "name",
        )

        self.fields[
            "supplier"
        ].queryset = Supplier.objects.order_by(
            "name",
        )

        self.fields[
            "treatment_plant"
        ].queryset = (
            self.fields[
                "treatment_plant"
            ].queryset.order_by(
                "name",
            )
        )

        if not self.instance.pk:
            self.fields[
                "unit"
            ].initial = "kg"

        apply_field_classes(self)

    def clean_delivery_note_number(self):
        value = (
            self.cleaned_data
            .get("delivery_note_number")
            or ""
        ).strip()

        if not value:
            return value

        queryset = ChemicalBatch.objects.filter(
            delivery_note_number__iexact=value,
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise ValidationError(
                "A chemical batch with this delivery note number already exists."
            )

        return value

    def clean_batch_number(self):
        value = (
            self.cleaned_data
            .get("batch_number")
            or ""
        ).strip()

        queryset = ChemicalBatch.objects.filter(
            batch_number__iexact=value,
        )

        if self.instance.pk:
            queryset = queryset.exclude(
                pk=self.instance.pk,
            )

        if queryset.exists():
            raise ValidationError(
                "A chemical batch with this batch number already exists."
            )

        return value

    def clean_quantity_received(self):
        value = self.cleaned_data.get(
            "quantity_received"
        )

        if value is None or value <= 0:
            raise ValidationError(
                "Quantity received must be greater than zero."
            )

        return value

    def clean(self):
        cleaned = super().clean()

        chemical = cleaned.get(
            "chemical"
        )
        plant = cleaned.get(
            "treatment_plant"
        )

        if chemical and plant:
            if not ChemicalSpecification.objects.filter(
                chemical=chemical,
                treatment_plant=plant,
                is_required=True,
            ).exists():
                self._form_warnings = [
                    "No required analytical specifications are configured "
                    "for this chemical at the selected treatment plant."
                ]

        return cleaned


class ReceiveChemicalBatchForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm receipt of chemical batch",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Receiving remarks",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class ChemicalAnalysisRequestForm(forms.ModelForm):
    class Meta:
        model = ChemicalAnalysisRequest
        fields = (
            "batch",
            "delivery_date",
            "location",
        )
        widgets = {
            "delivery_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }

    def __init__(
        self,
        *args,
        user=None,
        treatment_plant=None,
        batch=None,
        **kwargs,
    ):
        self.user = user
        self.treatment_plant = treatment_plant
        self.selected_batch = batch

        super().__init__(*args, **kwargs)

        batches = (
            ChemicalBatch.objects
            .select_related(
                "chemical",
                "supplier",
                "treatment_plant",
            )
            .filter(
                status=ChemicalBatch.Status.RECEIVED,
            )
            .order_by(
                "-received_date",
                "-created_at",
            )
        )

        if treatment_plant is not None:
            batches = batches.filter(
                treatment_plant=treatment_plant,
            )

        if batch is not None:
            batches = batches.filter(
                pk=getattr(
                    batch,
                    "pk",
                    batch,
                )
            )

        self.fields[
            "batch"
        ].queryset = batches

        locations = (
            ChemicalLocation.objects
            .select_related(
                "treatment_plant",
            )
            .order_by(
                "treatment_plant__name",
                "name",
            )
        )

        if treatment_plant is not None:
            locations = locations.filter(
                treatment_plant=treatment_plant,
            )

        self.fields[
            "location"
        ].queryset = locations

        if not self.instance.pk:
            self.fields[
                "delivery_date"
            ].initial = timezone.localdate()

        apply_field_classes(self)

    def clean_delivery_date(self):
        value = self.cleaned_data.get(
            "delivery_date"
        )

        if value is None:
            return value

        if value > timezone.localdate():
            raise ValidationError(
                "Delivery date cannot be in the future."
            )

        return value

    def clean(self):
        cleaned = super().clean()

        batch = cleaned.get(
            "batch"
        )
        location = cleaned.get(
            "location"
        )

        if batch is None:
            self.add_error(
                "batch",
                "A chemical batch is required.",
            )
            return cleaned

        if batch.status != ChemicalBatch.Status.RECEIVED:
            self.add_error(
                "batch",
                "Only received chemical batches can be submitted for analysis.",
            )

        if location:
            if (
                batch.treatment_plant_id
                and location.treatment_plant_id
                and batch.treatment_plant_id
                != location.treatment_plant_id
            ):
                self.add_error(
                    "location",
                    "The analysis location must belong to the same treatment plant.",
                )

        existing = (
            ChemicalAnalysisRequest.objects
            .filter(
                batch=batch,
            )
        )

        if self.instance.pk:
            existing = existing.exclude(
                pk=self.instance.pk,
            )

        if existing.exists():
            self.add_error(
                "batch",
                "An analysis request already exists for this chemical batch.",
            )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False,
        )

        if (
            self.user is not None
            and not instance.requested_by_id
        ):
            instance.requested_by = self.user

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = ChecklistForWaterTreatmentChemicalAnalysis
        fields = (
            "chemical",
            "manufacturer_name_indicated",
            "chemical_name_on_label",
            "min_mass_indicated",
            "grade",
            "manufacture_date",
            "expiry_date",
            "storage_conditions",
            "net_weight",
            "country_of_origin",
            "handling_instructions",
            "is_oxidizing",
            "is_corrosive",
            "may_cause_fire",
            "contact_with_acids_liberates_toxic_gas",
            "causes_burns",
            "keep_out_of_reach_of_children",
            "contact_with_eyes_action",
            "fire_action_requires_respiratory_equipment",
        )
        widgets = {
            "manufacture_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "expiry_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
            "storage_conditions": forms.TextInput(),
            "net_weight": forms.NumberInput(
                attrs={
                    "min": "0",
                    "step": "any",
                }
            ),
            "handling_instructions": forms.Textarea(
                attrs={
                    "rows": 3,
                }
            ),
        }

    def __init__(
        self,
        *args,
        request=None,
        user=None,
        **kwargs,
    ):
        self.analysis_request = request
        self.user = user

        super().__init__(*args, **kwargs)

        self.fields[
            "chemical"
        ].queryset = Chemical.objects.order_by(
            "name",
        )

        if (
            request is not None
            and request.batch_id
        ):
            chemical_id = request.batch.chemical_id

            self.fields[
                "chemical"
            ].queryset = Chemical.objects.filter(
                pk=chemical_id,
            )

            self.initial.setdefault(
                "chemical",
                chemical_id,
            )

        if not self.instance.pk:
            self.fields[
                "country_of_origin"
            ].initial = "KE"

        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        manufacture = cleaned.get(
            "manufacture_date"
        )
        expiry = cleaned.get(
            "expiry_date"
        )
        weight = cleaned.get(
            "net_weight"
        )

        if (
            manufacture
            and expiry
            and expiry <= manufacture
        ):
            self.add_error(
                "expiry_date",
                "Expiry date must be later than manufacture date.",
            )

        if (
            manufacture
            and manufacture > timezone.localdate()
        ):
            self.add_error(
                "manufacture_date",
                "Manufacture date cannot be in the future.",
            )

        if (
            weight is not None
            and weight <= 0
        ):
            self.add_error(
                "net_weight",
                "Net weight must be greater than zero.",
            )

        if (
            self.analysis_request is not None
            and self.analysis_request.batch_id
        ):
            chemical = cleaned.get(
                "chemical"
            )

            if (
                chemical
                and chemical.pk
                != self.analysis_request.batch.chemical_id
            ):
                self.add_error(
                    "chemical",
                    "The checklist chemical must match the batch chemical.",
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False,
        )

        if self.analysis_request is not None:
            instance.chemical_analysis_request = (
                self.analysis_request
            )

        if self.user is not None:
            if not instance.sampled_by_id:
                instance.sampled_by = self.user

            if not instance.requested_by_id:
                instance.requested_by = (
                    self.analysis_request.requested_by
                    if (
                        self.analysis_request
                        and self.analysis_request.requested_by_id
                    )
                    else self.user
                )

        if commit:
            instance.save()

        return instance


class CompleteChecklistForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm that the chemical receiving checklist is complete",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class SystematicSamplingPlanForm(forms.Form):
    sample_size = forms.IntegerField(
        required=True,
        min_value=1,
        label="Required sample size",
    )
    sampling_interval = forms.IntegerField(
        required=True,
        min_value=1,
        label="Sampling interval",
    )
    rationale = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Sampling plan rationale",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm systematic random sampling plan",
    )

    def __init__(
        self,
        *args,
        process=None,
        **kwargs,
    ):
        self.process = process
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        process = self.process

        if process is not None:
            process.refresh_assigned_analysts()

            if not process.has_assigned_analysts:
                raise ValidationError(
                    "No analysts are currently assigned to this "
                    "chemical analysis through the weekly duty schedule."
                )

        return cleaned


class SystematicSamplingMeasurementForm(forms.Form):
    sample_number = forms.IntegerField(
        required=True,
        min_value=1,
        label="Sample number",
    )
    measurement = forms.DecimalField(
        required=True,
        max_digits=16,
        decimal_places=6,
        label="Measurement",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Sampling measurement remarks",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm sampling measurement",
    )

    def __init__(
        self,
        *args,
        process=None,
        **kwargs,
    ):
        self.process = process
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_measurement(self):
        value = self.cleaned_data.get(
            "measurement"
        )

        if value is None:
            return value

        if value < 0:
            raise ValidationError(
                "The sampling measurement cannot be negative."
            )

        return value


class SamplingCounterCheckForm(forms.Form):
    counter_checked = forms.BooleanField(
        required=True,
        label="Confirm counter-check completion",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Counter-check remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        process=None,
        **kwargs,
    ):
        self.process = process
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class SamplingQAReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(
            ("APPROVE", "Approve sampling"),
            ("REJECT", "Reject sampling"),
        ),
    )
    rationale = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Sampling QA rationale",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm sampling QA decision",
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        decision = cleaned.get(
            "decision"
        )
        rationale = (
            cleaned.get("rationale")
            or ""
        ).strip()

        if (
            decision == "REJECT"
            and not rationale
        ):
            self.add_error(
                "rationale",
                "A rationale is required when sampling is rejected.",
            )

        return cleaned


class SamplingQAApprovalForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm sampling QA approval",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Sampling approval remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        self.user = user
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_confirm(self):
        value = self.cleaned_data.get(
            "confirm"
        )

        if not value:
            raise ValidationError(
                "Sampling QA approval must be explicitly confirmed."
            )

        if (
            self.user is not None
            and not self.user.is_active
        ):
            raise ValidationError(
                "An inactive user cannot approve sampling."
            )

        return value


class SamplingQARejectForm(forms.Form):
    rationale = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Reason for rejecting sampling",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm sampling rejection",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class CompleteSystematicRandomSamplingForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm completion of systematic random sampling",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Sampling completion remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        process=None,
        **kwargs,
    ):
        self.process = process
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        if self.process is not None:
            self.process.refresh_assigned_analysts()

            if not self.process.has_assigned_analysts:
                raise ValidationError(
                    "No analysts are currently assigned to this "
                    "chemical analysis through the weekly duty schedule."
                )

        return cleaned


class BatchTestResultForm(forms.ModelForm):
    class Meta:
        model = BatchTestResult
        fields = (
            "parameter",
            "value",
            "textual_result",
            "status",
        )
        widgets = {
            "value": forms.NumberInput(
                attrs={
                    "step": "any",
                    "placeholder": "Measured value",
                }
            ),
            "textual_result": forms.TextInput(
                attrs={
                    "placeholder": "Textual result, if applicable",
                }
            ),
        }

    def __init__(
        self,
        *args,
        process=None,
        batch=None,
        analyst=None,
        parameter=None,
        **kwargs,
    ):
        self.process = process
        self.batch = (
            batch
            or getattr(
                process,
                "batch",
                None,
            )
        )
        self.analyst = analyst
        self.selected_parameter = parameter

        super().__init__(*args, **kwargs)

        if self.batch is not None:
            queryset = (
                ChemicalSpecification.objects
                .filter(
                    chemical_id=self.batch.chemical_id,
                    treatment_plant_id=self.batch.treatment_plant_id,
                    is_required=True,
                )
                .select_related(
                    "chemical",
                    "method",
                )
                .order_by(
                    "parameter_name",
                    "version",
                )
            )
        else:
            queryset = ChemicalSpecification.objects.none()

        self.fields[
            "parameter"
        ].queryset = queryset

        if parameter is not None:
            self.fields[
                "parameter"
            ].initial = parameter

        self.fields[
            "status"
        ].choices = BatchTestResult.Status.choices

        apply_field_classes(self)

    def clean_parameter(self):
        parameter = self.cleaned_data.get(
            "parameter"
        )

        if parameter is None:
            raise ValidationError(
                "An analytical parameter is required."
            )

        if self.batch is not None:
            if (
                parameter.chemical_id
                != self.batch.chemical_id
            ):
                raise ValidationError(
                    "The selected parameter does not belong to the batch chemical."
                )

            if (
                self.batch.treatment_plant_id
                and parameter.treatment_plant_id
                != self.batch.treatment_plant_id
            ):
                raise ValidationError(
                    "The selected parameter is not configured for this treatment plant."
                )

        if (
            self.selected_parameter is not None
            and parameter.pk
            != self.selected_parameter.pk
        ):
            raise ValidationError(
                "The selected parameter is not the current required parameter."
            )

        return parameter

    def clean_value(self):
        value = self.cleaned_data.get(
            "value"
        )

        if value is not None:
            try:
                float(value)
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValidationError(
                    "The analytical value must be numeric."
                ) from exc

        return value

    def clean(self):
        cleaned = super().clean()

        parameter = cleaned.get(
            "parameter"
        )
        value = cleaned.get(
            "value"
        )
        textual = (
            cleaned.get("textual_result")
            or ""
        ).strip()
        status = cleaned.get(
            "status"
        )

        if (
            self.analyst is None
        ):
            raise ValidationError(
                "An analyst is required to record an analytical result."
            )

        if not self.analyst.is_active:
            raise ValidationError(
                "An inactive user cannot record an analytical result."
            )

        if self.process is not None:
            self.process.refresh_assigned_analysts()

            if not self.process.is_authorized_analyst(
                self.analyst
            ):
                raise ValidationError(
                    "The analyst recording this result is not currently "
                    "assigned to this chemical analysis through the weekly duty schedule."
                )
        elif self.batch is not None:
            analysis_request = getattr(
                self.batch,
                "analysis_request",
                None,
            )

            if analysis_request is not None:
                analysis_request.populate_assigned_analysts()

                if not analysis_request.is_assigned_analyst(
                    self.analyst
                ):
                    raise ValidationError(
                        "The analyst recording this result is not currently "
                        "assigned to this chemical analysis through the weekly duty schedule."
                    )

        if status in (
            BatchTestResult.Status.PASS,
            BatchTestResult.Status.FAIL,
        ) and value is None and not textual:
            raise ValidationError(
                "A numerical or textual analytical result is required."
            )

        if (
            status == BatchTestResult.Status.NA
            and value is not None
        ):
            self.add_error(
                "value",
                "Not Applicable results cannot contain a numerical value.",
            )

        if parameter and value is not None:
            if (
                parameter.min_limit is not None
                and value < parameter.min_limit
                and status == BatchTestResult.Status.PASS
            ):
                self.add_error(
                    "status",
                    "The result is below the configured minimum specification limit.",
                )

            if (
                parameter.max_limit is not None
                and value > parameter.max_limit
                and status == BatchTestResult.Status.PASS
            ):
                self.add_error(
                    "status",
                    "The result is above the configured maximum specification limit.",
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False,
        )

        if self.batch is not None:
            instance.batch = self.batch

        if self.analyst is not None:
            instance.analyst = self.analyst

        instance.tested_at = timezone.now()

        if commit:
            instance.save()

        return instance


class ChemicalAnalysisInputForm(forms.ModelForm):
    class Meta:
        model = ChemicalAnalysisInput
        fields = (
            "test_result",
            "inputs",
        )
        widgets = {
            "inputs": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": (
                        '{"mass1": 5.0, "mass2": 5.2, '
                        '"mass3": 5.1, "volume": 10.0}'
                    ),
                }
            )
        }

    def __init__(
        self,
        *args,
        test_result=None,
        **kwargs,
    ):
        self.selected_test_result = test_result

        super().__init__(*args, **kwargs)

        if test_result is not None:
            self.fields[
                "test_result"
            ].queryset = BatchTestResult.objects.filter(
                pk=test_result.pk,
            )
            self.initial[
                "test_result"
            ] = test_result.pk

        apply_field_classes(self)

    def clean_inputs(self):
        value = self.cleaned_data.get(
            "inputs"
        )

        if isinstance(value, dict):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as exc:
                raise ValidationError(
                    "Enter valid JSON containing the analysis input values."
                ) from exc
        else:
            raise ValidationError(
                "Analysis inputs must be supplied as a JSON object."
            )

        if not isinstance(parsed, dict):
            raise ValidationError(
                "Analysis inputs must be a JSON object."
            )

        if not parsed:
            raise ValidationError(
                "At least one analytical input is required."
            )

        return parsed

    def clean(self):
        cleaned = super().clean()

        result = cleaned.get(
            "test_result"
        )
        inputs = cleaned.get(
            "inputs"
        ) or {}

        if result is None:
            return cleaned

        parameter = result.parameter
        method = getattr(
            parameter,
            "method",
            None,
        )

        if method is not None:
            fields = method.get_input_fields() or []

            if isinstance(fields, str):
                fields = [
                    item.strip()
                    for item in fields.split(",")
                    if item.strip()
                ]

            missing = [
                field
                for field in fields
                if field not in inputs
            ]

            if missing:
                raise ValidationError(
                    "Missing required analytical inputs: "
                    + ", ".join(missing)
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(
            commit=False,
        )

        if self.selected_test_result is not None:
            instance.test_result = (
                self.selected_test_result
            )

        if commit:
            instance.save()

        return instance


class DynamicChemicalAnalysisInputForm(forms.Form):
    def __init__(
        self,
        *args,
        test_result=None,
        **kwargs,
    ):
        self.test_result = test_result

        super().__init__(*args, **kwargs)

        method = getattr(
            getattr(
                test_result,
                "parameter",
                None,
            ),
            "method",
            None,
        )

        if method is not None:
            definitions = _normalise_input_definitions(
                method.get_input_fields()
                if hasattr(
                    method,
                    "get_input_fields",
                )
                else []
            )

            for definition in definitions:
                name = definition["name"]
                label = definition["label"]

                field_type = str(
                    definition.get(
                        "type",
                        "number",
                    )
                ).lower()

                if field_type in {
                    "text",
                    "string",
                }:
                    field = forms.CharField(
                        required=definition["required"],
                        label=label,
                    )
                elif field_type in {
                    "integer",
                    "int",
                }:
                    field = forms.IntegerField(
                        required=definition["required"],
                        label=label,
                    )
                else:
                    field = forms.DecimalField(
                        required=definition["required"],
                        label=label,
                        max_digits=16,
                        decimal_places=6,
                    )

                if (
                    field_type
                    not in {
                        "text",
                        "string",
                    }
                ):
                    field.widget = forms.NumberInput(
                        attrs={
                            "step": "any",
                            "placeholder": label,
                        }
                    )

                self.fields[
                    name
                ] = field

        apply_field_classes(self)

    @staticmethod
    def _labelize(value: str) -> str:
        return (
            value
            .replace("_", " ")
            .strip()
            .title()
        )

    def as_input_dictionary(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.cleaned_data.items()
            if value is not None
        }


class StartAnalysisForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm that analysis is ready to start",
    )

    def __init__(
        self,
        *args,
        process=None,
        user=None,
        **kwargs,
    ):
        self.process = process
        self.user = user

        super().__init__(*args, **kwargs)

        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        if self.user is None:
            raise ValidationError(
                "An authenticated analyst is required to start the analysis."
            )

        if not self.user.is_active:
            raise ValidationError(
                "An inactive user cannot start a chemical analysis."
            )

        if self.process is None:
            raise ValidationError(
                "The chemical analysis process is required."
            )

        self.process.refresh_assigned_analysts()

        if not self.process.is_authorized_analyst(
            self.user
        ):
            raise ValidationError(
                "You are not currently assigned to this chemical analysis "
                "through the weekly duty schedule."
            )

        return cleaned


class CompleteAnalysisForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm that all required analytical tests are complete",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Analysis completion remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        process=None,
        user=None,
        **kwargs,
    ):
        self.process = process
        self.user = user

        super().__init__(*args, **kwargs)

        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        if self.user is None:
            raise ValidationError(
                "An authenticated analyst is required to complete the analysis."
            )

        if not self.user.is_active:
            raise ValidationError(
                "An inactive user cannot complete a chemical analysis."
            )

        if self.process is None:
            raise ValidationError(
                "The chemical analysis process is required."
            )

        self.process.refresh_assigned_analysts()

        if not self.process.is_authorized_analyst(
            self.user
        ):
            raise ValidationError(
                "You are not currently assigned to this chemical analysis "
                "through the weekly duty schedule."
            )

        return cleaned


class QAReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(
            ("PASS", "Accept analysis"),
            ("REWORK", "Return for rework"),
            ("CAPA", "Require CAPA"),
            ("REJECT", "Reject analysis"),
        )
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "QA review findings and remarks",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm QA review decision",
    )

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        self.user = user
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        decision = cleaned.get(
            "decision"
        )
        remarks = (
            cleaned.get("remarks")
            or ""
        ).strip()

        if (
            decision in {
                "REWORK",
                "CAPA",
                "REJECT",
            }
            and not remarks
        ):
            self.add_error(
                "remarks",
                "Remarks are required for this QA decision.",
            )

        if (
            self.user is not None
            and not self.user.is_active
        ):
            raise ValidationError(
                "An inactive user cannot perform QA review."
            )

        return cleaned


class ApprovalForm(forms.Form):
    decision = forms.ChoiceField(
        choices=(
            ("APPROVE", "Approve"),
            ("REJECT", "Reject"),
        )
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Approval or rejection remarks",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="I confirm this approval decision",
    )

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        self.user = user
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean(self):
        cleaned = super().clean()

        decision = cleaned.get(
            "decision"
        )
        remarks = (
            cleaned.get("remarks")
            or ""
        ).strip()

        if (
            decision == "REJECT"
            and not remarks
        ):
            self.add_error(
                "remarks",
                "A rejection reason is required.",
            )

        if (
            self.user is not None
            and not self.user.is_active
        ):
            raise ValidationError(
                "An inactive user cannot approve a chemical analysis."
            )

        return cleaned


class RejectAnalysisForm(forms.Form):
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Reason for rejection",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm rejection",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)

    def clean_reason(self):
        value = (
            self.cleaned_data
            .get("reason")
            or ""
        ).strip()

        if not value:
            raise ValidationError(
                "A rejection reason is required."
            )

        return value


class RetestForm(forms.Form):
    parameter = forms.ModelChoiceField(
        queryset=ChemicalSpecification.objects.none(),
        empty_label="Select parameter",
    )
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Reason for retesting",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm retest request",
    )

    def __init__(
        self,
        *args,
        process=None,
        **kwargs,
    ):
        self.process = process

        super().__init__(*args, **kwargs)

        if process is not None:
            self.fields[
                "parameter"
            ].queryset = (
                process
                .required_specifications()
                .select_related(
                    "chemical",
                    "method",
                )
            )

        apply_field_classes(self)

    def clean_parameter(self):
        parameter = self.cleaned_data.get(
            "parameter"
        )

        if parameter is None:
            raise ValidationError(
                "An analytical parameter is required."
            )

        if self.process is not None:
            if not (
                self.process
                .required_specifications()
                .filter(
                    pk=parameter.pk,
                )
                .exists()
            ):
                raise ValidationError(
                    "The selected parameter is not required for this analysis."
                )

        return parameter


class CAPAForm(forms.Form):
    corrective_action = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Corrective action",
            }
        ),
    )
    preventive_action = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": "Preventive action",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm CAPA submission",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class CoAGenerationForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm generation of the Certificate of Analysis",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class CoAApprovalForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm approval of the Certificate of Analysis",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Approval remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        user=None,
        **kwargs,
    ):
        self.user = user

        super().__init__(*args, **kwargs)

        apply_field_classes(self)

    def clean_confirm(self):
        value = self.cleaned_data.get(
            "confirm"
        )

        if not value:
            raise ValidationError(
                "CoA approval must be explicitly confirmed."
            )

        if (
            self.user is not None
            and not self.user.is_active
        ):
            raise ValidationError(
                "An inactive user cannot approve a CoA."
            )

        return value


class ConfirmActionForm(forms.Form):
    action = forms.ChoiceField(
        choices=(
            ("UTILIZE", "Utilize batch"),
            ("RETURN", "Return to supplier"),
        ),
        widget=forms.Select(),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm this workflow action",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Disposition remarks",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_field_classes(self)


class BatchStatusTransitionForm(forms.Form):
    target_status = forms.ChoiceField(
        choices=(),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Transition remarks",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm status transition",
    )

    def __init__(
        self,
        *args,
        batch=None,
        **kwargs,
    ):
        self.batch = batch

        super().__init__(*args, **kwargs)

        if batch is not None:
            labels = dict(
                ChemicalBatch.Status.choices
            )

            self.fields[
                "target_status"
            ].choices = [
                (
                    status,
                    labels.get(
                        status,
                        status,
                    ),
                )
                for status in batch.batch_transitions.get(
                    batch.status,
                    [],
                )
            ]

        apply_field_classes(self)

    def clean_target_status(self):
        target = self.cleaned_data.get(
            "target_status"
        )

        if (
            self.batch is not None
            and not self.batch.can_transition_to(
                target
            )
        ):
            raise ValidationError(
                f"The batch cannot transition from "
                f"{self.batch.status} to {target}."
            )

        return target


class RequestStatusTransitionForm(forms.Form):
    target_status = forms.ChoiceField(
        choices=(),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm analysis request transition",
    )

    def __init__(
        self,
        *args,
        request=None,
        **kwargs,
    ):
        self.analysis_request = request

        super().__init__(*args, **kwargs)

        if request is not None:
            labels = dict(
                ChemicalAnalysisRequest.Status.choices
            )

            self.fields[
                "target_status"
            ].choices = [
                (
                    status,
                    labels.get(
                        status,
                        status,
                    ),
                )
                for status in request.request_transitions.get(
                    request.status,
                    (),
                )
            ]

        apply_field_classes(self)

    def clean_target_status(self):
        target = self.cleaned_data.get(
            "target_status"
        )

        if (
            self.analysis_request is not None
            and not self.analysis_request.can_transition_to(
                target
            )
        ):
            raise ValidationError(
                f"The analysis request cannot transition from "
                f"{self.analysis_request.status} to {target}."
            )

        return target


class ChemicalProcessActionForm(forms.Form):
    ACTION_CHOICES = (
        ("START_ANALYSIS", "Start analysis"),
        ("COMPLETE_ANALYSIS", "Complete analysis"),
        ("SEND_TO_QA", "Send to QA"),
        ("APPROVE", "Approve"),
        ("REJECT", "Reject"),
        ("RETEST", "Request retest"),
        ("CAPA", "Initiate CAPA"),
    )

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Workflow remarks",
            }
        ),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm workflow action",
    )

    def __init__(
        self,
        *args,
        process=None,
        available_actions=None,
        **kwargs,
    ):
        self.process = process

        super().__init__(*args, **kwargs)

        if available_actions is not None:
            labels = dict(
                self.ACTION_CHOICES
            )

            self.fields[
                "action"
            ].choices = [
                (
                    action,
                    labels.get(
                        action,
                        action.replace(
                            "_",
                            " ",
                        ).title(),
                    ),
                )
                for action in available_actions
            ]

        apply_field_classes(self)

    def clean_action(self):
        action = self.cleaned_data.get(
            "action"
        )

        if (
            self.process is not None
            and self.process.status
            == ChemicalAnalysisProcess.WorkflowStatus.COMPLETED
        ):
            raise ValidationError(
                "No further workflow actions are available after completion."
            )

        return action


class ChemicalDashboardActionForm(forms.Form):
    ACTION_CHOICES = (
        ("start_analysis", "Start analysis"),
        ("complete_analysis", "Complete analysis"),
        ("complete_checklist", "Complete checklist"),
        ("complete_sampling", "Complete sampling"),
        ("request_retest", "Request retest"),
        ("qa_review", "QA review"),
        ("capa", "CAPA"),
        ("approve", "Approve"),
        ("reject", "Reject"),
        ("utilize", "Utilize"),
        ("return", "Return to supplier"),
    )

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
    )
    process_id = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm action",
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Action remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        available_actions=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if available_actions is not None:
            available = set(
                available_actions
            )

            self.fields[
                "action"
            ].choices = [
                choice
                for choice in self.ACTION_CHOICES
                if choice[0] in available
            ]

        apply_field_classes(self)


class UtilizationForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm that the approved chemical batch is being utilized",
    )
    quantity_used = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "step": "any",
            }
        ),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Utilization remarks",
            }
        ),
    )

    def __init__(
        self,
        *args,
        batch=None,
        **kwargs,
    ):
        self.batch = batch

        super().__init__(*args, **kwargs)

        apply_field_classes(self)

    def clean_quantity_used(self):
        quantity = self.cleaned_data.get(
            "quantity_used"
        )

        if (
            quantity is not None
            and self.batch is not None
            and quantity > self.batch.quantity_received
        ):
            raise ValidationError(
                "Quantity utilized cannot exceed the quantity received."
            )

        return quantity


class ReturnToSupplierForm(forms.Form):
    confirm = forms.BooleanField(
        required=True,
        label="Confirm return of the chemical batch to supplier",
    )
    quantity_returned = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(
            attrs={
                "step": "any",
            }
        ),
    )
    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Reason for return to supplier",
            }
        ),
    )

    def __init__(
        self,
        *args,
        batch=None,
        **kwargs,
    ):
        self.batch = batch

        super().__init__(*args, **kwargs)

        apply_field_classes(self)

    def clean_quantity_returned(self):
        quantity = self.cleaned_data.get(
            "quantity_returned"
        )

        if (
            quantity is not None
            and self.batch is not None
            and quantity > self.batch.quantity_received
        ):
            raise ValidationError(
                "Quantity returned cannot exceed the quantity received."
            )

        return quantity


class ChemicalSpecificationFilterForm(forms.Form):
    chemical = forms.ModelChoiceField(
        queryset=Chemical.objects.all(),
        required=False,
        empty_label="All chemicals",
    )
    treatment_plant = forms.ModelChoiceField(
        queryset=TreatmentPlant.objects.none(),
        required=False,
        empty_label="All treatment plants",
    )
    required_only = forms.BooleanField(
        required=False,
        initial=True,
        label="Required specifications only",
    )

    def __init__(
        self,
        *args,
        treatment_plant=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields[
            "treatment_plant"
        ].queryset = TreatmentPlant.objects.order_by(
            "name",
        )

        self.fields[
            "chemical"
        ].queryset = Chemical.objects.order_by(
            "name",
        )

        if treatment_plant is not None:
            self.fields[
                "treatment_plant"
            ].initial = treatment_plant

        apply_field_classes(self)


class TestResultFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "All statuses"),
            *BatchTestResult.Status.choices,
        ),
    )
    parameter = forms.ModelChoiceField(
        queryset=ChemicalSpecification.objects.none(),
        required=False,
        empty_label="All parameters",
    )
    analyst = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="All analysts",
    )

    def __init__(
        self,
        *args,
        treatment_plant=None,
        section=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields[
            "analyst"
        ].queryset = scoped_user_queryset(
            treatment_plant,
            section=section,
        )

        self.fields[
            "parameter"
        ].queryset = (
            ChemicalSpecification.objects
            .select_related(
                "chemical",
                "treatment_plant",
            )
            .order_by(
                "chemical__name",
                "parameter_name",
                "version",
            )
        )

        apply_field_classes(self)


class ProcessFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "All workflow states"),
            *ChemicalAnalysisProcess.WorkflowStatus.choices,
        ),
    )
    analyst = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="All analysts",
    )
    qa_officer = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="All QA officers",
    )
    overdue_only = forms.BooleanField(
        required=False,
        label="Overdue only",
    )

    def __init__(
        self,
        *args,
        treatment_plant=None,
        section=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        users = scoped_user_queryset(
            treatment_plant,
            section=section,
        )

        self.fields[
            "analyst"
        ].queryset = users

        self.fields[
            "qa_officer"
        ].queryset = users

        apply_field_classes(self)


class ChemicalCertApproverForm(forms.Form):
    approver = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=True,
        empty_label="Select certificate approver",
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirm certificate approval assignment",
    )

    def __init__(
        self,
        *args,
        treatment_plant=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.fields[
            "approver"
        ].queryset = approver_queryset(
            treatment_plant=treatment_plant,
        )

        apply_field_classes(self)

    def clean_approver(self):
        approver = self.cleaned_data.get(
            "approver"
        )

        if approver is None:
            raise ValidationError(
                "A certificate approver is required."
            )

        if not approver.is_active:
            raise ValidationError(
                "An inactive user cannot approve a certificate."
            )

        if not (
            approver.has_perm(
                "ca.approve_chemical_coa"
            )
            or approver.has_perm(
                "ca.approve_chemical_batch"
            )
        ):
            raise ValidationError(
                "The selected user does not have the required "
                "chemical certificate approval permission."
            )

        return approver