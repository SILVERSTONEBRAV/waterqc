(() => {
    "use strict";

    const root = document.querySelector(".ca-batch-command");
    if (!root) return;

    const form = root.querySelector("[data-register-filter-form]");
    const table = root.querySelector("[data-batch-register-table]");
    const plantScope = root.querySelector("[data-register-plant-scope]");
    const columnInputs = Array.from(root.querySelectorAll("[data-column-toggle]"));
    const allowedColumns = new Set(columnInputs.map((input) => input.value));
    const storageKey = `ca-batch-register-columns:${root.dataset.registerUser || "user"}`;
    const defaultColumns = new Set(columnInputs.filter((input) => input.checked).map((input) => input.value));

    let visibleColumns = new Set(defaultColumns);
    try {
        const stored = JSON.parse(window.localStorage.getItem(storageKey) || "null");
        if (Array.isArray(stored)) {
            const filtered = stored.filter((key) => allowedColumns.has(key));
            if (filtered.length) visibleColumns = new Set(filtered);
        }
    } catch (_) {
        // Storage may be disabled; the server-provided defaults still work.
    }

    const applyColumns = () => {
        if (table) {
            table.querySelectorAll("[data-column]").forEach((cell) => {
                const key = cell.dataset.column;
                cell.hidden = key !== "actions" && !visibleColumns.has(key);
            });
        }
        columnInputs.forEach((input) => {
            input.checked = visibleColumns.has(input.value);
        });
        try {
            window.localStorage.setItem(storageKey, JSON.stringify(Array.from(visibleColumns)));
        } catch (_) {
            // A private browsing policy can deny writes without affecting the register.
        }
    };
    applyColumns();

    plantScope?.addEventListener("change", () => {
        const params = new URLSearchParams(window.location.search);
        if (plantScope.value === "all") params.set("plant", "all");
        else params.set("plant", plantScope.value);
        params.delete("page");
        window.location.assign(`${window.location.pathname}?${params.toString()}`);
    });

    columnInputs.forEach((input) => {
        input.addEventListener("change", () => {
            const next = new Set(columnInputs.filter((item) => item.checked).map((item) => item.value));
            if (!next.size) {
                input.checked = true;
                next.add(input.value);
            }
            visibleColumns = next;
            applyColumns();
        });
    });

    if (form) {
        form.addEventListener("submit", () => {
            let columnsField = form.querySelector("input[name='columns']");
            if (!columnsField) {
                columnsField = document.createElement("input");
                columnsField.type = "hidden";
                columnsField.name = "columns";
                form.append(columnsField);
            }
            columnsField.value = Array.from(visibleColumns).join(",");
            const page = form.querySelector("input[name='page']");
            if (page) page.remove();
        });

        form.querySelectorAll("select[name='page_size']").forEach((select) => {
            select.addEventListener("change", () => form.requestSubmit());
        });

        const clearSearch = form.querySelector("[data-clear-search]");
        clearSearch?.addEventListener("click", () => {
            const search = form.querySelector("input[name='q']");
            if (search) search.value = "";
            form.requestSubmit();
        });
    }

    const exportBase = root.dataset.exportBase;
    root.querySelectorAll("[data-register-export]").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            if (!exportBase) return;
            const params = new URLSearchParams(form ? new FormData(form) : window.location.search);
            params.delete("page");
            params.set("format", link.dataset.registerExport);
            params.set("columns", Array.from(visibleColumns).join(","));
            window.location.assign(`${exportBase}?${params.toString()}`);
            link.closest("details")?.removeAttribute("open");
        });
    });

    document.addEventListener("click", (event) => {
        root.querySelectorAll(".batch-columns[open], .batch-export[open]").forEach((menu) => {
            if (!menu.contains(event.target)) menu.removeAttribute("open");
        });
    });
})();
