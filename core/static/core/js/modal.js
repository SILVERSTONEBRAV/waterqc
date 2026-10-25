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
        modal.setAttribute("role", "dialog");
        modal.setAttribute("aria-modal", "true");

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

        if (lastTrigger && document.contains(lastTrigger)) lastTrigger.focus();
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
        if (dropdown && dropdown.tagName === "DIALOG" && dropdown.open) {
            dropdown.close();
        } else if (dropdown) {
            dropdown.classList.remove("show");
        }
        document.getElementById("userMenuBtn")?.setAttribute("aria-expanded", "false");

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
        if (!activeModal) return;

        if (e.key === "Escape") {
            e.preventDefault();
            closeModal(activeModal);
            return;
        }

        if (e.key === "Tab") {
            const focusable = Array.from(activeModal.querySelectorAll(
                "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
            )).filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== "hidden");

            if (!focusable.length) {
                e.preventDefault();
                activeModal.focus();
                return;
            }

            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey && (document.activeElement === first || !activeModal.contains(document.activeElement))) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && (document.activeElement === last || !activeModal.contains(document.activeElement))) {
                e.preventDefault();
                first.focus();
            }
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
