from django.urls import path
from core.workflow_view import WorkflowDashboardView
from core import views_cascade
from accounts.ProfileView import (
    SectionCreateView,
    SectionUpdateView,
    SectionDeleteView,
    SectionListView,
)

app_name = "core"

urlpatterns = [
    path("", WorkflowDashboardView.as_view(), name="index"),
    path("workflow/", WorkflowDashboardView.as_view(), name="workflow-dashboard"),
    path("sections/", SectionListView.as_view(), name="section_list"),
    path("sections/create/", SectionCreateView.as_view(), name="section_create"),
    path("sections/<int:pk>/edit/", SectionUpdateView.as_view(), name="section_update"),
    path("sections/<int:pk>/delete/", SectionDeleteView.as_view(), name="section_delete"),
    # Cascading filtering endpoints (Plant -> Section -> User)
    path("api/plant-sections/", views_cascade.plant_sections_api, name="api_plant_sections"),
    path("api/section-users/", views_cascade.section_users_api, name="api_section_users"),
    path("api/cascade-hierarchy/", views_cascade.cascade_hierarchy_api, name="api_cascade_hierarchy"),
]


