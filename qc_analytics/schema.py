import graphene
from graphene_django import DjangoObjectType
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import pandas as pd

from .engine import QuantumQCAnalyticsEngineV4
from .tasks import run_quantum_analysis_task
from qc.models import (
    TreatedWaterResult,
    RawWaterResult,
    CoagulatedWaterResult,
    ClarifiedWaterResult,
    WaterAnalysis
)


# ============================================
# 🚀 --- GraphQL Object Types ---
# ============================================

class ParameterAnalyticsType(graphene.ObjectType):
    parameter = graphene.String()
    phase = graphene.String()
    stats = graphene.JSONString()
    forecast = graphene.JSONString()
    anomalies = graphene.JSONString()
    correlations = graphene.JSONString()
    nonconformities = graphene.List(graphene.Int)
    summary = graphene.String(description="Summary of analytics, AI-free")


class MultiPhaseAnalyticsType(graphene.ObjectType):
    combined_stats = graphene.JSONString()
    covariance_matrix = graphene.JSONString()
    correlation_heatmap = graphene.JSONString()
    phases = graphene.List(ParameterAnalyticsType)


# ============================================
# 🧠 --- Query Layer ---
# ============================================

class Query(graphene.ObjectType):
    parameter_analytics = graphene.Field(
        ParameterAnalyticsType,
        parameter=graphene.String(required=True),
        phase=graphene.String(),
        start=graphene.String(),
        end=graphene.String(),
        forecast_method=graphene.String(default_value="hybrid"),
        periods=graphene.Int(default_value=30),
    )

    multi_phase_analytics = graphene.Field(
        MultiPhaseAnalyticsType,
        parameters=graphene.List(graphene.String, required=True),
        phases=graphene.List(graphene.String, required=True),
        start=graphene.String(),
        end=graphene.String(),
    )

    # -------------------------
    # Single Parameter Analytics
    # -------------------------
    def resolve_parameter_analytics(
        self, info, parameter, phase=None, start=None, end=None,
        forecast_method="hybrid", periods=30
    ):
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else None

        df = QuantumQCAnalyticsEngineV4.aggregate_results(start_date, end_date)
        df = QuantumQCAnalyticsEngineV4.detect_anomalies(df)
        stats = QuantumQCAnalyticsEngineV4.generate_statistics(df)
        forecast = QuantumQCAnalyticsEngineV4.forecast(df, parameter, forecast_method, periods)
        correlations = QuantumQCAnalyticsEngineV4.compound_correlation(df)
        nonconformities = QuantumQCAnalyticsEngineV4.detect_nonconformities(df)

        anomalies = df[df.get("anomaly", False)].to_dict(orient="records")

        return ParameterAnalyticsType(
            parameter=parameter,
            phase=phase,
            stats=stats,
            forecast=forecast,
            anomalies=anomalies,
            correlations=correlations,
            nonconformities=[nc.id for nc in nonconformities],
            summary=f"{len(anomalies)} anomalies detected, {len(nonconformities)} nonconformities"
        )

    # -------------------------
    # Multi-Phase Analytics
    # -------------------------
    def resolve_multi_phase_analytics(self, info, parameters, phases, start=None, end=None):
        start_date = datetime.strptime(start, "%Y-%m-%d") if start else None
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else None

        phase_objects = []
        all_dfs = []

        for p in parameters:
            for ph in phases:
                df = QuantumQCAnalyticsEngineV4.aggregate_results(start_date, end_date)
                df = QuantumQCAnalyticsEngineV4.detect_anomalies(df)
                stats = QuantumQCAnalyticsEngineV4.generate_statistics(df)
                forecast = QuantumQCAnalyticsEngineV4.forecast(df, p, "hybrid", 30)
                anomalies = df[df.get("anomaly", False)].to_dict(orient="records")
                nonconformities = QuantumQCAnalyticsEngineV4.detect_nonconformities(df)

                phase_objects.append(
                    ParameterAnalyticsType(
                        parameter=p,
                        phase=ph,
                        stats=stats,
                        forecast=forecast,
                        anomalies=anomalies,
                        nonconformities=[nc.id for nc in nonconformities],
                        summary=f"{len(anomalies)} anomalies, {len(nonconformities)} nonconformities"
                    )
                )
                all_dfs.append(df)

        combined_stats = QuantumQCAnalyticsEngineV4.generate_statistics(pd.concat(all_dfs))
        correlations = QuantumQCAnalyticsEngineV4.compound_correlation(pd.concat(all_dfs))

        return MultiPhaseAnalyticsType(
            combined_stats=combined_stats,
            covariance_matrix=correlations.get("covariance_matrix", {}),
            correlation_heatmap=correlations.get("correlation_matrix", {}),
            phases=phase_objects,
        )


# ============================================
# ⚙️ --- Mutations (Async Analysis + PDF) ---
# ============================================

class RunQCAnalysis(graphene.Mutation):
    class Arguments:
        parameters = graphene.List(graphene.String, required=True)
        phases = graphene.List(graphene.String, required=True)
        start = graphene.String()
        end = graphene.String()
        forecast_method = graphene.String(default_value="hybrid")
        periods = graphene.Int(default_value=30)
        mode = graphene.String(default_value="async")  # async vs sync

    task_id = graphene.String()
    status = graphene.String()
    message = graphene.String()

    @staticmethod
    def mutate(root, info, parameters, phases, start=None, end=None, forecast_method="hybrid", periods=30, mode="async"):
        if mode == "async":
            task = run_quantum_analysis_task.delay(parameters, phases, start, end, forecast_method, periods)
            return RunQCAnalysis(task_id=task.id, status="queued", message="Analysis scheduled in background.")
        else:
            df = QuantumQCAnalyticsEngineV4.aggregate_results(
                start=datetime.strptime(start, "%Y-%m-%d") if start else None,
                end=datetime.strptime(end, "%Y-%m-%d") if end else None
            )
            df = QuantumQCAnalyticsEngineV4.detect_anomalies(df)
            stats = QuantumQCAnalyticsEngineV4.generate_statistics(df)
            return RunQCAnalysis(task_id="none", status="completed", message=f"Analysis completed synchronously with {len(df)} records.")


# ============================================
# 🔌 --- Subscriptions for Live Updates ---
# ============================================

class AnalyticsUpdateSubscription(graphene.ObjectType):
    data = graphene.JSONString()

    async def subscribe(root, info):
        channel_layer = get_channel_layer()
        group_name = "qc_analytics"

        async def generator():
            async for event in channel_layer.group_listen(group_name):
                yield AnalyticsUpdateSubscription(data=event["data"])

        return generator()


# ============================================
# 🧩 --- Schema ---
# ============================================

class Mutation(graphene.ObjectType):
    run_qc_analysis = RunQCAnalysis.Field()

schema = graphene.Schema(query=Query, mutation=Mutation)
