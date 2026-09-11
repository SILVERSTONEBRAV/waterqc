from django.db import models

class AnalysisData(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    metric = models.CharField(max_length=100)
    value = models.FloatField()

class StatisticalTestResult(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    t_stat = models.FloatField()
    p_val = models.FloatField()
    chi2_stat = models.FloatField()
    chi2_p_val = models.FloatField()
    u_stat = models.FloatField()
    u_p_val = models.FloatField()
    kw_stat = models.FloatField()
    kw_p_val = models.FloatField()

class ClusteringResult(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    clusters = models.JSONField()  # Store clusters as a JSON list
    silhouette_avg = models.FloatField()

class RegressionResult(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    feature_importances = models.JSONField()  # Store feature importances as a JSON list
    mean_squared_error = models.FloatField()
    r2_score = models.FloatField()
    y_pred = models.JSONField()  # Store predictions as a JSON list

# Import models from other apps
from clarified_water.models import ClarifiedWaterAnalysis
from coagulated_water.models import CoagulatedWaterAnalysis
from filtered_water.models import FilteredWaterAnalysis
from raw_water.models import RawWaterAnalysis
from treated_water.models import TreatedWaterAnalysis
from heavy_metal_analysis.models import HeavyMetalWaterSample
from microbial.models import MicrobialAnalysis
