# monitoring/views.py
"""
Next-generation server & infrastructure monitoring dashboard views for QAD.
Provides REST JSON endpoints consumed by the frontend dashboard,
plus the main HTML template view with real-time telemetry streaming.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from typing import Any, Dict, List

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from .docker_client import docker_client

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Shell Command Helper (for kubectl and OS utilities)
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10) -> tuple[str, str, int]:
    """Run a shell command safely; return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except FileNotFoundError:
        return "", f"Command not found: {cmd[0]}", 127
    except subprocess.TimeoutExpired:
        return "", "Timed out", 124
    except Exception as exc:
        return "", str(exc), 1


def _kubectl_available() -> bool:
    _, _, code = _run(["kubectl", "version", "--client", "--output=json"], timeout=5)
    return code == 0


# ─────────────────────────────────────────────────────────────────────────────
# Main dashboard view
# ─────────────────────────────────────────────────────────────────────────────

class MonitoringDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "monitoring/dashboard.html"
    login_url = "/login/"

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Monitoring dashboard requires staff or superuser access.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        # User display role
        if user.is_superuser:
            user_role = "System Administrator"
        elif user.is_staff:
            user_role = "Staff Officer"
        else:
            first_group = user.groups.first()
            user_role = first_group.name if first_group else "Infrastructure Operator"

        # Landing URL for universal redirect
        landing_url = "/"
        try:
            from accounts.utils import get_user_landing_url
            landing_url = get_user_landing_url(user)
        except Exception:
            landing_url = "/"

        ctx["user_role"] = user_role
        ctx["landing_url"] = landing_url
        ctx["docker_available"] = docker_client.is_available()
        ctx["k8s_available"] = _kubectl_available()
        ctx["hostname"] = socket.gethostname()
        ctx["now"] = timezone.now()
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# API: Realtime Telemetry Wave (High-Frequency 1s-5s Poller)
# ─────────────────────────────────────────────────────────────────────────────

class RealtimeTelemetryAPI(LoginRequiredMixin, View):
    """Ultra-responsive real-time telemetry stream combining OS, DB, Redis, and Containers."""
    login_url = "/login/"

    def get(self, request):
        now = timezone.now()
        data: Dict[str, Any] = {
            "ok": True,
            "timestamp": now.strftime("%H:%M:%S"),
            "iso": now.isoformat(),
        }

        # 1. OS CPU & Memory
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            net = psutil.net_io_counters()
            disk = psutil.disk_usage("/")
            data["cpu"] = cpu
            data["mem_percent"] = mem.percent
            data["mem_used_mb"] = round(mem.used / (1024 * 1024), 1)
            data["mem_total_mb"] = round(mem.total / (1024 * 1024), 1)
            data["net_sent_kb"] = round(net.bytes_sent / 1024, 1)
            data["net_recv_kb"] = round(net.bytes_recv / 1024, 1)
            data["disk_percent"] = disk.percent
        except Exception:
            data["cpu"] = 0
            data["mem_percent"] = 0
            data["disk_percent"] = 0

        # 2. PostgreSQL Live Pool & Stats
        try:
            from django.db import connection
            with connection.cursor() as cur:
                cur.execute("""
                    SELECT numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
                           ROUND(blks_hit::numeric / NULLIF(blks_hit + blks_read, 0) * 100, 2) AS hit_ratio
                    FROM pg_stat_database WHERE datname = current_database();
                """)
                row = cur.fetchone()
                if row:
                    data["db"] = {
                        "backends": row[0] or 0,
                        "commits": row[1] or 0,
                        "rollbacks": row[2] or 0,
                        "hit_ratio": float(row[5] or 99.5),
                        "status": "healthy",
                    }
                else:
                    data["db"] = {"backends": 0, "status": "connected"}
        except Exception as exc:
            data["db"] = {"backends": 0, "status": "error", "error": str(exc)}

        # 3. Redis Live Metrics
        try:
            import redis
            r_host = os.environ.get("REDIS_HOST", "redis")
            r_port = int(os.environ.get("REDIS_PORT", 6379))
            r = redis.Redis(host=r_host, port=r_port, socket_timeout=1)
            r_info = r.info()
            keyspace_hits = r_info.get("keyspace_hits", 0)
            keyspace_misses = r_info.get("keyspace_misses", 0)
            total_lookups = keyspace_hits + keyspace_misses
            hit_rate = round((keyspace_hits / total_lookups) * 100, 1) if total_lookups else 100.0

            data["redis"] = {
                "used_memory_human": r_info.get("used_memory_human", "0M"),
                "used_memory_bytes": r_info.get("used_memory", 0),
                "connected_clients": r_info.get("connected_clients", 0),
                "ops_per_sec": r_info.get("instantaneous_ops_per_sec", 0),
                "hit_rate": hit_rate,
                "status": "healthy",
            }
        except Exception as exc:
            data["redis"] = {"connected_clients": 0, "ops_per_sec": 0, "status": "error"}

        # 4. Containers summary
        try:
            containers = docker_client.list_containers()
            running = sum(1 for c in containers if c.get("state") == "running")
            total = len(containers)
            data["containers"] = {
                "running": running,
                "total": total,
                "status": "ok" if running > 0 else "warn",
            }
        except Exception:
            data["containers"] = {"running": 0, "total": 0, "status": "unknown"}

        return JsonResponse(data)


