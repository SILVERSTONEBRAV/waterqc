(function () {
    "use strict";

    const sidebar = document.getElementById("qcaSidebar");
    const backdrop = document.getElementById("qcaSidebarBackdrop");
    const toggle = document.getElementById("qcaSidebarToggle");
    const closeButton = document.getElementById("qcaSidebarClose");
    const pageContent = document.getElementById("main-dashboard");

    if (!sidebar || !backdrop || !toggle || !closeButton) return;

    function setOpen(open) {
        sidebar.classList.toggle("is-open", open);
        backdrop.hidden = !open;
        sidebar.setAttribute("aria-hidden", String(!open));
        sidebar.inert = !open;
        if (pageContent) pageContent.inert = open;
        toggle.setAttribute("aria-expanded", String(open));
        toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
        toggle.setAttribute("title", open ? "Close navigation" : "Open navigation");
        document.body.classList.toggle("qca-navigation-open", open);

        if (open) {
            closeButton.focus();
        } else {
            toggle.focus();
        }
    }

    toggle.addEventListener("click", function () {
        setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    closeButton.addEventListener("click", function () {
        setOpen(false);
    });
    backdrop.addEventListener("click", function () {
        setOpen(false);
    });
    sidebar.addEventListener("click", function (event) {
        if (event.target.closest("a")) setOpen(false);
    });
    sidebar.addEventListener("keydown", function (event) {
        if (event.key !== "Tab") return;
        const focusable = Array.from(
            sidebar.querySelectorAll('a[href], button:not([disabled])')
        ).filter((element) => !element.hidden);
        if (!focusable.length) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    });
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
            setOpen(false);
        }
    });
})();
