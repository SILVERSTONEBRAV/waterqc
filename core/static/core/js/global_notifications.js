(function () {
    "use strict";

    const container = document.querySelector(".notification-container");
    const btn = document.getElementById("notificationBtn");
    const dropdown = document.getElementById("notificationDropdown");
    const badge = document.getElementById("notificationBadge");
    if (!container || !btn || !dropdown || !badge) return;

    const api = {
        alerts: [],
        refreshTimer: null,
        initialized: false,
        fetchUrl: container.dataset.feedUrl || "/accounts/notifications/",
        ackUrlTemplate: container.dataset.ackUrl || "/ca/notifications/__ID__/ack/",

        scopedUrl() {
            const url = new URL(this.fetchUrl, window.location.origin);
            const plantId = this.plantId();
            if (plantId) url.searchParams.set("plant", plantId);
            return url.toString();
        },

        plantId() {
            const queryPlant = new URLSearchParams(window.location.search).get("plant");
            return queryPlant || container.dataset.plantId || document.body.dataset.plantId || "";
        },

        csrfToken() {
            const part = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith("csrftoken="));
            return part ? decodeURIComponent(part.slice("csrftoken=".length)) : "";
        },

        escape(value) {
            return String(value == null ? "" : value).replace(/[&<>"']/g, char => ({
                "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
            })[char]);
        },

        safeUrl(value) {
            if (!value) return "";
            try {
                const url = new URL(value, window.location.origin);
                return url.origin === window.location.origin ? url.href : "";
            } catch (_) {
                return "";
            }
        },

        async fetchNotifications() {
            try {
                const response = await fetch(this.scopedUrl(), {
                    credentials: "same-origin",
                    cache: "no-store",
                    headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json", "Cache-Control": "no-cache" }
                });
                if (!response.ok) throw new Error("Notification feed returned HTTP " + response.status);
                const data = await response.json();
                if (!data || !Array.isArray(data.alerts)) return;
                this.alerts = data.alerts;
                this.renderDropdown(data.alerts, Number(data.unread_count || 0));
                this.updateBadge(Number(data.unread_count || 0));
                const status = dropdown.querySelector(".notification-status");
                if (status) status.hidden = true;
            } catch (error) {
                console.warn("[Dashboard notifications] Could not refresh alerts:", error);
                const status = dropdown.querySelector(".notification-status");
                if (status) {
                    status.textContent = "Notifications are temporarily unavailable. Try opening the bell again.";
                    status.hidden = false;
                }
            }
        },

        updateBadge(count) {
            badge.textContent = count > 99 ? "99+" : String(count);
            badge.style.display = count > 0 ? "grid" : "none";
            btn.classList.remove("has-alert--expired", "has-alert--almost-expiring", "has-alert--average", "has-alert--new");
            const urgencyOrder = ["expired", "almost-expiring", "average", "new"];
            const highest = urgencyOrder.find(kind => this.alerts.some(alert => !alert.acknowledged && alert.urgency === kind));
            if (highest) btn.classList.add("has-alert--" + highest);
            btn.setAttribute("aria-label", count ? `Notifications, ${count} unread` : "Notifications");
        },

        renderDropdown(alerts, unreadCount) {
            const rows = (alerts || []).slice(0, 15).map(alert => {
                const urgency = ["expired", "almost-expiring", "average", "new"].includes(alert.urgency) ? alert.urgency : "average";
                const url = this.safeUrl(alert.url);
                const canAck = Boolean(alert.can_acknowledge) && !alert.acknowledged;
                const ack = canAck
                    ? `<button type="button" class="notification-ack" data-notification-ack="${this.escape(alert.id)}">Acknowledge</button>`
                    : "";
                const open = url
                    ? `<a class="notification-open" href="${this.escape(url)}">${alert.type === "ca_assignment_pending" ? "Assign analyst" : "Open"}</a>`
                    : "";
                const voiceBtn = alert.voice_url
                    ? `<button type="button" class="notification-voice-btn" data-notification-voice="${this.escape(alert.voice_url)}" title="Listen to spoken voice alert" style="display:inline-flex;align-items:center;gap:4px;padding:3px 7px;border-radius:4px;background:#eef2ff;color:#4f46e5;font-size:11px;font-weight:600;border:1px solid #c7d2fe;cursor:pointer;"><i class="fa-solid fa-volume-high" aria-hidden="true"></i> Voice</button>`
                    : "";
                return `<li class="notification-item notification-item--${urgency}" role="none">
                    <div class="notification-item-top"><span class="notification-urgency">${urgency.replace("-", " ")}</span><time>${this.escape(alert.time_ago || "")}</time></div>
                    <strong class="notification-item-title">${this.escape(alert.title || "Notification")}</strong>
                    <span class="notification-item-message">${this.escape(alert.message || "")}</span>
                    <div class="notification-item-actions">${voiceBtn}${open}${ack}</div>
                </li>`;
            }).join("");
            dropdown.innerHTML = `<li class="notification-header" role="presentation"><span><i class="fa-solid fa-bell" aria-hidden="true"></i> Notifications</span><span class="notification-unread-count">${unreadCount} unread</span></li>${rows || '<li class="notification-empty" role="presentation">You are all caught up.</li>'}<li class="notification-status" role="status" aria-live="polite" hidden></li>`;
        },

        async ack(alertId) {
            const url = new URL(
                this.ackUrlTemplate.replace("__ID__", encodeURIComponent(alertId)),
                window.location.origin
            );
            const plantId = this.plantId();
            if (plantId) url.searchParams.set("plant", plantId);
            try {
                const response = await fetch(url.toString(), {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": this.csrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded"
                    },
                    body: "alert_id=" + encodeURIComponent(alertId)
                });
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.error || "Could not acknowledge notification.");
                const redirectUrl = this.safeUrl(data.redirect_url);
                if (redirectUrl) {
                    window.location.assign(redirectUrl);
                    return;
                }
                this.alerts = this.alerts.filter(alert => String(alert.id) !== String(alertId));
                const unread = this.alerts.filter(alert => !alert.acknowledged).length;
                this.renderDropdown(this.alerts, unread);
                this.updateBadge(unread);
                const streamItem = document.getElementById("alarm-item-" + String(alertId).replace(/[^A-Za-z0-9_-]/g, ""));
                if (streamItem) streamItem.remove();
            } catch (error) {
                console.error("[Dashboard notifications] Acknowledge failed:", error);
                const status = dropdown.querySelector(".notification-status");
                if (status) {
                    status.textContent = "Could not acknowledge this notification. Please try again.";
                    status.hidden = false;
                }
                this.scheduleRefresh();
            }
        },

        pushNotification(alert) {
            if (!alert || !alert.id) return;
            const next = Object.assign({ urgency: "new", acknowledged: false, time_ago: "Just now" }, alert);
            this.alerts = [next].concat(this.alerts.filter(item => item.id !== next.id));
            const unread = this.alerts.filter(item => !item.acknowledged).length;
            this.renderDropdown(this.alerts, unread);
            this.updateBadge(unread);
        },

        playChime() {
            try {
                const Audio = window.AudioContext || window.webkitAudioContext;
                if (!Audio) return;
                const context = new Audio();
                const oscillator = context.createOscillator();
                const gain = context.createGain();
                oscillator.frequency.value = 660;
                gain.gain.setValueAtTime(.035, context.currentTime);
                gain.gain.exponentialRampToValueAtTime(.001, context.currentTime + .22);
                oscillator.connect(gain);
                gain.connect(context.destination);
                oscillator.start();
                oscillator.stop(context.currentTime + .22);
            } catch (_) { /* Audio is an optional enhancement. */ }
        },

        connectWebSocket() {
            if (this._wsConnected || !window.WebSocket) return;
            this._wsConnected = false;
            this._wsRetryDelay = 1000;
            this._wsRetryTimer = null;
            this._wsStopped = false;

            const self = this;
            function connect() {
                if (self._wsStopped || document.hidden || !navigator.onLine) return;
                clearTimeout(self._wsRetryTimer);
                const scheme = location.protocol === "https:" ? "wss:" : "ws:";
                let ws;
                try {
                    ws = new WebSocket(`${scheme}//${location.host}/ws/alerts/`);
                } catch (_) {
                    scheduleReconnect();
                    return;
                }
                self._ws = ws;
                ws.onopen = () => {
                    self._wsConnected = true;
                    self._wsRetryDelay = 1000;
                };
                ws.onmessage = event => {
                    let data;
                    try { data = JSON.parse(event.data); } catch (_) { return; }
                    if (data.type === "connection.ready") {
                        self.scheduleRefresh();
                        return;
                    }
                    // Real-time alert push — update bell immediately
                    if (data.type === "alert" || data.type === "alert.message") {
                        const msg = data.message || "";
                        const title = data.title || "Notification";
                        const alertId = data.instance_ref || ("ws_" + Date.now());
                        self.pushNotification({
                            id: alertId,
                            type: data.alert_type || "ws_alert",
                            title: title,
                            message: msg,
                            urgency: data.priority === "critical" ? "expired" : (data.priority === "high" ? "almost-expiring" : "new"),
                            time_ago: "Just now",
                            acknowledged: false,
                            voice_url: data.voice_url || null,
                        });
                        self.playChime();
                        if (data.voice_url) self._playVoice(data.voice_url);
                        // Also schedule a feed refresh to sync DB state
                        self.scheduleRefresh();
                        return;
                    }
                    // Persistent voice alert pushed over WebSocket
                    if (data.type === "voice_alert") {
                        const audioUrl = data.audio_url || data.voice_url || null;
                        const title = data.title || data.message || "Voice Alert";
                        self.pushNotification({
                            id: data.id || ("va_" + Date.now()),
                            type: "voice_alert",
                            title: title,
                            message: data.message || "",
                            urgency: "new",
                            time_ago: "Just now",
                            acknowledged: false,
                            voice_url: audioUrl,
                        });
                        self.playChime();
                        if (audioUrl) self._playVoice(audioUrl);
                        self.scheduleRefresh();
                        return;
                    }
                };
                ws.onerror = () => { if (ws) ws.close(); };
                ws.onclose = () => {
                    self._ws = null;
                    self._wsConnected = false;
                    scheduleReconnect();
                };
            }
            function scheduleReconnect() {
                if (self._wsStopped || document.hidden || !navigator.onLine) return;
                clearTimeout(self._wsRetryTimer);
                self._wsRetryTimer = window.setTimeout(connect, self._wsRetryDelay);
                self._wsRetryDelay = Math.min(self._wsRetryDelay * 2, 30000);
            }
            document.addEventListener("visibilitychange", () => {
                if (document.hidden) {
                    if (self._ws) self._ws.close();
                    return;
                }
                if (!self._ws) connect();
            });
            window.addEventListener("online", () => { if (!self._ws) connect(); });
            window.addEventListener("beforeunload", () => {
                self._wsStopped = true;
                clearTimeout(self._wsRetryTimer);
                if (self._ws) self._ws.close();
            }, { once: true });
            connect();
        },

        _playVoice(url) {
            if (!url) return;
            // Respect browser autoplay policy — errors are silently ignored
            try {
                const audio = new Audio(url);
                audio.play().catch(() => {/* autoplay blocked; user will see voice button */});
            } catch (_) { /* ignore */ }
        },

        scheduleRefresh() {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = window.setTimeout(() => this.fetchNotifications(), 100);
        },

        init() {
            if (this.initialized) return;
            this.initialized = true;
            // The feed may refresh in the background, but it never opens the
            // drawer or restores an old open state from browser storage.
            dropdown.hidden = true;
            dropdown.setAttribute("aria-hidden", "true");
            btn.setAttribute("aria-expanded", "false");
            this.fetchNotifications();
            this.connectWebSocket();
            btn.addEventListener("click", () => this.fetchNotifications());
            dropdown.addEventListener("click", event => {
                const voiceBtn = event.target.closest("[data-notification-voice]");
                if (voiceBtn) {
                    event.stopPropagation();
                    const src = voiceBtn.dataset.notificationVoice;
                    if (src) {
                        const icon = voiceBtn.querySelector("i");
                        if (icon) icon.className = "fa-solid fa-spinner fa-spin";
                        const audio = new Audio(src);
                        audio.play()
                            .then(() => {
                                if (icon) icon.className = "fa-solid fa-volume-high";
                            })
                            .catch(err => {
                                console.warn("[VoiceAlert] Playback notice:", err);
                                if (icon) icon.className = "fa-solid fa-volume-high";
                                window.open(src, "_blank");
                            });
                    }
                    return;
                }
                const button = event.target.closest("[data-notification-ack]");
                if (button) this.ack(button.dataset.notificationAck);
            });
            window.addEventListener("focus", () => {
                if (!document.hidden) this.fetchNotifications();
            });
            window.addEventListener("qad:resume", () => this.fetchNotifications());
            window.addEventListener("qad:data-changed", () => this.scheduleRefresh());
        }
    };

    window.GlobalNotifications = api;
    window.CA_Notifications = api;
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => api.init(), { once: true });
    } else {
        api.init();
    }
})();
