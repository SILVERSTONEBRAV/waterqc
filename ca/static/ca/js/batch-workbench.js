(() => {
    const workbench = document.querySelector("[data-workbench]");
    if (!workbench) return;

    const tabs = Array.from(workbench.querySelectorAll('[role="tab"][href]'));
    const panels = Array.from(workbench.querySelectorAll('[role="tabpanel"]'));
    if (!tabs.length || !panels.length) return;

    tabs.forEach((tab) => {
        tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;
    });

    const activate = (tab, updateHistory = true) => {
        const key = tab.id.replace("workflow-tab-", "");
        tabs.forEach((item) => {
            const selected = item === tab;
            item.setAttribute("aria-selected", String(selected));
            item.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel) => {
            panel.hidden = panel.id !== `workflow-stage-${key}`;
        });
        if (updateHistory) {
            const url = new URL(tab.href, window.location.href);
            window.history.pushState({ stage: key }, "", url);
        }
    };

    tabs.forEach((tab) => {
        tab.addEventListener("click", (event) => {
            if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
            event.preventDefault();
            activate(tab);
        });
        tab.addEventListener("keydown", (event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const current = tabs.indexOf(tab);
            let target = current;
            if (event.key === "ArrowRight") target = (current + 1) % tabs.length;
            if (event.key === "ArrowLeft") target = (current - 1 + tabs.length) % tabs.length;
            if (event.key === "Home") target = 0;
            if (event.key === "End") target = tabs.length - 1;
            tabs[target].focus();
            activate(tabs[target]);
        });
    });

    window.addEventListener("popstate", () => {
        const requested = new URL(window.location.href).searchParams.get("stage");
        const tab = tabs.find((item) => item.id === `workflow-tab-${requested}`);
        if (tab) activate(tab, false);
    });
})();
