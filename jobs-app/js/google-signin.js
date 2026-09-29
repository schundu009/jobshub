/* Use the server OAuth flow; Google credentials never enter the browser. */
(() => {
    const button = document.getElementById('google-login');
    if (!button) return;
    const local = ['localhost', '127.0.0.1'].includes(location.hostname);
    const backend = local ? 'http://localhost:8000' : 'https://cariara-backend.up.railway.app';
    button.href = `${backend}/auth/google/login?redirect=jobs`;
    const status = document.createElement('p');
    status.id = 'google-signin-status';
    status.setAttribute('role', 'status');
    status.style.cssText = 'font-size:13px;color:var(--text-muted);text-align:center;';
    button.parentElement.after(status);
    button.setAttribute('aria-describedby', status.id);
    button.addEventListener('click', event => {
        if (button.getAttribute('aria-disabled') === 'true') {
            event.preventDefault();
            status.textContent = 'Google sign-in is currently unavailable. Please use your email.';
        }
    });
    fetch(`${backend}/auth/providers`)
        .then(response => response.ok ? response.json() : null)
        .then(providers => {
            if (providers && providers.google === false) {
                button.setAttribute('aria-disabled', 'true');
                status.textContent = 'Google sign-in is currently unavailable. Please use your email.';
            }
        })
        .catch(() => { /* Keep the direct login link usable during a transient failure. */ });
})();
