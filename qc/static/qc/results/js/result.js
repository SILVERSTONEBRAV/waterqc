// static/qc/results/js/result.js
// ──────────────────────────────────────────────────────────────
// QC Results Card Client Logic (Autosave removed, validation & navigation preserved)
// ──────────────────────────────────────────────────────────────

(() => {
  "use strict";

  document.addEventListener("DOMContentLoaded", () => {
    const cardsContainer = document.getElementById("cards-container");
    const loadingIndicator = document.getElementById("loading-indicator");

    // Autosave completely removed — manual form submission only

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
        // Ensure cards remain visible immediately
        if (cardsContainer) {
          cardsContainer.querySelectorAll(".result-card").forEach((card) => {
            card.style.opacity = "1";
            card.style.visibility = "visible";
            card.style.display = "flex";
          });
        }
        // Re‑initialize validation and navigation
        initCardValidation();
        initNavigation();
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
        showSpec(input, spec, "violation");
      } else {
        showSpec(input, spec, "compliant");
      }
    }

    function parseSpec(text) {
      const match = text.match(/(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)/);
      if (match) return { min: parseFloat(match[1]), max: parseFloat(match[2]) };
      const maxMatch = text.match(/≤\s*(\d+\.?\d*)/);
      if (maxMatch) return { min: -Infinity, max: parseFloat(maxMatch[1]) };
      const minMatch = text.match(/≥\s*(\d+\.?\d*)/);
      if (minMatch) return { min: parseFloat(minMatch[1]), max: Infinity };
      return null;
    }

    function showSpec(input, spec, type) {
      spec.classList.remove("hidden-spec", "compliant", "violation");
      spec.classList.add(type);
      input.classList.remove("input-compliant", "input-violation");
      input.classList.add(`input-${type}`);
    }

    function hideSpec(input, spec) {
      spec.classList.add("hidden-spec");
      input.classList.remove("input-compliant", "input-violation");
    }

    /* ================================
       Excel‑like Navigation
       ================================ */
    function initNavigation() {
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
            const next = inputs[idx + 1];
            if (next) next.focus();
          }
          if (e.ctrlKey && e.key.toLowerCase() === "c") {
            document.execCommand("copy");
          }
          if (e.ctrlKey && e.key.toLowerCase() === "v") {
            document.execCommand("paste");
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

    // Initialize once on page load
    initCardValidation();
    initNavigation();
  });
})();
