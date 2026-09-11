# ca/services/forecasting.py

import pandas as pd
from prophet import Prophet

from ca.models import ChemicalBatch


class ForecastingService:

    @staticmethod
    def batch_forecast(periods=30):

        qs = (
            ChemicalBatch.objects
            .values(
                "created_at"
            )
        )

        df = pd.DataFrame(qs)

        if df.empty:
            return []

        df["ds"] = pd.to_datetime(
            df["created_at"]
        )

        df["y"] = 1

        df = (
            df.groupby("ds")
            .sum()
            .reset_index()
        )

        model = Prophet()
        model.fit(df)

        future = model.make_future_dataframe(
            periods=periods
        )

        forecast = model.predict(
            future
        )

        return (
            forecast[
                ["ds", "yhat"]
            ]
            .to_dict("records")
        )