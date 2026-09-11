# analysis/data_analysis.py
import numpy as np
import pandas as pd
from scipy.stats import ttest_ind, chi2_contingency, mannwhitneyu, kruskal
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, silhouette_score
from sklearn.ensemble import GradientBoostingRegressor
from .models import (
    ClarifiedWaterAnalysis, CoagulatedWaterAnalysis, FilteredWaterAnalysis,
    RawWaterAnalysis, TreatedWaterAnalysis, HeavyMetalWaterSample, MicrobialAnalysis
)

def fetch_water_data(water_type):
    if water_type == 'clarified':
        return pd.DataFrame(list(ClarifiedWaterAnalysis.objects.values()))
    elif water_type == 'coagulated':
        return pd.DataFrame(list(CoagulatedWaterAnalysis.objects.values()))
    elif water_type == 'filtered':
        return pd.DataFrame(list(FilteredWaterAnalysis.objects.values()))
    elif water_type == 'raw':
        return pd.DataFrame(list(RawWaterAnalysis.objects.values()))
    elif water_type == 'treated':
        return pd.DataFrame(list(TreatedWaterAnalysis.objects.values()))
    elif water_type == 'heavy_metal':
        return pd.DataFrame(list(HeavyMetalWaterSample.objects.values()))
    elif water_type == 'microbial':
        return pd.DataFrame(list(MicrobialAnalysis.objects.values()))
    return pd.DataFrame()

def perform_statistical_tests(data):
    t_stat, p_val = ttest_ind(data['feature1'], data['feature2'])
    chi2_stat, chi2_p_val, _, _ = chi2_contingency(data[['feature1', 'feature2']])
    u_stat, u_p_val = mannwhitneyu(data['feature1'], data['feature2'])
    kw_stat, kw_p_val = kruskal(data['feature1'], data['feature2'])

    test_results = {
        't_stat': t_stat,
        'p_val': p_val,
        'chi2_stat': chi2_stat,
        'chi2_p_val': chi2_p_val,
        'u_stat': u_stat,
        'u_p_val': u_p_val,
        'kw_stat': kw_stat,
        'kw_p_val': kw_p_val,
    }
    return test_results

def perform_clustering(data):
    scaler = StandardScaler()
    scaled_data = scaler.fit_transform(data)

    kmeans = KMeans(n_clusters=3)
    clusters = kmeans.fit_predict(scaled_data)

    silhouette_avg = silhouette_score(scaled_data, clusters)

    return clusters, silhouette_avg

def perform_regression(data):
    X = data[['feature1', 'feature2']]
    y = data['target']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    model = GradientBoostingRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    regression_results = {
        'feature_importances': model.feature_importances_,
        'mean_squared_error': mean_squared_error(y_test, y_pred),
        'r2_score': r2_score(y_test, y_pred),
    }

    return regression_results, y_pred
