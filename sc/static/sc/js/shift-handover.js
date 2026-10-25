/**
 * QAD Enterprise — Shift Handover & Takeover Workflow Controller
 * ──────────────────────────────────────────────────────────────
 * Multi-stage modal workflow:
 *   Stage 1: Fill Handover Form (Outgoing Supervisor)
 *   Stage 2: Shift Taking Over Form (Same form, locked/non-editable outgoing data)
 *   Stage 3: Supervisor Credential Authentication Dialog
 *   Transition: Effects the shift transition upon correct password verification.
 */
(function () {
    "use strict";

    // ─── DOM Elements ────────────────────────────────────────
    var handoverBtn = document.getElementById("shiftHandoverBtn");
    var modal = document.getElementById("shiftHandoverModal");
    var authDialog = document.getElementById("shiftAuthDialog");

    if (!handoverBtn || !modal) return;

    var handoverForm = document.getElementById("shiftHandoverForm");
    var takeoverContainer = document.getElementById("shiftTakeoverContainer");
    var authForm = document.getElementById("shiftAuthForm");

    var modalTitle = document.getElementById("shiftModalTitle");
    var modalStageBadge = document.getElementById("shiftModalStageBadge");
    var modalAlertBox = document.getElementById("modalAlertBox");
    var authAlertBox = document.getElementById("authAlertBox");

    var incomingSelect = document.getElementById("incomingSupervisorSelect");
    var outgoingSelect = document.getElementById("outgoingSupervisorSelect");
    var apparatusTbody = document.getElementById("apparatusTableBody");

    var currentHandoverId = null;
    var currentNextShiftData = null;

    // ─── CSRF Helper ─────────────────────────────────────────
    function getCSRFToken() {
        var cookie = document.cookie.split("; ").find(function (row) { return row.startsWith("csrftoken="); });
        if (cookie) return cookie.split("=")[1];
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    // ─── Alert Helpers ───────────────────────────────────────
    function showAlert(el, msg, type) {
        if (!el) return;
        el.className = "shift-alert shift-alert-" + (type || "danger");
        el.textContent = msg;
        el.style.display = "block";
    }

    function hideAlert(el) {
        if (el) el.style.display = "none";
    }

    // ─── Open Modal & Load Telemetry ─────────────────────────
    function openHandoverModal() {
        hideAlert(modalAlertBox);
        hideAlert(authAlertBox);

        // Reset to Stage 1
        modalTitle.textContent = "Shift Handing Over";
        modalStageBadge.textContent = "STAGE 1";
        handoverForm.style.display = "block";
        takeoverContainer.style.display = "none";

        modal.style.display = "grid";
        modal.setAttribute("aria-hidden", "false");

        // Fetch fresh shift and supervisor options
        fetch("/sc/handover/modal-data/", {
            headers: { "Accept": "application/json" }
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            if (!data.success) {
                showAlert(modalAlertBox, data.message || "Failed to load shift information.");
                return;
            }

            // Update top bar telemetry
            if (data.plant) document.getElementById("modalPlantName").textContent = data.plant.name;
            if (data.current_shift) document.getElementById("modalCurrentShiftName").textContent = data.current_shift.name + " (" + data.current_shift.start_time + " – " + data.current_shift.end_time + ")";
            if (data.next_shift) {
                document.getElementById("modalNextShiftName").textContent = data.next_shift.name + " (" + data.next_shift.start_time + " – " + data.next_shift.end_time + ")";
                currentNextShiftData = data.next_shift;
            }
            if (data.handover_window_time) document.getElementById("modalWindowBadge").textContent = data.handover_window_time;

            // Populate outgoing supervisor
            outgoingSelect.innerHTML = "";
            if (data.eligible_outgoing_supervisors && data.eligible_outgoing_supervisors.length > 0) {
                data.eligible_outgoing_supervisors.forEach(function (u) {
                    var opt = document.createElement("option");
                    opt.value = u.id;
                    opt.textContent = u.name + " (" + u.username + ")";
                    if (data.current_supervisor && u.id === data.current_supervisor.id) opt.selected = true;
                    outgoingSelect.appendChild(opt);
                });
            } else if (data.current_supervisor) {
                var opt = document.createElement("option");
                opt.value = data.current_supervisor.id;
                opt.textContent = data.current_supervisor.name + " (" + data.current_supervisor.username + ")";
                opt.selected = true;
                outgoingSelect.appendChild(opt);
            }

            // Populate incoming supervisor dropdown (only users belonging to incoming shift)
            incomingSelect.innerHTML = '<option value="">-- Select Incoming Shift Supervisor --</option>';
            if (data.eligible_incoming_supervisors && data.eligible_incoming_supervisors.length > 0) {
                data.eligible_incoming_supervisors.forEach(function (u) {
                    var opt = document.createElement("option");
                    opt.value = u.id;
                    opt.textContent = u.name + " (" + u.username + ")" + (u.is_superuser ? " [Overseer]" : "");
                    opt.dataset.username = u.username;
                    incomingSelect.appendChild(opt);
                });
            }

            // Populate apparatus checklist
            apparatusTbody.innerHTML = "";
            if (data.apparatus_list && data.apparatus_list.length > 0) {
                data.apparatus_list.forEach(function (app, idx) {
                    var tr = document.createElement("tr");
                    tr.dataset.apparatusId = app.id;
                    tr.innerHTML =
                        '<td><strong>' + app.name + '</strong><br><small style="color:#64748b;">' + (app.description || '') + '</small></td>' +
                        '<td>' +
                            '<div class="apparatus-status-radios">' +
                                '<label class="status-opt-working"><input type="radio" name="status_' + app.id + '" value="working" checked> Working</label>' +
                                '<label class="status-opt-repair"><input type="radio" name="status_' + app.id + '" value="needs_repair"> Needs Repair</label>' +
                                '<label class="status-opt-offline"><input type="radio" name="status_' + app.id + '" value="out_of_service"> Offline</label>' +
                            '</div>' +
                        '</td>' +
                        '<td><input type="text" class="shift-form-control app-remarks" placeholder="Optional notes" style="padding:0.35rem 0.5rem;font-size:0.78rem;"></td>';
                    apparatusTbody.appendChild(tr);
                });
            } else {
                apparatusTbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:#64748b;padding:1rem;">All major apparatus registered in operational status.</td></tr>';
            }
        })
        .catch(function (err) {
            showAlert(modalAlertBox, "Network error loading shift data: " + err.message);
        });
    }

    function closeHandoverModal() {
        modal.style.display = "none";
        modal.setAttribute("aria-hidden", "true");
        if (authDialog) authDialog.style.display = "none";
    }

    // ─── Stage 1: Submit Handover Form ───────────────────────
    handoverForm.addEventListener("submit", function (e) {
        e.preventDefault();
        hideAlert(modalAlertBox);

        var outgoingId = outgoingSelect.value;
        var incomingId = incomingSelect.value;
        var notes = document.getElementById("handoverNotesText").value.trim();
        var pending = document.getElementById("pendingWorkText").value.trim();

        if (!incomingId) {
            showAlert(modalAlertBox, "Please select an incoming shift supervisor.");
            incomingSelect.focus();
            return;
        }

        if (!notes) {
            showAlert(modalAlertBox, "Please provide shift operations and water treatment summary.");
            document.getElementById("handoverNotesText").focus();
            return;
        }

        // Collect apparatus conditions
        var apparatusConditions = [];
        var rows = apparatusTbody.querySelectorAll("tr[data-apparatus-id]");
        rows.forEach(function (tr) {
            var appId = tr.dataset.apparatusId;
            var checkedRadio = tr.querySelector('input[name="status_' + appId + '"]:checked');
            var remarksInput = tr.querySelector(".app-remarks");
            apparatusConditions.push({
                apparatus_id: appId,
                status: checkedRadio ? checkedRadio.value : "working",
                remarks: remarksInput ? remarksInput.value.trim() : ""
            });
        });

        var saveBtn = document.getElementById("saveHandoverBtn");
        var originalBtnHtml = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving Handover…';

        var payload = {
            shift_id: document.getElementById("handoverShiftId").value,
            next_shift_id: document.getElementById("handoverNextShiftId").value,
            outgoing_supervisor_id: outgoingId,
            incoming_supervisor_id: incomingId,
            handover_notes: notes,
            pending_work: pending,
            apparatus_conditions: apparatusConditions
        };

        fetch("/sc/handover/submit/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCSRFToken()
            },
            body: JSON.stringify(payload)
        })
        .then(function (res) { return res.json(); })
        .then(function (data) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalBtnHtml;

            if (!data.success) {
                showAlert(modalAlertBox, data.message || "Failed to save handover.");
                return;
            }

            currentHandoverId = data.handover_id;
            var h = data.handover_data;

            // ─── Immediately Transition to Stage 2: Shift Taking Over ───
            transitionToTakeover(h);
        })
        .catch(function (err) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalBtnHtml;
            showAlert(modalAlertBox, "Submission error: " + err.message);
        });
    });

    // ─── Transition to Stage 2 (Shift Taking Over) ───────────
    function transitionToTakeover(h) {
        modalTitle.textContent = "Shift Taking Over";
        modalStageBadge.textContent = "STAGE 2";
        modalStageBadge.style.background = "#10b981";

        // Fill locked values
        document.getElementById("lockedTimestamp").textContent = "Handed over at " + (h.handed_over_at || "Just now");
        document.getElementById("lockedOutgoingSup").textContent = h.outgoing_supervisor.name + " (" + h.outgoing_supervisor.username + ")";
        document.getElementById("lockedIncomingSup").textContent = h.incoming_supervisor.name + " (" + h.incoming_supervisor.username + ")";
        document.getElementById("lockedPlantShift").textContent = h.plant_name + " — " + h.shift_name + " ➔ " + h.next_shift_name;
        document.getElementById("lockedDate").textContent = h.date;

        document.getElementById("lockedNotes").textContent = h.handover_notes || "None provided.";
        document.getElementById("lockedPending").textContent = h.pending_work || "None reported. Operations normal.";

        // Locked apparatus checklist
        var appList = document.getElementById("lockedApparatusSummary");
        appList.innerHTML = "";
        if (h.apparatus_summary && h.apparatus_summary.length > 0) {
            h.apparatus_summary.forEach(function (item) {
                var div = document.createElement("div");
                div.className = "locked-app-item";
                var badgeClass = item.status === "working" ? "badge-status-working" : (item.status === "needs_repair" ? "badge-status-repair" : "badge-status-offline");
                div.innerHTML =
                    '<span><strong>' + item.apparatus_name + '</strong> ' + (item.remarks ? '<small style="color:#94a3b8;">(' + item.remarks + ')</small>' : '') + '</span>' +
                    '<span class="' + badgeClass + '">' + item.status.toUpperCase().replace("_", " ") + '</span>';
                appList.appendChild(div);
            });
        } else {
            appList.innerHTML = '<span style="color:#64748b;font-size:0.8rem;">All primary plant equipment confirmed in nominal state.</span>';
        }

        // Hide Handover form, show Taking Over view
        handoverForm.style.display = "none";
        takeoverContainer.style.display = "block";
        modalAlertBox.style.display = "none";

        // Scroll to top of modal body
        document.querySelector(".shift-modal-body").scrollTop = 0;
    }

    // ─── Back Button from Stage 2 to Stage 1 ─────────────────
    var backBtn = document.getElementById("backToHandoverBtn");
    if (backBtn) {
        backBtn.addEventListener("click", function () {
            modalTitle.textContent = "Shift Handing Over";
            modalStageBadge.textContent = "STAGE 1";
            modalStageBadge.style.background = "#0284c7";
            takeoverContainer.style.display = "none";
            handoverForm.style.display = "block";
        });
    }

    // ─── Stage 3: Open Authentication Dialog ─────────────────
    var proceedAuthBtn = document.getElementById("proceedToAuthBtn");
    if (proceedAuthBtn) {
        proceedAuthBtn.addEventListener("click", function () {
            var checkLog = document.getElementById("checkPhysicalLog");
            var checkApp = document.getElementById("checkApparatusVerify");

            if ((checkLog && !checkLog.checked) || (checkApp && !checkApp.checked)) {
                showAlert(modalAlertBox, "Please review and acknowledge both takeover compliance verification checkboxes.");
                return;
            }

            hideAlert(authAlertBox);

            // Pre-fill username from selected incoming supervisor
            var selectedOpt = incomingSelect.options[incomingSelect.selectedIndex];
            var username = selectedOpt ? (selectedOpt.dataset.username || selectedOpt.text.split("(")[1]?.replace(")", "") || "") : "";

            document.getElementById("authUsernameInput").value = username.trim();
            document.getElementById("authPasswordInput").value = "";

            authDialog.style.display = "grid";
            authDialog.setAttribute("aria-hidden", "false");
            setTimeout(function () {
                document.getElementById("authPasswordInput").focus();
            }, 100);
        });
    }

    function closeAuthDialog() {
        if (authDialog) {
            authDialog.style.display = "none";
            authDialog.setAttribute("aria-hidden", "true");
        }
    }

    // ─── Stage 3: Submit Authentication & Effect Transition ──
    if (authForm) {
        authForm.addEventListener("submit", function (e) {
            e.preventDefault();
            hideAlert(authAlertBox);

            var username = document.getElementById("authUsernameInput").value.trim();
            var password = document.getElementById("authPasswordInput").value;
            var takeoverNotes = document.getElementById("takeoverNotesText").value.trim();

            if (!username || !password) {
                showAlert(authAlertBox, "Username and password are required.");
                return;
            }

            var confirmBtn = document.getElementById("confirmTransitionBtn");
            var origHtml = confirmBtn.innerHTML;
            confirmBtn.disabled = true;
            confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating…';

            var payload = {
                handover_id: currentHandoverId,
                takeover_notes: takeoverNotes,
                username: username,
                password: password
            };

            fetch("/sc/handover/confirm-takeover/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": getCSRFToken()
                },
                body: JSON.stringify(payload)
            })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = origHtml;

                if (!data.success) {
                    showAlert(authAlertBox, data.message || "Authentication failed. Transition denied.");
                    return;
                }

                // ─── Transition Effected Successfully! ───
                closeAuthDialog();
                closeHandoverModal();

                // Update Header Status Bar live
                if (data.new_shift && data.new_shift.name) {
                    var shiftEl = document.getElementById("headerShiftName");
                    if (shiftEl) shiftEl.textContent = data.new_shift.name;
                }
                if (data.new_supervisor && data.new_supervisor.name) {
                    var supEl = document.getElementById("headerShiftSupervisor");
                    if (supEl) supEl.textContent = data.new_supervisor.name;
                }

                // Toast notification
                if (window.QADOfflineQueue && window.QADOfflineQueue.showToast) {
                    window.QADOfflineQueue.showToast("Shift Transition Completed", data.message, "success");
                } else {
                    alert(data.message);
                }

                // Smooth reload to update full dashboard context after 1.5s
                setTimeout(function () {
                    window.location.reload();
                }, 1500);
            })
            .catch(function (err) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = origHtml;
                showAlert(authAlertBox, "Verification error: " + err.message);
            });
        });
    }

    // ─── Event Delegation for Open/Close ─────────────────────
    document.addEventListener("click", function (event) {
        if (event.target.closest("[data-open-handover-modal]")) {
            event.preventDefault();
            openHandoverModal();
        }
        if (event.target.closest("[data-close-handover-modal]")) {
            event.preventDefault();
            closeHandoverModal();
        }
        if (event.target.closest("[data-close-auth-dialog]")) {
            event.preventDefault();
            closeAuthDialog();
        }
    });

    // Close on Escape key
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            if (authDialog && authDialog.style.display !== "none") {
                closeAuthDialog();
            } else if (modal && modal.style.display !== "none") {
                closeHandoverModal();
            }
        }
    });

})();
