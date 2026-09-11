from celery import shared_task
from .data_analysis import perform_statistical_tests, perform_clustering, perform_regression, perform_xgboost_regression, perform_lstm_forecasting
from .models import RawWater, TreatedWater, CoagulatedWater, ClarifiedWater, FilteredWater, WaterSample as BacteriologicalWaterSample
from heavy_metal_analysis.models import WaterSample as HeavyMetalWaterSample

@shared_task
def analyze_raw_water(data_id):
    raw_water = RawWater.objects.get(id=data_id)
    data = raw_water.parameters.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_treated_water(data_id):
    treated_water = TreatedWater.objects.get(id=data_id)
    data = treated_water.parameters.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_coagulated_water(data_id):
    coagulated_water = CoagulatedWater.objects.get(id=data_id)
    data = coagulated_water.parameters.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_clarified_water(data_id):
    clarified_water = ClarifiedWater.objects.get(id=data_id)
    data = clarified_water.parameters.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_filtered_water(data_id):
    filtered_water = FilteredWater.objects.get(id=data_id)
    data = filtered_water.parameters.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_bacteriological_water(data_id):
    water_sample = BacteriologicalWaterSample.objects.get(id=data_id)
    data = water_sample.bacteria.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def analyze_heavy_metal_water(data_id):
    water_sample = HeavyMetalWaterSample.objects.get(id=data_id)
    data = water_sample.heavy_metals.values()
    # Perform analysis
    perform_statistical_tests(data)
    perform_clustering(data)
    perform_regression(data)

@shared_task
def send_alert_email(subject, message, recipient_list):
    send_mail(subject, message, 'noreply@example.com', recipient_list)

@shared_task
def send_alert_notification(message):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "alerts_group",
        {
            "type": "alert.message",
            "message": message
        }
    )
