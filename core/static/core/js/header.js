"use strict";

class HeaderController {

    constructor() {

        /* =========================================================
           ELEMENT CACHE (SAFE LAZY RESOLUTION)
        ========================================================= */
        this.topbar = document.querySelector(".topbar");

        this.themeToggle = null;
        this.notificationBtn = null;
        this.notificationDropdown = null;
        this.notificationBadge = null;

        this.userMenuBtn = null;
        this.userDropdown = null;

        /* =========================================================
           STATE
        ========================================================= */
        this.activeDropdown = null;
        this.outsideHandlerActive = false;
        this.isAnimating = false;

        this.themes = [
            "daylight", "dawn", "ocean", "emerald",
            "celestial", "aurora", "inferno", "gold", "oled"
        ];

        this.currentThemeIndex = 0;

        /* =========================================================
           BINDINGS
        ========================================================= */
        this.boundOutsideClick = this.handleOutsideClick.bind(this);
        this.boundKeyHandler = this.handleKeydown.bind(this);
        this.boundScrollHandler = this.handleScroll.bind(this);
        this.boundStorageHandler = this.handleStorage.bind(this);

        this.init();
    }

    /* =========================================================
       INIT (DEFER SAFE)
    ========================================================= */
    init() {

        this.cacheElements();          // IMPORTANT FIX
        this.initializeTheme();
        this.bindThemeToggle();
        this.bindDropdowns();
        this.bindGlobalEvents();
        this.bindScrollState();
        this.initializeTooltips();
        this.initializeAccessibility();
    }

    /* =========================================================
       CACHE ELEMENTS (FIX: prevents null binding issues)
    ========================================================= */
    cacheElements() {

        this.themeToggle = document.getElementById("themeToggle");

        this.notificationBtn = document.getElementById("notificationBtn");
        this.notificationDropdown = document.getElementById("notificationDropdown");
        this.notificationBadge = document.getElementById("notificationBadge");

        this.userMenuBtn = document.getElementById("userMenuBtn");
        this.userDropdown = document.getElementById("userDropdown");
    }

    /* =========================================================
       ACCESSIBILITY
    ========================================================= */
    initializeAccessibility() {
        if (this.userMenuBtn)
            this.userMenuBtn.setAttribute("aria-expanded", "false");

        if (this.notificationBtn)
            this.notificationBtn.setAttribute("aria-expanded", "false");
    }

    /* =========================================================
       DROPDOWN CORE ENGINE (FIXED)
    ========================================================= */
    bindDropdowns() {

        this.bindDropdown(this.userMenuBtn, this.userDropdown);
        this.bindDropdown(this.notificationBtn, this.notificationDropdown);
    }

