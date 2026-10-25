/**
 * Shared QAD theme engine.
 * Keeps the Django Admin inspired enterprise palette consistent across apps,
 * with automatic time-of-day and operating-system lighting support.
 */
(function () {
    'use strict';

    var THEMES = [
        { name: 'day', label: 'Enterprise · Standard Admin', icon: 'fas fa-sun', color: '#417690', scheme: 'light' },
        { name: 'dawn', label: 'Dawn · Warm morning', icon: 'fas fa-sun', color: '#8c531e', scheme: 'light' },
        { name: 'ocean', label: 'Summer · Clear daylight', icon: 'fas fa-water', color: '#326d83', scheme: 'light' },
        { name: 'emerald', label: 'Spring · Fresh water', icon: 'fas fa-leaf', color: '#3c7557', scheme: 'light' },
        { name: 'autumn', label: 'Autumn · Warm neutral', icon: 'fas fa-leaf', color: '#81512a', scheme: 'light' },
        { name: 'winter', label: 'Winter · Cool daylight', icon: 'fas fa-snowflake', color: '#46688f', scheme: 'light' },
        { name: 'dusk', label: 'Dusk · Evening', icon: 'fas fa-cloud-moon', color: '#e0ad79', scheme: 'dark' },
        { name: 'night', label: 'Night · Low light', icon: 'fas fa-moon', color: '#8cc7db', scheme: 'dark' },
        { name: 'aurora', label: 'Aurora · Midnight', icon: 'fas fa-star', color: '#9bb8f2', scheme: 'dark' },
        { name: 'emerald-dark', label: 'Emerald Night', icon: 'fas fa-leaf', color: '#8bcba7', scheme: 'dark' },
        { name: 'high-contrast', label: 'High contrast · Bright environments', icon: 'fas fa-adjust', color: '#005fcc', scheme: 'light' }
    ];

    var AUTO = { name: 'auto', label: 'Automatic · Time and lighting', icon: 'fas fa-adjust' };
    var THEME_NAMES = THEMES.map(function (theme) { return theme.name; });
    var CYCLE_NAMES = ['auto'].concat(THEME_NAMES);
    var THEME_BY_NAME = THEMES.reduce(function (map, theme) {
        map[theme.name] = theme;
        return map;
    }, {});
    var ALIASES = {
        'default': 'day', 'standard': 'day', 'enterprise': 'day', 'light': 'day', 'daylight': 'day',
        'dark': 'night', 'oled': 'night', 'amoled': 'night',
        'celestial': 'aurora', 'gold': 'dawn', 'inferno': 'dusk',
        'summer': 'ocean', 'spring': 'emerald', 'contrast': 'high-contrast'
    };
    var root = document.documentElement;
    var STORAGE_KEY = 'qad_theme';
    var LEGACY_STORAGE_KEY = 'theme';
    var MANUAL_KEY = 'qad_theme_manual';
    var mode = 'auto';
    var darkThemes = THEMES.filter(function (theme) { return theme.scheme === 'dark'; })
        .map(function (theme) { return theme.name; });

    function normalize(name) {
        name = String(name || '').trim().toLowerCase();
        if (name === 'auto') return 'auto';
        if (ALIASES[name]) return ALIASES[name];
        return THEME_BY_NAME[name] ? name : 'day';
    }

    function mediaMatches(query) {
        try { return Boolean(window.matchMedia && window.matchMedia(query).matches); }
        catch (e) { return false; }
    }

    function automaticTheme() {
        if (mediaMatches('(prefers-contrast: more)')) return 'high-contrast';

        var hour = new Date().getHours();
        var darkPreference = mediaMatches('(prefers-color-scheme: dark)');

        // Evening keeps a warm, dark surface; other dark-system preferences use
        // the neutral night palette. Light-system preferences follow local time.
        if (hour >= 17 && hour < 20) return 'dusk';
        if (darkPreference || hour >= 20 || hour < 5) return 'night';
        if (hour >= 5 && hour < 9) return 'dawn';
        return 'day';
    }

    function updateMetaThemeColor(name) {
        var meta = document.querySelector('meta[name="theme-color"]');
        var theme = THEME_BY_NAME[name];
        if (meta && theme) meta.setAttribute('content', theme.color);
    }

    function updateToggleButtons(name) {
        var currentTheme = THEME_BY_NAME[name] || THEMES[0];
        var nextIndex = (CYCLE_NAMES.indexOf(mode) + 1) % CYCLE_NAMES.length;
        var nextName = CYCLE_NAMES[nextIndex];
        var nextTheme = nextName === 'auto' ? AUTO : THEME_BY_NAME[nextName];
        var currentLabel = mode === 'auto' ? 'Automatic · currently ' + currentTheme.label : currentTheme.label;
        var label = 'Current theme: ' + currentLabel + '. Activate to switch to ' + nextTheme.label + '.';

        document.querySelectorAll('#themeToggle, .theme-toggle, [data-theme-toggle]').forEach(function (button) {
            var icon = button.querySelector('i');
            if (icon) icon.className = mode === 'auto' ? AUTO.icon : currentTheme.icon;
            button.setAttribute('title', label);
            button.setAttribute('aria-label', label);
            button.setAttribute('data-current-theme', name);
            button.setAttribute('data-theme-mode', mode);
        });
    }

    function applyTheme(name, options) {
        options = options || {};
        name = normalize(name);
        if (name === 'auto') name = automaticTheme();
        var isDark = darkThemes.indexOf(name) !== -1;

        root.setAttribute('data-theme', name);
        root.setAttribute('data-theme-mode', mode);
        root.classList.toggle('theme-day', name === 'day');
        root.classList.toggle('theme-night', isDark);
        root.classList.toggle('theme-light', !isDark);
        root.classList.toggle('theme-dark', isDark);
        root.classList.toggle('theme-auto', mode === 'auto');

        if (options.persist !== false) {
            try {
                var storedName = mode === 'auto' ? 'auto' : name;
                localStorage.setItem(STORAGE_KEY, storedName);
                localStorage.setItem(LEGACY_STORAGE_KEY, storedName);
                if (mode === 'auto') localStorage.removeItem(MANUAL_KEY);
                else localStorage.setItem(MANUAL_KEY, 'true');
            } catch (e) { /* Storage may be disabled by the browser. */ }
        }

        updateToggleButtons(name);
        updateMetaThemeColor(name);

        if (options.dispatch !== false) {
            window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: name, mode: mode } }));
        }
        return name;
    }

    function setAutomatic(options) {
        mode = 'auto';
        return applyTheme(automaticTheme(), options);
    }

    function setTheme(name) {
        name = normalize(name);
        if (name === 'auto') return setAutomatic();
        mode = 'manual';
        return applyTheme(name);
    }

    function cycleTheme() {
        var current = mode === 'auto' ? 'auto' : normalize(root.getAttribute('data-theme'));
        var currentIndex = CYCLE_NAMES.indexOf(current);
        var nextName = CYCLE_NAMES[(currentIndex + 1) % CYCLE_NAMES.length];
        return nextName === 'auto' ? setAutomatic() : setTheme(nextName);
    }

    function readSavedTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY) ||
                localStorage.getItem(LEGACY_STORAGE_KEY) ||
                localStorage.getItem('qca_theme');
        } catch (e) {
            return null;
        }
    }

    function init() {
        var saved = readSavedTheme();
        mode = saved && normalize(saved) !== 'auto' ? 'manual' : 'auto';
        applyTheme(mode === 'auto' ? automaticTheme() : normalize(saved), {
            dispatch: false,
            persist: true
        });
        root.classList.add('fullscreen-app');
    }

    function wireButtons() {
        document.querySelectorAll('#themeToggle, .theme-toggle, [data-theme-toggle]').forEach(function (button) {
            if (button.dataset.themeEngineBound === 'true') return;
            button.dataset.themeEngineBound = 'true';
            button.addEventListener('click', function (event) {
                event.preventDefault();
                cycleTheme();
            });
        });
        updateToggleButtons(normalize(root.getAttribute('data-theme')));
    }

    function refreshAutomaticTheme() {
        if (mode === 'auto') applyTheme(automaticTheme(), { dispatch: true, persist: false });
    }

    window.ThemeEngine = {
        set: setTheme,
        cycle: cycleTheme,
        toggle: cycleTheme,
        get: function () { return normalize(root.getAttribute('data-theme')); },
        getMode: function () { return mode; },
        list: function () { return CYCLE_NAMES.slice(); },
        normalize: normalize,
        resetAuto: function () { return setAutomatic(); }
    };

    // Run synchronously in the document head to apply the saved theme before first paint.
    init();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireButtons, { once: true });
    } else {
        wireButtons();
    }

    window.addEventListener('storage', function (event) {
        if (event.key === STORAGE_KEY || event.key === LEGACY_STORAGE_KEY || event.key === 'qca_theme') {
            var next = event.newValue ? normalize(event.newValue) : 'auto';
            if (next === 'auto') setAutomatic({ dispatch: true, persist: false });
            else {
                mode = 'manual';
                applyTheme(next, { dispatch: true, persist: false });
            }
        }
    });

    ['(prefers-color-scheme: dark)', '(prefers-contrast: more)'].forEach(function (query) {
        try {
            var media = window.matchMedia && window.matchMedia(query);
            if (media && typeof media.addEventListener === 'function') {
                media.addEventListener('change', refreshAutomaticTheme);
            } else if (media && typeof media.addListener === 'function') {
                media.addListener(refreshAutomaticTheme);
            }
        } catch (e) { /* Ignore unavailable media-query APIs. */ }
    });

    window.setInterval(refreshAutomaticTheme, 60000);
})();
