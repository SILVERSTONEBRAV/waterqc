document.addEventListener('DOMContentLoaded', () => {

    // -----------------------------
    // Elements
    // -----------------------------
    const usernameInput = document.getElementById('username');
    const usernameGroup = document.getElementById('usernameGroup');
    const verifiedUsernameDiv = document.getElementById('verifiedUsername');

    const passwordInput = document.getElementById('password');
    const passwordGroup = document.getElementById('passwordGroup');
    const forgotDiv = document.getElementById('forgotDiv');
    const strengthContainer = document.getElementById('passwordStrengthContainer');
    const strengthBar = document.getElementById('passwordStrengthBar');
    const togglePassword = document.getElementById('togglePassword');

    const verifyBtn = document.getElementById('verifyBtn');
    const loginBtn = document.getElementById('loginBtn');
    const loginForm = document.getElementById('loginForm');

    const errorDiv = document.getElementById('errorMessage');

    // -----------------------------
    // Data attributes
    // -----------------------------
    const checkUsernameUrl = verifyBtn.dataset.url;

    // -----------------------------
    // State
    // -----------------------------
    let usernameVerified = false;
    let passwordValid = false;
    let errorTimeout = null;
    let isVerifying = false;

    const usernameRegex = /^NCWSC\d{5}$/;
    const MIN_PASSWORD_LENGTH = 8;

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

    function calculateStrength(p) {
        let score = 0;
        if (p.length >= MIN_PASSWORD_LENGTH) score++;
        if (/[A-Z]/.test(p)) score++;
        if (/\d/.test(p)) score++;
        if (/[!@#$%^&*]/.test(p)) score++;
        return score;
    }

    function updateStrengthMeter(p) {
        const score = calculateStrength(p);
        const percent = (score / 4) * 100;
        const colors = ['#ff4444', '#ffbb00', '#00ff88', '#00ffcc'];
        strengthBar.style.width = percent + '%';
        strengthBar.style.background = colors[Math.max(score - 1, 0)];
        strengthBar.setAttribute('title', ['Weak', 'Fair', 'Strong', 'Very Strong'][Math.max(score - 1, 0)]);
    }

    function validatePassword(p) {
        return calculateStrength(p) === 4;
    }

    function updateLoginButtonState() {
        loginBtn.disabled = !(usernameVerified && passwordValid);
    }

    function updateUI() {
        usernameGroup.style.display = usernameVerified ? 'none' : 'flex';
        verifyBtn.style.display = usernameVerified ? 'none' : 'block';
        verifiedUsernameDiv.style.display = usernameVerified ? 'block' : 'none';
        passwordGroup.style.display = usernameVerified ? 'flex' : 'none';
        strengthContainer.style.display = usernameVerified ? 'block' : 'none';
        forgotDiv.style.display = usernameVerified ? 'block' : 'none';
        loginBtn.style.display = usernameVerified ? 'block' : 'none';
        updateLoginButtonState();
    }

    // -----------------------------
    // Debounce helper
    // -----------------------------
    function debounce(fn, delay = 300) {
        let timer = null;
        return (...args) => {
            if (timer) clearTimeout(timer);
            timer = setTimeout(() => fn(...args), delay);
        };
    }

    // -----------------------------
    // Username Input Behavior
    // -----------------------------
    usernameInput.addEventListener('input', debounce(() => {
        usernameInput.value = usernameInput.value.toUpperCase();
        verifyBtn.disabled = !usernameRegex.test(usernameInput.value.trim());
    }, 200));

    // -----------------------------
    // Verify Username
    // -----------------------------
    async function verifyUsername() {
        const username = usernameInput.value.trim();

        if (isVerifying) return;
        if (!usernameRegex.test(username)) {
            showError('Username must be NCWSCXXXXX');
            return;
        }

        verifyBtn.disabled = true;
        isVerifying = true;

        try {
            const res = await fetch(checkUsernameUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': getCSRFToken()
                },
                body: `username=${encodeURIComponent(username)}`
            });

            if (res.status === 403) {
                showError('CSRF verification failed. Please refresh the page.');
                return;
            }

            const data = await res.json();

            if (data.exists) {
                usernameVerified = true;
                verifiedUsernameDiv.innerText = username;

                verifiedUsernameDiv.style.opacity = 0;
                verifiedUsernameDiv.style.transition = 'opacity 0.4s';
                updateUI();
                requestAnimationFrame(() => {
                    verifiedUsernameDiv.style.opacity = 1;
                });

                passwordInput.focus();
            } else {
                showError('Username does not exist');
                verifyBtn.disabled = false;
            }

        } catch (err) {
            console.error(err);
            showError('Error verifying username');
            verifyBtn.disabled = false;
        } finally {
            isVerifying = false;
        }
    }

    verifyBtn.addEventListener('click', verifyUsername);

    // -----------------------------
    // Password Input Behavior
    // -----------------------------
    passwordInput.addEventListener('input', () => {
        passwordValid = validatePassword(passwordInput.value);
        updateStrengthMeter(passwordInput.value);
        updateLoginButtonState();
    });

    // -----------------------------
    // Password Toggle
    // -----------------------------
    togglePassword.addEventListener('click', () => {
        const hidden = passwordInput.type === 'password';
        passwordInput.type = hidden ? 'text' : 'password';
        togglePassword.classList.toggle('fa-eye', !hidden);
        togglePassword.classList.toggle('fa-eye-slash', hidden);
        togglePassword.setAttribute('aria-pressed', hidden ? 'true' : 'false');
    });

    // -----------------------------
    // AJAX Login Submit
    // -----------------------------
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        if (!usernameVerified || !passwordValid) return;

        const data = new URLSearchParams();
        data.append('username', usernameInput.value);
        data.append('password', passwordInput.value);

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
                showError('CSRF verification failed. Please refresh the page.');
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
            } else {
                showError('Login failed. Check credentials.');
            }

        } catch (err) {
            console.error(err);
            showError('Network or server error occurred.');
        }
    });

    // -----------------------------
    // Enter Key Handling
    // -----------------------------
    function handleEnter(e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        if (!usernameVerified) verifyUsername();
        else if (passwordValid) loginBtn.click();
    }

    usernameInput.addEventListener('keydown', handleEnter);
    passwordInput.addEventListener('keydown', handleEnter);

    // -----------------------------
    // Advanced Security Hardening
    // -----------------------------
    // Disable right-click
    document.addEventListener('contextmenu', (e) => e.preventDefault());

    // Disable copy/cut/paste
    ['copy', 'cut', 'paste'].forEach(evt =>
        document.addEventListener(evt, (e) => e.preventDefault())
    );

    // Disable drag & drop
    [usernameInput, passwordInput].forEach(input => {
        input.addEventListener('drop', (e) => e.preventDefault());
        input.addEventListener('dragover', (e) => e.preventDefault());
    });

    // Clear clipboard on load and before unload
    navigator.clipboard?.writeText('').catch(() => {});
    window.addEventListener('beforeunload', () => {
        navigator.clipboard?.writeText('').catch(() => {});
    });

    // Prevent autocomplete / autofill
    passwordInput.setAttribute('autocomplete', 'new-password');
    usernameInput.setAttribute('autocomplete', 'off');
    loginForm.setAttribute('autocomplete', 'off');

    // Dummy hidden fields to prevent browser autofill
    const dummyUser = document.createElement('input');
    dummyUser.type = 'text'; dummyUser.name = 'username-fake'; dummyUser.style.display = 'none';
    loginForm.prepend(dummyUser);

    const dummyPass = document.createElement('input');
    dummyPass.type = 'password'; dummyPass.name = 'password-fake'; dummyPass.style.display = 'none';
    loginForm.prepend(dummyPass);

    // Strip control characters from password
    passwordInput.addEventListener('input', () => {
        const illegalChars = /[\u0000-\u001F\u007F]/g;
        if (illegalChars.test(passwordInput.value)) {
            passwordInput.value = passwordInput.value.replace(illegalChars, '');
        }
    });

    // Always require a new password
    passwordInput.value = '';
    passwordInput.addEventListener('focus', () => passwordInput.select());

    // Prevent clickjacking / iframe embedding
    if (window.top !== window.self) window.top.location = window.location;

    // -----------------------------
    // Initial focus and UI state
    // -----------------------------
    usernameInput.focus();
    usernameVerified = false;
    passwordValid = false;
    updateUI();

});
