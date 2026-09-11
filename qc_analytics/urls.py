from django.urls import path
from qc.views.result_card import (ResultCardEntryView,)

app_name = "qc_analytics"

urlpatterns = [
       path(
        "results/cards/",
        ResultCardEntryView.as_view(),
        name="dashboard",
    ),]


