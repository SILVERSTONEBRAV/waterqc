# ca/services/ml.py

import pandas as pd
from sklearn.ensemble import (
    IsolationForest
)

from ca.models import ChemicalBatch


class MLService:

    @staticmethod
    def anomaly_detection():

        qs = (
            ChemicalBatch.objects
            .values(
                "yield_percent",
                "quantity",
            )
        )

        df = pd.DataFrame(qs)

        if df.empty:
            return []

        model = IsolationForest(
            contamination=0.05,
            random_state=42,
        )

        df["anomaly"] = (
            model.fit_predict(df)
        )

        return df.to_dict(
            "records"
        )