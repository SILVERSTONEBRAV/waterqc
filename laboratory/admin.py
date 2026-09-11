from django.contrib import admin
from .models import Laboratory

@admin.register(Laboratory)
class LaboratoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'treatment_plant', 'created_at')
    search_fields = ('name', 'treatment_plant__name')
