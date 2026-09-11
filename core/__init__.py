def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)

    for name, field in self.fields.items():

        try:
            mf = model_cls._meta.get_field(name)
        except Exception:
            continue

        # =========================
        # FK → DROPDOWN
        # =========================
        if isinstance(mf, models.ForeignKey):
            field.__class__ = forms.ModelChoiceField
            field.queryset = mf.related_model.objects.all()

        # =========================
        # M2M → MULTISELECT
        # =========================
        elif isinstance(mf, models.ManyToManyField):
            field.__class__ = forms.ModelMultipleChoiceField
            field.queryset = mf.related_model.objects.all()

        # =========================
        # CHOICES
        # =========================
        if mf.choices:
            field.choices = mf.choices

        field.required = not mf.blank