# ─────────────────────────────────────────────────────────────────────────────
# API: System Metrics (Detailed)
# ─────────────────────────────────────────────────────────────────────────────

class SystemMetricsAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            net = psutil.net_io_counters()
            boot = datetime.datetime.fromtimestamp(psutil.boot_time(), tz=datetime.timezone.utc)
            uptime_secs = int((datetime.datetime.now(datetime.timezone.utc) - boot).total_seconds())
            load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)

            # Per-core CPU
            per_core = psutil.cpu_percent(percpu=True, interval=0.1)

            # Top processes by CPU
            procs = []
            for p in sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]),
                key=lambda x: x.info.get("cpu_percent", 0) or 0,
                reverse=True,
            )[:12]:
                try:
                    procs.append({
                        "pid": p.info["pid"],
                        "name": p.info["name"],
                        "cpu": round(p.info.get("cpu_percent") or 0, 1),
                        "mem": round(p.info.get("memory_percent") or 0, 2),
                        "status": p.info.get("status", ""),
                    })
                except Exception:
                    pass

            return JsonResponse({
                "ok": True,
                "cpu": cpu,
                "cpu_cores": per_core,
                "cpu_count": psutil.cpu_count(),
                "load": list(load),
                "memory": {
                    "total": mem.total,
                    "available": mem.available,
                    "used": mem.used,
                    "percent": mem.percent,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                },
                "network": {
                    "bytes_sent": net.bytes_sent,
                    "bytes_recv": net.bytes_recv,
                    "packets_sent": net.packets_sent,
                    "packets_recv": net.packets_recv,
                    "errin": net.errin,
                    "errout": net.errout,
                },
                "uptime_seconds": uptime_secs,
                "platform": platform.platform(),
                "hostname": socket.gethostname(),
                "top_processes": procs,
                "timestamp": timezone.now().isoformat(),
            })
        except Exception as exc:
            disk = shutil.disk_usage("/")
            return JsonResponse({
                "ok": True,
                "cpu": 0,
                "cpu_cores": [],
                "cpu_count": os.cpu_count() or 1,
                "load": [0, 0, 0],
                "memory": {"total": 0, "available": 0, "used": 0, "percent": 0},
                "disk": {"total": disk.total, "used": disk.used, "free": disk.free,
                         "percent": round(disk.used / disk.total * 100, 1) if disk.total else 0},
                "network": {},
                "uptime_seconds": 0,
                "platform": platform.platform(),
                "hostname": socket.gethostname(),
                "top_processes": [],
                "timestamp": timezone.now().isoformat(),
                "warning": str(exc),
            })


# ─────────────────────────────────────────────────────────────────────────────
# API: Docker Containers (Direct Docker Engine Integration)
# ─────────────────────────────────────────────────────────────────────────────

class DockerContainersAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        try:
            containers = docker_client.list_containers(all_containers=True)
            include_stats = request.GET.get("stats", "true").lower() == "true"
            if include_stats and containers:
                import concurrent.futures
                running_containers = [c for c in containers if c.get("state") == "running"]

                def _fetch_stat(c):
                    try:
                        s = docker_client.get_container_stats(c["name"])
                        if s:
                            c.update(s)
                    except Exception:
                        pass

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    list(executor.map(_fetch_stat, running_containers))

            return JsonResponse({
                "ok": True,
                "containers": containers,
                "count": len(containers),
                "docker_available": docker_client.is_available(),
            })
        except Exception as exc:
            logger.exception("DockerContainersAPI error")
            return JsonResponse({
                "ok": False,
                "error": str(exc),
                "containers": [],
                "docker_available": False,
            }, status=200)


# ─────────────────────────────────────────────────────────────────────────────
# API: Docker Actions (Restart / Stop / Start / Kill / Pause / Unpause)
# ─────────────────────────────────────────────────────────────────────────────

class DockerActionAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def post(self, request):
        if not (request.user.is_superuser or request.user.is_staff):
            return JsonResponse({"ok": False, "error": "Insufficient privileges"}, status=403)

        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({"ok": False, "error": "Invalid JSON body"}, status=400)

        action = body.get("action", "").lower().strip()
        container = body.get("container", "").strip()

        if not action or not container:
            return JsonResponse({"ok": False, "error": "action and container are required"}, status=400)

        # Safety: only alphanumeric + dash + underscore allowed for container name
        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", container):
            return JsonResponse({"ok": False, "error": "Invalid container name"}, status=400)

        success, msg = docker_client.container_action(container, action)

        logger.info(
            "MONITORING_DOCKER_ACTION user=%s action=%s container=%s success=%s msg=%s",
            request.user.username, action, container, success, msg,
        )

        return JsonResponse({
            "ok": success,
            "action": action,
            "container": container,
            "output": msg,
        })


# ─────────────────────────────────────────────────────────────────────────────
# API: Docker Logs
# ─────────────────────────────────────────────────────────────────────────────

class DockerLogsAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        container = request.GET.get("container", "").strip()
        tail = request.GET.get("tail", "150").strip()

        if not container or not re.fullmatch(r"[a-zA-Z0-9_\-]+", container):
            return JsonResponse({"ok": False, "error": "Invalid container name"}, status=400)

        try:
            tail_int = min(int(tail), 1000)
        except ValueError:
            tail_int = 150

        logs_content = docker_client.get_container_logs(container, tail=tail_int, timestamps=True)

        return JsonResponse({
            "ok": True,
            "container": container,
            "logs": logs_content,
        })


# ─────────────────────────────────────────────────────────────────────────────
# API: Docker Compose Services
# ─────────────────────────────────────────────────────────────────────────────

class DockerComposeAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        try:
            containers = docker_client.list_containers(all_containers=True)
            services = []
            for c in containers:
                services.append({
                    "Name": c.get("name"),
                    "Service": c.get("service"),
                    "State": c.get("state"),
                    "Status": c.get("status"),
                    "Ports": c.get("ports"),
                    "Image": c.get("image"),
                    "Health": c.get("health"),
                })
            return JsonResponse({"ok": True, "services": services, "count": len(services)})
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc), "services": []})


# ─────────────────────────────────────────────────────────────────────────────
# API: Kubernetes Nodes & Pods
# ─────────────────────────────────────────────────────────────────────────────

class KubernetesAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        resource = request.GET.get("resource", "pods").strip()
        namespace = request.GET.get("namespace", "default").strip()

        if resource not in {"pods", "nodes", "services", "deployments", "namespaces"}:
            return JsonResponse({"ok": False, "error": "Invalid resource"}, status=400)

        cmd = ["kubectl", "get", resource, "-o", "json"]
        if resource not in ("nodes", "namespaces"):
            cmd += ["-n", namespace]

        stdout, stderr, code = _run(cmd, timeout=20)

        if code != 0:
            return JsonResponse({
                "ok": False,
                "error": stderr or "Kubernetes cluster not configured or kubectl not found.",
                "items": [],
            })

        try:
            data = json.loads(stdout)
            items = data.get("items", [])
            slim = []
            for item in items:
                meta = item.get("metadata", {})
                status = item.get("status", {})
                spec = item.get("spec", {})
                slim.append({
                    "name": meta.get("name"),
                    "namespace": meta.get("namespace"),
                    "labels": meta.get("labels", {}),
                    "phase": status.get("phase"),
                    "conditions": status.get("conditions", []),
                    "ready": _k8s_ready(status),
                    "age": meta.get("creationTimestamp"),
                    "restarts": _k8s_restarts(status),
                    "node": spec.get("nodeName"),
                    "image": _k8s_images(spec),
                })
            return JsonResponse({"ok": True, "items": slim, "resource": resource, "namespace": namespace})
        except Exception as exc:
            return JsonResponse({"ok": False, "error": str(exc), "items": []})


