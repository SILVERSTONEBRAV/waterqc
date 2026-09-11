document.addEventListener("DOMContentLoaded", () => {
    const sidebar = document.querySelector(".sidebar");
    const contentWrapper = document.querySelector(".content-wrapper");
    const submenuToggles = document.querySelectorAll('.toggle-children');

    // =========================
    // Hover expansion/collapse
    // =========================
    sidebar.addEventListener("mouseenter", () => {
        sidebar.classList.add("expanded");
        contentWrapper.style.marginLeft = getComputedStyle(sidebar).width;
    });

    sidebar.addEventListener("mouseleave", () => {
        sidebar.classList.remove("expanded");
        contentWrapper.style.marginLeft = getComputedStyle(sidebar).width;
    });

    // =========================
    // Submenu toggling
    // =========================
    submenuToggles.forEach(toggle => {
        toggle.addEventListener("click", e => {
            e.preventDefault();
            const parent = toggle.parentElement;
            const submenu = parent.querySelector(".sidebar-submenu");

            parent.classList.toggle("open");

            if (submenu) {
                if (parent.classList.contains("open")) {
                    submenu.style.maxHeight = submenu.scrollHeight + "px";
                } else {
                    submenu.style.maxHeight = "0px";
                }
            }
        });
    });

    // =========================
    // Open submenus on page load
    // =========================
    document.querySelectorAll(".sidebar-item.open .sidebar-submenu").forEach(submenu => {
        submenu.style.maxHeight = submenu.scrollHeight + "px";
    });
});
