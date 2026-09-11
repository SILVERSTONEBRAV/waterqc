from typing import Optional, List, Dict, Any
from django import forms
from django.forms import modelform_factory
from django.core.exceptions import ValidationError
from django.db import models

from accounts.entities import EntityDefinition


class DynamicEntityFormFactory:
    """
    Factory responsible for generating ModelForms dynamically
    from EntityDefinition metadata.

    Supports:
    - Conditional read-only fields
    - Inline editing (single-field forms)
    - Bulk update forms
    - Per-entity overrides
    """

    @staticmethod
    def build_form(
        *,
        entity: EntityDefinition,
        instance: Optional[models.Model] = None,
        data=None,
        files=None,
        readonly: bool = False,
        inline_field: Optional[str] = None,
        bulk: bool = False,
    ) -> forms.ModelForm:
        """
        Build a ModelForm dynamically for an entity.

        Args:
            entity: EntityDefinition
            instance: model instance (if update)
            data: POST data
            files: FILES data
            readonly: force readonly mode
            inline_field: restrict form to a single field (inline edit)
            bulk: bulk update mode

        Returns:
            Django ModelForm instance
        """

        fields = DynamicEntityFormFactory._resolve_fields(
            entity=entity,
            instance=instance,
            readonly=readonly,
            inline_field=inline_field,
            bulk=bulk,
        )

        FormClass = modelform_factory(
            entity.model,
            fields=fields,
            form=DynamicEntityBaseForm,
        )

        return FormClass(
            data=data,
            files=files,
            instance=instance,
            entity=entity,
            readonly=readonly,
            inline_field=inline_field,
            bulk=bulk,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _resolve_fields(
        *,
        entity: EntityDefinition,
        instance: Optional[models.Model],
        readonly: bool,
        inline_field: Optional[str],
        bulk: bool,
    ) -> List[str]:
        """
        Decide which fields should be included.
        """

        resolved_fields: List[str] = []

        for f in entity.fields:
            # Skip read-only fields
            if f.read_only:
                continue

            # Conditional read-only
            if instance and f.conditionally_read_only and f.conditionally_read_only(instance):
                continue

            # Inline editing: only one field
            if inline_field and f.name != inline_field:
                continue

            # Bulk updates: only explicitly allowed fields
            if bulk and not f.allow_bulk:
                continue

            resolved_fields.append(f.name)

        if not resolved_fields:
            raise ValidationError("No editable fields available.")

        return resolved_fields


# ======================================================================
# Base Form Class
# ======================================================================
class DynamicEntityBaseForm(forms.ModelForm):
    """
    Base class injected into all dynamic entity forms.

    Handles:
    - Permission enforcement
    - Read-only rendering
    - Inline edit validation
    """

    def __init__(
        self,
        *args,
        entity: EntityDefinition,
        readonly: bool = False,
        inline_field: Optional[str] = None,
        bulk: bool = False,
        **kwargs,
    ):
        self.entity = entity
        self.readonly = readonly
        self.inline_field = inline_field
        self.bulk = bulk

        super().__init__(*args, **kwargs)

        self._apply_readonly()
        self._apply_inline_constraints()
        self._apply_bulk_constraints()

    # ------------------------------------------------------------------
    # Read-only handling
    # ------------------------------------------------------------------
    def _apply_readonly(self):
        if not self.readonly:
            return

        for field in self.fields.values():
            field.disabled = True
            field.required = False

    # ------------------------------------------------------------------
    # Inline edit constraints
    # ------------------------------------------------------------------
    def _apply_inline_constraints(self):
        if not self.inline_field:
            return

        for name, field in self.fields.items():
            if name != self.inline_field:
                field.widget = forms.HiddenInput()
                field.required = False

    # ------------------------------------------------------------------
    # Bulk update constraints
    # ------------------------------------------------------------------
    def _apply_bulk_constraints(self):
        if not self.bulk:
            return

        # In bulk mode, fields are optional
        for field in self.fields.values():
            field.required = False

    # ------------------------------------------------------------------
    # Validation hooks
    # ------------------------------------------------------------------
    def clean(self):
        cleaned = super().clean()

        # Entity-level validation hook
        if self.entity.form_validator:
            self.entity.form_validator(
                cleaned_data=cleaned,
                instance=self.instance,
                form=self,
            )

        return cleaned

    # ------------------------------------------------------------------
    # Save override
    # ------------------------------------------------------------------
    def save(self, commit=True):
        instance = super().save(commit=False)

        # Entity-level pre-save hook
        if self.entity.before_save:
            self.entity.before_save(
                instance=instance,
                cleaned_data=self.cleaned_data,
                form=self,
            )

        if commit:
            instance.save()

            # Entity-level post-save hook
            if self.entity.after_save:
                self.entity.after_save(
                    instance=instance,
                    cleaned_data=self.cleaned_data,
                    form=self,
                )

        return instance


# ======================================================================
# Bulk Action Helper
# ======================================================================
class BulkEntityForm(forms.Form):
    """
    Generic bulk action form (delete / update / toggle).
    """

    ids = forms.CharField(help_text="Comma-separated IDs")
    action = forms.CharField()

    def clean_ids(self):
        raw = self.cleaned_data["ids"]
        try:
            return [int(pk) for pk in raw.split(",") if pk.strip()]
        except ValueError:
            raise ValidationError("Invalid IDs format")
