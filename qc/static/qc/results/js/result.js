// static/qc/results/js/result.js

(() => {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const cardsContainer = document.getElementById("cards-container");
    const loadingIndicator = document.getElementById("loading-indicator");
    let saveTimer = null;

    /* ================================
       HTMX lifecycle hooks
       ================================ */
    document.body.addEventListener("htmx:beforeRequest", () => {
      if (loadingIndicator) loadingIndicator.classList.add("htmx-request");
    });

    document.body.addEventListener("htmx:afterRequest", () => {
      if (loadingIndicator) loadingIndicator.classList.remove("htmx-request");
    });

    document.body.addEventListener("htmx:afterSwap", (evt) => {
      if (evt.target.id === "cards-container") {
        // Animate cards on refresh
        cardsContainer.querySelectorAll(".result-card").forEach((card, i) => {
          card.style.opacity = 0;
          setTimeout(() => {
            card.style.transition = "opacity 0.4s ease, transform 0.4s ease";
            card.style.opacity = 1;
            card.style.transform = "translateY(0)";
          }, i * 100);
        });
        // Re‑initialize validation, navigation, autosave
        initCardValidation();
        initNavigationAndAutosave();
      }
    });

    /* ================================
       Spec Visibility Logic
       ================================ */
    function initCardValidation() {
      const inputs = document.querySelectorAll("#cards-container .form-control");
      inputs.forEach((input) => {
        input.addEventListener("input", () => {
          handleValidation(input);
          scheduleAutosave(); // trigger autosave countdown
        });
        input.addEventListener("blur", () => handleValidation(input));
      });
    }

    function handleValidation(input) {
      const spec = input.nextElementSibling;
      if (!spec || !spec.classList.contains("spec-text")) return;

      const value = parseFloat(input.value);
      const specText = spec.textContent || "";
      const limits = parseSpec(specText);

      if (isNaN(value) || !limits) {
        hideSpec(input, spec);
        return;
      }

      if (value < limits.min || value > limits.max) {
        showSpec(input, spec);
      } else {
        hideSpec(input, spec);
      }
    }

    function parseSpec(text) {
      const match = text.match(/(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)/);
      return match ? { min: parseFloat(match[1]), max: parseFloat(match[2]) } : null;
    }

    function showSpec(input, spec) {
      input.classList.add("form-control-danger");
      spec.style.display = "block";
      spec.style.color = "var(--danger-700)";
      spec.style.transition = "opacity 0.3s ease";
      spec.style.opacity = "1";
    }

    function hideSpec(input, spec) {
      input.classList.remove("form-control-danger");
      spec.style.transition = "opacity 0.3s ease";
      spec.style.opacity = "0";
      setTimeout(() => {
        spec.style.display = "none";
      }, 300);
    }

    /* ================================
       Excel‑like Navigation + Autosave
       ================================ */
    function initNavigationAndAutosave() {
      const inputs = Array.from(document.querySelectorAll("#cards-container .form-control"));

      inputs.forEach((input, idx) => {
        input.addEventListener("keydown", (e) => {
          if (e.key === "ArrowRight" || e.key === "ArrowDown") {
            e.preventDefault();
            const next = inputs[idx + 1];
            if (next) next.focus();
          }
          if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
            e.preventDefault();
            const prev = inputs[idx - 1];
            if (prev) prev.focus();
          }
          if (e.key === "Enter") {
            e.preventDefault();
            saveResults(); // immediate save
            const next = inputs[idx + 1];
            if (next) next.focus();
          }
          if (e.ctrlKey && e.key.toLowerCase() === "c") {
            document.execCommand("copy"); // basic copy support
          }
          if (e.ctrlKey && e.key.toLowerCase() === "v") {
            document.execCommand("paste"); // basic paste support
          }
        });

        // Highlight row/column on focus
        input.addEventListener("focus", () => {
          const cell = input.closest("td");
          const row = input.closest("tr");
          if (row) row.classList.add("excel-row-highlight");
          if (cell) cell.classList.add("excel-cell-highlight");
        });
        input.addEventListener("blur", () => {
          const cell = input.closest("td");
          const row = input.closest("tr");
          if (row) row.classList.remove("excel-row-highlight");
          if (cell) cell.classList.remove("excel-cell-highlight");
        });
      });
    }

    function scheduleAutosave() {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        saveResults();
      }, 3000); // auto‑save after 3s of inactivity
    }

    function saveResults() {
      const form = document.querySelector("form.dashboard-stack");
      if (!form) return;
      htmx.trigger(form, "submit");
      logSaveFeedback();
    }

    function logSaveFeedback() {
      console.log("[QC Autosave] Results saved at", new Date().toLocaleTimeString());
      const toast = document.createElement("div");
      toast.textContent = "Results auto‑saved";
      toast.className = "toast-notification";
      toast.style.position = "fixed";
      toast.style.bottom = "1rem";
      toast.style.right = "1rem";
      toast.style.background = "rgba(37,99,235,0.9)";
      toast.style.color = "#fff";
      toast.style.padding = "0.5rem 1rem";
      toast.style.borderRadius = "6px";
      toast.style.boxShadow = "0 2px 6px rgba(0,0,0,0.3)";
      toast.style.zIndex = "9999";
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2000);
    }

    // Initialize once on page load
    initCardValidation();
    initNavigationAndAutosave();
  });
})();
