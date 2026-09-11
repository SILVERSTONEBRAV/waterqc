# wsp/forms.py
from decimal import Decimal
from django import forms
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError
from django.db.models import Sum
from .models import (
    Survey,
    Response,
    Question,
    Option,
    ThematicArea,
    Category,
    OperationalUnit,
)


# ----------------------------------------------------------------------
# 1️⃣ Futuristic Dynamic Filter Form
# ----------------------------------------------------------------------
class UltraFilterForm(forms.Form):
    unit = forms.ModelChoiceField(
        queryset=OperationalUnit.objects.all(),
        required=False,
        label="Operational Unit",
        widget=forms.Select(
            attrs={
                "hx-get": "/dashboard/filter/",
                "hx-target": "#dashboard-content",
                "hx-trigger": "change",
                "class": "form-control futuristic-select",
            }
        ),
    )
    survey = forms.ModelChoiceField(queryset=Survey.objects.none(), required=False, label="Survey")
    category = forms.ModelChoiceField(queryset=Category.objects.all(), required=False)
    thematic_area = forms.ModelChoiceField(queryset=ThematicArea.objects.none(), required=False)

    start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    predictive_score = forms.BooleanField(
        required=False,
        label="Show Predicted Scores",
        widget=forms.CheckboxInput(attrs={"hx-get": "/dashboard/predictive/", "hx-target": "#dashboard-content"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically filter surveys and thematic areas based on selections
        if "unit" in self.data:
            try:
                unit_id = int(self.data.get("unit"))
                self.fields["survey"].queryset = Survey.objects.filter(unit_id=unit_id)
            except (ValueError, TypeError):
                self.fields["survey"].queryset = Survey.objects.none()
        if "category" in self.data:
            try:
                cat_id = int(self.data.get("category"))
                self.fields["thematic_area"].queryset = ThematicArea.objects.filter(category_id=cat_id)
            except (ValueError, TypeError):
                self.fields["thematic_area"].queryset = ThematicArea.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and start > end:
            raise ValidationError("Start date cannot be after end date.")
        return cleaned_data


# ----------------------------------------------------------------------
# 2️⃣ Ultra-Dynamic Real-Time Response Form
# ----------------------------------------------------------------------
class UltraResponseForm(forms.ModelForm):
    self_option = forms.ModelChoiceField(queryset=Option.objects.none(), required=False)
    supervisor_option = forms.ModelChoiceField(queryset=Option.objects.none(), required=False)
    inline_comment = forms.CharField(required=False, widget=forms.TextInput(attrs={"placeholder": "Add comment..."}))

    class Meta:
        model = Response
        fields = ["self_option", "supervisor_option", "inline_comment"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        question = getattr(self.instance, "question", None)
        if question:
            self.fields["self_option"].queryset = question.options.all()
            self.fields["supervisor_option"].queryset = question.options.all()
            # Ultra advanced color-coded choices with weighted visual cues
            for field_name in ["self_option", "supervisor_option"]:
                self.fields[field_name].widget.choices = [
                    (o.pk, mark_safe(
                        f'<span style="color:{o.color}; font-weight: bold;">{o.text} ({o.score})</span>'
                    ))
                    for o in self.fields[field_name].queryset
                ]
            # Add HTMX hooks for real-time update of dashboard widgets
            self.fields["self_option"].widget.attrs.update({
                "hx-post": "/response/edit/",
                "hx-target": f"#response-row-{self.instance.id}",
                "hx-swap": "outerHTML"
            })
            self.fields["supervisor_option"].widget.attrs.update({
                "hx-post": "/response/edit/",
                "hx-target": f"#response-row-{self.instance.id}",
                "hx-swap": "outerHTML"
            })

    def clean(self):
        cleaned_data = super().clean()
        for field in ["self_option", "supervisor_option"]:
            opt = cleaned_data.get(field)
            if opt and opt.score < 0:
                raise ValidationError(f"{field.replace('_',' ').title()} cannot be negative")
        return cleaned_data


# ----------------------------------------------------------------------
# 3️⃣ Futuristic Inline Question Form
# ----------------------------------------------------------------------
class UltraQuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["text", "weight", "thematic_area"]
        widgets = {
            "text": forms.Textarea(attrs={
                "rows": 2,
                "hx-post": "/question/edit/",
                "hx-target": "#question-row-{{id}}",
                "hx-swap": "outerHTML",
            }),
            "weight": forms.NumberInput(attrs={
                "step": 0.1,
                "hx-post": "/question/edit/",
                "hx-target": "#question-row-{{id}}",
                "hx-swap": "outerHTML",
            }),
        }


# ----------------------------------------------------------------------
# 4️⃣ Ultra-Dynamic Option Form
# ----------------------------------------------------------------------
class UltraOptionForm(forms.ModelForm):
    class Meta:
        model = Option
        fields = ["text", "score", "color"]
        widgets = {
            "text": forms.TextInput(attrs={
                "hx-post": "/option/edit/",
                "hx-target": "#option-row-{{id}}",
                "hx-swap": "outerHTML"
            }),
            "score": forms.NumberInput(attrs={
                "step": 0.1,
                "hx-post": "/option/edit/",
                "hx-target": "#option-row-{{id}}",
                "hx-swap": "outerHTML"
            }),
            "color": forms.TextInput(attrs={
                "type": "color",
                "hx-post": "/option/edit/",
                "hx-target": "#option-row-{{id}}",
                "hx-swap": "outerHTML"
            }),
        }


# ----------------------------------------------------------------------
# 5️⃣ Survey Progress & Real-Time Analytics Form
# ----------------------------------------------------------------------
class UltraSurveyProgressForm(forms.Form):
    survey = forms.ModelChoiceField(
        queryset=Survey.objects.all(),
        required=True,
        label="Survey",
        widget=forms.Select(attrs={
            "hx-get": "/dashboard/progress/",
            "hx-target": "#progress-bar",
            "hx-trigger": "change",
            "class": "futuristic-select"
        })
    )
    show_heatmap = forms.BooleanField(
        required=False,
        label="Show Heatmap",
        widget=forms.CheckboxInput(attrs={
            "hx-get": "/dashboard/heatmap/",
            "hx-target": "#heatmap-widget"
        })
    )
    show_trend = forms.BooleanField(
        required=False,
        label="Show Trend",
        widget=forms.CheckboxInput(attrs={
            "hx-get": "/dashboard/trend/",
            "hx-target": "#trend-widget"
        })
    )


# ----------------------------------------------------------------------
# 6️⃣ Predictive Analytics Toggle Form
# ----------------------------------------------------------------------
class PredictiveForm(forms.Form):
    enable_predictions = forms.BooleanField(
        required=False,
        label="Enable Predictive Scores",
        widget=forms.CheckboxInput(attrs={
            "hx-get": "/dashboard/predictive/",
            "hx-target": "#dashboard-content"
        })
    )
