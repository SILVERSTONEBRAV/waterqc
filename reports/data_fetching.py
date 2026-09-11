# reports/data_fetching.py
import pandas as pd
from django.apps import apps

def fetch_data_from_model(app_label, model_name):
    model = apps.get_model(app_label, model_name)
    if model:
        return pd.DataFrame(list(model.objects.values()))
    return pd.DataFrame()

def get_analysis_data(analysis_type):
    if analysis_type == 'statistical':
        return fetch_data_from_model('analysis', 'StatisticalTestResult')
    elif analysis_type == 'clustering':
        return fetch_data_from_model('analysis', 'ClusteringResult')
    elif analysis_type == 'regression':
        return fetch_data_from_model('analysis', 'RegressionResult')
    # Add other analysis types as needed
    return pd.DataFrame()
