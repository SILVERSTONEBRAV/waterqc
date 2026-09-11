// ca/static/ca/js/dropdown.js

(function () {
    console.log("✅ Sidebar controller loaded");

    const SIDEBAR_KEY = "sidebar_open_index";
    const COLLAPSE_DELAY = 200;

    let collapseTimeout = null;

    // ===============================
    // GET HELPERS
    // ===============================
    function getSidebar() {
        return document.querySelector(".sidebar");
    }

    function getMenuItems() {
        return document.querySelectorAll(".sidebar-item.has-children");
    }

    // ===============================
    // TOGGLE MENU
    // ===============================
    function toggleMenu(toggle) {
        const parent = toggle.closest(".sidebar-item");
        if (!parent) return;

        const allItems = getMenuItems();

        allItems.forEach(item => {
            if (item !== parent) item.classList.remove("open");
        });

        parent.classList.toggle("open");

        const index = [...allItems].indexOf(parent);

        if (parent.classList.contains("open")) {
            localStorage.setItem(SIDEBAR_KEY, index);
        } else {
            localStorage.removeItem(SIDEBAR_KEY);
        }
    }

    // ===============================
    // RESTORE STATE
    // ===============================
    function restoreState() {
        const index = localStorage.getItem(SIDEBAR_KEY);
        if (index === null || index === "") return;

        const items = getMenuItems();
        if (items[index]) {
            items[index].classList.add("open");
        }
    }

    // ===============================
    // AUTO OPEN ACTIVE LINK
    // ===============================
    function autoOpenActive() {
        const currentUrl = window.location.href;

        document.querySelectorAll(".sidebar-submenu a").forEach(link => {
            if (link.href === currentUrl) {
                const parent = link.closest(".sidebar-item.has-children");
                if (parent) parent.classList.add("open");
            }
        });
    }

    // ===============================
    // COLLAPSE ALL MENUS
    // ===============================
    function collapseAll() {
        getMenuItems().forEach(item => item.classList.remove("open"));
    }

    // ===============================
    // SIDEBAR HOVER BEHAVIOR
    // ===============================
    function setupSidebarHover() {
        const sidebar = getSidebar();
        if (!sidebar) return;

        sidebar.addEventListener("mouseleave", () => {
            collapseTimeout = setTimeout(() => {
                collapseAll();
                localStorage.removeItem(SIDEBAR_KEY);
                console.log("🔻 Sidebar collapsed → menus closed");
            }, COLLAPSE_DELAY);
        });

        sidebar.addEventListener("mouseenter", () => {
            if (collapseTimeout) {
                clearTimeout(collapseTimeout);
            }

            // Optional: restore state when re-entering
            restoreState();
        });
    }

    // ===============================
    // EVENT DELEGATION (HTMX SAFE)
    // ===============================
    function setupClickHandler() {
        document.body.addEventListener("click", function (e) {
            const toggle = e.target.closest(".toggle-children");
            if (!toggle) return;

            e.preventDefault();
            e.stopPropagation();

            console.log("📂 Sidebar toggle clicked");

            toggleMenu(toggle);
        });
    }

    // ===============================
    // INITIALIZE
    // ===============================
    function init() {
        restoreState();
        autoOpenActive();
        setupSidebarHover();
    }

    // ===============================
    // LIFECYCLE EVENTS
    // ===============================

    // Initial load
    document.addEventListener("DOMContentLoaded", init);

    // HTMX updates
    document.body.addEventListener("htmx:afterSwap", () => {
        console.log("🔄 HTMX content swapped → reinitializing sidebar");
        init();
    });

    // Setup global click once
    setupClickHandler();

})();
