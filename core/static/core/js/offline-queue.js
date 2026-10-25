/**
 * QAD Offline Queue Engine
 * ─────────────────────────
 * IndexedDB-backed queue for offline-first form submissions.
 * When the network is down, mutating requests (POST/PUT/PATCH/DELETE)
 * are stored locally and automatically replayed when connectivity restores.
 *
 * Architecture:
 *   1.  Monkey-patches window.fetch() to intercept network failures
 *   2.  Stores request payloads in IndexedDB (qad_offline_store)
 *   3.  On "online" event, replays all queued requests in FIFO order
 *   4.  Emits custom events for UI indicators (badge count, toast)
 *   5.  Service Worker can also trigger replay via Background Sync API
 */
(function () {
    "use strict";

    // ─── Constants ───────────────────────────────────────────
    var DB_NAME = "qad_offline_store";
    var DB_VERSION = 1;
    var STORE_NAME = "pending_requests";
    var SYNC_TAG = "qad-offline-sync";

    // Paths that should NEVER be queued (auth, session, health)
    var EXCLUDED_PATHS = [
        "/accounts/login/",
        "/accounts/logout/",
        "/accounts/session-check/",
        "/health/",
        "/health/live/",
        "/health/ready/",
        "/sw.js",
        "/manifest.json"
    ];

    // Only queue mutating methods
    var QUEUABLE_METHODS = ["POST", "PUT", "PATCH", "DELETE"];

    // ─── IndexedDB Helpers ───────────────────────────────────
    var dbPromise = null;

    function openDB() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise(function (resolve, reject) {
            var req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = function (e) {
                var db = e.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    var store = db.createObjectStore(STORE_NAME, { keyPath: "id", autoIncrement: true });
                    store.createIndex("timestamp", "timestamp", { unique: false });
                    store.createIndex("url", "url", { unique: false });
                }
            };
            req.onsuccess = function (e) { resolve(e.target.result); };
            req.onerror = function (e) { reject(e.target.error); };
        });
        return dbPromise;
    }

    function addToQueue(entry) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readwrite");
                var store = tx.objectStore(STORE_NAME);
                var req = store.add(entry);
                req.onsuccess = function () {
                    resolve(req.result);
                    emitQueueUpdate();
                };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    function getAllQueued() {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readonly");
                var store = tx.objectStore(STORE_NAME);
                var req = store.getAll();
                req.onsuccess = function () { resolve(req.result || []); };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    function removeFromQueue(id) {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readwrite");
                var store = tx.objectStore(STORE_NAME);
                var req = store.delete(id);
                req.onsuccess = function () {
                    resolve();
                    emitQueueUpdate();
                };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    function clearQueue() {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readwrite");
                var store = tx.objectStore(STORE_NAME);
                var req = store.clear();
                req.onsuccess = function () {
                    resolve();
                    emitQueueUpdate();
                };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    function getQueueCount() {
        return openDB().then(function (db) {
            return new Promise(function (resolve, reject) {
                var tx = db.transaction(STORE_NAME, "readonly");
                var store = tx.objectStore(STORE_NAME);
                var req = store.count();
                req.onsuccess = function () { resolve(req.result); };
                req.onerror = function () { reject(req.error); };
            });
        });
    }

    // ─── Custom Event Emitter ────────────────────────────────
    function emitQueueUpdate() {
        getQueueCount().then(function (count) {
            window.dispatchEvent(new CustomEvent("qad-offline-queue-update", {
                detail: { count: count }
            }));
        }).catch(function () {});
    }

    function emitSyncStatus(status, message) {
        window.dispatchEvent(new CustomEvent("qad-offline-sync-status", {
            detail: { status: status, message: message }
        }));
    }

    // ─── Path Exclusion Check ────────────────────────────────
    function isExcludedPath(url) {
        try {
            var u = new URL(url, window.location.origin);
            var path = u.pathname;
            for (var i = 0; i < EXCLUDED_PATHS.length; i++) {
                if (path === EXCLUDED_PATHS[i] || path.startsWith(EXCLUDED_PATHS[i])) {
                    return true;
                }
            }
            return false;
        } catch (e) {
            return true;
        }
    }

    // ─── Serialize Request for Storage ───────────────────────
    function serializeRequest(url, options) {
        var entry = {
            url: url,
            method: (options.method || "POST").toUpperCase(),
            timestamp: Date.now(),
            headers: {},
            body: null,
            contentType: null,
            formOrigin: window.location.pathname
        };

        // Serialize headers
        if (options.headers) {
            if (options.headers instanceof Headers) {
                options.headers.forEach(function (value, key) {
                    // Skip cookie headers; CSRF token is included separately
                    if (key.toLowerCase() !== "cookie") {
                        entry.headers[key] = value;
                    }
                });
            } else if (typeof options.headers === "object") {
                for (var key in options.headers) {
                    if (options.headers.hasOwnProperty(key) && key.toLowerCase() !== "cookie") {
                        entry.headers[key] = options.headers[key];
                    }
                }
            }
        }

        // Serialize body
        if (options.body) {
            if (typeof options.body === "string") {
                entry.body = options.body;
                entry.contentType = "string";
            } else if (options.body instanceof URLSearchParams) {
                entry.body = options.body.toString();
                entry.contentType = "urlsearchparams";
            } else if (options.body instanceof FormData) {
                // Convert FormData to serializable object
                var formObj = {};
                options.body.forEach(function (value, key) {
                    // Skip File objects — they cannot be serialized
                    if (value instanceof File) {
                        formObj[key] = { _file: true, name: value.name, type: value.type, size: value.size };
                    } else {
                        formObj[key] = value;
                    }
                });
                entry.body = JSON.stringify(formObj);
                entry.contentType = "formdata";
            } else if (options.body instanceof Blob) {
                entry.body = null; // Cannot serialize Blobs easily
                entry.contentType = "blob_skipped";
            } else {
                try {
                    entry.body = JSON.stringify(options.body);
                    entry.contentType = "json";
                } catch (e) {
                    entry.body = String(options.body);
                    entry.contentType = "string";
                }
            }
        }

        return entry;
    }

    // ─── Reconstruct Request from Storage ────────────────────
    function reconstructRequest(entry) {
        var options = {
            method: entry.method,
            headers: new Headers(entry.headers || {}),
            credentials: "same-origin"
        };

        // Reconstruct body
        if (entry.body) {
            switch (entry.contentType) {
                case "formdata":
                    var fd = new FormData();
                    try {
                        var obj = JSON.parse(entry.body);
                        for (var key in obj) {
                            if (obj.hasOwnProperty(key) && !(obj[key] && obj[key]._file)) {
                                fd.append(key, obj[key]);
                            }
                        }
                    } catch (e) {}
                    options.body = fd;
                    // Remove Content-Type so browser sets multipart boundary
                    options.headers.delete("Content-Type");
                    break;
                case "urlsearchparams":
                    options.body = entry.body;
                    break;
                default:
                    options.body = entry.body;
                    break;
            }
        }

        // Refresh CSRF token from cookie
        var csrfToken = getCSRFToken();
        if (csrfToken) {
            options.headers.set("X-CSRFToken", csrfToken);
        }

        return new Request(entry.url, options);
    }

    function getCSRFToken() {
        // From cookie
        var name = "csrftoken=";
        var cookies = document.cookie.split(";");
        for (var i = 0; i < cookies.length; i++) {
            var c = cookies[i].trim();
            if (c.indexOf(name) === 0) return c.substring(name.length);
        }
        // From meta tag
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    // ─── Monkey-Patch fetch() ────────────────────────────────
    var originalFetch = window.fetch;

    window.fetch = function (input, init) {
        var url = typeof input === "string" ? input : (input instanceof Request ? input.url : String(input));
        var options = init || {};
        var method = (options.method || (input instanceof Request ? input.method : "GET")).toUpperCase();

        // Only intercept queuable methods for same-origin, non-excluded paths
        if (QUEUABLE_METHODS.indexOf(method) === -1 || isExcludedPath(url)) {
            return originalFetch.apply(this, arguments);
        }

        // Check if cross-origin
        try {
            var requestUrl = new URL(url, window.location.origin);
            if (requestUrl.origin !== window.location.origin) {
                return originalFetch.apply(this, arguments);
            }
        } catch (e) {
            return originalFetch.apply(this, arguments);
        }

        // If already offline, queue immediately
        if (!navigator.onLine) {
            console.info("[QAD Offline] Offline — queueing:", method, url);
            var entry = serializeRequest(url, options);
            return addToQueue(entry).then(function () {
                requestBackgroundSync();
                emitSyncStatus("queued", "Saved offline. Will sync when connected.");
                // Return a synthetic "queued" response so the UI doesn't break
                return new Response(JSON.stringify({
                    success: true,
                    offline_queued: true,
                    message: "Saved offline. Will sync automatically when connection restores."
                }), {
                    status: 200,
                    headers: { "Content-Type": "application/json" }
                });
            });
        }

        // Online: try the real fetch, queue on network failure
        return originalFetch.apply(this, arguments).catch(function (error) {
            // Network error (server unreachable, DNS failure, etc.)
            console.warn("[QAD Offline] Network error — queueing:", method, url, error.message);
            var entry = serializeRequest(url, options);
            return addToQueue(entry).then(function () {
                requestBackgroundSync();
                emitSyncStatus("queued", "Network error. Saved locally — will retry.");
                return new Response(JSON.stringify({
                    success: true,
                    offline_queued: true,
                    message: "Saved offline. Will sync automatically when connection restores."
                }), {
                    status: 200,
                    headers: { "Content-Type": "application/json" }
                });
            });
        });
    };

    // ─── Background Sync Registration ────────────────────────
    function requestBackgroundSync() {
        if ("serviceWorker" in navigator && "SyncManager" in window) {
            navigator.serviceWorker.ready.then(function (registration) {
                return registration.sync.register(SYNC_TAG);
            }).catch(function (err) {
                console.warn("[QAD Offline] Background sync registration failed:", err);
            });
        }
    }

    // ─── Replay Queue (FIFO) ─────────────────────────────────
    var isSyncing = false;

    function replayQueue() {
        if (isSyncing || !navigator.onLine) return Promise.resolve();
        isSyncing = true;

        emitSyncStatus("syncing", "Syncing offline data…");

        return getAllQueued().then(function (items) {
            if (!items.length) {
                isSyncing = false;
                emitSyncStatus("idle", "");
                return;
            }

            console.info("[QAD Offline] Replaying", items.length, "queued request(s)…");

            // Process sequentially to preserve order
            var chain = Promise.resolve();
            var successCount = 0;
            var failCount = 0;

            items.forEach(function (item) {
                chain = chain.then(function () {
                    var request = reconstructRequest(item);

                    return originalFetch(request).then(function (response) {
                        if (response.ok || response.status === 302 || response.status === 301) {
                            successCount++;
                            return removeFromQueue(item.id);
                        } else if (response.status >= 400 && response.status < 500) {
                            // Client error (validation, 404, etc.) — remove to prevent infinite retry
                            console.warn("[QAD Offline] Request permanently failed:", item.url, response.status);
                            failCount++;
                            return removeFromQueue(item.id);
                        } else {
                            // Server error — keep in queue for retry
                            console.warn("[QAD Offline] Server error, will retry:", item.url, response.status);
                            failCount++;
                        }
                    }).catch(function (err) {
                        // Still offline or network error — stop processing
                        console.warn("[QAD Offline] Replay failed, stopping:", err.message);
                        failCount++;
                        throw err; // Break the chain
                    });
                });
            });

            return chain.then(function () {
                isSyncing = false;
                var msg = successCount + " record(s) synced successfully.";
                if (failCount > 0) msg += " " + failCount + " failed.";
                emitSyncStatus("complete", msg);
                emitQueueUpdate();
            }).catch(function () {
                isSyncing = false;
                emitSyncStatus("partial", successCount + " synced. Remaining will retry.");
                emitQueueUpdate();
            });
        }).catch(function (err) {
            isSyncing = false;
            console.error("[QAD Offline] Replay error:", err);
            emitSyncStatus("error", "Sync failed. Will retry.");
        });
    }

    // ─── Native Form Interception (when offline) ─────────────
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.tagName || form.tagName.toLowerCase() !== "form") return;

        var method = (form.method || "GET").toUpperCase();
        if (QUEUABLE_METHODS.indexOf(method) === -1) return;

        var action = form.action || window.location.href;
        if (isExcludedPath(action)) return;

        // If offline, catch the form submission, store in IndexedDB, and provide instant UI confirmation
        if (!navigator.onLine) {
            event.preventDefault();
            event.stopPropagation();

            var formData = new FormData(form);
            var formObj = {};
            formData.forEach(function (value, key) {
                if (value instanceof File) {
                    formObj[key] = { _file: true, name: value.name, type: value.type, size: value.size };
                } else {
                    formObj[key] = value;
                }
            });

            var entry = {
                url: action,
                method: method,
                timestamp: Date.now(),
                headers: {},
                body: JSON.stringify(formObj),
                contentType: "formdata",
                formOrigin: window.location.pathname
            };

            var csrfToken = getCSRFToken();
            if (csrfToken) {
                entry.headers["X-CSRFToken"] = csrfToken;
            }

            addToQueue(entry).then(function () {
                requestBackgroundSync();
                showOfflineToast("Saved Locally", "Internet connection is down. Your submission is saved safely on this device and will automatically sync once connection is restored.", "warning");
                emitSyncStatus("queued", "Form saved offline.");
                var submitBtn = form.querySelector('[type="submit"]');
                if (submitBtn) {
                    var originalHtml = submitBtn.innerHTML;
                    submitBtn.disabled = true;
                    submitBtn.innerHTML = '✓ Saved Offline';
                    setTimeout(function () {
                        submitBtn.disabled = false;
                        submitBtn.innerHTML = originalHtml;
                    }, 3500);
                }
            }).catch(function (err) {
                console.error("[QAD Offline] Failed to queue form:", err);
                showOfflineToast("Storage Error", "Could not save locally: " + err.message, "danger");
            });
        }
    }, true);

    // ─── Offline UI Toast & Sync Pill ────────────────────────
    function showOfflineToast(title, message, variant) {
        if (!document.body) return;
        var existing = document.querySelector(".pwa-offline-toast");
        if (existing) existing.remove();

        var toast = document.createElement("div");
        toast.className = "pwa-offline-toast" + (variant ? " toast-" + variant : "");
        var icon = variant === "success" ? "✓" : "⚡";

        toast.innerHTML =
            '<div class="pwa-offline-toast-icon">' + icon + '</div>' +
            '<div class="pwa-offline-toast-content">' +
                '<div class="pwa-offline-toast-title">' + title + '</div>' +
                '<div class="pwa-offline-toast-message">' + message + '</div>' +
            '</div>' +
            '<button type="button" class="pwa-offline-toast-close" aria-label="Close">&times;</button>';

        var closeBtn = toast.querySelector(".pwa-offline-toast-close");
        if (closeBtn) {
            closeBtn.addEventListener("click", function () { toast.remove(); });
        }

        document.body.appendChild(toast);
        setTimeout(function () {
            if (toast.parentNode) {
                toast.style.transition = "opacity 0.3s ease, transform 0.3s ease";
                toast.style.opacity = "0";
                toast.style.transform = "translateX(-50%) translateY(-20px)";
                setTimeout(function () { if (toast.parentNode) toast.remove(); }, 300);
            }
        }, 6000);
    }

    var syncPill = null;
    function ensureSyncPill() {
        if (!document.body || syncPill) return syncPill;
        syncPill = document.createElement("div");
        syncPill.id = "pwa-sync-pill";
        syncPill.style.display = "none";
        document.body.appendChild(syncPill);
        return syncPill;
    }

    function renderSyncPill(count, state, statusText) {
        var pill = ensureSyncPill();
        if (!pill) return;

        pill.className = "";

        if (!navigator.onLine) {
            pill.style.display = "inline-flex";
            pill.className = "status-offline";
            var text = count > 0
                ? "⚡ Offline — " + count + " change(s) saved locally"
                : "⚡ Offline Mode — Local data active";
            pill.innerHTML = '<span>' + text + '</span>';
            return;
        }

        if (state === "syncing") {
            pill.style.display = "inline-flex";
            pill.className = "status-syncing";
            pill.innerHTML = '<span class="pill-icon-spin">↻</span><span>' + (statusText || "Syncing offline data…") + '</span>';
            return;
        }

        if (state === "complete") {
            pill.style.display = "inline-flex";
            pill.className = "status-synced";
            pill.innerHTML = '<span>✓ ' + (statusText || "All data synced!") + '</span>';
            setTimeout(function () {
                if (pill && pill.classList.contains("status-synced")) {
                    pill.style.display = "none";
                }
            }, 3500);
            return;
        }

        if (count > 0) {
            pill.style.display = "inline-flex";
            pill.className = "status-pending";
            pill.innerHTML =
                '<span>⚡ ' + count + ' record(s) pending sync</span>' +
                '<button type="button" class="pill-action" id="pwa-sync-now-btn">Sync Now</button>';
            var btn = pill.querySelector("#pwa-sync-now-btn");
            if (btn) {
                btn.addEventListener("click", function (e) {
                    e.preventDefault();
                    replayQueue();
                });
            }
            return;
        }

        pill.style.display = "none";
    }

    window.addEventListener("qad-offline-queue-update", function (e) {
        var count = (e.detail && typeof e.detail.count === "number") ? e.detail.count : 0;
        renderSyncPill(count, isSyncing ? "syncing" : "idle");
    });

    window.addEventListener("qad-offline-sync-status", function (e) {
        var detail = e.detail || {};
        getQueueCount().then(function (count) {
            renderSyncPill(count, detail.status, detail.message);
            if (detail.status === "complete") {
                showOfflineToast("Sync Complete", detail.message, "success");
            }
        });
    });

    window.addEventListener("offline", function () {
        getQueueCount().then(function (count) {
            renderSyncPill(count, "idle");
            showOfflineToast("Connection Offline", "You are disconnected from the network. Data entered will be saved locally on this device.", "warning");
        });
    });

    // ─── Auto-Replay on Connectivity Restore ─────────────────
    window.addEventListener("online", function () {
        console.info("[QAD Offline] Connection restored — replaying queue…");
        setTimeout(replayQueue, 1500);
    });

    // ─── Listen for SW Messages ──────────────────────────────
    if ("serviceWorker" in navigator) {
        navigator.serviceWorker.addEventListener("message", function (event) {
            if (event.data && event.data.type === "REPLAY_QUEUE") {
                replayQueue();
            }
            if (event.data && event.data.type === "QUEUE_UPDATED") {
                emitQueueUpdate();
            }
        });
    }

    // ─── Public API ──────────────────────────────────────────
    window.QADOfflineQueue = {
        getCount: getQueueCount,
        getAll: getAllQueued,
        replay: replayQueue,
        clear: clearQueue,
        emitUpdate: emitQueueUpdate,
        showToast: showOfflineToast
    };

    // ─── Initial Check ───────────────────────────────────────
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            emitQueueUpdate();
            if (navigator.onLine) {
                setTimeout(replayQueue, 2000);
            }
        }, { once: true });
    } else {
        emitQueueUpdate();
        if (navigator.onLine) {
            setTimeout(replayQueue, 2000);
        }
    }

})();
