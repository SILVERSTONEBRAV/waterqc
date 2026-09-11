import json
from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync
from .models import DisplayControl, RawWater, TreatedWater, CoagulatedWater, ClarifiedWater, FilteredWater
from .data_analysis import perform_statistical_tests, perform_clustering, perform_regression, perform_xgboost_regression, perform_lstm_forecasting
from .tasks import send_alert_notification, send_alert_email

class SCADAConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()
        async_to_sync(self.channel_layer.group_add)("scada_group", self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)("scada_group", self.channel_name)

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        action = text_data_json['action']
        if action == 'fetch_data':
            self.fetch_data(text_data_json['water_type'])
        elif action == 'perform_analysis':
            self.perform_analysis(text_data_json['analysis_type'], text_data_json['water_type'])
        elif action == 'check_alerts':
            self.check_alerts()

    def fetch_data(self, water_type):
        data = self.get_water_data(water_type)
        self.send(text_data=json.dumps({'data': data}))

    def perform_analysis(self, analysis_type, water_type):
        data = pd.DataFrame(self.get_water_data(water_type))
        if analysis_type == 'statistical_tests':
            results = perform_statistical_tests(data)
        elif analysis_type == 'clustering':
            results = perform_clustering(data)
        elif analysis_type == 'regression':
            results = perform_regression(data)
        elif analysis_type == 'xgboost_regression':
            results = perform_xgboost_regression(data)
        elif analysis_type == 'lstm_forecasting':
            results = perform_lstm_forecasting(data)
        self.send(text_data=json.dumps({'results': results}))

    def check_alerts(self):
        alerts = []
        scheduled_forms = DisplayControl.objects.order_by('display_start_time')
        for scheduled_form in scheduled_forms:
            if self.should_generate_alert(scheduled_form):
                alerts.append(f"No data entry for {scheduled_form.get_form_type_display()}")
                send_alert_notification.delay(f"No data entry for {scheduled_form.get_form_type_display()}")
                send_alert_email.delay(f"No data entry for {scheduled_form.get_form_type_display()}", "Please check the system for more details.")

        self.send(text_data=json.dumps({'alerts': alerts}))

    def should_generate_alert(self, scheduled_form):
        # Implement the logic to determine if an alert should be generated
        return True

    def get_water_data(self, water_type):
        if water_type == 'raw':
            return list(RawWater.objects.values())
        elif water_type == 'treated':
            return list(TreatedWater.objects.values())
        elif water_type == 'coagulated':
            return list(CoagulatedWater.objects.values())
        elif water_type == 'clarified':
            return list(ClarifiedWater.objects.values())
        elif water_type == 'filtered':
            return list(FilteredWater.objects.values())
        return []

class AlertConsumer(WebsocketConsumer):
    def connect(self):
        self.accept()

    def disconnect(self, close_code):
        pass

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        action = text_data_json['action']
        if action == 'check_alerts':
            self.check_alerts()

    def check_alerts(self):
        alerts = []
        scheduled_forms = DisplayControl.objects.order_by('display_start_time')
        for scheduled_form in scheduled_forms:
            if self.should_generate_alert(scheduled_form):
                alerts.append(f"No data entry for {scheduled_form.get_form_type_display()}")

        self.send(text_data=json.dumps({'alerts': alerts}))

    def should_generate_alert(self, scheduled_form):
        # Implement the logic to determine if an alert should be generated
        return True
