# dashboards/definitions/dashboard.py

from __future__ import annotations

from dataclasses import dataclass, field

from .base import BaseDefinition


@dataclass(slots=True, frozen=True)
class DashboardDefinition(BaseDefinition):
    """
    Defines a top-level dashboard and all of its capabilities.
    """

    # ============================================================
    # UI
    # ============================================================
    template: str = ""
    layout: str = "grid"

    icon: str = "fa-chart-line"
    color: str = ""
    accent: str = ""
    badge: str = ""
    badge_color: str = "primary"

    # ============================================================
    # Navigation
    # ============================================================
    url_name: str = ""
    url: str = ""
    app_label: str = ""
    group: str = "General"
    order: int = 0

    # ============================================================
    # Visibility
    # ============================================================
    public: bool = False
    realtime: bool = False
    mobile_enabled: bool = True

    # ============================================================
    # Components
    # ============================================================
    widgets: tuple[str, ...] = ()
    charts: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()
    kpis: tuple[str, ...] = ()

    # ============================================================
    # Extended Capabilities
    # ============================================================
    forecasts: tuple[str, ...] = ()
    analytics: tuple[str, ...] = ()
    ml_models: tuple[str, ...] = ()
    notifications: tuple[str, ...] = ()
    selectors: tuple[str, ...] = ()

    # ============================================================
    # Dashboard Actions
    # ============================================================
    actions: tuple[dict, ...] = ()

    # ============================================================
    # Search
    # ============================================================
    searchable_models: tuple[str, ...] = ()

    # ============================================================
    # Export
    # ============================================================
    export_formats: tuple[str, ...] = (
        "pdf",
        "xlsx",
        "csv",
    )

    # ============================================================
    # Caching
    # ============================================================
    cache_timeout: int = 300
    cache_key: str = ""

    # ============================================================
    # Realtime
    # ============================================================
    websocket_group: str = ""
    websocket_endpoint: str = ""
    refresh_interval: int = 60

    # ============================================================
    # Dependencies
    # ============================================================
    dependencies: tuple[str, ...] = ()

    # ============================================================
    # Ownership
    # ============================================================
    owner: str = ""
    support_email: str = ""
    documentation_url: str = ""

    # ============================================================
    # Metadata
    # ============================================================
    category: str = ""
    priority: str = "normal"
    version: str = "1.0.0"

    tenant_aware: bool = False
    audit_enabled: bool = False