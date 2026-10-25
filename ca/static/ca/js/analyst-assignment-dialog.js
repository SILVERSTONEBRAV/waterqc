(() => {
    const dialog = document.getElementById("ca-analyst-assignment-dialog");
    const content = document.getElementById("ca-analyst-assignment-content");
    if (!dialog || !content) return;

    const setMessage = (message, isError = false) => {
        content.innerHTML = "";
        const paragraph = document.createElement("p");
        paragraph.className = isError ? "ca-assignment-error" : "ca-assignment-loading";
        paragraph.setAttribute("role", isError ? "alert" : "status");
        paragraph.textContent = message;
        content.append(paragraph);
    };

    const showFormError = (message) => {
        const form = content.querySelector("form[data-ca-assignment-form]");
        if (!form) {
            setMessage(message, true);
            return;
        }
        let errors = form.querySelector("[data-ca-assignment-errors]");
        if (!errors) {
            errors = document.createElement("div");
            errors.className = "ca-assignment-errors";
            errors.dataset.caAssignmentErrors = "";
            errors.setAttribute("aria-live", "assertive");
            form.prepend(errors);
        }
        errors.replaceChildren();
        const panel = document.createElement("div");
        panel.className = "ca-assignment-error-panel";
        panel.setAttribute("role", "alert");
        const title = document.createElement("strong");
        title.textContent = "Assignment not saved";
        const detail = document.createElement("span");
        detail.textContent = message;
        panel.append(title, detail);
        errors.append(panel);
    };

    const clearFormError = (form) => {
        const errors = form.querySelector("[data-ca-assignment-errors]");
        if (errors) errors.replaceChildren();
    };

    const filterAnalysts = (scope) => {
        const search = scope.querySelector("[data-ca-analyst-search]");
        const list = scope.querySelector(".ca-assignment-checklist ul");
        if (!search || !list) return;
        const items = Array.from(list.querySelectorAll("li"));
        const term = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        items.forEach((item) => {
            const matches = !term || item.textContent.toLocaleLowerCase().includes(term);
            item.hidden = !matches;
            if (matches) visible += 1;
        });
        const count = scope.querySelector("[data-ca-analyst-visible-count]");
        if (count) count.textContent = String(visible);
        const noMatch = scope.querySelector("[data-ca-analyst-no-match]");
        if (noMatch) noMatch.hidden = visible !== 0;
    };

    const openDialogFor = async (href) => {
        const url = new URL(href, window.location.href);
        url.searchParams.set("dialog", "1");
        setMessage("Loading users who can perform chemical analysis…");
        if (!dialog.open) dialog.showModal();
        dialog.setAttribute("aria-busy", "true");
        try {
            const response = await fetch(url, {
                credentials: "same-origin",
                cache: "no-store",
                headers: {
                    Accept: "text/html",
                    "X-CA-Dialog": "1",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            if (response.redirected && !response.url.includes("assign-analyst")) {
                window.location.assign(response.url);
                return;
            }
            if (!response.ok) {
                throw new Error(response.status === 403
                    ? "You do not have permission to assign analysts for this request."
                    : "The analyst assignment form could not be loaded.");
            }
            content.innerHTML = await response.text();
            updateAssignmentButton(content);
            filterAnalysts(content);
        } catch (error) {
            setMessage(error.message || "The analyst assignment form could not be loaded.", true);
        } finally {
            dialog.removeAttribute("aria-busy");
        }
    };

    const updateAssignmentButton = (scope) => {
        const form = scope.querySelector("form[data-ca-assignment-form]");
        if (!form) return;
        const button = form.querySelector("[data-ca-assignment-submit]");
        const checkboxes = Array.from(form.querySelectorAll('input[type="checkbox"]'))
            .filter((input) => input.name === "analysts");
        if (!button) return;
        const selected = checkboxes.filter((input) => input.checked).length;
        button.disabled = selected === 0;
        button.textContent = selected
            ? `Assign ${selected} analyst${selected === 1 ? "" : "s"}`
            : "Select analysts";
    };

    document.addEventListener("click", (event) => {
        const closeButton = event.target.closest("[data-ca-assignment-close]");
        if (closeButton && dialog.contains(closeButton)) {
            dialog.close();
            return;
        }

        const link = event.target.closest('a[data-ca-analyst-assignment], a[href*="/assign-analyst/"]');
        if (!link || event.defaultPrevented || event.button !== 0
            || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
            || link.target === "_blank") return;

        event.preventDefault();
        openDialogFor(link.href);
    });

    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });

    dialog.addEventListener("change", (event) => {
        if (event.target.matches('input[type="checkbox"][name="analysts"]')) {
            updateAssignmentButton(content);
        }
    });

    dialog.addEventListener("input", (event) => {
        if (event.target.matches("[data-ca-analyst-search]")) {
            filterAnalysts(content);
        }
    });

    dialog.addEventListener("submit", async (event) => {
        const form = event.target.closest("form[data-ca-assignment-form]");
        if (!form) return;
        event.preventDefault();
        if (dialog.hasAttribute("aria-busy")) return;
        clearFormError(form);
        const button = form.querySelector("[data-ca-assignment-submit]");
        if (button) {
            button.disabled = true;
            button.textContent = "Saving assignment…";
        }
        dialog.setAttribute("aria-busy", "true");
        try {
            const response = await fetch(form.action || window.location.href, {
                method: "POST",
                credentials: "same-origin",
                cache: "no-store",
                body: new FormData(form),
                headers: {
                    Accept: "application/json, text/html",
                    "X-CA-Dialog": "1",
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const contentType = response.headers.get("content-type") || "";
            if (contentType.includes("application/json")) {
                const payload = await response.json();
                if (!response.ok || !payload.success || !payload.redirect_url) {
                    throw new Error(payload.message || "The analyst assignment could not be saved.");
                }
                window.location.assign(payload.redirect_url);
                return;
            }
            if (response.redirected && !response.url.includes("assign-analyst")) {
                window.location.assign(response.url);
                return;
            }
            const html = await response.text();
            const parsed = new DOMParser().parseFromString(html, "text/html");
            const renderedForm = parsed.querySelector(".ca-assignment-form-content");
            if (renderedForm) {
                content.replaceChildren(renderedForm);
                updateAssignmentButton(content);
                filterAnalysts(content);
                const firstError = content.querySelector('[role="alert"]');
                if (firstError) firstError.setAttribute("tabindex", "-1");
                firstError?.focus({ preventScroll: true });
                return;
            }
            if (!response.ok) {
                throw new Error(response.status === 403
                    ? "You do not have permission to assign analysts for this request."
                    : "The assignment could not be saved. Please try again.");
            }
            content.innerHTML = html;
            updateAssignmentButton(content);
            filterAnalysts(content);
        } catch (error) {
            showFormError(error.message || "The analyst assignment could not be saved. Please try again.");
            updateAssignmentButton(content);
        } finally {
            dialog.removeAttribute("aria-busy");
        }
    });
})();
