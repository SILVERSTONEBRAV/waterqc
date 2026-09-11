"use strict";

/* ============================================================
 * ULTRA-DYNAMIC CRUD.JS - MERGED & ENHANCED
 * Features:
 * - CRUD operations via AJAX
 * - Pagination, sorting, searching
 * - Modal add/edit forms with FK & textarea support
 * - Inline editing including FK fields
 * - Dashboard notifications via CustomEvent & Dashboard API
 * - Toast notifications
 * ============================================================ */

const CRUD = (() => {

    const state = {
        containers: new Map(),
        pagination: {},
        sort: {},
        inlineEdit: new Set(),
    };

    // ===================== UTILITIES =====================
    const createElement = (tag, opts = {}) => {
        const el = document.createElement(tag);
        Object.entries(opts).forEach(([k, v]) => {
            if (k === "class") el.className = v;
            else if (k === "html") el.innerHTML = v;
            else if (k === "text") el.textContent = v;
            else el.setAttribute(k, v);
        });
        return el;
    };

    const getCSRF = () =>
        document.cookie.split("; ").find(c => c.startsWith("csrftoken="))?.split("=")[1] || "";

    const CSRFTOKEN = getCSRF();

    const ajax = async (url, method = "GET", data = null) => {
        const opts = {
            method,
            headers: {
                "X-CSRFToken": CSRFTOKEN,
                "X-Requested-With": "XMLHttpRequest",
            },
        };
        if (data) {
            opts.body = JSON.stringify(data);
            opts.headers["Content-Type"] = "application/json";
        }
        const resp = await fetch(url, opts);
        let json = {};
        try { json = await resp.json(); } catch {}
        if (!resp.ok || json.success === false) throw json;
        return json;
    };

    const toast = (msg, type = "success") => {
        let container = document.getElementById("toast-container");
        if (!container) {
            container = createElement("div", { id: "toast-container", class: "toast-container position-fixed top-0 end-0 p-3" });
            document.body.appendChild(container);
        }
        const el = createElement("div", { class: `toast text-bg-${type} border-0` });
        el.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
                <button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>`;
        container.appendChild(el);
        const instance = new bootstrap.Toast(el, { delay: 3000 });
        instance.show();
        el.addEventListener("hidden.bs.toast", () => el.remove());
    };

    const debounce = (fn, delay = 300) => {
        let timer;
        return (...args) => {
            clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    };

    // ===================== DASHBOARD NOTIFICATIONS =====================
    const notifyDashboard = (msgType, data = {}) => {
        if (window.Dashboard) {
            switch (msgType) {
                case "update_cards":
                    if (data.cards) data.cards.forEach(c => Dashboard.updateStatCard(c.id, c.value, c.trend, c.donut));
                    break;
                case "update_batch":
                    if (data) Dashboard.renderBatch(data);
                    break;
                case "update_request":
                    if (data) Dashboard.renderRequest(data);
                    break;
            }
        }
        document.dispatchEvent(new CustomEvent("dashboard:update", { detail: { type: msgType, data } }));
    };

    // ===================== INITIALIZATION =====================
    const initContainer = (container) => {
        const endpoint = container.dataset.endpoint;
        const entity = container.dataset.entity || "Item";
        if (!endpoint) return;

        state.containers.set(container, { endpoint, entity });
        state.pagination[container] = { page: 1, perPage: parseInt(container.dataset.perPage || 20) };
        state.sort[container] = { column: null, direction: null };

        loadList(container);
        bindSearch(container);
        bindAddEdit(container);
    };

    const autoInit = () => document.querySelectorAll(".crud-container").forEach(initContainer);

    // ===================== LIST =====================
    const loadList = async (container) => {
        const { endpoint, entity } = state.containers.get(container);
        const { page, perPage } = state.pagination[container];
        const { column, direction } = state.sort[container];

        const searchInput = container.querySelector("#crud-search");
        const searchQuery = searchInput?.value || "";

        let url = `${endpoint}?page=${page}&per_page=${perPage}`;
        if (column && direction) url += `&sort=${column}&direction=${direction}`;
        if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

        try {
            const res = await ajax(url);
            const items = res.data || [];
            const metadata = res.meta || { fields: [], total_pages: 1 };

            renderTable(container, items, metadata);
        } catch (err) {
            console.error(err);
            toast(`Failed to load ${entity} list`, "danger");
        }
    };

    const renderTable = (container, items, metadata) => {
        const tbody = container.querySelector("#crud-table-body");
        tbody.innerHTML = "";

        items.forEach(item => {
            const tr = createElement("tr", { "data-id": item.id });

            metadata.fields.forEach(field => {
                const td = createElement("td");
                if (field.inline_edit) {
                    td.innerHTML = `<span class="crud-value">${item[field.name]}</span>`;
                    td.addEventListener("click", () => startInlineEdit(container, tr, field));
                } else {
                    td.textContent = item[field.name];
                }
                tr.appendChild(td);
            });

            const actionTd = createElement("td");
            const editBtn = createElement("button", { class: "btn btn-sm btn-primary me-1", text: "Edit" });
            editBtn.addEventListener("click", () => openModal(container, item.id, metadata));
            const delBtn = createElement("button", { class: "btn btn-sm btn-danger", text: "Delete" });
            delBtn.addEventListener("click", () => deleteItem(container, item.id));
            actionTd.appendChild(editBtn);
            actionTd.appendChild(delBtn);
            tr.appendChild(actionTd);

            tbody.appendChild(tr);
        });

        renderPagination(container, metadata.total_pages || 1);
        bindSorting(container, metadata.fields);
    };

    // ===================== PAGINATION =====================
    const renderPagination = (container, totalPages) => {
        const paginationContainer = container.querySelector("#crud-pagination");
        if (!paginationContainer) return;

        paginationContainer.innerHTML = "";
        const currentPage = state.pagination[container].page;

        const addBtn = (text, page) => {
            const btn = createElement("button", {
                class: `btn btn-sm ${page === currentPage ? "btn-primary" : "btn-outline-primary"} me-1`,
                text
            });
            btn.addEventListener("click", () => {
                state.pagination[container].page = page;
                loadList(container);
            });
            paginationContainer.appendChild(btn);
        };

        addBtn("First", 1);
        addBtn("Prev", Math.max(1, currentPage - 1));
        for (let i = 1; i <= totalPages; i++) addBtn(i, i);
        addBtn("Next", Math.min(totalPages, currentPage + 1));
        addBtn("Last", totalPages);
    };

    // ===================== SORTING =====================
    const bindSorting = (container, fields) => {
        const headers = container.querySelectorAll("#crud-table thead th[data-field]");
        headers.forEach(th => {
            th.style.cursor = "pointer";
            th.innerHTML = th.textContent + `<span class="sort-indicator"></span>`;
            th.addEventListener("click", () => {
                const field = th.dataset.field;
                const sortState = state.sort[container];
                if (sortState.column === field) {
                    sortState.direction = sortState.direction === "asc" ? "desc" : "asc";
                } else {
                    sortState.column = field;
                    sortState.direction = "asc";
                }
                updateSortIndicators(container);
                loadList(container);
            });
        });
    };

    const updateSortIndicators = (container) => {
        const { column, direction } = state.sort[container];
        container.querySelectorAll("#crud-table thead th[data-field]").forEach(th => {
            const indicator = th.querySelector(".sort-indicator");
            if (th.dataset.field === column) indicator.textContent = direction === "asc" ? " ▲" : " ▼";
            else indicator.textContent = "";
        });
    };

    // ===================== SEARCH =====================
    const bindSearch = (container) => {
        const searchInput = container.querySelector("#crud-search");
        if (!searchInput) return;

        searchInput.addEventListener("input", debounce(() => {
            state.pagination[container].page = 1;
            loadList(container);
        }, 300));
    };

    // ===================== MODAL / FORM =====================
    const bindAddEdit = (container) => {
        const addBtn = container.querySelector("#crud-add-btn");
        if (addBtn) addBtn.addEventListener("click", () => openModal(container));

        const form = container.querySelector("#crud-form");
        if (!form) return;

        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            await submitForm(container);
        });

        const cancelBtn = container.querySelector("#crud-cancel");
        if (cancelBtn) cancelBtn.addEventListener("click", () => closeModal(container));
    };

    const openModal = async (container, objId = null, metadata = null) => {
        const { endpoint, entity } = state.containers.get(container);
        const modal = container.querySelector("#crud-modal");
        const form = container.querySelector("#crud-form");
        const title = container.querySelector("#crud-modal-title");

        title.textContent = objId ? `Edit ${entity}` : `Add ${entity}`;
        form.innerHTML = "";
        form.dataset.objId = objId || "";

        try {
            if (!metadata) {
                const res = await ajax(endpoint + (objId ? `${objId}/` : ""));
                metadata = res.meta;
                if (objId) var item = res.data;
            }

            metadata.fields.forEach(field => {
                const value = objId ? item[field.name] : field.default || "";
                let input;

                if (field.type === "fk" && field.choices_endpoint) {
                    input = createElement("select", { name: field.name, class: "form-control mb-2" });
                    fetchFKOptions(field.choices_endpoint, input, value);
                } else if (field.type === "textarea") {
                    input = createElement("textarea", { name: field.name, class: "form-control mb-2", text: value });
                } else {
                    input = createElement("input", { type: field.type || "text", name: field.name, class: "form-control mb-2", value });
                }

                form.appendChild(input);
            });

            modal.classList.remove("hidden");
            form.querySelector("input, select, textarea")?.focus();
        } catch (err) {
            console.error(err);
            toast(`Failed to load form for ${entity}`, "danger");
        }
    };

    const closeModal = (container) => container.querySelector("#crud-modal")?.classList.add("hidden");

    const submitForm = async (container) => {
        const { endpoint, entity } = state.containers.get(container);
        const form = container.querySelector("#crud-form");
        const objId = form.dataset.objId || null;
        const url = objId ? `${endpoint}${objId}/` : endpoint;

        const data = {};
        form.querySelectorAll("input, select, textarea").forEach(el => data[el.name] = el.value);

        try {
            const res = await ajax(url, "POST", data);
            toast(`${entity} ${objId ? "updated" : "created"} successfully`);
            closeModal(container);
            loadList(container);

            if (res.updated_cards) notifyDashboard("update_cards", { cards: res.updated_cards });
            if (res.updated_batch) notifyDashboard("update_batch", res.updated_batch);
            if (res.updated_request) notifyDashboard("update_request", res.updated_request);

        } catch (err) {
            console.error(err);
            toast(err.error || `Failed to ${objId ? "update" : "create"} ${entity}`, "danger");
        }
    };

    // ===================== DELETE =====================
    const deleteItem = async (container, objId) => {
        const { endpoint, entity } = state.containers.get(container);
        if (!confirm(`Are you sure you want to delete this ${entity}?`)) return;

        try {
            const res = await ajax(`${endpoint}${objId}/`, "POST", { _method: "DELETE" });
            toast(`${entity} deleted`);
            loadList(container);

            if (res.updated_cards) notifyDashboard("update_cards", { cards: res.updated_cards });
            if (res.updated_batch) notifyDashboard("update_batch", res.updated_batch);
            if (res.updated_request) notifyDashboard("update_request", res.updated_request);

        } catch (err) {
            console.error(err);
            toast(err.error || `Failed to delete ${entity}`, "danger");
        }
    };

    // ===================== INLINE EDITING =====================
    const startInlineEdit = (container, row, field) => {
        if (state.inlineEdit.has(row)) return;
        state.inlineEdit.add(row);

        const td = [...row.children].find(td => td.querySelector(".crud-value")?.textContent === td.textContent);
        const currentValue = td.textContent;
        let input;

        if (field.type === "fk" && field.choices_endpoint) {
            input = createElement("select", { class: "form-control form-control-sm" });
            fetchFKOptions(field.choices_endpoint, input, currentValue);
        } else {
            input = createElement("input", { class: "form-control form-control-sm", value: currentValue });
        }

        td.innerHTML = "";
        td.appendChild(input);
        input.focus();

        input.addEventListener("keydown", async e => {
            if (e.key === "Enter") input.blur();
            if (e.key === "Escape") {
                td.textContent = currentValue;
                state.inlineEdit.delete(row);
            }
        });

        input.addEventListener("blur", async () => {
            const newValue = input.value;
            const objId = row.dataset.id;
            try {
                const { endpoint } = state.containers.get(container);
                const res = await ajax(`${endpoint}${objId}/`, "POST", { [field.name]: newValue });
                td.textContent = newValue;
                state.inlineEdit.delete(row);
                toast("Updated inline successfully");

                if (res.updated_cards) notifyDashboard("update_cards", { cards: res.updated_cards });
                if (res.updated_batch) notifyDashboard("update_batch", res.updated_batch);
                if (res.updated_request) notifyDashboard("update_request", res.updated_request);

            } catch {
                td.textContent = currentValue;
                state.inlineEdit.delete(row);
                toast("Failed to update inline", "danger");
            }
        });
    };

    const fetchFKOptions = async (url, selectEl, selectedValue) => {
        try {
            const res = await ajax(url);
            (res.data || []).forEach(item => {
                const opt = createElement("option", { value: item.id, text: item.name });
                if (item.id == selectedValue) opt.selected = true;
                selectEl.appendChild(opt);
            });
        } catch (err) {
            console.error("Failed to load FK options", err);
        }
    };

    return { autoInit, loadList, openModal };

})();

// ===================== AUTO INIT =====================
document.addEventListener("DOMContentLoaded", () => CRUD.autoInit());
