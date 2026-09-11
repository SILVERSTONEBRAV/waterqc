from django.urls import path
from core.views import (
    NAMUBUYA_ListView,
    NAMUBUYA_DetailView,
    NAMUBUYA_CreateView,
    NAMUBUYA_UpdateView,
    NAMUBUYA_DeleteView,
    NAMUBUYA_RowView,
    NAMUBUYA_DrillDownView
)
from core.platform import PLATFORM_MODELS

urlpatterns = []

for key, meta in PLATFORM_MODELS.items():
    model = meta["model"]
    app = model._meta.app_label
    name = model._meta.model_name

    urlpatterns += [
        path(f"{app}/{name}/", NAMUBUYA_ListView.as_view(model=model), name=f"{name}_list"),
        path(f"{app}/{name}/add/", NAMUBUYA_CreateView.as_view(model=model), name=f"{name}_create"),
        path(f"{app}/{name}/<int:pk>/", NAMUBUYA_DetailView.as_view(model=model), name=f"{name}_detail"),
        path(f"{app}/{name}/<int:pk>/edit/", NAMUBUYA_UpdateView.as_view(model=model), name=f"{name}_update"),
        path(f"{app}/{name}/<int:pk>/delete/", NAMUBUYA_DeleteView.as_view(model=model), name=f"{name}_delete"),
        path(f"{app}/{name}/<int:pk>/row/", NAMUBUYA_RowView.as_view(model=model), name=f"{name}_row"),
        path(f"{app}/{name}/<int:pk>/drilldown/", NAMUBUYA_DrillDownView.as_view(model=model), name=f"{name}_drilldown"),
    ]
