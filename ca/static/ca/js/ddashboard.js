<script>
(function () {

    "use strict";


    /* =========================================================
       CONFIGURATION
    ========================================================== */

    const DASHBOARD_URL =
        window.location.href;


    /* =========================================================
       SCROLL
    ========================================================== */

    window.scrollToSection =
        function (id) {

            const element =
                document.getElementById(id);

            if (!element) {
                return;
            }

            element.scrollIntoView({
                behavior: "smooth",
                block: "center"
            });
        };


    /* =========================================================
       TOAST
    ========================================================== */

    function toast(
        message,
        type = "info"
    ) {

        const container =
            document.getElementById(
                "toast-container"
            );

        if (!container) {
            return;
        }

        const item =
            document.createElement("div");

        item.className =
            "toast toast-" + type;

        item.textContent =
            message;

        container.appendChild(item);

        window.setTimeout(
            function () {

                item.style.opacity = "0";

                item.style.transform =
                    "translateY(8px)";

                window.setTimeout(
                    function () {
                        item.remove();
                    },
                    180
                );

            },
            4300
        );
    }


    /* =========================================================
       LOCAL TIME
    ========================================================== */

    function renderLocalTimes() {

        document
            .querySelectorAll(
                ".local-time[data-time]"
            )
            .forEach(
                function (element) {

                    const value =
                        element.dataset.time;

                    if (!value) {
                        return;
                    }

                    const date =
                        new Date(value);

                    if (
                        Number.isNaN(
                            date.getTime()
                        )
                    ) {
                        return;
                    }

                    element.textContent =
                        new Intl.DateTimeFormat(
                            undefined,
                            {
                                dateStyle:
                                    "medium",

                                timeStyle:
                                    "short"
                            }
                        ).format(date);
                }
            );
    }


    /* =========================================================
       COOKIE / CSRF
    ========================================================== */

    function getCookie(name) {

        const cookies =
            document.cookie
                .split(";")
                .map(
                    value =>
                        value.trim()
                );

        for (
            const cookie
            of cookies
        ) {

            if (
                cookie.startsWith(
                    name + "="
                )
            ) {

                return decodeURIComponent(
                    cookie.substring(
                        name.length + 1
                    )
                );

            }

        }

        return null;
    }


    /* =========================================================
       WORKFLOW ACTIONS
    ========================================================== */

    document
        .querySelectorAll(
            ".workflow-action-form"
        )
        .forEach(
            function (form) {

                form.addEventListener(
                    "submit",
                    async function (event) {

                        event.preventDefault();


                        const button =
                            form.querySelector(
                                "button[type='submit']"
                            );


                        if (!button) {
                            return;
                        }


                        const originalHTML =
                            button.innerHTML;


                        button.disabled =
                            true;


                        button.innerHTML =
                            '<span class="spinner"></span> Processing…';


                        form.classList.add(
                            "is-loading"
                        );


                        try {

                            const response =
                                await fetch(
                                    form.action ||
                                    DASHBOARD_URL,
                                    {
                                        method:
                                            "POST",

                                        body:
                                            new FormData(
                                                form
                                            ),

                                        headers: {

                                            "X-Requested-With":
                                                "XMLHttpRequest",

                                            "Accept":
                                                "application/json",

                                            "X-CSRFToken":
                                                getCookie(
                                                    "csrftoken"
                                                )
                                        },

                                        credentials:
                                            "same-origin"
                                    }
                                );


                            const contentType =
                                response.headers
                                    .get(
                                        "content-type"
                                    ) || "";


                            if (
                                !contentType.includes(
                                    "application/json"
                                )
                            ) {

                                if (
                                    response.redirected
                                ) {

                                    window.location.href =
                                        response.url;

                                } else {

                                    window.location.reload();

                                }

                                return;
                            }


                            const payload =
                                await response.json();


                            if (
                                !response.ok ||
                                !payload.success
                            ) {

                                throw new Error(
                                    payload.error ||
                                    payload.message ||
                                    "Workflow action failed."
                                );

                            }


                            toast(
                                payload.result?.message ||
                                payload.message ||
                                "Workflow action completed.",
                                "success"
                            );


                            window.setTimeout(
                                function () {

                                    if (
                                        payload.redirect_url
                                    ) {

                                        window.location.href =
                                            payload.redirect_url;

                                    } else {

                                        window.location.reload();

                                    }

                                },
                                650
                            );


                        } catch (error) {

                            console.error(
                                "Workflow action error:",
                                error
                            );


                            toast(
                                error.message ||
                                "Unable to execute workflow action.",
                                "error"
                            );


                            button.disabled =
                                false;


                            button.innerHTML =
                                originalHTML;


                            form.classList.remove(
                                "is-loading"
                            );

                        }

                    }
                );

            }
        );


    /* =========================================================
       PROCESS SEARCH
    ========================================================== */

    const processSearch =
        document.getElementById(
            "processSearch"
        );


    if (processSearch) {

        processSearch.addEventListener(
            "input",
            function () {

                const query =
                    this.value
                        .trim()
                        .toLowerCase();


                document
                    .querySelectorAll(
                        "#processList .process-item"
                    )
                    .forEach(
                        function (item) {

                            const text =
                                (
                                    item.dataset.processSearch ||
                                    item.textContent ||
                                    ""
                                ).toLowerCase();


                            item.style.display =
                                !query ||
                                text.includes(query)
                                    ? ""
                                    : "none";

                        }
                    );

            }
        );

    }


    /* =========================================================
       HTMX
    ========================================================== */

    document.body.addEventListener(
        "htmx:beforeRequest",
        function (event) {

            const element =
                event.detail?.elt;

            if (element) {

                element.classList.add(
                    "is-loading"
                );

            }

        }
    );


    document.body.addEventListener(
        "htmx:afterRequest",
        function (event) {

            const element =
                event.detail?.elt;

            if (element) {

                element.classList.remove(
                    "is-loading"
                );

            }

        }
    );


    document.body.addEventListener(
        "htmx:responseError",
        function () {

            toast(
                "The server rejected the workflow request.",
                "error"
            );

        }
    );


    /* =========================================================
       STATISTICS
    ========================================================== */

    const statistics = {

        total:
            Number(
                "{{ statistics.total|default:0 }}"
            ),

        active:
            Number(
                "{{ statistics.active|default:0 }}"
            ),

        completed:
            Number(
                "{{ statistics.completed_today|default:0 }}"
            ),

        overdue:
            Number(
                "{{ statistics.overdue|default:0 }}"
            ),

        failed:
            Number(
                "{{ statistics.failed_batches|default:0 }}"
            ),

        qa:
            Number(
                "{{ statistics.awaiting_qa|default:0 }}"
            ),

        approval:
            Number(
                "{{ statistics.awaiting_approval|default:0 }}"
            ),

        retests:
            Number(
                "{{ statistics.retests|default:0 }}"
            ),

        escalated:
            Number(
                "{{ statistics.escalated|default:0 }}"
            )
    };


    /* =========================================================
       CHART DEFAULTS
    ========================================================== */

    if (
        typeof Chart !==
        "undefined"
    ) {

        Chart.defaults.font.family =
            "Inter, system-ui, sans-serif";

        Chart.defaults.font.size =
            10;

        Chart.defaults.color =
            "#8ea3b9";

    }


    /* =========================================================
       WORKFLOW BAR CHART
    ========================================================== */

    const workflowCanvas =
        document.getElementById(
            "workflowAnalyticsChart"
        );


    if (
        workflowCanvas &&
        typeof Chart !== "undefined"
    ) {

        new Chart(
            workflowCanvas,
            {

                type:
                    "bar",

                data: {

                    labels: [

                        "Active",
                        "Completed",
                        "Overdue",
                        "Failed",
                        "QA",
                        "Approval",
                        "Retests",
                        "Escalated"

                    ],

                    datasets: [

                        {

                            label:
                                "Workflow Population",

                            data: [

                                statistics.active,
                                statistics.completed,
                                statistics.overdue,
                                statistics.failed,
                                statistics.qa,
                                statistics.approval,
                                statistics.retests,
                                statistics.escalated

                            ],

                            borderWidth:
                                1,

                            borderRadius:
                                7,

                            maxBarThickness:
                                42

                        }

                    ]

                },


                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },


                    plugins: {

                        legend: {
                            display:
                                false
                        },

                        tooltip: {

                            callbacks: {

                                label:
                                    function (
                                        context
                                    ) {

                                        return (
                                            " " +
                                            context.parsed.y +
                                            " process" +
                                            (
                                                context.parsed.y === 1
                                                    ? ""
                                                    : "es"
                                            )
                                        );

                                    }

                            }

                        }

                    },


                    scales: {

                        x: {

                            ticks: {

                                color:
                                    "#8ea3b9",

                                maxRotation:
                                    35,

                                minRotation:
                                    0

                            },

                            grid: {

                                color:
                                    "rgba(148,163,184,.06)"

                            }

                        },


                        y: {

                            beginAtZero:
                                true,

                            ticks: {

                                precision:
                                    0,

                                color:
                                    "#8ea3b9"

                            },

                            grid: {

                                color:
                                    "rgba(148,163,184,.07)"

                            }

                        }

                    }

                }

            }
        );

    }


    /* =========================================================
       HEALTH DOUGHNUT
    ========================================================== */

    const healthCanvas =
        document.getElementById(
            "workflowHealthChart"
        );


    if (
        healthCanvas &&
        typeof Chart !== "undefined"
    ) {

        const healthy =
            Math.max(
                statistics.active -
                statistics.failed -
                statistics.overdue,
                0
            );


        const risk =
            statistics.failed +
            statistics.overdue;


        const queues =
            statistics.qa +
            statistics.approval;


        new Chart(
            healthCanvas,
            {

                type:
                    "doughnut",

                data: {

                    labels: [

                        "Healthy / Active",
                        "Risk",
                        "Controlled Queues"

                    ],

                    datasets: [

                        {

                            data: [

                                healthy,
                                risk,
                                queues

                            ],

                            borderWidth:
                                0,

                            hoverOffset:
                                5

                        }

                    ]

                },


                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    cutout:
                        "68%",

                    plugins: {

                        legend: {

                            position:
                                "bottom",

                            labels: {

                                color:
                                    "#8ea3b9",

                                boxWidth:
                                    10,

                                boxHeight:
                                    10,

                                padding:
                                    12

                            }

                        }

                    }

                }

            }
        );

    }


    /* =========================================================
       LOCAL TIME + INITIALIZATION
    ========================================================== */

    renderLocalTimes();


    /* =========================================================
       PAGE VISIBILITY
    ========================================================== */

    document.addEventListener(
        "visibilitychange",
        function () {

            if (
                document.visibilityState ===
                "visible"
            ) {

                renderLocalTimes();

            }

        }
    );

})();
</script>