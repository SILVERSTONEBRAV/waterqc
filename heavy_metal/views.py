from django.shortcuts import render

# Create your views here.
# heavy_metal/views.py
from django.urls import reverse
from django.db.models import Prefetch
from core.views import NAMUBUYA_ListView, NAMUBUYA_CreateView, NAMUBUYA_UpdateView, NAMUBUYA_DeleteView, NAMUBUYA_DetailView
from .models import (
    HeavyMetalSamplingSchedule,
    HeavyMetalSamplingTime,
    HeavyMetalAnalysis,
    HeavyMetalParameter,
    Cause,
    HeavyMetalNonConformity,
    HeavyMetalNonConformityLog,
    HeavyMetalAnalysisLog,
)


# ==================================================
# 🔹 HEAVY METAL SAMPLING SCHEDULE
# ==================================================
class HeavyMetalSamplingScheduleListView(NAMUBUYA_ListView):
    model = HeavyMetalSamplingSchedule
    table_fields = ["start_time", "interval_minutes", "enabled", "adaptive", "last_auto_update"]
    create_url_name = "heavymetal:schedule_create"
    edit_url_name = "heavymetal:schedule_update"
    delete_url_name = "heavymetal:schedule_delete"
    search_fields = ["start_time"]
    bulk_actions = ["delete"]


class HeavyMetalSamplingScheduleCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalSamplingSchedule
    success_url_name = "heavymetal:schedule_list"


class HeavyMetalSamplingScheduleUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalSamplingSchedule
    success_url_name = "heavymetal:schedule_list"


class HeavyMetalSamplingScheduleDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalSamplingSchedule
    success_url = "/heavymetal/schedules/"


# ==================================================
# 🔹 HEAVY METAL SAMPLING TIME
# ==================================================
class HeavyMetalSamplingTimeListView(NAMUBUYA_ListView):
    model = HeavyMetalSamplingTime
    table_fields = ["schedule", "time"]
    create_url_name = "heavymetal:time_create"
    edit_url_name = "heavymetal:time_update"
    delete_url_name = "heavymetal:time_delete"
    search_fields = ["time"]
    bulk_actions = ["delete"]
    select_related_fields = ["schedule"]


class HeavyMetalSamplingTimeCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalSamplingTime
    success_url_name = "heavymetal:time_list"


class HeavyMetalSamplingTimeUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalSamplingTime
    success_url_name = "heavymetal:time_list"


class HeavyMetalSamplingTimeDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalSamplingTime
    success_url = "/heavymetal/times/"


# ==================================================
# 🔹 HEAVY METAL ANALYSIS
# ==================================================
class HeavyMetalAnalysisListView(NAMUBUYA_ListView):
    model = HeavyMetalAnalysis
    table_fields = [
        "reference_id", "treatment_plant", "treatment_plant_phase", "shift",
        "sampling_time", "analysis_date", "state", "analysed_by", "verified_by", "approved_by"
    ]
    create_url_name = "heavymetal:analysis_create"
    edit_url_name = "heavymetal:analysis_update"
    delete_url_name = "heavymetal:analysis_delete"
    detail_url_name = "heavymetal:analysis_detail"
    search_fields = ["reference_id"]
    bulk_actions = ["delete"]
    select_related_fields = ["treatment_plant", "treatment_plant_phase", "shift", "sampling_time", "analysed_by", "verified_by", "approved_by"]
    prefetch_related_fields = ["parameters", "nonconformities", "logs"]


class HeavyMetalAnalysisCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalAnalysis
    success_url_name = "heavymetal:analysis_list"


class HeavyMetalAnalysisUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalAnalysis
    success_url_name = "heavymetal:analysis_list"


class HeavyMetalAnalysisDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalAnalysis
    success_url = "/heavymetal/analyses/"


class HeavyMetalAnalysisDetailView(NAMUBUYA_DetailView):
    model = HeavyMetalAnalysis
    select_related_fields = ["treatment_plant", "treatment_plant_phase", "shift", "sampling_time", "analysed_by", "verified_by", "approved_by"]
    prefetch_related_fields = ["parameters", "nonconformities", "logs"]


