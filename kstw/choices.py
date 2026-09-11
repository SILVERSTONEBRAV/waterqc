from django.db import models

class WaterAnalysisState(models.TextChoices):
    NEW = "NEW", "New"
    ANALYSED = "ANALYSED", "Analysed"
    VERIFIED = "VERIFIED", "Verified"
    CONFIRMED = "CONFIRMED", "Confirmed"
    APPROVED = "APPROVED", "Approved"

STATE_TRANSITIONS = {
    WaterAnalysisState.NEW: [WaterAnalysisState.ANALYSED],
    WaterAnalysisState.ANALYSED: [WaterAnalysisState.VERIFIED],
    WaterAnalysisState.VERIFIED: [WaterAnalysisState.CONFIRMED],
    WaterAnalysisState.CONFIRMED: [WaterAnalysisState.APPROVED],
    WaterAnalysisState.APPROVED: [],
}

STATE_PERMISSIONS = {
    WaterAnalysisState.ANALYSED: "can_analyse",
    WaterAnalysisState.VERIFIED: "can_verify",
    WaterAnalysisState.CONFIRMED: "can_confirm",
    WaterAnalysisState.APPROVED: "can_approve",
}

STATE_USER_FIELD = {
    WaterAnalysisState.ANALYSED: "analysed_by",
    WaterAnalysisState.VERIFIED: "verified_by",
    WaterAnalysisState.CONFIRMED: "confirmed_by",
    WaterAnalysisState.APPROVED: "approved_by",
}
