(() => {
    "use strict";

    const root = document.querySelector("[data-ca-dashboard]");

    if (!root) {
        return;
    }

    const config = {
        refreshInterval: parseInt(
            root.dataset.refreshInterval || "30000",
            10
        ),
        processUrlTemplate:
            root.dataset.processUrlTemplate ||
            "/ca/process/{id}/json/",
        dashboardUrl:
            root.dataset.dashboardUrl ||
            window.location.pathname,
        csrfToken:
            document.querySelector(
                "[name=csrfmiddlewaretoken]"
            )?.value ||
            getCookie("csrftoken"),
        autoRefresh:
            root.dataset.autoRefresh !== "false",
    };

    const state = {
        refreshTimer: null,
        refreshInProgress: false,
        selectedProcessId: null,
        selectedBatchId: null,
        activePanel:
            localStorage.getItem("ca-dashboard-panel") ||
            root.dataset.defaultPanel ||
            "overview",
        filters: {},
        charts: {},
        requestController: null,
        lastRefresh: null,
        processCache: new Map(),
    };

    const selectors = {
        panel:
            "[data-dashboard-panel]",
        panelTrigger:
            "[data-dashboard-panel-trigger]",
        refresh:
            "[data-dashboard-refresh]",
        autoRefresh:
            "[data-dashboard-auto-refresh]",
        process:
            "[data-process-id]",
        processAction:
            "[data-process-action]",
        processOpen:
            "[data-process-open]",
        batchOpen:
            "[data-batch-open]",
        modal:
            "[data-ca-modal]",
        modalClose:
            "[data-ca-modal-close]",
        modalBody:
            "[data-ca-modal-body]",
        modalTitle:
            "[data-ca-modal-title]",
        processDrawer:
            "[data-process-drawer]",
        processDrawerClose:
            "[data-process-drawer-close]",
        processDrawerBody:
            "[data-process-drawer-body]",
        filter:
            "[data-dashboard-filter]",
        search:
            "[data-dashboard-search]",
        queue:
            "[data-workflow-queue]",
        liveRegion:
            "[data-dashboard-live-region]",
        chart:
            "[data-ca-chart]",
        table:
            "[data-ca-table]",
        row:
            "[data-ca-row]",
        loading:
            "[data-dashboard-loading]",
        empty:
            "[data-dashboard-empty]",
    };

    document.addEventListener("DOMContentLoaded", init);

    if (document.readyState !== "loading") {
        init();
    }

    function init() {
        if (root.dataset.caDashboardInitialized === "true") {
            return;
        }

        root.dataset.caDashboardInitialized = "true";

        initializePanels();
        initializeFilters();
        initializeSearch();
        initializeWorkflowActions();
        initializeProcessNavigation();
        initializeModals();
        initializeTables();
        initializeCharts();
        initializeHTMX();
        initializeKeyboardShortcuts();
        initializeAutoRefresh();
        initializeLiveClock();
        updateLastRefresh();
    }

    function initializePanels() {
        const triggers = document.querySelectorAll(
            selectors.panelTrigger
        );

        triggers.forEach((trigger) => {
            trigger.addEventListener("click", () => {
                const panelName =
                    trigger.dataset.dashboardPanelTrigger;

                if (!panelName) {
                    return;
                }

                activatePanel(panelName);
            });
        });

        activatePanel(state.activePanel, false);
    }

    function activatePanel(panelName, updateUrl = true) {
        const panels = document.querySelectorAll(
            selectors.panel
        );

        if (!panels.length) {
            return;
        }

        let found = false;

        panels.forEach((panel) => {
            const current =
                panel.dataset.dashboardPanel === panelName;

            panel.hidden = !current;
            panel.setAttribute(
                "aria-hidden",
                current ? "false" : "true"
            );

            if (current) {
                panel.classList.add("is-active");
                found = true;
            } else {
                panel.classList.remove("is-active");
            }
        });

        document
            .querySelectorAll(
                selectors.panelTrigger
            )
            .forEach((trigger) => {
                const current =
                    trigger.dataset.dashboardPanelTrigger ===
                    panelName;

                trigger.classList.toggle(
                    "is-active",
                    current
                );

                trigger.setAttribute(
                    "aria-selected",
                    current ? "true" : "false"
                );
            });

        if (!found) {
            return;
        }

        state.activePanel = panelName;

        localStorage.setItem(
            "ca-dashboard-panel",
            panelName
        );

        if (updateUrl) {
            const url = new URL(
                window.location.href
            );

            url.searchParams.set(
                "panel",
                panelName
            );

            window.history.replaceState(
                {},
                "",
                url
            );
        }

        dispatchEvent("dashboard:panel-changed", {
            panel: panelName,
        });

        requestAnimationFrame(() => {
            initializeCharts(
                document.querySelector(
                    `[data-dashboard-panel="${escapeSelector(panelName)}"]`
                )
            );
        });
    }

    function initializeFilters() {
        document
            .querySelectorAll(selectors.filter)
            .forEach((filter) => {
                filter.addEventListener(
                    "change",
                    debounce(() => {
                        collectFilters();
                        applyClientFilters();
                        refreshDashboard();
                    }, 250)
                );
            });

        collectFilters();
    }

    function collectFilters() {
        state.filters = {};

        document
            .querySelectorAll(selectors.filter)
            .forEach((element) => {
                const name =
                    element.name ||
                    element.dataset.filterName;

                if (!name) {
                    return;
                }

                state.filters[name] =
                    element.value;
            });
    }

    function initializeSearch() {
        document
            .querySelectorAll(selectors.search)
            .forEach((input) => {
                input.addEventListener(
                    "input",
                    debounce(() => {
                        applyClientFilters(
                            input.value
                        );
                    }, 150)
                );
            });
    }

    function applyClientFilters(searchValue = null) {
        const search =
            searchValue !== null
                ? searchValue.trim().toLowerCase()
                : getGlobalSearchValue();

        document
            .querySelectorAll(selectors.row)
            .forEach((row) => {
                const haystack = (
                    row.textContent || ""
                ).toLowerCase();

                const matchesSearch =
                    !search ||
                    haystack.includes(search);

                let matchesFilters = true;

                Object.entries(state.filters)
                    .forEach(([name, value]) => {
                        if (!value) {
                            return;
                        }

                        const rowValue =
                            row.dataset[
                                `filter${capitalize(name)}`
                            ];

                        if (
                            rowValue !== undefined &&
                            rowValue !== value
                        ) {
                            matchesFilters = false;
                        }
                    });

                row.hidden =
                    !matchesSearch ||
                    !matchesFilters;
            });

        updateEmptyTableStates();
    }

    function getGlobalSearchValue() {
        const input =
            document.querySelector(
                `${selectors.search}[data-global-search]`
            ) ||
            document.querySelector(
                selectors.search
            );

        return input
            ? input.value.trim().toLowerCase()
            : "";
    }

    function updateEmptyTableStates() {
        document
            .querySelectorAll(selectors.table)
            .forEach((table) => {
                const rows = Array.from(
                    table.querySelectorAll(
                        selectors.row
                    )
                );

                if (!rows.length) {
                    return;
                }

                const visibleRows =
                    rows.filter(
                        (row) => !row.hidden
                    );

                const empty =
                    table.querySelector(
                        selectors.empty
                    );

                if (empty) {
                    empty.hidden =
                        visibleRows.length > 0;
                }
            });
    }

    function initializeWorkflowActions() {
        document.addEventListener(
            "click",
            async (event) => {
                const actionElement =
                    event.target.closest(
                        selectors.processAction
                    );

                if (!actionElement) {
                    return;
                }

                event.preventDefault();

                await executeWorkflowAction(
                    actionElement
                );
            }
        );
    }

    async function executeWorkflowAction(
        element
    ) {
        const url =
            element.dataset.actionUrl ||
            element.getAttribute("href");

        const method = (
            element.dataset.actionMethod ||
            "POST"
        ).toUpperCase();

        const confirmation =
            element.dataset.actionConfirm;

        if (!url) {
            return;
        }

        if (
            confirmation &&
            !window.confirm(confirmation)
        ) {
            return;
        }

        const originalDisabled =
            element.disabled;

        element.disabled = true;

        setBusy(element, true);

        try {
            const response =
                await request(url, {
                    method,
                    body:
                        method === "GET"
                            ? undefined
                            : buildActionBody(
                                  element
                              ),
                });

            const payload =
                await parseResponse(
                    response
                );

            if (!response.ok) {
                throw new Error(
                    extractErrorMessage(
                        payload,
                        response.statusText
                    )
                );
            }

            handleActionSuccess(
                element,
                payload
            );
        } catch (error) {
            showError(
                error.message ||
                    "The workflow action could not be completed."
            );
        } finally {
            element.disabled =
                originalDisabled;
            setBusy(element, false);
        }
    }

    function buildActionBody(element) {
        const form =
            element.closest("form");

        if (form) {
            return new FormData(form);
        }

        const data = new FormData();

        const processId =
            element.dataset.processId;

        const batchId =
            element.dataset.batchId;

        if (processId) {
            data.append(
                "process_id",
                processId
            );
        }

        if (batchId) {
            data.append(
                "batch_id",
                batchId
            );
        }

        if (config.csrfToken) {
            data.append(
                "csrfmiddlewaretoken",
                config.csrfToken
            );
        }

        return data;
    }

    function handleActionSuccess(
        element,
        payload
    ) {
        const message =
            payload?.message ||
            "Workflow action completed successfully.";

        showSuccess(message);

        dispatchEvent(
            "workflow:action-completed",
            {
                element,
                payload,
            }
        );

        if (
            payload?.redirect_url
        ) {
            if (
                element.dataset.actionRedirect !==
                "false"
            ) {
                window.location.href =
                    payload.redirect_url;
                return;
            }
        }

        refreshDashboard();

        const processId =
            element.dataset.processId ||
            payload?.process_id;

        if (processId) {
            refreshProcess(
                processId,
                true
            );
        }
    }

    function initializeProcessNavigation() {
        document.addEventListener(
            "click",
            (event) => {
                const openButton =
                    event.target.closest(
                        selectors.processOpen
                    );

                if (
                    openButton
                ) {
                    event.preventDefault();

                    const processId =
                        openButton.dataset.processId;

                    if (processId) {
                        openProcessDrawer(
                            processId
                        );
                    }

                    return;
                }

                const batchButton =
                    event.target.closest(
                        selectors.batchOpen
                    );

                if (
                    batchButton
                ) {
                    const url =
                        batchButton.dataset.batchUrl ||
                        batchButton.getAttribute(
                            "href"
                        );

                    if (url) {
                        window.location.href =
                            url;
                    }
                }
            }
        );
    }

    async function openProcessDrawer(
        processId
    ) {
        state.selectedProcessId =
            processId;

        const drawer =
            document.querySelector(
                selectors.processDrawer
            );

        if (!drawer) {
            return;
        }

        drawer.classList.add(
            "is-open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "false"
        );

        document.body.classList.add(
            "ca-drawer-open"
        );

        showDrawerLoading();

        try {
            const data =
                await refreshProcess(
                    processId,
                    false
                );

            renderProcessDrawer(
                data
            );
        } catch (error) {
            renderDrawerError(
                error.message
            );
        }
    }

    function closeProcessDrawer() {
        const drawer =
            document.querySelector(
                selectors.processDrawer
            );

        if (!drawer) {
            return;
        }

        drawer.classList.remove(
            "is-open"
        );

        drawer.setAttribute(
            "aria-hidden",
            "true"
        );

        document.body.classList.remove(
            "ca-drawer-open"
        );

        state.selectedProcessId =
            null;
    }

    function initializeModals() {
        document.addEventListener(
            "click",
            (event) => {
                const close =
                    event.target.closest(
                        selectors.modalClose
                    );

                if (close) {
                    event.preventDefault();
                    closeModal(
                        close.closest(
                            selectors.modal
                        )
                    );
                    return;
                }

                const modal =
                    event.target.closest(
                        selectors.modal
                    );

                if (
                    modal &&
                    event.target === modal
                ) {
                    closeModal(modal);
                }
            }
        );

        document
            .querySelectorAll(
                selectors.processDrawerClose
            )
            .forEach((button) => {
                button.addEventListener(
                    "click",
                    closeProcessDrawer
                );
            });
    }

    function openModal(
        modal,
        title,
        html
    ) {
        if (!modal) {
            return;
        }

        const titleElement =
            modal.querySelector(
                selectors.modalTitle
            );

        const body =
            modal.querySelector(
                selectors.modalBody
            );

        if (titleElement) {
            titleElement.textContent =
                title || "";
        }

        if (body) {
            body.innerHTML =
                html || "";
        }

        modal.hidden = false;

        requestAnimationFrame(() => {
            modal.classList.add(
                "is-open"
            );
        });

        document.body.classList.add(
            "ca-modal-open"
        );
    }

    function closeModal(modal) {
        if (!modal) {
            return;
        }

        modal.classList.remove(
            "is-open"
        );

        window.setTimeout(() => {
            modal.hidden = true;
        }, 150);

        document.body.classList.remove(
            "ca-modal-open"
        );
    }

    function showDrawerLoading() {
        const body =
            document.querySelector(
                selectors.processDrawerBody
            );

        if (body) {
            body.innerHTML = `
                <div class="ca-loading-state">
                    <div class="ca-spinner"></div>
                    <span>Loading workflow state…</span>
                </div>
            `;
        }
    }

    function renderDrawerError(
        message
    ) {
        const body =
            document.querySelector(
                selectors.processDrawerBody
            );

        if (!body) {
            return;
        }

        body.innerHTML = `
            <div class="ca-alert ca-alert-danger">
                <strong>Unable to load process.</strong>
                <div>${escapeHtml(
                    message
                )}</div>
            </div>
        `;
    }

    function renderProcessDrawer(
        process
    ) {
        const body =
            document.querySelector(
                selectors.processDrawerBody
            );

        if (!body) {
            return;
        }

        const sampling =
            process.sampling;

        const coa =
            process.coa;

        const results =
            process.results || [];

        const counts =
            calculateResultCounts(
                results
            );

        body.innerHTML = `
            <div class="ca-process-summary">

                <div class="ca-process-summary-header">
                    <div>
                        <span class="ca-eyebrow">
                            Process #${escapeHtml(
                                process.id
                            )}
                        </span>

                        <h3>
                            ${escapeHtml(
                                process.batch_sample_id ||
                                    process.sample_id ||
                                    `Batch ${process.batch_id}`
                            )}
                        </h3>
                    </div>

                    <span class="ca-status-badge ca-status-${slug(
                        process.status
                    )}">
                        ${escapeHtml(
                            humanize(process.status)
                        )}
                    </span>
                </div>

                <div class="ca-process-metrics">
                    ${metric(
                        "Results",
                        results.length
                    )}

                    ${metric(
                        "Passed",
                        counts.PASS
                    )}

                    ${metric(
                        "Failed",
                        counts.FAIL
                    )}

                    ${metric(
                        "Pending",
                        counts.PENDING
                    )}
                </div>

                <div class="ca-process-section">
                    <h4>Workflow state</h4>

                    <div class="ca-workflow-state">
                        ${workflowState(
                            process
                        )}
                    </div>
                </div>

                <div class="ca-process-section">
                    <h4>Sampling</h4>
                    ${
                        sampling
                            ? samplingMarkup(
                                  sampling
                              )
                            : emptyState(
                                  "No sampling record."
                              )
                    }
                </div>

                <div class="ca-process-section">
                    <h4>Certificate of Analysis</h4>
                    ${
                        coa
                            ? coaMarkup(coa)
                            : emptyState(
                                  "No Certificate of Analysis."
                              )
                    }
                </div>

                <div class="ca-process-section">
                    <h4>Test results</h4>

                    ${
                        results.length
                            ? resultsMarkup(
                                  results
                              )
                            : emptyState(
                                  "No test results recorded."
                              )
                    }
                </div>

                <div class="ca-process-actions">
                    ${renderAvailableActions(
                        process
                    )}
                </div>
            </div>
        `;

        bindDynamicActionButtons(
            body
        );
    }

    function renderAvailableActions(
        process
    ) {
        const actions =
            process.available_actions ||
            process.actions ||
            [];

        if (
            !Array.isArray(actions) ||
            !actions.length
        ) {
            return "";
        }

        return actions
            .map((action) => {
                if (
                    typeof action ===
                    "string"
                ) {
                    return "";
                }

                return `
                    <button
                        type="button"
                        class="ca-button ca-button-primary"
                        data-process-action
                        data-process-id="${escapeHtml(
                            process.id
                        )}"
                        data-action-url="${escapeHtml(
                            action.url || ""
                        )}"
                        data-action-method="${escapeHtml(
                            action.method || "POST"
                        )}"
                        ${
                            action.confirm
                                ? `data-action-confirm="${escapeHtml(
                                      action.confirm
                                  )}"`
                                : ""
                        }
                    >
                        ${escapeHtml(
                            action.label ||
                                humanize(
                                    action.key
                                )
                        )}
                    </button>
                `;
            })
            .join("");
    }

    function bindDynamicActionButtons(
        container
    ) {
        container
            .querySelectorAll(
                selectors.processAction
            )
            .forEach((button) => {
                button.addEventListener(
                    "click",
                    async () => {
                        await executeWorkflowAction(
                            button
                        );
                    }
                );
            });
    }

    async function refreshProcess(
        processId,
        rerender = true
    ) {
        if (!processId) {
            return null;
        }

        const url =
            config.processUrlTemplate.replace(
                "{id}",
                encodeURIComponent(
                    processId
                )
            );

        const response =
            await request(url, {
                method: "GET",
                signal:
                    createAbortSignal(),
            });

        const data =
            await parseResponse(
                response
            );

        if (!response.ok) {
            throw new Error(
                extractErrorMessage(
                    data,
                    "Unable to retrieve process state."
                )
            );
        }

        state.processCache.set(
            String(processId),
            data
        );

        if (rerender) {
            renderProcessDrawer(
                data
            );
        }

        updateProcessRows(
            data
        );

        return data;
    }

    function updateProcessRows(
        process
    ) {
        document
            .querySelectorAll(
                `[data-process-id="${escapeSelector(
                    String(process.id)
                )}"]`
            )
            .forEach((element) => {
                const status =
                    element.querySelector(
                        "[data-process-status]"
                    );

                if (status) {
                    status.textContent =
                        humanize(
                            process.status
                        );

                    status.className =
                        `${status.className.replace(
                            /ca-status-[^\s]+/g,
                            ""
                        )} ca-status-${slug(
                            process.status
                        )}`.trim();
                }

                element.dataset.processStatus =
                    process.status;
            });
    }

    function initializeTables() {
        document
            .querySelectorAll(
                "[data-sortable-table]"
            )
            .forEach(
                initializeSortableTable
            );

        updateEmptyTableStates();
    }

    function initializeSortableTable(
        table
    ) {
        const headers =
            table.querySelectorAll(
                "[data-sort-key]"
            );

        headers.forEach((header) => {
            header.setAttribute(
                "role",
                "button"
            );
            header.tabIndex = 0;

            const handler = () => {
                sortTable(
                    table,
                    header.dataset.sortKey,
                    header.dataset.sortType ||
                        "text"
                );
            };

            header.addEventListener(
                "click",
                handler
            );

            header.addEventListener(
                "keydown",
                (event) => {
                    if (
                        event.key ===
                            "Enter" ||
                        event.key ===
                            " "
                    ) {
                        event.preventDefault();
                        handler();
                    }
                }
            );
        });
    }

    function sortTable(
        table,
        key,
        type
    ) {
        const tbody =
            table.querySelector(
                "tbody"
            );

        if (!tbody) {
            return;
        }

        const rows = Array.from(
            tbody.querySelectorAll(
                selectors.row
            )
        );

        const direction =
            table.dataset.sortDirection ===
            "asc"
                ? -1
                : 1;

        table.dataset.sortDirection =
            direction === 1
                ? "asc"
                : "desc";

        rows.sort((a, b) => {
            const av =
                a.dataset[
                    `sort${capitalize(
                        key
                    )}`
                ] ??
                a.querySelector(
                    `[data-sort-value="${escapeSelector(
                        key
                    )}"]`
                )?.textContent ??
                "";

            const bv =
                b.dataset[
                    `sort${capitalize(
                        key
                    )}`
                ] ??
                b.querySelector(
                    `[data-sort-value="${escapeSelector(
                        key
                    )}"]`
                )?.textContent ??
                "";

            return (
                compareValues(
                    av,
                    bv,
                    type
                ) * direction
            );
        });

        rows.forEach((row) =>
            tbody.appendChild(row)
        );
    }

    function compareValues(
        a,
        b,
        type
    ) {
        if (type === "number") {
            return (
                parseFloat(a || 0) -
                parseFloat(b || 0)
            );
        }

        if (type === "date") {
            return (
                new Date(a).getTime() -
                new Date(b).getTime()
            );
        }

        return String(a).localeCompare(
            String(b),
            undefined,
            {
                numeric: true,
                sensitivity: "base",
            }
        );
    }

    function initializeCharts(
        scope = document
    ) {
        const charts =
            scope.querySelectorAll(
                selectors.chart
            );

        charts.forEach((chart) => {
            renderChart(chart);
        });
    }

    function renderChart(
        element
    ) {
        if (
            element.dataset.chartInitialized ===
            "true"
        ) {
            return;
        }

        const type =
            element.dataset.chartType ||
            "bar";

        const labels =
            parseJSONAttribute(
                element,
                "chartLabels"
            );

        const values =
            parseJSONAttribute(
                element,
                "chartValues"
            );

        if (
            !Array.isArray(labels) ||
            !Array.isArray(values)
        ) {
            return;
        }

        if (
            window.Chart
        ) {
            renderChartJS(
                element,
                type,
                labels,
                values
            );

            return;
        }

        renderNativeChart(
            element,
            type,
            labels,
            values
        );
    }

    function renderChartJS(
        element,
        type,
        labels,
        values
    ) {
        const canvas =
            element.tagName ===
            "CANVAS"
                ? element
                : element.querySelector(
                      "canvas"
                  );

        if (!canvas) {
            return;
        }

        const ctx =
            canvas.getContext(
                "2d"
            );

        if (
            state.charts[
                element
            ]
        ) {
            state.charts[
                element
            ].destroy();
        }

        const chartType =
            normalizeChartType(
                type
            );

        state.charts[element] =
            new window.Chart(
                ctx,
                {
                    type: chartType,
                    data: {
                        labels,
                        datasets: [
                            {
                                label:
                                    element
                                        .dataset
                                        .chartLabel ||
                                    "Count",
                                data: values,
                                borderWidth: 1,
                                tension: 0.25,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: {
                            duration: 250,
                        },
                        plugins: {
                            legend: {
                                display:
                                    element
                                        .dataset
                                        .chartLegend ===
                                    "true",
                            },
                        },
                        scales:
                            chartType ===
                                "pie" ||
                            chartType ===
                                "doughnut"
                                ? {}
                                : {
                                      y: {
                                          beginAtZero:
                                              true,
                                      },
                                  },
                    },
                }
            );

        element.dataset.chartInitialized =
            "true";
    }

    function renderNativeChart(
        element,
        type,
        labels,
        values
    ) {
        const max =
            Math.max(
                ...values.map(
                    (value) =>
                        Number(value) || 0
                ),
                1
            );

        element.innerHTML = `
            <div class="ca-native-chart ca-native-chart-${escapeHtml(
                type
            )}">
                ${labels
                    .map(
                        (
                            label,
                            index
                        ) => {
                            const value =
                                Number(
                                    values[
                                        index
                                    ]
                                ) || 0;

                            const width =
                                Math.max(
                                    2,
                                    (value /
                                        max) *
                                        100
                                );

                            return `
                                <div class="ca-chart-row">
                                    <div class="ca-chart-label">
                                        ${escapeHtml(
                                            label
                                        )}
                                    </div>

                                    <div class="ca-chart-track">
                                        <div
                                            class="ca-chart-bar"
                                            style="width:${width}%"
                                        ></div>
                                    </div>

                                    <div class="ca-chart-value">
                                        ${escapeHtml(
                                            value
                                        )}
                                    </div>
                                </div>
                            `;
                        }
                    )
                    .join("")}
            </div>
        `;

        element.dataset.chartInitialized =
            "true";
    }

    function initializeHTMX() {
        if (
            !window.htmx
        ) {
            return;
        }

        document.body.addEventListener(
            "htmx:afterSwap",
            () => {
                initializePanels();
                initializeFilters();
                initializeSearch();
                initializeTables();
                initializeCharts();
                bindDynamicActionButtons(
                    document
                );
                updateEmptyTableStates();
            }
        );

        document.body.addEventListener(
            "htmx:responseError",
            (event) => {
                const response =
                    event.detail?.xhr;

                showError(
                    response
                        ? `Request failed (${response.status}).`
                        : "Workflow request failed."
                );
            }
        );
    }

    function initializeKeyboardShortcuts() {
        document.addEventListener(
            "keydown",
            (event) => {
                if (
                    event.target.matches(
                        "input, textarea, select"
                    )
                ) {
                    return;
                }

                if (
                    event.key === "Escape"
                ) {
                    closeProcessDrawer();

                    document
                        .querySelectorAll(
                            selectors.modal
                        )
                        .forEach(
                            closeModal
                        );

                    return;
                }

                if (
                    event.key === "r" &&
                    !event.ctrlKey &&
                    !event.metaKey
                ) {
                    event.preventDefault();
                    refreshDashboard();
                }

                if (
                    event.key >= "1" &&
                    event.key <= "9"
                ) {
                    const index =
                        Number(
                            event.key
                        ) - 1;

                    const triggers =
                        Array.from(
                            document.querySelectorAll(
                                selectors.panelTrigger
                            )
                        );

                    const trigger =
                        triggers[index];

                    if (trigger) {
                        trigger.click();
                    }
                }
            }
        );
    }

    function initializeAutoRefresh() {
        const toggle =
            document.querySelector(
                selectors.autoRefresh
            );

        if (toggle) {
            toggle.checked =
                config.autoRefresh;

            toggle.addEventListener(
                "change",
                () => {
                    config.autoRefresh =
                        toggle.checked;

                    if (
                        toggle.checked
                    ) {
                        startAutoRefresh();
                    } else {
                        stopAutoRefresh();
                    }
                }
            );
        }

        if (
            config.autoRefresh
        ) {
            startAutoRefresh();
        }

        document
            .querySelectorAll(
                selectors.refresh
            )
            .forEach((button) => {
                button.addEventListener(
                    "click",
                    () =>
                        refreshDashboard(
                            true
                        )
                );
            });
    }

    function startAutoRefresh() {
        stopAutoRefresh();

        state.refreshTimer =
            window.setInterval(
                () => {
                    if (
                        document.visibilityState ===
                        "visible"
                    ) {
                        refreshDashboard();
                    }
                },
                config.refreshInterval
            );
    }

    function stopAutoRefresh() {
        if (
            state.refreshTimer
        ) {
            window.clearInterval(
                state.refreshTimer
            );

            state.refreshTimer =
                null;
        }
    }

    async function refreshDashboard(
        manual = false
    ) {
        if (
            state.refreshInProgress
        ) {
            return;
        }

        state.refreshInProgress =
            true;

        setDashboardLoading(
            true
        );

        try {
            collectFilters();

            const url =
                buildDashboardURL();

            if (
                window.htmx &&
                root.dataset.refreshMode ===
                    "htmx"
            ) {
                window.htmx.ajax(
                    "GET",
                    url,
                    {
                        target:
                            root,
                        swap:
                            "outerHTML",
                    }
                );

                return;
            }

            const response =
                await request(
                    url,
                    {
                        method: "GET",
                        headers: {
                            Accept:
                                "text/html",
                            "X-CA-Dashboard-Refresh":
                                "true",
                        },
                    }
                );

            if (!response.ok) {
                throw new Error(
                    `Dashboard refresh failed (${response.status}).`
                );
            }

            const html =
                await response.text();

            replaceDashboardHTML(
                html
            );

            state.lastRefresh =
                new Date();

            updateLastRefresh();

            dispatchEvent(
                "dashboard:refreshed",
                {
                    manual,
                }
            );
        } catch (error) {
            showError(
                error.message ||
                    "Unable to refresh dashboard."
            );
        } finally {
            state.refreshInProgress =
                false;

            setDashboardLoading(
                false
            );
        }
    }

    function buildDashboardURL() {
        const url =
            new URL(
                config.dashboardUrl,
                window.location.origin
            );

        Object.entries(
            state.filters
        ).forEach(
            ([name, value]) => {
                if (
                    value !==
                    undefined &&
                    value !== null &&
                    value !== ""
                ) {
                    url.searchParams.set(
                        name,
                        value
                    );
                } else {
                    url.searchParams.delete(
                        name
                    );
                }
            }
        );

        if (
            state.activePanel
        ) {
            url.searchParams.set(
                "panel",
                state.activePanel
            );
        }

        return url.toString();
    }

    function replaceDashboardHTML(
        html
    ) {
        const parser =
            new DOMParser();

        const documentFragment =
            parser.parseFromString(
                html,
                "text/html"
            );

        const newRoot =
            documentFragment.querySelector(
                "[data-ca-dashboard]"
            );

        if (!newRoot) {
            return;
        }

        root.replaceWith(
            newRoot
        );

        const replacement =
            document.querySelector(
                "[data-ca-dashboard]"
            );

        if (!replacement) {
            return;
        }

        initializeReplacement(
            replacement
        );
    }

    function initializeReplacement(
        replacement
    ) {
        replacement.dataset.caDashboardInitialized =
            "false";

        window.setTimeout(
            () => {
                if (
                    replacement !==
                    root
                ) {
                    window.location.reload();
                    return;
                }

                init();
            },
            0
        );
    }

    function setDashboardLoading(
        loading
    ) {
        document
            .querySelectorAll(
                selectors.loading
            )
            .forEach((element) => {
                element.hidden =
                    !loading;
            });

        document
            .querySelectorAll(
                selectors.refresh
            )
            .forEach((button) => {
                button.disabled =
                    loading;
                button.classList.toggle(
                    "is-loading",
                    loading
                );
            });
    }

    function updateLastRefresh() {
        document
            .querySelectorAll(
                "[data-dashboard-last-refresh]"
            )
            .forEach((element) => {
                const date =
                    state.lastRefresh ||
                    new Date();

                element.textContent =
                    formatDateTime(
                        date
                    );

                element.setAttribute(
                    "datetime",
                    date.toISOString()
                );
            });
    }

    function initializeLiveClock() {
        const update =
            () => {
                const now =
                    new Date();

                document
                    .querySelectorAll(
                        "[data-dashboard-clock]"
                    )
                    .forEach(
                        (element) => {
                            element.textContent =
                                formatTime(
                                    now
                                );
                        }
                    );
            };

        update();

        window.setInterval(
            update,
            1000
        );
    }

    function showSuccess(
        message
    ) {
        showNotification(
            message,
            "success"
        );
    }

    function showError(
        message
    ) {
        showNotification(
            message,
            "danger"
        );
    }

    function showNotification(
        message,
        type
    ) {
        const region =
            document.querySelector(
                selectors.liveRegion
            );

        if (!region) {
            return;
        }

        const notification =
            document.createElement(
                "div"
            );

        notification.className =
            `ca-alert ca-alert-${type}`;

        notification.setAttribute(
            "role",
            "status"
        );

        notification.innerHTML = `
            <span>
                ${escapeHtml(
                    message
                )}
            </span>

            <button
                type="button"
                class="ca-alert-close"
                aria-label="Dismiss"
            >
                ×
            </button>
        `;

        notification
            .querySelector(
                ".ca-alert-close"
            )
            ?.addEventListener(
                "click",
                () => {
                    notification.remove();
                }
            );

        region.prepend(
            notification
        );

        window.setTimeout(
            () => {
                notification.remove();
            },
            7000
        );
    }

    function setBusy(
        element,
        busy
    ) {
        element.classList.toggle(
            "is-loading",
            busy
        );

        element.setAttribute(
            "aria-busy",
            busy ? "true" : "false"
        );
    }

    async function request(
        url,
        options = {}
    ) {
        const headers =
            new Headers(
                options.headers || {}
            );

        headers.set(
            "X-Requested-With",
            "XMLHttpRequest"
        );

        if (
            config.csrfToken &&
            !headers.has(
                "X-CSRFToken"
            )
        ) {
            headers.set(
                "X-CSRFToken",
                config.csrfToken
            );
        }

        return fetch(url, {
            credentials: "same-origin",
            ...options,
            headers,
        });
    }

    async function parseResponse(
        response
    ) {
        const contentType =
            response.headers.get(
                "content-type"
            ) || "";

        if (
            contentType.includes(
                "application/json"
            )
        ) {
            return response.json();
        }

        const text =
            await response.text();

        return {
            html: text,
            message:
                response.ok
                    ? null
                    : text,
        };
    }

    function extractErrorMessage(
        payload,
        fallback
    ) {
        if (!payload) {
            return fallback;
        }

        if (
            typeof payload ===
            "string"
        ) {
            return payload;
        }

        return (
            payload.message ||
            payload.error ||
            payload.detail ||
            fallback
        );
    }

    function createAbortSignal() {
        if (
            state.requestController
        ) {
            state.requestController.abort();
        }

        state.requestController =
            new AbortController();

        return (
            state.requestController
                .signal
        );
    }

    function dispatchEvent(
        name,
        detail = {}
    ) {
        document.dispatchEvent(
            new CustomEvent(
                name,
                {
                    detail,
                }
            )
        );
    }

    function calculateResultCounts(
        results
    ) {
        return results.reduce(
            (counts, result) => {
                const status =
                    String(
                        result.status ||
                            "PENDING"
                    ).toUpperCase();

                counts[status] =
                    (counts[status] ||
                        0) + 1;

                return counts;
            },
            {
                PASS: 0,
                FAIL: 0,
                NA: 0,
                PENDING: 0,
            }
        );
    }

    function workflowState(
        process
    ) {
        const states = [
            "CREATED",
            "RECEIVED",
            "REQUESTED",
            "CHECKLIST",
            "ASSIGNED",
            "SYSTEMATIC_RANDOM_SAMPLING",
            "ANALYSIS",
            "RETEST",
            "QA",
            "CAPA",
            "APPROVED",
            "REJECTED",
            "UTILIZED",
            "RETURNED",
            "COMPLETED",
        ];

        const current =
            states.indexOf(
                process.status
            );

        return states
            .map(
                (
                    status,
                    index
                ) => `
                    <div
                        class="ca-workflow-step ${
                            index <
                            current
                                ? "is-complete"
                                : ""
                        } ${
                            index ===
                            current
                                ? "is-current"
                                : ""
                        }"
                    >
                        <span class="ca-workflow-step-marker">
                            ${
                                index <
                                current
                                    ? "✓"
                                    : index ===
                                      current
                                    ? "●"
                                    : "○"
                            }
                        </span>

                        <span>
                            ${escapeHtml(
                                humanize(
                                    status
                                )
                            )}
                        </span>
                    </div>
                `
            )
            .join("");
    }

    function samplingMarkup(
        sampling
    ) {
        return `
            <div class="ca-inline-grid">
                ${metric(
                    "Status",
                    humanize(
                        sampling.status
                    )
                )}

                ${metric(
                    "Samples",
                    sampling.sample_count ??
                        0
                )}

                ${metric(
                    "Interval",
                    sampling.sampling_interval ??
                        "—"
                )}

                ${metric(
                    "Random start",
                    sampling.random_start ??
                        "—"
                )}

                ${metric(
                    "QA",
                    sampling.qa_required
                        ? sampling.qa_approved
                            ? "Approved"
                            : "Required"
                        : "Not required"
                )}
            </div>
        `;
    }

    function coaMarkup(
        coa
    ) {
        return `
            <div class="ca-inline-grid">
                ${metric(
                    "Approval",
                    coa.is_approved
                        ? "Approved"
                        : "Pending"
                )}

                ${metric(
                    "Integrity",
                    coa.integrity_status ||
                        "Unknown"
                )}

                ${metric(
                    "PDF",
                    coa.pdf_available
                        ? "Available"
                        : "Missing"
                )}

                ${metric(
                    "QR",
                    coa.qr_available
                        ? "Available"
                        : "Missing"
                )}
            </div>
        `;
    }

    function resultsMarkup(
        results
    ) {
        return `
            <div class="ca-result-list">
                ${results
                    .map(
                        (result) => `
                            <div
                                class="ca-result-row"
                                data-result-id="${escapeHtml(
                                    result.id
                                )}"
                            >
                                <div>
                                    <strong>
                                        ${escapeHtml(
                                            result.parameter_name ||
                                                result.parameter__parameter_name ||
                                                "Parameter"
                                        )}
                                    </strong>
                                </div>

                                <span class="ca-status-badge ca-status-${slug(
                                    result.status
                                )}">
                                    ${escapeHtml(
                                        humanize(
                                            result.status
                                        )
                                    )}
                                </span>
                            </div>
                        `
                    )
                    .join("")}
            </div>
        `;
    }

    function metric(
        label,
        value
    ) {
        return `
            <div class="ca-inline-metric">
                <span class="ca-inline-metric-label">
                    ${escapeHtml(
                        label
                    )}
                </span>

                <strong class="ca-inline-metric-value">
                    ${escapeHtml(
                        value ??
                            "—"
                    )}
                </strong>
            </div>
        `;
    }

    function emptyState(
        message
    ) {
        return `
            <div class="ca-empty-state">
                ${escapeHtml(
                    message
                )}
            </div>
        `;
    }

    function parseJSONAttribute(
        element,
        name
    ) {
        const raw =
            element.dataset[name];

        if (!raw) {
            return [];
        }

        try {
            return JSON.parse(
                raw
            );
        } catch {
            return [];
        }
    }

    function normalizeChartType(
        type
    ) {
        const allowed = new Set([
            "bar",
            "line",
            "pie",
            "doughnut",
            "radar",
            "polarArea",
        ]);

        return allowed.has(type)
            ? type
            : "bar";
    }

    function humanize(
        value
    ) {
        if (
            value === null ||
            value === undefined ||
            value === ""
        ) {
            return "—";
        }

        return String(value)
            .toLowerCase()
            .replace(
                /[_-]+/g,
                " "
            )
            .replace(
                /\b\w/g,
                (char) =>
                    char.toUpperCase()
            );
    }

    function slug(
        value
    ) {
        return String(
            value || ""
        )
            .toLowerCase()
            .replace(
                /[^a-z0-9]+/g,
                "-"
            )
            .replace(
                /^-+|-+$/g,
                ""
            );
    }

    function capitalize(
        value
    ) {
        const string =
            String(value);

        return (
            string.charAt(0).toUpperCase() +
            string.slice(1)
        );
    }

    function debounce(
        callback,
        delay
    ) {
        let timer = null;

        return (...args) => {
            window.clearTimeout(
                timer
            );

            timer =
                window.setTimeout(
                    () =>
                        callback(
                            ...args
                        ),
                    delay
                );
        };
    }

    function getCookie(
        name
    ) {
        const cookies =
            document.cookie
                .split(";")
                .map(
                    (cookie) =>
                        cookie.trim()
                );

        const prefix =
            `${name}=`;

        for (
            const cookie of cookies
        ) {
            if (
                cookie.startsWith(
                    prefix
                )
            ) {
                return decodeURIComponent(
                    cookie.slice(
                        prefix.length
                    )
                );
            }
        }

        return null;
    }

    function formatDateTime(
        date
    ) {
        return new Intl.DateTimeFormat(
            undefined,
            {
                dateStyle: "medium",
                timeStyle: "medium",
            }
        ).format(date);
    }

    function formatTime(
        date
    ) {
        return new Intl.DateTimeFormat(
            undefined,
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
            }
        ).format(date);
    }

    function escapeHtml(
        value
    ) {
        if (
            value === null ||
            value === undefined
        ) {
            return "";
        }

        return String(value)
            .replace(
                /&/g,
                "&amp;"
            )
            .replace(
                /</g,
                "&lt;"
            )
            .replace(
                />/g,
                "&gt;"
            )
            .replace(
                /"/g,
                "&quot;"
            )
            .replace(
                /'/g,
                "&#039;"
            );
    }

    function escapeSelector(
        value
    ) {
        if (
            window.CSS &&
            typeof window.CSS
                .escape ===
                "function"
        ) {
            return window.CSS.escape(
                String(value)
            );
        }

        return String(value).replace(
            /([ !"#$%&'()*+,./:;<=>?@[\\\]^`{|}~])/g,
            "\\$1"
        );
    }

    window.CADashboard = {
        refresh: refreshDashboard,

        refreshProcess,

        openProcess:
            openProcessDrawer,

        closeProcess:
            closeProcessDrawer,

        activatePanel,

        openModal,

        closeModal,

        getState() {
            return {
                ...state,
                filters: {
                    ...state.filters,
                },
            };
        },
    };
})();