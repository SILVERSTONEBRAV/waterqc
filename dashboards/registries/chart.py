from __future__ import annotations

import base64
import hashlib
import importlib
import inspect
import io
import json
import logging
import pickle
import threading
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any, Callable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import seaborn as sns
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.utils.functional import cached_property

from .base import BaseRegistry, RegistryItem

logger = logging.getLogger(__name__)


class ChartRegistry(BaseRegistry):
    category = "charts"

    def __init__(self):
        super().__init__()

        self._types: dict[str, dict[str, RegistryItem]] = defaultdict(dict)
        self._themes: dict[str, Any] = {}
        self._builders: dict[str, Callable] = {}
        self._renderers: dict[str, Callable] = {}
        self._exporters: dict[str, Callable] = {}
        self._pipelines: dict[str, Callable] = {}
        self._datasets: dict[str, Any] = {}
        self._transforms: dict[str, Callable] = {}
        self._subscriptions: dict[str, set[str]] = defaultdict(set)
        self._templates: dict[str, Any] = {}
        self._statistics: dict[str, dict] = defaultdict(dict)
        self._figures: dict[str, go.Figure] = {}
        self._lock = threading.RLock()
        self.executor = ThreadPoolExecutor(
            max_workers=16,
            thread_name_prefix="charts",
        )
        self.channel_layer = get_channel_layer()

    def register(
        self,
        key: str,
        obj: Any,
        *,
        chart_type: str = "plotly",
        renderer: str = "html",
        theme: str | None = None,
        realtime: bool = False,
        exportable: bool = True,
        cache_timeout: int = 300,
        singleton: bool = False,
        dataset: Any = None,
        dependencies=(),
        permissions=(),
        tags=(),
        aliases=(),
        **metadata,
    ):
        metadata.update(
            {
                "chart_type": chart_type,
                "renderer": renderer,
                "theme": theme,
                "realtime": realtime,
                "exportable": exportable,
                "cache_timeout": cache_timeout,
                "dataset": dataset,
            }
        )

        item = super().register(
            key=key,
            obj=obj,
            aliases=aliases,
            tags=tags,
            permissions=permissions,
            dependencies=dependencies,
            singleton=singleton,
            cache=True,
            cache_timeout=cache_timeout,
            **metadata,
        )

        self._types[chart_type][key] = item

        if dataset is not None:
            self._datasets[key] = dataset

        return item

    def register_theme(
        self,
        name: str,
        template: Any,
    ):
        self._themes[name] = template

    def register_template(
        self,
        name: str,
        template: Any,
    ):
        self._templates[name] = template

    def register_builder(
        self,
        name: str,
        builder: Callable,
    ):
        self._builders[name] = builder

    def register_transform(
        self,
        name: str,
        transformer: Callable,
    ):
        self._transforms[name] = transformer

    def register_renderer(
        self,
        name: str,
        renderer: Callable,
    ):
        self._renderers[name] = renderer

    def register_exporter(
        self,
        name: str,
        exporter: Callable,
    ):
        self._exporters[name] = exporter

    def register_pipeline(
        self,
        name: str,
        pipeline: Callable,
    ):
        self._pipelines[name] = pipeline

    def register_dataset(
        self,
        name: str,
        dataset: Any,
    ):
        self._datasets[name] = dataset

    def build(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        return self._builders[name](
            *args,
            **kwargs,
        )

    def transform(
        self,
        name: str,
        data: Any,
        **kwargs,
    ):
        return self._transforms[name](
            data,
            **kwargs,
        )

    def pipeline(
        self,
        name: str,
        *args,
        **kwargs,
    ):
        return self._pipelines[name](
            *args,
            **kwargs,
        )

    def render(
        self,
        figure,
        renderer="html",
        **kwargs,
    ):
        fn = self._renderers.get(renderer)

        if fn:
            return fn(
                figure,
                **kwargs,
            )

        if renderer == "html":
            return pio.to_html(
                figure,
                full_html=False,
                include_plotlyjs="cdn",
            )

        if renderer == "json":
            return figure.to_json()

        if renderer == "dict":
            return figure.to_dict()

        if renderer == "png":
            return pio.to_image(
                figure,
                format="png",
            )

        if renderer == "svg":
            return pio.to_image(
                figure,
                format="svg",
            )

        return figure

    def export(
        self,
        figure,
        fmt="html",
        **kwargs,
    ):
        exporter = self._exporters.get(fmt)

        if exporter:
            return exporter(
                figure,
                **kwargs,
            )

        if fmt == "html":
            return pio.to_html(
                figure,
                full_html=True,
                include_plotlyjs="cdn",
            )

        if fmt == "json":
            return figure.to_json()

        if fmt in {
            "png",
            "jpeg",
            "svg",
            "pdf",
            "webp",
        }:
            return pio.to_image(
                figure,
                format=fmt,
            )

        raise ValueError(f"Unsupported export format: {fmt}")

    def cache_key(
        self,
        key,
        *args,
        **kwargs,
    ):
        payload = pickle.dumps(
            (
                key,
                args,
                kwargs,
            )
        )

        digest = hashlib.sha256(
            payload
        ).hexdigest()

        return f"dashboard:chart:{digest}"

    def get_cached(
        self,
        key,
        *args,
        **kwargs,
    ):
        return cache.get(
            self.cache_key(
                key,
                *args,
                **kwargs,
            )
        )

    def set_cached(
        self,
        value,
        key,
        *args,
        timeout=300,
        **kwargs,
    ):
        cache.set(
            self.cache_key(
                key,
                *args,
                **kwargs,
            ),
            value,
            timeout,
        )

    def generate(
        self,
        key,
        *args,
        refresh=False,
        **kwargs,
    ):
        item = self.get(key)

        if not item:
            raise KeyError(key)

        if not refresh:
            cached = self.get_cached(
                key,
                *args,
                **kwargs,
            )

            if cached is not None:
                return cached

        chart = item.obj

        if inspect.isclass(chart):
            chart = chart()

        if callable(chart):
            figure = chart(
                *args,
                **kwargs,
            )
        else:
            figure = chart

        self._figures[key] = figure

        self.set_cached(
            figure,
            key,
            *args,
            timeout=item.metadata.get(
                "cache_timeout",
                300,
            ),
            **kwargs,
        )

        if item.metadata.get("realtime"):
            self.broadcast(
                f"chart:{key}",
                {
                    "chart": key,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        return figure

    def generate_async(
        self,
        key,
        *args,
        **kwargs,
    ) -> Future:
        return self.executor.submit(
            self.generate,
            key,
            *args,
            **kwargs,
        )

    def generate_parallel(
        self,
        keys: list[str],
        *args,
        **kwargs,
    ):
        futures = {
            key: self.generate_async(
                key,
                *args,
                **kwargs,
            )
            for key in keys
        }

        results = {}

        for future in as_completed(
            futures.values()
        ):
            for key, f in futures.items():
                if f == future:
                    results[key] = f.result()
                    break

        return results

    def broadcast(
        self,
        group: str,
        payload: dict,
    ):
        if not self.channel_layer:
            return

        try:
            async_to_sync(
                self.channel_layer.group_send
            )(
                group,
                {
                    "type": "dashboard.update",
                    "data": payload,
                },
            )
        except Exception:
            logger.exception(
                "Chart broadcast failed."
            )

    def subscribe(
        self,
        chart,
        group,
    ):
        self._subscriptions[chart].add(
            group
        )

    def unsubscribe(
        self,
        chart,
        group,
    ):
        self._subscriptions[chart].discard(
            group
        )

    def dataframe(
        self,
        chart,
        *args,
        **kwargs,
    ):
        fig = self.generate(
            chart,
            *args,
            **kwargs,
        )

        if isinstance(
            fig,
            pd.DataFrame,
        ):
            return fig

        if isinstance(
            fig,
            go.Figure,
        ):
            rows = []

            for trace in fig.data:
                try:
                    rows.append(
                        pd.DataFrame(
                            trace.to_plotly_json()
                        )
                    )
                except Exception:
                    continue

            if rows:
                return pd.concat(
                    rows,
                    ignore_index=True,
                )

        return pd.DataFrame()

    def matplotlib(
        self,
        figure,
        dpi=300,
    ):
        buffer = io.BytesIO()
        figure.savefig(
            buffer,
            format="png",
            dpi=dpi,
            bbox_inches="tight",
        )
        buffer.seek(0)
        return buffer.getvalue()

    def base64(
        self,
        figure,
        fmt="png",
    ):
        image = pio.to_image(
            figure,
            format=fmt,
        )
        return base64.b64encode(
            image
        ).decode()

    def describe(
        self,
        chart,
        *args,
        **kwargs,
    ):
        df = self.dataframe(
            chart,
            *args,
            **kwargs,
        )

        if df.empty:
            return {}

        return (
            df.describe(
                include="all"
            )
            .replace(
                [np.inf, -np.inf],
                np.nan,
            )
            .fillna("")
            .to_dict()
        )

    def correlation(
        self,
        chart,
        *args,
        **kwargs,
    ):
        df = self.dataframe(
            chart,
            *args,
            **kwargs,
        )

        if df.empty:
            return pd.DataFrame()

        return df.corr(
            numeric_only=True
        )

    def heatmap(
        self,
        chart,
        *args,
        **kwargs,
    ):
        corr = self.correlation(
            chart,
            *args,
            **kwargs,
        )

        if corr.empty:
            return None

        fig, ax = plt.subplots(
            figsize=(12, 8)
        )

        sns.heatmap(
            corr,
            annot=True,
            ax=ax,
        )

        return fig

    @cached_property
    def capabilities(self):
        return {
            "plotly": True,
            "dash": importlib.util.find_spec("dash") is not None,
            "django_plotly_dash": importlib.util.find_spec(
                "django_plotly_dash"
            )
            is not None,
            "matplotlib": True,
            "seaborn": True,
            "numpy": True,
            "pandas": True,
            "scipy": importlib.util.find_spec("scipy") is not None,
            "statsmodels": importlib.util.find_spec(
                "statsmodels"
            )
            is not None,
            "prophet": importlib.util.find_spec(
                "prophet"
            )
            is not None,
            "sklearn": importlib.util.find_spec(
                "sklearn"
            )
            is not None,
            "transformers": importlib.util.find_spec(
                "transformers"
            )
            is not None,
            "redis": importlib.util.find_spec(
                "redis"
            )
            is not None,
            "reportlab": importlib.util.find_spec(
                "reportlab"
            )
            is not None,
            "openpyxl": importlib.util.find_spec(
                "openpyxl"
            )
            is not None,
            "channels": importlib.util.find_spec(
                "channels"
            )
            is not None,
        }

    def statistics(self):
        return {
            "charts": len(self),
            "types": {
                k: len(v)
                for k, v in self._types.items()
            },
            "themes": len(self._themes),
            "builders": len(self._builders),
            "renderers": len(self._renderers),
            "exporters": len(self._exporters),
            "pipelines": len(self._pipelines),
            "datasets": len(self._datasets),
            "subscriptions": {
                k: len(v)
                for k, v in self._subscriptions.items()
            },
            "capabilities": self.capabilities,
        }

    def by_type(
        self,
        chart_type,
    ):
        return self._types.get(
            chart_type,
            {},
        )

    def by_tag(
        self,
        tag,
    ):
        return [
            item
            for item in self.values()
            if tag in item.tags
        ]

    def schema(self):
        return json.loads(
            json.dumps(
                {
                    key: item.metadata
                    for key, item in self.items()
                },
                cls=DjangoJSONEncoder,
            )
        )

    def dashboard_schema(self):
        return {
            "statistics": self.statistics(),
            "charts": self.schema(),
        }


charts = ChartRegistry()