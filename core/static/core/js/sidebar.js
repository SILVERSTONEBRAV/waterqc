document.addEventListener("DOMContentLoaded", () => {

    const sidebar = document.querySelector(".sidebar");
    const toggles = document.querySelectorAll(".toggle-children");
    const items = document.querySelectorAll(".sidebar-item.has-children");

    const currentUrl = window.location.pathname;

    let animating = false;

    // =========================================================
    // SAFE SLIDE DOWN
    // =========================================================
    function slideDown(el, duration = 220) {
        if (!el || animating) return;
        animating = true;

        el.style.display = "block";
        el.style.overflow = "hidden";
        el.style.height = "0px";

        const height = el.scrollHeight;

        el.style.transition = `height ${duration}ms cubic-bezier(.22,1,.36,1)`;

        requestAnimationFrame(() => {
            el.style.height = height + "px";
        });

        setTimeout(() => {
            el.style.height = "";
            el.style.overflow = "";
            el.style.transition = "";
            animating = false;
        }, duration);
    }

    // =========================================================
    // SAFE SLIDE UP
    // =========================================================
    function slideUp(el, duration = 220) {
        if (!el || animating) return;
        animating = true;

        el.style.height = el.scrollHeight + "px";
        el.style.overflow = "hidden";

        requestAnimationFrame(() => {
            el.style.transition = `height ${duration}ms cubic-bezier(.22,1,.36,1)`;
            el.style.height = "0px";
        });

        setTimeout(() => {
            el.style.display = "none";
            el.style.height = "";
            el.style.overflow = "";
            el.style.transition = "";
            animating = false;
        }, duration);
    }

    // =========================================================
    // CLOSE ALL SUBMENUS
    // =========================================================
    function closeAll(except = null) {
        items.forEach(item => {
            if (item === except) return;

            item.classList.remove("open");

            const submenu = item.querySelector(".sidebar-submenu");
            if (submenu && submenu.style.display !== "none") {
                slideUp(submenu);
            }
        });
    }

    // =========================================================
    // TOGGLE HANDLER
    // =========================================================
    toggles.forEach(toggle => {

        toggle.addEventListener("click", (e) => {
            e.preventDefault();

            const parent = toggle.closest(".sidebar-item");
            if (!parent) return;

            const submenu = parent.querySelector(".sidebar-submenu");
            if (!submenu) return;

            const isOpen = parent.classList.contains("open");

            closeAll(parent);

            if (isOpen) {
                parent.classList.remove("open");
                toggle.setAttribute("aria-expanded", "false");
                slideUp(submenu);
            } else {
                parent.classList.add("open");
                toggle.setAttribute("aria-expanded", "true");
                slideDown(submenu);
            }
        });
    });

    // =========================================================
    // AUTO-OPEN ACTIVE ROUTE
    // =========================================================
    items.forEach(item => {

        const links = item.querySelectorAll(".sidebar-submenu a");

        links.forEach(link => {

            const href = link.getAttribute("href");

            if (!href) return;

            // safer match (avoid /user matching /usersettings incorrectly)
            const normalizedHref = new URL(href, window.location.origin).pathname;

            if (currentUrl === normalizedHref || currentUrl.startsWith(normalizedHref + "/")) {

                item.classList.add("open");

                const submenu = item.querySelector(".sidebar-submenu");

                if (submenu) {
                    submenu.style.display = "block";
                }

                link.classList.add("active");

                const toggle = item.querySelector(".toggle-children");
                if (toggle) {
                    toggle.setAttribute("aria-expanded", "true");
                }
            }
        });
    });

    // =========================================================
    // TOP LEVEL ACTIVE STATE
    // =========================================================
    document.querySelectorAll(".sidebar-item > a.nav-link").forEach(link => {

        const href = link.getAttribute("href");
        if (!href) return;

        const normalizedHref = new URL(href, window.location.origin).pathname;

        if (currentUrl === normalizedHref) {
            link.classList.add("active");
        }
    });

    // =========================================================
    // OPTIONAL: SYNC WITH COLLAPSED SIDEBAR
    // (prevents submenu glitches when sidebar collapses)
    // =========================================================
    if (sidebar) {
        const observer = new MutationObserver(() => {
            if (document.body.classList.contains("sidebar-collapsed")) {
                closeAll();
            }
        });

        observer.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    }
});