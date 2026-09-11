document.addEventListener("DOMContentLoaded", () => {

    const THEMES = ["default", "dark", "aurora", "celestial"];

    const root = document.documentElement;
    const body = document.body;

    const toggleBtn = document.getElementById("themeToggle");

    let currentThemeIndex = 0;
    let isAnimating = false;

    // --------------------------------------------
    // LOAD SAVED THEME
    // --------------------------------------------
    const savedTheme = localStorage.getItem("theme");

    if (savedTheme && THEMES.includes(savedTheme)) {
        currentThemeIndex = THEMES.indexOf(savedTheme);
        applyTheme(savedTheme, false);
    } else {
        applyTheme(THEMES[0], false);
    }

    // --------------------------------------------
    // APPLY THEME CORE ENGINE
    // --------------------------------------------
    function applyTheme(theme, animate = true, x = 0.5, y = 0.5) {

        if (isAnimating) return;
        isAnimating = true;

        const flash = createFlash();

        if (animate) {
            triggerPortalEffect(flash, x, y);
        }

        requestAnimationFrame(() => {

            if (theme === "default") {
                root.removeAttribute("data-theme");
            } else {
                root.setAttribute("data-theme", theme);
            }

            localStorage.setItem("theme", theme);

            updateToggleIcon(theme);

            setTimeout(() => {
                isAnimating = false;
            }, animate ? 600 : 0);
        });
    }

    // --------------------------------------------
    // THEME CYCLE
    // --------------------------------------------
    function nextTheme() {
        currentThemeIndex = (currentThemeIndex + 1) % THEMES.length;
        const theme = THEMES[currentThemeIndex];
        applyTheme(theme, true);
    }

    // --------------------------------------------
    // BUTTON EVENT
    // --------------------------------------------
    if (toggleBtn) {
        toggleBtn.addEventListener("click", (e) => {

            const rect = toggleBtn.getBoundingClientRect();

            const x = (rect.left + rect.width / 2) / window.innerWidth;
            const y = (rect.top + rect.height / 2) / window.innerHeight;

            nextTheme(x, y);
        });
    }

    // --------------------------------------------
    // CURSOR-DRIVEN PORTAL EFFECT
    // --------------------------------------------
    document.addEventListener("mousemove", (e) => {
        document.documentElement.style.setProperty("--x", `${e.clientX}px`);
        document.documentElement.style.setProperty("--y", `${e.clientY}px`);
    });

    // --------------------------------------------
    // PORTAL FLASH LAYER
    // --------------------------------------------
    function createFlash() {
        let flash = document.querySelector(".theme-flash");

        if (!flash) {
            flash = document.createElement("div");
            flash.className = "theme-flash";
            document.body.appendChild(flash);
        }

        return flash;
    }

    function triggerPortalEffect(flash, x, y) {

        flash.style.setProperty("--x", `${x * 100}%`);
        flash.style.setProperty("--y", `${y * 100}%`);

        flash.classList.add("active");

        setTimeout(() => {
            flash.classList.remove("active");
        }, 450);
    }

    // --------------------------------------------
    // ICON UPDATE (INTELLIGENT STATE)
    // --------------------------------------------
    function updateToggleIcon(theme) {
        if (!toggleBtn) return;

        const icon = toggleBtn.querySelector("i");

        if (!icon) return;

        switch (theme) {
            case "dark":
                icon.className = "fas fa-moon";
                break;
            case "aurora":
                icon.className = "fas fa-wand-magic-sparkles";
                break;
            case "celestial":
                icon.className = "fas fa-star";
                break;
            default:
                icon.className = "fas fa-sun";
                break;
        }
    }

    // --------------------------------------------
    // GLOBAL EVENT API (FOR FUTURE SYSTEMS)
    // --------------------------------------------
    window.ThemeEngine = {
        set: (theme) => applyTheme(theme, true),
        next: nextTheme,
        get: () => THEMES[currentThemeIndex],
        list: () => [...THEMES]
    };

});