    bindDropdown(button, dropdown) {

        if (!button || !dropdown) return;

        // enforce class consistency
        dropdown.classList.add("dropdown-menu");
        dropdown.classList.remove("show");

        button.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();

            this.toggleDropdown(button, dropdown);
        });
    }

    toggleDropdown(button, dropdown) {

        const isOpen = dropdown.classList.contains("show");

        this.closeAllDropdowns();

        if (isOpen) return;

        dropdown.classList.add("show");
        button.setAttribute("aria-expanded", "true");

        this.activeDropdown = dropdown;

        if (!this.outsideHandlerActive) {
            document.addEventListener("click", this.boundOutsideClick);
            this.outsideHandlerActive = true;
        }
    }

    closeAllDropdowns() {

        document.querySelectorAll(".dropdown-menu.show")
            .forEach(el => el.classList.remove("show"));

        document.querySelectorAll("[aria-expanded='true']")
            .forEach(btn => btn.setAttribute("aria-expanded", "false"));

        this.activeDropdown = null;

        if (this.outsideHandlerActive) {
            document.removeEventListener("click", this.boundOutsideClick);
            this.outsideHandlerActive = false;
        }
    }

    handleOutsideClick(e) {

        if (!this.activeDropdown) return;

        const clickedInside = this.activeDropdown.contains(e.target);

        const clickedButton =
            (this.userMenuBtn && this.userMenuBtn.contains(e.target)) ||
            (this.notificationBtn && this.notificationBtn.contains(e.target));

        if (clickedInside || clickedButton) return;

        this.closeAllDropdowns();
    }

    /* =========================================================
       NOTIFICATIONS
    ========================================================= */
    updateNotificationBadge(count = 0) {

        if (!this.notificationBadge) return;

        if (count <= 0) {
            this.notificationBadge.style.display = "none";
            return;
        }

        this.notificationBadge.style.display = "grid";
        this.notificationBadge.textContent = count > 99 ? "99+" : String(count);
    }

    /* =========================================================
       KEYBOARD SUPPORT
    ========================================================= */
    handleKeydown(e) {

        if (e.key === "Escape") {
            this.closeAllDropdowns();
        }

        if (e.key.toLowerCase() === "t") {
            this.nextTheme();
        }
    }

    /* =========================================================
       SCROLL EFFECT
    ========================================================= */
    bindScrollState() {

        window.addEventListener("scroll", this.boundScrollHandler, { passive: true });

        this.handleScroll();
    }

    handleScroll() {

        if (!this.topbar) return;

        this.topbar.classList.toggle("scrolled", window.scrollY > 10);
    }

    /* =========================================================
       THEME ENGINE (SAFE + FIXED)
    ========================================================= */
    initializeTheme() {

        const stored = localStorage.getItem("theme");

        if (stored && this.themes.includes(stored)) {
            this.currentThemeIndex = this.themes.indexOf(stored);
            this.applyTheme(stored, false);
        } else {
            this.applyTheme(this.themes[0], false);
        }
    }

    bindThemeToggle() {

        if (!this.themeToggle) return;

        this.themeToggle.addEventListener("click", () => {

            const rect = this.themeToggle.getBoundingClientRect();

            const x = (rect.left + rect.width / 2) / window.innerWidth;
            const y = (rect.top + rect.height / 2) / window.innerHeight;

            this.nextTheme(x, y);
        });
    }

    nextTheme(x = 0.5, y = 0.5) {

        this.currentThemeIndex =
            (this.currentThemeIndex + 1) % this.themes.length;

        const theme = this.themes[this.currentThemeIndex];

        this.applyTheme(theme, true, x, y);
    }

    applyTheme(theme, animate = true, x = 0.5, y = 0.5) {

        if (this.isAnimating) return;
        this.isAnimating = true;

        const flash = this.createFlash();

        if (animate) this.triggerPortalEffect(flash, x, y);

        requestAnimationFrame(() => {

            document.documentElement.setAttribute("data-theme", theme);

            localStorage.setItem("theme", theme);

            this.updateToggleIcon(theme);

            setTimeout(() => {
                this.isAnimating = false;
            }, animate ? 500 : 0);
        });
    }

    /* =========================================================
       PORTAL EFFECT
    ========================================================= */
    createFlash() {

        let flash = document.querySelector(".theme-flash");

        if (!flash) {
            flash = document.createElement("div");
            flash.className = "theme-flash";
            document.body.appendChild(flash);
        }

        return flash;
    }

    triggerPortalEffect(flash, x, y) {

        flash.style.setProperty("--x", `${x * 100}%`);
        flash.style.setProperty("--y", `${y * 100}%`);

        flash.classList.add("active");

        setTimeout(() => {
            flash.classList.remove("active");
        }, 450);
    }

    /* =========================================================
       ICON UPDATE
    ========================================================= */
    updateToggleIcon(theme) {

        if (!this.themeToggle) return;

        const icon = this.themeToggle.querySelector("i");

        if (!icon) return;

        const ICON_MAP = {
            "daylight": "fas fa-sun",
            "dawn": "fas fa-sun",
            "ocean": "fas fa-water",
            "emerald": "fas fa-leaf",
            "celestial": "fas fa-star",
            "aurora": "fas fa-wand-magic-sparkles",
            "inferno": "fas fa-fire",
            "gold": "fas fa-gem",
            "oled": "fas fa-moon"
        };

        icon.className = ICON_MAP[theme] || "fas fa-sun";
    }

    /* =========================================================
       GLOBAL EVENTS
    ========================================================= */
    bindGlobalEvents() {

        document.addEventListener("keydown", this.boundKeyHandler);
        window.addEventListener("storage", this.boundStorageHandler);

        document.addEventListener("mousemove", (e) => {
            document.documentElement.style.setProperty("--x", `${e.clientX}px`);
            document.documentElement.style.setProperty("--y", `${e.clientY}px`);
        });
    }

    handleStorage(event) {

        if (
            event.key === "theme" &&
            event.newValue &&
            this.themes.includes(event.newValue)
        ) {
            this.currentThemeIndex =
                this.themes.indexOf(event.newValue);

            this.applyTheme(event.newValue, false);
        }
    }

    /* =========================================================
       TOOLTIP CLEANUP
    ========================================================= */
    initializeTooltips() {

        document.querySelectorAll("[title]").forEach(el => {

            el.dataset.tooltip = el.getAttribute("title");
            el.removeAttribute("title");
        });
    }
}

/* =========================================================
   BOOTSTRAP
========================================================= */
document.addEventListener("DOMContentLoaded", () => {
    window.headerController = new HeaderController();
});