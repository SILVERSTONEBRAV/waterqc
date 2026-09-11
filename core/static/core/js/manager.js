export class TableManager {

    constructor({
        tableSelector,
        searchSelector,
        addBtnSelector,
        printBtnSelector,
        exportSelector,
        csrfToken,
        urls = {},
        debounce = 250,
        autoSaveDelay = 1500,
        enableInlineEdit = true,
        enableOptimisticUI = true,
        debug = false
    }) {

        // =====================================================
        // CORE ELEMENTS
        // =====================================================
        this.table = document.querySelector(tableSelector);
        if (!this.table) throw new Error("Table not found");

        this.tableBody = this.table.querySelector("tbody");
        if (!this.tableBody) throw new Error("Table body not found");

        this.searchInput = document.querySelector(searchSelector);
        this.addBtn = document.querySelector(addBtnSelector);
        this.printBtn = document.querySelector(printBtnSelector);
        this.exportLinks = document.querySelectorAll(exportSelector);

        // =====================================================
        // CONFIG
        // =====================================================
        this.csrfToken = csrfToken;
        this.urls = urls;

        this.debounce = debounce;
        this.autoSaveDelay = autoSaveDelay;

        this.enableInlineEdit = enableInlineEdit;
        this.enableOptimisticUI = enableOptimisticUI;
        this.debug = debug;

        // =====================================================
        // INTERNAL STATE
        // =====================================================
        this.requestLock = false;
        this.pendingSave = null;
        this.fields = this.detectFields();

        this.init();
        this.enableKeyboard();
        this.enableAutoSave();
    }

    // =========================================================
    // DEBUG LOGGING
    // =========================================================
    log(...args) {
        if (this.debug) console.log("[TableManager]", ...args);
    }

    // =========================================================
    // FIELD DETECTION (BACKEND-SCHEMA SAFE)
    // =========================================================
    detectFields() {
        const headers = this.table.querySelectorAll("thead th[data-field]");

        if (headers.length) {
            return Array.from(headers).map(th => th.dataset.field);
        }

        const row = this.tableBody.querySelector("tr");
        if (!row) return [];

        return Array.from(row.querySelectorAll("[data-field]"))
            .map(td => td.dataset.field);
    }

    // =========================================================
    // INIT
    // =========================================================
    init() {

        this.searchInput && this.initSearch();

        this.addBtn?.addEventListener("click", () => this.handleAdd());
        this.printBtn?.addEventListener("click", () => this.handlePrint());

        this.exportLinks.forEach(link =>
            link.addEventListener("click", e =>
                this.handleExport(e, link.dataset.type)
            )
        );

        // EVENT DELEGATION (CLEAN + SCALABLE)
        this.tableBody.addEventListener("click", (e) => {
            const row = e.target.closest("tr");
            if (!row) return;

            const id = row.dataset.id;

            if (e.target.matches(".edit-btn")) this.handleEdit(row);
            if (e.target.matches(".delete-btn")) this.handleDelete(row);
            if (e.target.matches(".view-btn")) this.handleView(id);
            if (e.target.matches(".save-new-btn")) this.handleSaveNew(row);
            if (e.target.matches(".cancel-new-btn")) this.handleCancelNew(row);
            if (e.target.matches(".cancel-edit-btn")) this.handleCancelEdit(row);
        });
    }

    // =========================================================
    // SEARCH (DEBOUNCED + BACKEND READY EXTENSION POINT)
    // =========================================================
    initSearch() {
        let t;

        this.searchInput.addEventListener("input", () => {
            clearTimeout(t);

            t = setTimeout(() => {
                const q = this.searchInput.value.toLowerCase();

                this.tableBody.querySelectorAll("tr").forEach(row => {
                    const text = Array.from(row.querySelectorAll("[data-field]"))
                        .map(c => c.textContent.toLowerCase())
                        .join(" ");

                    row.style.display = text.includes(q) ? "" : "none";
                });

            }, this.debounce);
        });
    }

    // =========================================================
    // ADD ROW (INLINE CREATION)
    // =========================================================
    handleAdd() {

        const tr = document.createElement("tr");
        tr.dataset.editing = "new";

        let html = `<td></td>`;

        this.fields.forEach(f => {
            html += `
                <td data-field="${f}">
                    <input class="form-control form-control-sm"/>
                </td>
            `;
        });

        html += `
            <td class="text-end">
                <button class="btn btn-sm btn-success save-new-btn">Save</button>
                <button class="btn btn-sm btn-danger cancel-new-btn">Cancel</button>
            </td>
        `;

        tr.innerHTML = html;
        this.tableBody.prepend(tr);

        tr.querySelector("input")?.focus();
    }

    handleCancelNew(row) {
        row.remove();
    }

    // =========================================================
    // CREATE (BACKEND / NAMUBUYA / REGISTRY COMPATIBLE)
    // =========================================================
    async handleSaveNew(row) {
        if (this.requestLock) return;
        this.requestLock = true;

        const data = this.collectRowData(row);

        try {
            const res = await this.post(this.urls.create, data);
            const json = await res.json();

            if (!res.ok || !json.success) {
                throw json.errors || "Create failed";
            }

            if (this.enableOptimisticUI) {
                this.replaceInputsWithText(row, data);
                row.dataset.id = json.object_id;
                delete row.dataset.editing;
            } else {
                row.remove();
            }

        } catch (err) {
            this.log("CREATE FAILED:", err);
            alert("Create failed");
        } finally {
            this.requestLock = false;
        }
    }

    // =========================================================
    // EDIT MODE (INLINE OR FALLBACK)
    // =========================================================
    handleEdit(row) {

        if (!this.enableInlineEdit) {
            window.location.href = this.urls.edit(row.dataset.id);
            return;
        }

        const btn = row.querySelector(".edit-btn");

        if (!row.dataset.editing) {

            row.dataset.editing = "edit";
            btn.textContent = "Save";

            this.fields.forEach(f => {
                const cell = row.querySelector(`[data-field="${f}"]`);
                const val = cell.textContent.trim();

                cell.dataset.original = val;
               if (cell.dataset.kind === "fk") {
    cell.innerHTML = `
        <select class="form-select form-select-sm fk-render"></select>
    `;
    this.hydrateFKCell(cell);
} else {
    cell.innerHTML = `
        <input value="${val}" class="form-control form-control-sm"/>
    `;
}

            });

            this.injectCancelEdit(row);
            return;
        }

        btn.textContent = "Edit";
        this.saveEdit(row);
    }

    injectCancelEdit(row) {
        if (row.querySelector(".cancel-edit-btn")) return;

        const btn = document.createElement("button");
        btn.className = "btn btn-sm btn-secondary cancel-edit-btn";
        btn.textContent = "Cancel";

        row.querySelector("td:last-child").appendChild(btn);
    }

    handleCancelEdit(row) {

    this.fields.forEach(f => {
        const cell = row.querySelector(`[data-field="${f}"]`);
        if (!cell) return;

        if (cell.dataset.kind === "fk") {

            const wrapper = cell.querySelector(".fk-wrapper");
            if (!wrapper) return;

            wrapper.querySelector(".fk-display")?.classList.remove("d-none");
            wrapper.querySelector(".fk-render")?.classList.add("d-none");

        } else {
            cell.textContent = cell.dataset.original;
        }
    });

    delete row.dataset.editing;

    row.querySelector(".cancel-edit-btn")?.remove();
    row.querySelector(".edit-btn").textContent = "Edit";
}


    async populateFK(select, endpoint, selected) {

    if (!endpoint) {
        console.warn("Missing FK endpoint");
        return;
    }

    try {
        const res = await fetch(endpoint, {
            headers: { "X-Requested-With": "XMLHttpRequest" }
        });

        if (!res.ok) throw new Error("FK fetch failed");

        const data = await res.json();

        select.innerHTML = `<option value="">---------</option>`;

        (data.results || []).forEach(item => {

            const opt = document.createElement("option");
            opt.value = String(item.id);
            opt.textContent = item.label;

            if (String(item.id) === String(selected)) {
                opt.selected = true;
            }

            select.appendChild(opt);
        });

    } catch (err) {
        console.error("FK populate failed:", err);
        select.innerHTML = `<option>Error</option>`;
    }
}

    // =====================================================
// GLOBAL STATE ENGINE
// =====================================================
const state = {
    editingRows: new Set(),
    dirtyCells: new Map()
};

const csrf = document.querySelector('meta[name="csrf-token"]').content;
const [app, model] = location.pathname.split("/").filter(Boolean);
const baseURL = `/${app}/${model}`;

// =====================================================
// ACTION DISPATCHER (CENTRAL BRAIN)
// =====================================================
document.body.addEventListener("click", async (e) => {

    const btn = e.target.closest("[data-action]");
    if (!btn) return;

    const action = btn.dataset.action;
    const row = btn.closest("tr");
    const id = row.dataset.id;

    switch (action) {

        case "view":
            window.location.href = `${baseURL}/${id}/detail/`;
            break;

        case "edit":
            enterEditMode(row);
            break;

        case "save":
            await saveRow(row);
            break;

        case "cancel":
            cancelRow(row);
            break;

        case "delete":
            await deleteRow(row, id);
            break;

        default:
            await customAction(row, id, action);
    }
});

// =====================================================
// ENTER EDIT MODE (SPREADSHEET STATE)
// =====================================================
function enterEditMode(row) {

    row.dataset.state = "edit";

    // toggle buttons
    toggleActions(row, true);

    // show inputs
    row.querySelectorAll(".cell-view").forEach(v => v.classList.add("d-none"));
    row.querySelectorAll(".cell-edit").forEach(i => i.classList.remove("d-none"));

    state.editingRows.add(row.dataset.id);
}

// =====================================================
// CANCEL EDIT MODE
// =====================================================
function cancelRow(row) {

    row.dataset.state = "view";

    toggleActions(row, false);

    row.querySelectorAll(".cell-view").forEach(v => v.classList.remove("d-none"));
    row.querySelectorAll(".cell-edit").forEach(i => {
        i.classList.add("d-none");
        i.value = i.dataset.original;
    });

    state.editingRows.delete(row.dataset.id);
}

// =====================================================
// SAVE ROW (BULK CELL SYNC)
// =====================================================
async function saveRow(row) {

    const id = row.dataset.id;
    const payload = {};

    row.querySelectorAll(".cell-edit").forEach(input => {
        const field = input.dataset.field;
        payload[field] = input.value;
    });

    try {
        const res = await fetch(`${baseURL}/${id}/inline_edit/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrf
            },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error("Save failed");

        // sync UI
        row.querySelectorAll(".cell-edit").forEach(input => {
            const view = input.parentElement.querySelector(".cell-view");
            view.textContent = input.value;
            input.dataset.original = input.value;
        });

        cancelRow(row);

    } catch (err) {
        console.error(err);
        alert("Save failed");
    }
}

// =====================================================
// DELETE ROW
// =====================================================
async function deleteRow(row, id) {

    if (!confirm("Delete this row?")) return;

    await fetch(`${baseURL}/${id}/delete/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrf }
    });

    row.remove();
}

