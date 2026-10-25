# monitoring/docker_client.py
"""
High-performance pure-Python Docker Engine client for QAD Infrastructure Command Center.
Communicates via Docker HTTP proxy (qad-docker-proxy:2375) or direct Unix Domain Socket (/var/run/docker.sock)
or DOCKER_HOST env var without requiring the docker CLI binary.
"""
from __future__ import annotations

import http.client
import json
import logging
import os
import re
import socket
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DOCKER_PROXY_URL = os.environ.get("DOCKER_PROXY_URL", "http://qad-docker-proxy:2375")
DOCKER_SOCKET_PATH = os.environ.get("DOCKER_SOCKET_PATH", "/var/run/docker.sock")


class UnixHTTPConnection(http.client.HTTPConnection):
    """HTTPConnection over a Unix Domain Socket."""
    def __init__(self, socket_path: str, timeout: int = 10):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


class DockerClient:
    """Lightweight Docker Engine API v1.41 client."""

    def __init__(self):
        self._mode: Optional[str] = None  # "http", "unix", or "none"
        self._base_url: Optional[str] = None
        self._detect_connection()

    def _detect_connection(self):
        # 1. Try DOCKER_HOST if explicitly set
        docker_host = os.environ.get("DOCKER_HOST", "").strip()
        if docker_host:
            if docker_host.startswith("unix://"):
                path = docker_host.replace("unix://", "")
                if os.path.exists(path):
                    self._mode = "unix"
                    self._base_url = path
                    return
            elif docker_host.startswith("tcp://") or docker_host.startswith("http://"):
                self._mode = "http"
                self._base_url = docker_host.replace("tcp://", "http://")
                return

        # 2. Try internal compose proxy container (qad-docker-proxy:2375)
        try:
            conn = http.client.HTTPConnection("qad-docker-proxy", 2375, timeout=2)
            conn.request("GET", "/_ping")
            resp = conn.getresponse()
            if resp.status == 200 and resp.read().decode().strip() == "OK":
                self._mode = "http"
                self._base_url = "http://qad-docker-proxy:2375"
                conn.close()
                return
            conn.close()
        except Exception:
            pass

        # 3. Try direct Unix socket if present and readable
        if os.path.exists(DOCKER_SOCKET_PATH):
            try:
                conn = UnixHTTPConnection(DOCKER_SOCKET_PATH, timeout=2)
                conn.request("GET", "/_ping")
                resp = conn.getresponse()
                if resp.status == 200:
                    self._mode = "unix"
                    self._base_url = DOCKER_SOCKET_PATH
                    conn.close()
                    return
                conn.close()
            except Exception:
                pass

        # 4. Try host.docker.internal:2375
        try:
            conn = http.client.HTTPConnection("host.docker.internal", 2375, timeout=1)
            conn.request("GET", "/_ping")
            resp = conn.getresponse()
            if resp.status == 200:
                self._mode = "http"
                self._base_url = "http://host.docker.internal:2375"
                conn.close()
                return
            conn.close()
        except Exception:
            pass

        self._mode = "none"

    def is_available(self) -> bool:
        if self._mode is None or self._mode == "none":
            self._detect_connection()
        return self._mode in ("http", "unix")

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 15,
    ) -> Tuple[int, bytes]:
        if not self.is_available():
            raise RuntimeError("Docker daemon is unreachable. Check qad-docker-proxy or docker.sock.")

        headers = headers or {}
        if body and "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        if self._mode == "http":
            parsed = urllib.parse.urlparse(self._base_url)
            port = parsed.port or 80
            conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
        else:
            conn = UnixHTTPConnection(self._base_url, timeout=timeout)

        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            return resp.status, data
        finally:
            conn.close()

    def get_info(self) -> Dict[str, Any]:
        status, data = self._request("GET", "/info")
        if status == 200:
            return json.loads(data.decode("utf-8"))
        return {}

    def get_version(self) -> Dict[str, Any]:
        status, data = self._request("GET", "/version")
        if status == 200:
            return json.loads(data.decode("utf-8"))
        return {}

    def list_containers(self, all_containers: bool = True) -> List[Dict[str, Any]]:
        path = f"/containers/json?all={'1' if all_containers else '0'}"
        status, data = self._request("GET", path)
        if status != 200:
            logger.error("Failed to list containers: status=%s data=%s", status, data[:200])
            return []

        raw_list = json.loads(data.decode("utf-8"))
        results = []

        for c in raw_list:
            cid = c.get("Id", "")
            names = [n.lstrip("/") for n in (c.get("Names") or [])]
            primary_name = names[0] if names else cid[:12]

            labels = c.get("Labels") or {}
            service = labels.get("com.docker.compose.service", primary_name)
            project = labels.get("com.docker.compose.project", "qad")

            # Format ports
            ports_formatted = []
            for p in (c.get("Ports") or []):
                pub = p.get("PublicPort")
                priv = p.get("PrivatePort")
                ptype = p.get("Type", "tcp")
                ip = p.get("IP", "")
                if pub:
                    ports_formatted.append(f"{ip + ':' if ip else ''}{pub}->{priv}/{ptype}")
                elif priv:
                    ports_formatted.append(f"{priv}/{ptype}")
            ports_str = ", ".join(ports_formatted) if ports_formatted else "-"

            state = c.get("State", "").lower()
            status_text = c.get("Status", "")

            # Health extraction from Status e.g. "Up 12 minutes (healthy)"
            health = "none"
            if "(healthy)" in status_text:
                health = "healthy"
            elif "(unhealthy)" in status_text:
                health = "unhealthy"
            elif "(health: starting)" in status_text:
                health = "starting"

            results.append({
                "id": cid[:12],
                "full_id": cid,
                "name": primary_name,
                "names": names,
                "service": service,
                "project": project,
                "image": c.get("Image", ""),
                "state": state,
                "status": status_text,
                "health": health,
                "ports": ports_str,
                "created": c.get("Created", 0),
                "cpu": "0.0%",
                "mem": "0 MB",
                "mem_perc": "0.0%",
                "net": "0B / 0B",
                "block": "0B / 0B",
            })

        return sorted(results, key=lambda x: x["name"])

    def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """Fetch real-time one-shot stats for a container."""
        path = f"/containers/{container_id}/stats?stream=false"
        try:
            status, data = self._request("GET", path, timeout=5)
            if status != 200:
                return {}
            s = json.loads(data.decode("utf-8"))

            # Calculate CPU %
            cpu_pct = 0.0
            cpu_stats = s.get("cpu_stats", {})
            precpu_stats = s.get("precpu_stats", {})
            cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
            online_cpus = cpu_stats.get("online_cpus") or len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", [1])) or 1
            if system_delta > 0 and cpu_delta > 0:
                cpu_pct = round((cpu_delta / system_delta) * online_cpus * 100.0, 2)

            # Calculate Memory
            mem_stats = s.get("memory_stats", {})
            usage_bytes = mem_stats.get("usage", 0)
            limit_bytes = mem_stats.get("limit", 1)
            mem_pct = round((usage_bytes / limit_bytes) * 100.0, 2) if limit_bytes else 0.0

            def fmt_bytes(b: int) -> str:
                if b < 1024:
                    return f"{b}B"
                elif b < 1024 * 1024:
                    return f"{round(b / 1024, 1)}KB"
                elif b < 1024 * 1024 * 1024:
                    return f"{round(b / (1024*1024), 1)}MB"
                return f"{round(b / (1024*1024*1024), 2)}GB"

            # Network I/O
            networks = s.get("networks", {})
            rx_total = sum(n.get("rx_bytes", 0) for n in networks.values())
            tx_total = sum(n.get("tx_bytes", 0) for n in networks.values())

            # Block I/O
            blkio = s.get("blkio_stats", {}).get("io_service_bytes_recursive", []) or []
            read_bytes = sum(b.get("value", 0) for b in blkio if b.get("op") == "Read")
            write_bytes = sum(b.get("value", 0) for b in blkio if b.get("op") == "Write")

            pids = s.get("pids_stats", {}).get("current", 0)

            return {
                "id": container_id[:12],
                "cpu": f"{cpu_pct}%",
                "cpu_num": cpu_pct,
                "mem": fmt_bytes(usage_bytes),
                "mem_bytes": usage_bytes,
                "mem_limit": fmt_bytes(limit_bytes),
                "mem_perc": f"{mem_pct}%",
                "mem_num": mem_pct,
                "net": f"{fmt_bytes(rx_total)} / {fmt_bytes(tx_total)}",
                "block": f"{fmt_bytes(read_bytes)} / {fmt_bytes(write_bytes)}",
                "pids": pids,
            }
        except Exception as exc:
            logger.debug("Failed to get stats for container %s: %s", container_id, exc)
            return {}

    def container_action(self, container_id: str, action: str) -> Tuple[bool, str]:
        """Perform action: restart, stop, start, pause, unpause, kill."""
        valid_actions = {"restart", "stop", "start", "pause", "unpause", "kill"}
        action = action.lower().strip()
        if action not in valid_actions:
            return False, f"Invalid action: {action}"

        path = f"/containers/{container_id}/{action}"
        try:
            status, data = self._request("POST", path, timeout=30)
            if status in (204, 200, 304):
                return True, f"Successfully executed '{action}' on {container_id}."
            err_msg = data.decode("utf-8", errors="replace")
            return False, f"Action failed (HTTP {status}): {err_msg}"
        except Exception as exc:
            return False, str(exc)

    def get_container_logs(
        self,
        container_id: str,
        tail: int = 150,
        timestamps: bool = True,
    ) -> str:
        """Fetch recent container logs, stripping docker multiplex headers."""
        path = (
            f"/containers/{container_id}/logs"
            f"?stdout=1&stderr=1&tail={tail}&timestamps={'1' if timestamps else '0'}"
        )
        try:
            status, raw_data = self._request("GET", path, timeout=10)
            if status != 200:
                return f"Error fetching logs (HTTP {status}): {raw_data.decode('utf-8', errors='replace')}"

            # Strip docker 8-byte multiplexing header if present
            # Header format: [1 byte stream_type][3 bytes 0][4 bytes size big-endian]
            lines = []
            pos = 0
            length = len(raw_data)
            has_docker_headers = False

            while pos + 8 <= length:
                stream_type = raw_data[pos]
                if stream_type in (1, 2) and raw_data[pos+1:pos+4] == b'\x00\x00\x00':
                    has_docker_headers = True
                    chunk_len = int.from_bytes(raw_data[pos+4:pos+8], byteorder="big")
                    pos += 8
                    chunk = raw_data[pos:pos+chunk_len]
                    pos += chunk_len
                    lines.append(chunk.decode("utf-8", errors="replace"))
                else:
                    break

            if has_docker_headers:
                return "".join(lines)
            else:
                return raw_data.decode("utf-8", errors="replace")
        except Exception as exc:
            return f"Error retrieving logs: {str(exc)}"


# Global singleton instance
docker_client = DockerClient()
