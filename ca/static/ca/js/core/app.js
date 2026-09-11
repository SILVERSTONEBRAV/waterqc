(function () {
    "use strict";

    const CA = window.CA = window.CA || {};

    CA.state = CA.state || {
        sidebarOpen: true,
        activeOverlay: null,
        loading: false
    };

    CA.dom = {
        ready(callback) {
            if (document.readyState === "loading") {
                document.addEventListener("DOMContentLoaded", callback, {
                    once: true
                });
            } else {
                callback();
            }
        },

        get(selector, root = document) {
            return root.querySelector(selector);
        },

        getAll(selector, root = document) {
            return Array.from(root.querySelectorAll(selector));
        }
    };

    CA.events = {
        on(target, event, handler, options) {
            if (!target) {
                return;
            }

            target.addEventListener(event, handler, options);
        },

        emit(name, detail = {}) {
            document.dispatchEvent(
                new CustomEvent(`ca:${name}`, {
                    detail
                })
            );
        }
    };

    CA.storage = {
        get(key, fallback = null) {
            try {
                const value = localStorage.getItem(key);

                if (value === null) {
                    return fallback;
                }

                return JSON.parse(value);
            } catch (error) {
                return fallback;
            }
        },

        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
            } catch (error) {
                return false;
            }

            return true;
        },

        remove(key) {
            try {
                localStorage.removeItem(key);
            } catch (error) {
                return false;
            }

            return true;
        }
    };

    CA.ui = {
        show(element) {
            if (!element) {
                return;
            }

            element.hidden = false;
            element.setAttribute("aria-hidden", "false");
        },

        hide(element) {
            if (!element) {
                return;
            }

            element.hidden = true;
            element.setAttribute("aria-hidden", "true");
        },

        toggle(element, force) {
            if (!element) {
                return;
            }

            const visible = force === undefined
                ? element.hidden
                : force;

            if (visible) {
                this.show(element);
            } else {
                this.hide(element);
            }
        }
    };

    CA.sidebar = {
        init() {
            const toggle = CA.dom.get("#sidebar-toggle");
            const sidebar = CA.dom.get("#ca-sidebar, .ca-sidebar");

            if (!toggle || !sidebar) {
                return;
            }

            const stored = CA.storage.get(
                "ca.sidebar.open",
                window.innerWidth > 800
            );

            this.setOpen(stored);

            CA.events.on(toggle, "click", () => {
                this.setOpen(!CA.state.sidebarOpen);
            });
        },

        setOpen(open) {
            const sidebar = CA.dom.get("#ca-sidebar, .ca-sidebar");
            const toggle = CA.dom.get("#sidebar-toggle");

            if (!sidebar) {
                return;
            }

            CA.state.sidebarOpen = Boolean(open);

            sidebar.classList.toggle("is-open", CA.state.sidebarOpen);

            if (toggle) {
                toggle.setAttribute(
                    "aria-expanded",
                    String(CA.state.sidebarOpen)
                );
            }

            CA.storage.set(
                "ca.sidebar.open",
                CA.state.sidebarOpen
            );
        }
    };

    CA.overlays = {
        closeAll() {
            CA.dom.getAll(
                ".ca-overlay, .ca-modal-root, .ca-drawer-root, .ca-loading-overlay"
            ).forEach((element) => {
                CA.ui.hide(element);
            });

            CA.state.activeOverlay = null;
            document.body.classList.remove("ca-overlay-open");
        },

        open(selector) {
            this.closeAll();

            const element = CA.dom.get(selector);

            if (!element) {
                return;
            }

            CA.ui.show(element);
            CA.state.activeOverlay = selector;
            document.body.classList.add("ca-overlay-open");
        }
    };

    CA.search = {
        init() {
            CA.dom.getAll(
                '[data-action="open-search"]'
            ).forEach((button) => {
                CA.events.on(button, "click", () => {
                    this.open();
                });
            });

            CA.dom.getAll(
                '[data-action="close-search"]'
            ).forEach((button) => {
                CA.events.on(button, "click", () => {
                    this.close();
                });
            });

            const input = CA.dom.get("#global-search-input");

            if (input) {
                CA.events.on(input, "keydown", (event) => {
                    if (event.key === "Escape") {
                        this.close();
                    }
                });
            }
        },

        open() {
            CA.overlays.open("#search-overlay");

            const input = CA.dom.get("#global-search-input");

            if (input) {
                window.setTimeout(() => input.focus(), 50);
            }
        },

        close() {
            CA.ui.hide(CA.dom.get("#search-overlay"));
            document.body.classList.remove("ca-overlay-open");
            CA.state.activeOverlay = null;
        }
    };

    CA.commandPalette = {
        init() {
            CA.dom.getAll(
                '[data-action="open-command-palette"]'
            ).forEach((button) => {
                CA.events.on(button, "click", () => {
                    this.open();
                });
            });

            const input = CA.dom.get("#command-search");

            if (input) {
                CA.events.on(input, "input", () => {
                    this.filter(input.value);
                });

                CA.events.on(input, "keydown", (event) => {
                    if (event.key === "Escape") {
                        this.close();
                    }
                });
            }

            CA.dom.getAll(".ca-command-item").forEach((item) => {
                CA.events.on(item, "click", () => {
                    this.execute(item.dataset.command);
                });
            });
        },

        open() {
            CA.overlays.open("#command-palette");

            const input = CA.dom.get("#command-search");

            if (input) {
                input.value = "";
                this.filter("");

                window.setTimeout(() => input.focus(), 50);
            }
        },

        close() {
            CA.ui.hide(CA.dom.get("#command-palette"));
            document.body.classList.remove("ca-overlay-open");
            CA.state.activeOverlay = null;
        },

        filter(query) {
            const normalized = query.trim().toLowerCase();

            CA.dom.getAll(".ca-command-item").forEach((item) => {
                const text = item.textContent.toLowerCase();

                item.hidden = normalized.length > 0 &&
                    !text.includes(normalized);
            });
        },

        execute(command) {
            const routes = {
                dashboard: "{% url 'ca:dashboard' %}",
                batches: "#",
                requests: "#",
                reports: "#",
                "create-batch": "#",
                "new-request": "#",
                "generate-report": "#"
            };

            const target = routes[command];

            if (target && target !== "#") {
                window.location.href = target;
                return;
            }

            this.close();

            CA.events.emit("command", {
                command
            });
        }
    };

    CA.userMenu = {
        init() {
            const trigger = CA.dom.get(
                '[data-action="toggle-user-menu"]'
            );

            const menu = CA.dom.get(".ca-user-dropdown");

            if (!trigger || !menu) {
                return;
            }

            CA.events.on(trigger, "click", (event) => {
                event.stopPropagation();

                const open = menu.hidden;

                menu.hidden = !open;
                trigger.setAttribute(
                    "aria-expanded",
                    String(open)
                );
            });

            CA.events.on(document, "click", () => {
                menu.hidden = true;
                trigger.setAttribute(
                    "aria-expanded",
                    "false"
                );
            });
        }
    };

    CA.notifications = {
        init() {
            const trigger = CA.dom.get(
                '[data-action="toggle-notifications"]'
            );

            const panel = CA.dom.get(".ca-notification-panel");

            if (!trigger || !panel) {
                return;
            }

            CA.events.on(trigger, "click", (event) => {
                event.stopPropagation();

                const open = panel.hidden;

                panel.hidden = !open;

                trigger.setAttribute(
                    "aria-expanded",
                    String(open)
                );
            });

            CA.events.on(document, "click", () => {
                panel.hidden = true;

                trigger.setAttribute(
                    "aria-expanded",
                    "false"
                );
            });
        }
    };

    CA.keyboard = {
        init() {
            CA.events.on(document, "keydown", (event) => {
                if (
                    (event.ctrlKey || event.metaKey) &&
                    event.key.toLowerCase() === "k"
                ) {
                    event.preventDefault();
                    CA.search.open();
                }

                if (event.key === "Escape") {
                    CA.overlays.closeAll();
                }
            });
        }
    };

    CA.loading = {
        show(title = "Processing", message = "Please wait...") {
            const overlay = CA.dom.get("#global-loading");

            if (!overlay) {
                return;
            }

            const titleElement = CA.dom.get("#loading-title");
            const messageElement = CA.dom.get("#loading-message");

            if (titleElement) {
                titleElement.textContent = title;
            }

            if (messageElement) {
                messageElement.textContent = message;
            }

            CA.ui.show(overlay);
            CA.state.loading = true;
        },

        hide() {
            CA.ui.hide(
                CA.dom.get("#global-loading")
            );

            CA.state.loading = false;
        }
    };

    CA.toast = {
        show(message, type = "info", duration = 4000) {
            const container = CA.dom.get("#toast-container");

            if (!container) {
                return;
            }

            const toast = document.createElement("div");

            toast.className = `ca-toast ca-toast-${type}`;
            toast.textContent = message;
            toast.setAttribute("role", "status");

            container.appendChild(toast);

            window.setTimeout(() => {
                toast.remove();
            }, duration);
        }
    };

    CA.actions = {
        init() {
            CA.dom.getAll(
                '[data-action="close-modal"]'
            ).forEach((element) => {
                CA.events.on(element, "click", () => {
                    CA.ui.hide(CA.dom.get("#ca-modal-root"));
                });
            });

            CA.dom.getAll(
                '[data-action="close-drawer"]'
            ).forEach((element) => {
                CA.events.on(element, "click", () => {
                    CA.ui.hide(CA.dom.get("#ca-drawer-root"));
                });
            });
        }
    };

    CA.init = function () {
        CA.sidebar.init();
        CA.search.init();
        CA.commandPalette.init();
        CA.userMenu.init();
        CA.notifications.init();
        CA.keyboard.init();
        CA.actions.init();

        CA.events.emit("ready");
    };

    CA.dom.ready(CA.init);
})();