// =====================================================
// CUSTOM ACTIONS (BACKEND EXTENSIBLE)
// =====================================================
async function customAction(row, id, action) {

    await fetch(`${baseURL}/${id}/${action}/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrf }
    });

    // optional refresh or partial update
    row.classList.add("flash");
}

// =====================================================
// UI STATE TOGGLE
// =====================================================
function toggleActions(row, editing) {

    const group = row.querySelector(".row-actions");

    group.querySelector('[data-action="edit"]').classList.toggle("d-none", editing);
    group.querySelector('[data-action="save"]').classList.toggle("d-none", !editing);
    group.querySelector('[data-action="cancel"]').classList.toggle("d-none", !editing);
}



    // =========================================================
    // UPDATE (PATCH SAFE FOR NAMUBUYA)
    // =========================================================
    async saveEdit(row) {
        if (this.requestLock) return;
        this.requestLock = true;

        const id = row.dataset.id;
        const data = this.collectRowData(row);

        try {
            const res = await this.post(this.urls.edit(id), {
                ...data,
                _method: "patch"
            });

            const json = await res.json();

            if (!res.ok || !json.success) {
                throw json.errors || "Update failed";
            }

            this.replaceInputsWithText(row, data);
            delete row.dataset.editing;

            row.querySelector(".cancel-edit-btn")?.remove();

        } catch (err) {
            this.log("UPDATE FAILED:", err);
            alert("Update failed");
        } finally {
            this.requestLock = false;
        }
    }

    // =========================================================
    // DELETE (BACKEND SAFE + ID GUARD)
    // =========================================================


    async handleDelete(row) {

        const id = row.dataset.id;

        if (!id) {
            this.log("DELETE ERROR: missing ID");
            alert("Invalid row ID");
            return;
        }

        if (!confirm("Delete this record?")) return;

        try {
            const res = await this.post(this.urls.delete(id), { id });
            const json = await res.json();

            if (!res.ok || !json.success) {
                throw json.errors || "Delete failed";
            }

            row.remove();

        } catch (err) {
            this.log("DELETE FAILED:", err);
            alert("Delete failed");
        }
    }

    // =========================================================
    // VIEW (BACKEND DETAIL HANDLER SUPPORT)
    // =========================================================
    handleView(id) {
        if (!id) return;

        const url = this.urls.detail(id);
        window.location.href = url;
    }
    async populateFK(select, endpoint, selected) {

    if (!endpoint) {
        console.warn("Missing FK endpoint");
        return;
    }

    try {
        const res = await fetch(endpoint, {
            headers: { "X-Requested-With": "XMLHttpRequest" }
        });

        if (!res.ok) throw new Error("FK fetch failed");

        const data = await res.json();

        select.innerHTML = `<option value="">---------</option>`;

        (data.results || []).forEach(item => {

            const opt = document.createElement("option");
            opt.value = String(item.id);
            opt.textContent = item.label;

            if (String(item.id) === String(selected)) {
                opt.selected = true;
            }

            select.appendChild(opt);
        });

    } catch (err) {
        console.error("FK populate failed:", err);
        select.innerHTML = `<option>Error</option>`;
    }
}


    // =========================================================
    // POST WRAPPER (ROBUST + SAFE)
    // =========================================================
    async post(url, data = {}) {

        if (!url) throw new Error("Missing URL");

        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": this.csrfToken || "",
                "X-Requested-With": "XMLHttpRequest"
            },
            body: new URLSearchParams(data)
        });
    }

    // =========================================================
    // HELPERS
    // =========================================================
    collectRowData(row) {
    const data = {};

    this.fields.forEach(f => {

        const cell = row.querySelector(`[data-field="${f}"]`);

        if (!cell) return;

        // FK
        const select = cell.querySelector("select.fk-render");
        if (select) {
            data[f] = select.value;
            return;
        }

        // INPUT
        const input = cell.querySelector("input");
        if (input) {
            data[f] = input.value;
            return;
        }

        // TEXT fallback
        data[f] = cell.textContent.trim();
    });

    return data;
}

    // =========================================================
    // AUTO SAVE (SMART + DEBOUNCED + SAFE LOCK)
    // =========================================================
    enableAutoSave() {

        let t;

        this.tableBody.addEventListener("input", e => {
            const row = e.target.closest("tr");
            if (!row?.dataset.editing) return;

            clearTimeout(t);

            t = setTimeout(() => {
                this.saveEdit(row);
            }, this.autoSaveDelay);
        });
    }

    // =========================================================
    // KEYBOARD UX (ENTER / ESC / TAB)
    // =========================================================
    enableKeyboard() {

        this.tableBody.addEventListener("keydown", e => {

            const input = e.target;
            if (!input.matches("input")) return;

            const row = input.closest("tr");
            const inputs = Array.from(row.querySelectorAll("input"));
            const idx = inputs.indexOf(input);

            if (e.key === "Enter") {
                e.preventDefault();
                row.querySelector(".save-new-btn, .edit-btn")?.click();
            }

            if (e.key === "Tab") {
                e.preventDefault();
                inputs[idx + 1]?.focus();
            }

            if (e.key === "Escape") {
                row.querySelector(".cancel-new-btn, .cancel-edit-btn")?.click();
            }
        });
    }

    // =========================================================
    // PRINT
    // =========================================================
    handlePrint() {
        window.print();
    }

    // =========================================================
    // EXPORT (BACKEND COMPATIBLE QUERY ROUTING)
    // =========================================================
    handleExport(e, type) {
        e.preventDefault();

        const url = new URL(window.location.href);

        url.searchParams.set("action", "export");
        url.searchParams.set("type", type);

        window.open(url.toString(), "_blank");
    }
}
