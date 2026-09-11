from django.db import models

class SampleType(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class AnalysisSchedule(models.Model):
    sample_type = models.ForeignKey(SampleType, on_delete=models.CASCADE)
    interval_minutes = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.sample_type.name} - {self.interval_minutes} minutes"
