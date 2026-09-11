document.addEventListener("DOMContentLoaded", () => {

    const form = document.getElementById("change-password-form");
    const newPwd = document.getElementById("new_password");
    const confirmPwd = document.getElementById("confirm_password");

    const strengthFill = document.querySelector(".strength-fill");
    const strengthText = document.querySelector(".strength-text");
    const submitBtn = form?.querySelector("button[type='submit']");

    function strength(val) {
        let s = 0;
        if (/[A-Z]/.test(val)) s++;
        if (/[a-z]/.test(val)) s++;
        if (/[0-9]/.test(val)) s++;
        if (/[^A-Za-z0-9]/.test(val)) s++;
        if (val.length >= 8) s++;
        return s;
    }

    function update() {
        if (!newPwd || !confirmPwd) return;

        const v = newPwd.value;
        const c = confirmPwd.value;

        const score = strength(v);
        const pct = (score / 5) * 100;

        if (strengthFill) {
            strengthFill.style.width = pct + "%";
        }

        const labels = ["Very Weak", "Weak", "Medium", "Strong", "Very Strong"];

        if (v && v === c) {
            strengthText.textContent = "Passwords Match";
            submitBtn.disabled = false;
        } else {
            strengthText.textContent = labels[score] || "Weak";
            submitBtn.disabled = true;
        }
    }

    newPwd?.addEventListener("input", update);
    confirmPwd?.addEventListener("input", update);

    // password toggle
    [newPwd, confirmPwd].forEach(input => {
        if (!input) return;

        const toggle = document.createElement("span");
        toggle.className = "toggle-password";
        toggle.innerHTML = '<i class="fas fa-eye"></i>';

        input.parentElement.style.position = "relative";
        input.parentElement.appendChild(toggle);

        toggle.addEventListener("click", () => {
            const visible = input.type === "text";
            input.type = visible ? "password" : "text";
            toggle.innerHTML = visible
                ? '<i class="fas fa-eye"></i>'
                : '<i class="fas fa-eye-slash"></i>';
        });
    });

    // reset after success render
    const changed = document.getElementById("passwordChangedFlag");

    if (changed) {
        form?.reset();
        strengthFill && (strengthFill.style.width = "0%");
        strengthText && (strengthText.textContent = "");

        setTimeout(() => {
            Modal.close("changePasswordModal");
        }, 1200);
    }
});