def _k8s_ready(status: dict) -> bool:
    for cond in status.get("conditions", []):
        if cond.get("type") == "Ready":
            return cond.get("status") == "True"
    return False


def _k8s_restarts(status: dict) -> int:
    total = 0
    for cs in status.get("containerStatuses", []):
        total += cs.get("restartCount", 0)
    return total


def _k8s_images(spec: dict) -> list:
    return [c.get("image", "") for c in spec.get("containers", [])]


# ─────────────────────────────────────────────────────────────────────────────
# API: Security Audit & Threat Intelligence
# ─────────────────────────────────────────────────────────────────────────────

class SecurityAuditAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        risks = []
        score = 100

        # 1. Containers port exposure check via docker_client
        try:
            containers = docker_client.list_containers()
            for c in containers:
                ports_str = c.get("ports", "")
                name = c.get("name", "")
                if "0.0.0.0" in ports_str and any(p in ports_str for p in ("5432", "6379", "15432", "16379", "27017")):
                    risks.append({
                        "severity": "CRITICAL",
                        "category": "Docker Security",
                        "title": f"Container '{name}' exposes raw DB/Cache port globally",
                        "detail": f"Port configuration ({ports_str}) is reachable outside the internal Docker network.",
                        "recommendation": "Bind exclusively to 127.0.0.1 or utilize isolated Docker networks.",
                    })
                    score -= 20
        except Exception:
            pass

        # 2. Failed login attempts from audit log
        try:
            from core.models import AuditLogEntry
            from django.utils import timezone as tz
            from datetime import timedelta
            cutoff = tz.now() - timedelta(hours=1)
            failed = AuditLogEntry.objects.filter(
                action="LOGIN",
                description__icontains="fail",
                timestamp__gte=cutoff,
            ).count()
            if failed >= 10:
                risks.append({
                    "severity": "HIGH",
                    "category": "Authentication",
                    "title": f"{failed} failed login attempts in the last hour",
                    "detail": "High frequency of login failures detected — possible credential stuffing or brute force.",
                    "recommendation": "Inspect origin IP addresses, activate IP rate-limiting, and review lockout policies.",
                })
                score -= 15
        except Exception:
            pass

        # 3. Locked accounts
        try:
            from accounts.models import CustomUser
            locked = CustomUser.objects.filter(is_locked=True, is_active=True).count()
            if locked:
                risks.append({
                    "severity": "MEDIUM",
                    "category": "Identity",
                    "title": f"{locked} user account(s) currently locked",
                    "detail": "Accounts locked due to repeated authentication failures or administrative action.",
                    "recommendation": "Audit accounts in User Management to verify legitimate operator access.",
                })
                score -= 5 * min(locked, 4)
        except Exception:
            pass

        # 4. Django configuration checks
        from django.conf import settings
        if getattr(settings, "DEBUG", False):
            risks.append({
                "severity": "CRITICAL",
                "category": "Django Core",
                "title": "DEBUG mode is active in application environment",
                "detail": "DEBUG=True leaks stack traces, environment secrets, and sensitive queries.",
                "recommendation": "Disable DEBUG mode immediately in production deployment.",
            })
            score -= 25

        secret = getattr(settings, "SECRET_KEY", "")
        if len(secret) < 50:
            risks.append({
                "severity": "HIGH",
                "category": "Cryptographic",
                "title": "SECRET_KEY entropy is substandard (< 50 chars)",
                "detail": "Short or default secret keys weaken session cookies and CSRF tokens.",
                "recommendation": "Generate a 64-character high-entropy secret in .env.",
            })
            score -= 15

        allowed = getattr(settings, "ALLOWED_HOSTS", [])
        if "*" in allowed:
            risks.append({
                "severity": "HIGH",
                "category": "Network Routing",
                "title": "ALLOWED_HOSTS includes wildcard '*'",
                "detail": "Allows host header injection and cache poisoning attacks.",
                "recommendation": "Enumerate strict FQDNs and internal service names.",
            })
            score -= 10

        # 5. Superuser count audit
        try:
            from accounts.models import CustomUser
            su_count = CustomUser.objects.filter(is_superuser=True, is_active=True).count()
            if su_count > 3:
                risks.append({
                    "severity": "LOW",
                    "category": "Privilege Access",
                    "title": f"{su_count} active superusers registered",
                    "detail": "High proportion of superusers expands administrative attack surface.",
                    "recommendation": "Delegate granular role-based permissions instead of global superuser status.",
                })
                score -= 5
        except Exception:
            pass

        score = max(0, min(100, score))
        grade = "A+" if score >= 95 else "A" if score >= 88 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

        return JsonResponse({
            "ok": True,
            "score": score,
            "grade": grade,
            "risks": risks,
            "risk_count": len(risks),
            "critical": sum(1 for r in risks if r["severity"] == "CRITICAL"),
            "high": sum(1 for r in risks if r["severity"] == "HIGH"),
            "medium": sum(1 for r in risks if r["severity"] == "MEDIUM"),
            "low": sum(1 for r in risks if r["severity"] == "LOW"),
            "timestamp": timezone.now().isoformat(),
        })


