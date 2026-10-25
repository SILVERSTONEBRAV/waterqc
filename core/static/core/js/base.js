document.addEventListener("DOMContentLoaded", () => {

    const sidebar = document.querySelector(".sidebar");

    /* Theme is owned by the shared multi-palette ThemeEngine. */
    const cycleTheme = () => {
        if (window.ThemeEngine && typeof window.ThemeEngine.cycle === "function") {
            window.ThemeEngine.cycle();
        }
    };

    const setCollapsed = (state) => {
        document.body.classList.toggle("sidebar-collapsed", state);
    };

    const initSidebar = () => {
        if (!sidebar) return;
        sidebar.addEventListener("mouseenter", () => setCollapsed(false));
        sidebar.addEventListener("mouseleave", () => setCollapsed(true));
        setCollapsed(true);
    };

    const initSubmenus = () => {
        document.querySelectorAll(".toggle-children").forEach(toggle => {
            toggle.addEventListener("click", e => {
                e.preventDefault();
                const parent = toggle.closest(".sidebar-item");
                if (parent) parent.classList.toggle("open");
            });
        });
    };

    const initTabs = () => {
        document.querySelectorAll('[data-bs-toggle="tab"]').forEach(tabEl => {
            tabEl.addEventListener("shown.bs.tab", event => {
                console.log("Active tab:", event.target.textContent.trim());
            });
        });
    };

    const initGlobalKeyboardShortcuts = () => {
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key.toLowerCase() === "j") {
                cycleTheme();
            }
        });
    };

    const init = () => {
        initSidebar();
        initSubmenus();
        initTabs();
        initGlobalKeyboardShortcuts();
    };

    init();
});
