"use strict";

(() => {

  const getCSRF = () =>
    document.cookie
      .split("; ")
      .find(c => c.startsWith("csrftoken="))
      ?.split("=")[1] || "";

  const CSRFTOKEN = getCSRF();

  const locks = new Set();
  let refreshInFlight = false;

  const lock = (key) => {
    if (locks.has(key)) return false;
    locks.add(key);
    return true;
  };

  const unlock = (key) => locks.delete(key);

  const toast = (message, type = "success") => {
    let container = document.getElementById("toast-container");

    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "toast-container position-fixed top-0 end-0 p-3";
      document.body.appendChild(container);
    }

    const el = document.createElement("div");
    el.className = `toast text-bg-${type} border-0`;
    el.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>
    `;

    container.appendChild(el);

    const instance = new bootstrap.Toast(el, { delay: 2500 });
    instance.show();

    el.addEventListener("hidden.bs.toast", () => el.remove());
  };

  async function ajax(url, method = "GET", data = null, isForm = false) {
    const opts = {
      method,
      headers: {
        "X-CSRFToken": CSRFTOKEN,
        "X-Requested-With": "XMLHttpRequest"
      }
    };

    if (data) {
      opts.body = isForm ? data : JSON.stringify(data);
      if (!isForm) opts.headers["Content-Type"] = "application/json";
    }

    const resp = await fetch(url, opts);
    let json = {};

    try { json = await resp.json(); } catch {}

    if (!resp.ok || json.success === false) {
      throw json;
    }

    return json;
  }

  const buildUrl = (base, id = "") =>
    id ? `${base.replace(/\/+$/, "")}/${id}/` : `${base.replace(/\/+$/, "")}/`;

  async function refreshDashboard() {
    if (refreshInFlight) return;
    refreshInFlight = true;

    try {
      const { data } = await ajax(DASHBOARD_URLS.dashboard.counts);

      Object.entries(data).forEach(([entity, rows]) => {
        const tbody = document.querySelector(`#${entity}Table tbody`);
        if (!tbody) return;

        const existing = new Map(
          [...tbody.querySelectorAll("tr[data-id]")].map(tr => [tr.dataset.id, tr])
        );

        rows.forEach(item => {
          const id = String(item.id);

          if (existing.has(id)) {
            const tr = existing.get(id);
            tr.querySelectorAll("[data-field]").forEach(td => {
              const f = td.dataset.field;
              if (item[f] !== undefined) td.textContent = item[f];
            });
          } else if (item.html_row) {
            tbody.insertAdjacentHTML("beforeend", item.html_row);
          }
        });
      });

    } catch (err) {
      console.error("Dashboard refresh failed:", err);
    } finally {
      refreshInFlight = false;
    }
  }

  function bindDelete(selector, base) {
    const bound = new Set();
    if (bound.has(selector)) return;
    bound.add(selector);

    document.addEventListener("click", async e => {
      const btn = e.target.closest(selector);
      if (!btn) return;

      const tr = btn.closest("tr");
      const id = tr?.dataset.id;
      if (!id) return;

      if (!confirm("Delete this record?")) return;

      const key = `delete:${base}:${id}`;
      if (!lock(key)) return;

      try {
        await ajax(buildUrl(base, id), "POST", { _method: "DELETE" });
        tr.remove();
        toast("Deleted successfully");
      } catch (err) {
        toast(err.error || "Delete failed", "danger");
      } finally {
        unlock(key);
      }
    });
  }

  function bindToggle(selector, base, field) {
    document.addEventListener("change", async e => {
      const el = e.target.closest(selector);
      if (!el) return;

      const tr = el.closest("tr");
      const id = tr?.dataset.id;
      if (!id) return;

      const prev = !el.checked;
      const key = `toggle:${base}:${id}:${field}`;

      if (!lock(key)) {
        el.checked = prev;
        return;
      }

      try {
        await ajax(buildUrl(base, id), "POST", { [field]: el.checked });
      } catch {
        el.checked = prev;
        toast("Update failed", "danger");
      } finally {
        unlock(key);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {

    refreshDashboard();
    setInterval(refreshDashboard, 30000);

    bindDelete(".delete-user", DASHBOARD_URLS.users.base);
    bindDelete(".delete-section", DASHBOARD_URLS.sections.base);
    bindDelete(".delete-group", DASHBOARD_URLS.groups.base);

    bindToggle(".toggle-active", DASHBOARD_URLS.users.base, "is_active");
    bindToggle(".toggle-locked", DASHBOARD_URLS.users.base, "is_locked");
  });

})();