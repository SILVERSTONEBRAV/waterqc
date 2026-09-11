import graphene
from graphene_django.types import DjangoObjectType
from .models import AnalysisData, StatisticalTestResult, ClusteringResult, RegressionResult
from .data_analysis import perform_statistical_tests, perform_clustering, perform_regression, fetch_water_data

class AnalysisDataType(DjangoObjectType):
    class Meta:
        model = AnalysisData

class StatisticalTestResultType(DjangoObjectType):
    class Meta:
        model = StatisticalTestResult

class ClusteringResultType(DjangoObjectType):
    class Meta:
        model = ClusteringResult

class RegressionResultType(DjangoObjectType):
    class Meta:
        model = RegressionResult

class Query(graphene.ObjectType):
    all_analysis_data = graphene.List(AnalysisDataType)
    statistical_test_results = graphene.Field(StatisticalTestResultType, water_type=graphene.String())
    clustering_results = graphene.Field(ClusteringResultType, water_type=graphene.String())
    regression_results = graphene.Field(RegressionResultType, water_type=graphene.String())

    def resolve_all_analysis_data(self, info):
        return AnalysisData.objects.all()

    def resolve_statistical_test_results(self, info, water_type):
        data = fetch_water_data(water_type)
        test_results = perform_statistical_tests(data)
        return StatisticalTestResult(
            t_stat=test_results['t_stat'],
            p_val=test_results['p_val'],
            chi2_stat=test_results['chi2_stat'],
            chi2_p_val=test_results['chi2_p_val'],
            u_stat=test_results['u_stat'],
            u_p_val=test_results['u_p_val'],
            kw_stat=test_results['kw_stat'],
            kw_p_val=test_results['kw_p_val']
        )

    def resolve_clustering_results(self, info, water_type):
        data = fetch_water_data(water_type)
        clusters, silhouette_avg = perform_clustering(data)
        return ClusteringResult(clusters=clusters.tolist(), silhouette_avg=silhouette_avg)

    def resolve_regression_results(self, info, water_type):
        data = fetch_water_data(water_type)
        regression_results, y_pred = perform_regression(data)
        return RegressionResult(
            feature_importances=regression_results['feature_importances'],
            mean_squared_error=regression_results['mean_squared_error'],
            r2_score=regression_results['r2_score'],
            y_pred=y_pred.tolist()
        )

schema = graphene.Schema(query=Query)
