# core/router.py

from django.urls import path
from core.registry import registry
from core.view_factory import create_crud_views


def generate_crud_urls():
    urlpatterns = []

    for item in registry.get_all():
        model = item["model"]
        config = item["config"]

        views = create_crud_views(model, config)

        app_label = model._meta.app_label
        model_name = model._meta.model_name

        base = f"{model_name}"

        urlpatterns += [
            path(f"{base}/", views["list"].as_view(), name=f"{model_name}_list"),
            path(f"{base}/create/", views["create"].as_view(), name=f"{model_name}_create"),
            path(f"{base}/<int:pk>/", views["detail"].as_view(), name=f"{model_name}_detail"),
            path(f"{base}/<int:pk>/edit/", views["update"].as_view(), name=f"{model_name}_update"),
            path(f"{base}/<int:pk>/delete/", views["delete"].as_view(), name=f"{model_name}_delete"),
        ]

    return urlpatterns
