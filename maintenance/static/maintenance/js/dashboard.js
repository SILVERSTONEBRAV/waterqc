(() => {
    "use strict";

    const form = document.getElementById("incident-report-form");
    const dialog = document.getElementById("incident-report-dialog");
    if (!form || !dialog) return;

    const keyField = document.getElementById("incident-submission-key");
    const queueStatus = document.getElementById("incident-queue-status");
    const plantSelect = document.getElementById("incident-report-plant");
    const houseSelect = document.getElementById("incident-report-house");
    const queueKey = `maintenance-incident-queue-v1:${dialog.dataset.queueUser}`;
    let isSending = false;

    function newKey() {
        if (window.crypto && typeof window.crypto.randomUUID === "function") {
            return window.crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
            const random = Math.random() * 16 | 0;
            return (char === "x" ? random : (random & 0x3 | 0x8)).toString(16);
        });
    }

    function readQueue() {
        try {
            const queue = JSON.parse(window.sessionStorage.getItem(queueKey) || "[]");
            return Array.isArray(queue) ? queue : [];
        } catch (_) {
            return [];
        }
    }

    function saveQueue(queue) {
        try {
            if (queue.length) window.sessionStorage.setItem(queueKey, JSON.stringify(queue));
            else window.sessionStorage.removeItem(queueKey);
            return true;
        } catch (_) {
            setStatus("This tab could not save an offline report. Keep it open and retry when connected.", true);
            return false;
        }
    }

    function setStatus(message, isError = false) {
        if (!queueStatus) return;
        queueStatus.textContent = message;
        queueStatus.classList.toggle("is-error", isError);
    }

    function updateQueueStatus(message = "") {
        const count = readQueue().length;
        if (count) {
            setStatus(message || `${count} report${count === 1 ? "" : "s"} queued in this tab${navigator.onLine ? " · syncing when possible" : " · waiting for connection"}.`);
        } else if (message) {
            setStatus(message);
        } else {
            setStatus("No offline reports queued.");
        }
    }

    async function postReport(record) {
        const body = new FormData();
        Object.entries(record).forEach(([name, value]) => body.append(name, value ?? ""));
        const csrf = form.querySelector("[name='csrfmiddlewaretoken']");
        if (csrf) body.append("csrfmiddlewaretoken", csrf.value);

        const response = await fetch(form.action, {
            method: "POST",
            body,
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            return { success: false, retry: response.status >= 500 || response.status === 0, message: "Your session or permissions need attention before this report can sync." };
        }
        const payload = await response.json();
        return {
            success: response.ok && payload.success,
            retry: response.status >= 500,
            message: payload.message || "The report could not be submitted.",
        };
    }

    async function synchronizeQueue() {
        if (isSending || !navigator.onLine) {
            updateQueueStatus();
            return;
        }
        const queue = readQueue();
        if (!queue.length) {
            updateQueueStatus();
            return;
        }
        isSending = true;
        let sent = 0;
        const remaining = [];
        for (const record of queue) {
            try {
                const result = await postReport(record);
                if (result.success) {
                    sent += 1;
                    continue;
                }
                remaining.push(record, ...queue.slice(sent + remaining.length + 1));
                setStatus(result.message, true);
                break;
            } catch (_) {
                remaining.push(record, ...queue.slice(sent + remaining.length + 1));
                setStatus("Connection interrupted. The remaining report is still queued in this tab.", true);
                break;
            }
        }
        saveQueue(remaining);
        isSending = false;
        if (sent && !remaining.length) updateQueueStatus(`${sent} queued report${sent === 1 ? "" : "s"} synchronized.`);
        else if (remaining.length && !queueStatus.classList.contains("is-error")) updateQueueStatus();
        else if (!remaining.length) updateQueueStatus();
    }

    function queueRecord(record) {
        const queue = readQueue();
        if (!queue.some((item) => item.offline_submission_key === record.offline_submission_key)) {
            queue.push(record);
        }
        if (saveQueue(queue)) {
            form.reset();
            keyField.value = newKey();
            updateQueueStatus("Report saved to this tab and will sync when the connection returns.");
        }
    }

    function openDialog() {
        if (!keyField.value) keyField.value = newKey();
        updateQueueStatus();
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "open");
    }

    document.querySelectorAll("[data-open-incident-report]").forEach((button) => {
        button.addEventListener("click", openDialog);
    });
    document.querySelectorAll("[data-close-incident-report]").forEach((button) => {
        button.addEventListener("click", () => dialog.close());
    });

    if (plantSelect && houseSelect) {
        plantSelect.addEventListener("change", () => {
            if (houseSelect.selectedOptions[0]?.dataset.plant !== plantSelect.value) {
                houseSelect.value = "";
            }
        });
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (isSending) return;
        if (!keyField.value) keyField.value = newKey();
        const record = Object.fromEntries(new FormData(form).entries());
        delete record.csrfmiddlewaretoken;

        if (!navigator.onLine) {
            queueRecord(record);
            return;
        }

        isSending = true;
        setStatus("Submitting incident report…");
        try {
            const result = await postReport(record);
            if (result.success) {
                form.reset();
                keyField.value = newKey();
                setStatus(result.message);
                window.setTimeout(() => dialog.close(), 900);
            } else if (result.retry) {
                queueRecord(record);
            } else {
                setStatus(result.message, true);
            }
        } catch (_) {
            queueRecord(record);
        } finally {
            isSending = false;
        }
    });

    window.addEventListener("online", synchronizeQueue);
    window.addEventListener("offline", () => updateQueueStatus());
    keyField.value = newKey();
    synchronizeQueue();
})();
