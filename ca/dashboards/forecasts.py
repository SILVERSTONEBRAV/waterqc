import pandas as pd
from prophet import Prophet

from ca.models import ChemicalBatch
from dashboards.registry import registry


@registry.forecasts.register(
    key="ca.batch_forecast"
)
def batch_forecast():

    qs = (
        ChemicalBatch.objects
        .extra(
            {"ds": "received_date"}
        )
        .values(
            "ds"
        )
    )

    if not qs:
        return []

    df = pd.DataFrame(qs)
    df["y"] = 1
    df = (
        df.groupby("ds")
        .sum()
        .reset_index()
    )

    model = Prophet()
    model.fit(df)

    future = model.make_future_dataframe(
        periods=90
    )

    forecast = model.predict(
        future
    )

    return forecast[
        [
            "ds",
            "yhat",
            "yhat_lower",
            "yhat_upper",
        ]
    ].tail(90).to_dict(
        "records"
    )