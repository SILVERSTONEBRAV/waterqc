document.addEventListener("DOMContentLoaded", () => {

    const sidebar = document.querySelector(".sidebar");

    const themes = ["light", "dark", "aurora", "celestial"];

    const getStoredTheme = () => localStorage.getItem("theme");

    const getSystemTheme = () =>
        window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

    const applyTheme = (theme) => {
        document.documentElement.setAttribute("data-theme", theme);
        localStorage.setItem("theme", theme);

        const btn = document.getElementById("themeToggle");
        const icon = btn?.querySelector("i");

        if (icon) {
            if (theme === "dark") icon.className = "fas fa-moon";
            else if (theme === "light") icon.className = "fas fa-sun";
            else if (theme === "aurora") icon.className = "fas fa-wand-magic-sparkles";
            else icon.className = "fas fa-star";
        }
    };

    const initTheme = () => {
        const theme = getStoredTheme() || getSystemTheme();
        applyTheme(theme);
    };

    const cycleTheme = () => {
        const current = document.documentElement.getAttribute("data-theme") || "light";
        const next = themes[(themes.indexOf(current) + 1) % themes.length];
        applyTheme(next);
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

    const initThemeToggle = () => {
        const btn = document.getElementById("themeToggle");
        if (!btn) return;

        btn.addEventListener("click", cycleTheme);
    };

    const initGlobalKeyboardShortcuts = () => {
        document.addEventListener("keydown", (e) => {
            if (e.ctrlKey && e.key.toLowerCase() === "j") {
                cycleTheme();
            }
        });
    };

    const init = () => {
        initTheme();
        initSidebar();
        initSubmenus();
        initTabs();
        initThemeToggle();
        initGlobalKeyboardShortcuts();
    };

    init();
});