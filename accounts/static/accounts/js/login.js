document.addEventListener('DOMContentLoaded', () => {

    // -----------------------------
    // Elements
    // -----------------------------
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const togglePassword = document.getElementById('togglePassword');
    const loginBtn = document.getElementById('loginBtn');
    const loginForm = document.getElementById('loginForm');
    const errorDiv = document.getElementById('errorMessage');

    let errorTimeout = null;

    // -----------------------------
    // CSRF Helper (cookie-based)
    // -----------------------------
    function getCSRFToken() {
        const name = 'csrftoken=';
        const cookies = document.cookie.split(';');
        for (let c of cookies) {
            c = c.trim();
            if (c.startsWith(name)) return c.substring(name.length);
        }
        return '';
    }

    // -----------------------------
    // Utility Functions
    // -----------------------------
    function showError(message, duration = 4000) {
        if (!errorDiv) return;
        if (errorTimeout) clearTimeout(errorTimeout);

        errorDiv.innerText = message;
        errorDiv.classList.add('show');
        errorDiv.setAttribute('role', 'alert');
        errorDiv.style.display = 'block';

        errorTimeout = setTimeout(() => {
            errorDiv.classList.remove('show');
            errorDiv.style.display = 'none';
            errorDiv.innerText = '';
        }, duration);
    }

    function updateLoginButtonState() {
        const hasUsername = usernameInput.value.trim().length > 0;
        const hasPassword = passwordInput.value.length > 0;
        loginBtn.disabled = !(hasUsername && hasPassword);
    }

    function clearCredentialFields() {
        usernameInput.value = '';
        passwordInput.value = '';
        updateLoginButtonState();
    }

    function resetLoginButton() {
        loginBtn.textContent = 'Login';
        updateLoginButtonState();
    }

    // Clear browser-restored values, including when a page is restored from
    // the back/forward cache after navigating away.
    clearCredentialFields();
    window.addEventListener('pageshow', () => {
        clearCredentialFields();
        setTimeout(clearCredentialFields, 0);
        setTimeout(clearCredentialFields, 150);
    });

    // -----------------------------
    // Input events — enable/disable login button
    // -----------------------------
    usernameInput.addEventListener('input', () => {
        usernameInput.value = usernameInput.value.toUpperCase();
        updateLoginButtonState();
    });

    passwordInput.addEventListener('input', updateLoginButtonState);

    // -----------------------------
    // Password Toggle
    // -----------------------------
    if (togglePassword) {
        togglePassword.addEventListener('click', () => {
            const hidden = passwordInput.type === 'password';
            passwordInput.type = hidden ? 'text' : 'password';
            togglePassword.classList.toggle('fa-eye', !hidden);
            togglePassword.classList.toggle('fa-eye-slash', hidden);
            togglePassword.setAttribute('aria-pressed', hidden ? 'true' : 'false');
        });
    }

    // -----------------------------
    // AJAX Login Submit
    // -----------------------------
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = usernameInput.value.trim();
        const password = passwordInput.value;

        if (!username || !password) {
            showError('Username and password are required.');
            return;
        }

        loginBtn.disabled = true;
        loginBtn.textContent = 'Signing in…';

        const data = new URLSearchParams();
        data.append('username', username);
        data.append('password', password);
        clearCredentialFields();

        try {
            const res = await fetch(loginForm.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCSRFToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: data.toString(),
                redirect: 'manual'
            });

            if (res.status === 403) {
                const json = await res.json().catch(() => null);
                showError(json?.error || 'Login failed. Please check your credentials.');
                resetLoginButton();
                return;
            }

            if (res.status >= 300 && res.status < 400) {
                const redirectUrl = res.headers.get('Location');
                if (redirectUrl) {
                    window.location.href = redirectUrl;
                    return;
                }
            }

            const json = await res.json().catch(() => null);

            if (json?.success) {
                const container = document.querySelector('.login-container');
                container.style.transition = 'opacity 0.5s';
                container.style.opacity = 0;
                setTimeout(() => window.location.href = json.redirect, 500);
            } else if (json?.error) {
                showError(json.error);
                resetLoginButton();
            } else {
                showError('Login failed. Check credentials.');
                resetLoginButton();
            }

        } catch (err) {
            console.error(err);
            showError('Network or server error occurred.');
            resetLoginButton();
        }
    });

    // -----------------------------
    // Enter Key Handling
    // -----------------------------
    function handleEnter(e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        if (!loginBtn.disabled) loginBtn.click();
    }

    usernameInput.addEventListener('keydown', handleEnter);
    passwordInput.addEventListener('keydown', handleEnter);

    // -----------------------------
    // Security Hardening
    // -----------------------------
    // Prevent clickjacking / iframe embedding
    if (window.top !== window.self) window.top.location = window.location;

    // Strip control characters from password
    passwordInput.addEventListener('input', () => {
        const illegalChars = /[\u0000-\u001F\u007F]/g;
        if (illegalChars.test(passwordInput.value)) {
            passwordInput.value = passwordInput.value.replace(illegalChars, '');
        }
    });

    // -----------------------------
    // Forgot Password (AJAX)
    // -----------------------------
    const forgotLink = document.getElementById('forgotPasswordLink');
    const resetMsg = document.getElementById('resetMessage');

    if (forgotLink) {
        forgotLink.addEventListener('click', async (e) => {
            e.preventDefault();
            if (forgotLink.classList.contains('disabled-link')) return;

            const username = usernameInput.value.trim();
            if (!username) {
                showError('Please enter your username first.');
                return;
            }

            const url = forgotLink.dataset.url;
            forgotLink.classList.add('disabled-link');

            // Show sending state
            resetMsg.style.display = 'block';
            resetMsg.className = 'reset-status sending';
            resetMsg.innerHTML = '<i class="fas fa-spinner fa-spin"></i>&nbsp; Sending reset email…';

            try {
                const res = await fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-CSRFToken': getCSRFToken(),
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: `username=${encodeURIComponent(username)}`
                });

                const data = await res.json();

                if (data.success) {
                    resetMsg.className = 'reset-status success';
                    resetMsg.innerHTML = '<i class="fas fa-check-circle"></i>&nbsp; ' + data.message;
                } else {
                    resetMsg.className = 'reset-status error';
                    resetMsg.innerHTML = '<i class="fas fa-exclamation-circle"></i>&nbsp; ' + data.message;
                }
            } catch (err) {
                console.error(err);
                resetMsg.className = 'reset-status error';
                resetMsg.innerHTML = '<i class="fas fa-exclamation-circle"></i>&nbsp; Network error. Please try again.';
            }

            // Re-enable after 30s cooldown
            setTimeout(() => {
                forgotLink.classList.remove('disabled-link');
            }, 30000);
        });
    }

    // -----------------------------
    // Initial focus and UI state
    // -----------------------------
    usernameInput.focus();
    updateLoginButtonState();

});