# ─────────────────────────────────────────────────────────────────────────────
# API: Django App & Infrastructure Health
# ─────────────────────────────────────────────────────────────────────────────

class AppHealthAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        checks = []

        # 1. PostgreSQL Database
        try:
            from django.db import connection
            with connection.cursor() as cur:
                cur.execute("SELECT version();")
                ver = cur.fetchone()[0].split()[1]
            checks.append({
                "name": "PostgreSQL Database",
                "status": "healthy",
                "detail": f"v{ver} · Responsive",
                "icon": "🗄️",
            })
        except Exception as exc:
            checks.append({"name": "PostgreSQL Database", "status": "error", "detail": str(exc), "icon": "🗄️"})

        # 2. Redis Cache & Broker
        try:
            import redis
            r_host = os.environ.get("REDIS_HOST", "redis")
            r_port = int(os.environ.get("REDIS_PORT", 6379))
            r = redis.Redis(host=r_host, port=r_port, socket_timeout=2)
            r_info = r.info()
            checks.append({
                "name": "Redis Memory Engine",
                "status": "healthy",
                "detail": f"{r_info.get('used_memory_human')} · {r_info.get('connected_clients')} clients",
                "icon": "⚡",
            })
        except Exception as exc:
            checks.append({"name": "Redis Memory Engine", "status": "error", "detail": str(exc), "icon": "⚡"})

        # 3. Docker Engine Daemon
        if docker_client.is_available():
            containers = docker_client.list_containers()
            running = sum(1 for c in containers if c.get("state") == "running")
            checks.append({
                "name": "Docker Engine Daemon",
                "status": "healthy",
                "detail": f"{running}/{len(containers)} containers running",
                "icon": "🐳",
            })
        else:
            checks.append({
                "name": "Docker Engine Daemon",
                "status": "warning",
                "detail": "Proxy socket not connected",
                "icon": "🐳",
            })

        # 4. Celery Task Queue
        try:
            from qad.celery import app as celery_app
            insp = celery_app.control.inspect(timeout=1.5)
            active = insp.active()
            if active is not None:
                worker_count = len(active)
                checks.append({
                    "name": "Celery Distributed Fleet",
                    "status": "healthy",
                    "detail": f"{worker_count} active workers registered",
                    "icon": "⚙️",
                })
            else:
                checks.append({
                    "name": "Celery Distributed Fleet",
                    "status": "warning",
                    "detail": "Inspect timed out; Redis broker running",
                    "icon": "⚙️",
                })
        except Exception as exc:
            checks.append({"name": "Celery Distributed Fleet", "status": "warning", "detail": str(exc), "icon": "⚙️"})

        # 5. Django Channels Layer
        try:
            from channels.layers import get_channel_layer
            layer = get_channel_layer()
            if layer:
                checks.append({
                    "name": "Channels ASGI Layer",
                    "status": "healthy",
                    "detail": "WebSocket layer operational",
                    "icon": "🔌",
                })
            else:
                checks.append({"name": "Channels ASGI Layer", "status": "none", "detail": "Not configured", "icon": "🔌"})
        except Exception as exc:
            checks.append({"name": "Channels ASGI Layer", "status": "error", "detail": str(exc), "icon": "🔌"})

        # 6. Database Migrations Status
        try:
            from django.db.migrations.executor import MigrationExecutor
            from django.db import connection
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            unapplied = executor.migration_plan(targets)
            if unapplied:
                checks.append({
                    "name": "Schema Migrations",
                    "status": "warning",
                    "detail": f"{len(unapplied)} pending migration(s)",
                    "icon": "📦",
                })
            else:
                checks.append({
                    "name": "Schema Migrations",
                    "status": "healthy",
                    "detail": "All schemas up to date",
                    "icon": "📦",
                })
        except Exception as exc:
            checks.append({"name": "Schema Migrations", "status": "error", "detail": str(exc), "icon": "📦"})

        # 7. Media & Storage
        try:
            from django.conf import settings
            media_root = getattr(settings, "MEDIA_ROOT", "")
            if media_root and os.path.exists(media_root):
                usage = shutil.disk_usage(media_root)
                free_gb = round(usage.free / (1024**3), 1)
                checks.append({
                    "name": "Media Volume Storage",
                    "status": "healthy",
                    "detail": f"{free_gb} GB free space",
                    "icon": "💾",
                })
            else:
                checks.append({"name": "Media Volume Storage", "status": "healthy", "detail": "Storage accessible", "icon": "💾"})
        except Exception as exc:
            checks.append({"name": "Media Volume Storage", "status": "error", "detail": str(exc), "icon": "💾"})

        return JsonResponse({"ok": True, "checks": checks, "count": len(checks)})


