document.addEventListener("DOMContentLoaded", () => {

    const modals = Array.from(document.querySelectorAll(".app-modal"));

    let activeModal = null;
    let lastTrigger = null;

    /* ==========================================================
       CLOSE MODAL
    ========================================================== */

    function closeModal(modal, restoreFocus = true) {
        if (!modal) return;

        modal.classList.remove("show");
        modal.setAttribute("aria-hidden", "true");

        if (restoreFocus && lastTrigger && document.contains(lastTrigger)) {
            lastTrigger.focus();
        }

        if (activeModal === modal) {
            activeModal = null;
            lastTrigger = null;
        }
    }

    /* ==========================================================
       OPEN MODAL (CSS HANDLES TOP-RIGHT POSITION)
    ========================================================== */

    function openModal(modal, trigger = null) {
        if (!modal) return;

        if (activeModal && activeModal !== modal) {
            closeModal(activeModal, false);
        }

        activeModal = modal;
        lastTrigger = trigger;

        modal.classList.add("show");
        modal.setAttribute("aria-hidden", "false");

        requestAnimationFrame(() => {
            const focusTarget = modal.querySelector(
                "input, button, select, textarea, [tabindex]:not([tabindex='-1'])"
            );
            focusTarget?.focus();
        });
    }

    /* ==========================================================
       CLOSE ALL MODALS
    ========================================================== */

    function closeAllModals() {
        modals.forEach(modal => {
            modal.classList.remove("show");
            modal.setAttribute("aria-hidden", "true");
        });

        activeModal = null;
        lastTrigger = null;
    }

    /* ==========================================================
       OPEN TRIGGER
    ========================================================== */

    document.addEventListener("click", (e) => {

        const trigger = e.target.closest("[data-modal-open]");
        if (!trigger) return;

        e.preventDefault();

        const id = trigger.getAttribute("data-modal-open");
        const modal = document.getElementById(id);

        if (!modal) return;

        /* close dropdown (user menu coupling) */
        const dropdown = document.getElementById("userDropdown");
        if (dropdown) {
            dropdown.classList.remove("show");
            dropdown.setAttribute("aria-expanded", "false");
        }

        openModal(modal, trigger);
    });

    /* ==========================================================
       BACKDROP CLICK (OUTSIDE PANEL ONLY)
    ========================================================== */

    modals.forEach(modal => {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                closeModal(modal);
            }
        });
    });

    /* ==========================================================
       ESC KEY CLOSES EVERYTHING (CLEAN STATE RESET)
    ========================================================== */

    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            closeAllModals();
        }
    });

    /* ==========================================================
       GLOBAL API
    ========================================================== */

    window.Modal = {
        open: (id) => openModal(document.getElementById(id)),
        close: (id) => closeModal(document.getElementById(id)),
        closeAll: closeAllModals,
        getActive: () => activeModal
    };
});