# ==================================================
# 🔹 HEAVY METAL PARAMETERS
# ==================================================
class HeavyMetalParameterListView(NAMUBUYA_ListView):
    model = HeavyMetalParameter
    table_fields = ["analysis", "parameter", "value", "manually_editable"]
    search_fields = ["parameter__parameter__name"]
    bulk_actions = ["delete"]
    select_related_fields = ["analysis", "parameter"]


class HeavyMetalParameterCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalParameter
    success_url_name = "heavymetal:parameter_list"


class HeavyMetalParameterUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalParameter
    success_url_name = "heavymetal:parameter_list"


class HeavyMetalParameterDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalParameter
    success_url = "/heavymetal/parameters/"


# ==================================================
# 🔹 NONCONFORMITIES / CAUSES
# ==================================================
class CauseListView(NAMUBUYA_ListView):
    model = Cause
    table_fields = ["name", "description", "created_by"]
    search_fields = ["name"]
    bulk_actions = ["delete"]
    select_related_fields = ["created_by"]


class CauseCreateView(NAMUBUYA_CreateView):
    model = Cause
    success_url_name = "heavymetal:cause_list"


class CauseUpdateView(NAMUBUYA_UpdateView):
    model = Cause
    success_url_name = "heavymetal:cause_list"


class CauseDeleteView(NAMUBUYA_DeleteView):
    model = Cause
    success_url = "/heavymetal/causes/"


class HeavyMetalNonConformityListView(NAMUBUYA_ListView):
    model = HeavyMetalNonConformity
    table_fields = ["analysis", "parameter_name", "observed_value", "status", "resolved_at", "risk_score"]
    search_fields = ["parameter_name"]
    bulk_actions = ["delete"]
    select_related_fields = ["analysis", "triggered_by", "reviewed_by"]
    prefetch_related_fields = ["causes"]


class HeavyMetalNonConformityCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalNonConformity
    success_url_name = "heavymetal:nonconformity_list"


class HeavyMetalNonConformityUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalNonConformity
    success_url_name = "heavymetal:nonconformity_list"


class HeavyMetalNonConformityDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalNonConformity
    success_url = "/heavymetal/nonconformities/"


# ==================================================
# 🔹 NONCONFORMITY LOGS
# ==================================================
class HeavyMetalNonConformityLogListView(NAMUBUYA_ListView):
    model = HeavyMetalNonConformityLog
    table_fields = ["nonconformity", "actor", "action", "remarks", "auto_generated", "created_at"]
    select_related_fields = ["nonconformity", "actor"]
    bulk_actions = ["delete"]


class HeavyMetalNonConformityLogCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalNonConformityLog
    success_url_name = "heavymetal:nonconformitylog_list"


class HeavyMetalNonConformityLogUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalNonConformityLog
    success_url_name = "heavymetal:nonconformitylog_list"


class HeavyMetalNonConformityLogDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalNonConformityLog
    success_url = "/heavymetal/nonconformitylogs/"


# ==================================================
# 🔹 ANALYSIS LOGS
# ==================================================
class HeavyMetalAnalysisLogListView(NAMUBUYA_ListView):
    model = HeavyMetalAnalysisLog
    table_fields = ["analysis", "actor", "action", "remarks", "auto_generated", "created_at"]
    select_related_fields = ["analysis", "actor"]
    bulk_actions = ["delete"]


class HeavyMetalAnalysisLogCreateView(NAMUBUYA_CreateView):
    model = HeavyMetalAnalysisLog
    success_url_name = "heavymetal:analysislog_list"


class HeavyMetalAnalysisLogUpdateView(NAMUBUYA_UpdateView):
    model = HeavyMetalAnalysisLog
    success_url_name = "heavymetal:analysislog_list"


class HeavyMetalAnalysisLogDeleteView(NAMUBUYA_DeleteView):
    model = HeavyMetalAnalysisLog
    success_url = "/heavymetal/analysislogs/"
