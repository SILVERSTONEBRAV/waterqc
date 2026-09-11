from django.urls import path
from graphene_django.views import GraphQLView
from . import views

urlpatterns = [
    path('', views.WaterListView.as_view(), name='water_list'),
    path('<str:water_type>/create/', views.WaterCRUDView.as_view(), name='water_create'),
    path('<str:water_type>/<int:pk>/detail/', views.WaterDetailView.as_view(), name='water_detail'),
    path('<str:water_type>/<int:pk>/update/', views.WaterCRUDView.as_view(), name='water_update'),
    path('<str:water_type>/<int:pk>/delete/', views.WaterDeleteView.as_view(), name='water_delete'),
    path('data_entry/', views.data_entry, name='data_entry'),
    path('statistical_tests/', views.statistical_tests, name='statistical_tests'),
    path('clustering/', views.clustering, name='clustering'),
    path('regression/', views.regression, name='regression'),
    path('xgboost_regression/', views.xgboost_regression, name='xgboost_regression'),
    path('lstm_forecasting/', views.lstm_forecasting, name='lstm_forecasting'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('control/', views.control_view, name='control'),
    path('graphql/', GraphQLView.as_view(graphiql=True, schema=views.schema)),
    path('dynamic_form/', views.dynamic_form, name='dynamic_form'),
]