# ─────────────────────────────────────────────────────────────────────────────
# API: Daily Operations Report
# ─────────────────────────────────────────────────────────────────────────────

class DailyReportAPI(LoginRequiredMixin, View):
    login_url = "/login/"

    def get(self, request):
        now = timezone.now()
        yesterday = now - datetime.timedelta(days=1)

        try:
            from core.models import AuditLogEntry
            logins_24h = AuditLogEntry.objects.filter(
                action="LOGIN",
                timestamp__gte=yesterday,
            ).exclude(description__icontains="fail").count()

            failed_logins_24h = AuditLogEntry.objects.filter(
                action="LOGIN",
                timestamp__gte=yesterday,
                description__icontains="fail",
            ).count()
        except Exception:
            logins_24h = 0
            failed_logins_24h = 0

        try:
            from accounts.models import CustomUser
            active_users = CustomUser.objects.filter(is_active=True).count()
            locked_users = CustomUser.objects.filter(is_locked=True).count()
        except Exception:
            active_users = 0
            locked_users = 0

        # Containers summary
        containers = docker_client.list_containers()
        running_cnt = sum(1 for c in containers if c.get("state") == "running")
        total_cnt = len(containers)

        # Automated alerts
        alerts = []
        if failed_logins_24h > 20:
            alerts.append({"level": "CRITICAL", "msg": f"Elevated failed logins: {failed_logins_24h} in past 24h."})
        if locked_users > 0:
            alerts.append({"level": "WARNING", "msg": f"{locked_users} account(s) currently locked in directory."})
        if total_cnt > 0 and running_cnt < total_cnt:
            alerts.append({"level": "WARNING", "msg": f"{total_cnt - running_cnt} Docker container(s) are stopped or unhealthy."})
        if not alerts:
            alerts.append({"level": "INFO", "msg": "All core subsystems and security metrics nominal over the past 24 hours."})

        return JsonResponse({
            "ok": True,
            "period": f"{yesterday.strftime('%Y-%m-%d %H:%M')} to {now.strftime('%Y-%m-%d %H:%M')}",
            "stats": {
                "successful_logins": logins_24h,
                "failed_logins": failed_logins_24h,
                "active_users": active_users,
                "locked_users": locked_users,
                "containers_running": running_cnt,
                "containers_total": total_cnt,
            },
            "alerts": alerts,
            "generated_at": now.isoformat(),
        })
