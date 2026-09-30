// Auto-detect environment: production or local development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const BACKEND_URL = isProduction ? 'https://cariara-backend.up.railway.app' : 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api`;
const AUTH_BASE = `${BACKEND_URL}/auth`;

// Global error handler to prevent black screens
window.onerror = function(message, source, lineno, colno, error) {
    console.error('Global error:', message, 'at', source, lineno, colno);
    // Show error to user if page appears blank
    if (document.body && document.body.innerHTML.trim() === '') {
        document.body.innerHTML = `
            <div style="padding: 40px; text-align: center; font-family: system-ui, sans-serif;">
                <h2 style="color: var(--c-red);">Something went wrong</h2>
                <p style="color: var(--c-ink-2);">${escapeHtml(message)}</p>
                <button onclick="window.location.reload()" style="padding: 10px 20px; cursor: pointer; margin-top: 16px;">Reload Page</button>
            </div>
        `;
    }
    return false;
};

// Handle unhandled promise rejections
window.onunhandledrejection = function(event) {
    console.error('Unhandled promise rejection:', event.reason);
};

// =============================================================================
// AUTHENTICATION
// =============================================================================

// Roles the backend accepts for admin endpoints (keep in sync with login.html).
const ADMIN_ROLES = ['admin', 'administrator', 'manager', 'developer'];

function getAccessToken() {
    return localStorage.getItem('access_token');
}

function getRefreshToken() {
    return localStorage.getItem('refresh_token');
}

function getCurrentUser() {
    try {
        const userJson = localStorage.getItem('user');
        return userJson ? JSON.parse(userJson) : null;
    } catch (e) {
        return null;
    }
}

function isAuthenticated() {
    return !!getAccessToken();
}

function isAdminUser(user = getCurrentUser()) {
    return !!user && ADMIN_ROLES.includes(user.role);
}

// Remember where the user was (path + query) so login.html can send them back.
function rememberCurrentPage() {
    const path = window.location.pathname || '/';
    if (/\/(login|register)(\.html)?$/.test(path)) return;
    localStorage.setItem('redirect_after_login', path + window.location.search);
}

/**
 * Require authentication - redirects to login if not authenticated.
 */
function requireAuth() {
    if (!isAuthenticated()) {
        rememberCurrentPage();
        window.location.replace('/login.html');
        return false;
    }
    return true;
}

/**
 * Require a signed-in admin. Non-admins go to /login.html, which re-validates
 * the session via /api/users/me and explains that the account lacks admin access.
 * Call at the top of every admin page (it includes requireAuth()).
 */
function requireAdmin() {
    if (!requireAuth()) return false;
    if (!isAdminUser()) {
        rememberCurrentPage();
        window.location.replace('/login.html');
        return false;
    }
    return true;
}

function logout() {
    ['access_token', 'refresh_token', 'token', 'user', 'redirect_after_login'].forEach(k => localStorage.removeItem(k));
    window.location.href = '/login.html';
}

// Single-flight refresh: parallel 401s share one /auth/refresh call, because the
// backend rotates the refresh token and a second concurrent refresh would fail.
let _refreshPromise = null;

function refreshAccessToken() {
    if (_refreshPromise) return _refreshPromise;
    _refreshPromise = (async () => {
        const refreshToken = getRefreshToken();
        if (!refreshToken) return false;
        try {
            const response = await fetch(`${AUTH_BASE}/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });
            if (!response.ok) {
                // Another tab may have rotated the token meanwhile; treat that as success.
                return getRefreshToken() !== refreshToken && !!getAccessToken();
            }
            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
            if (data.user) localStorage.setItem('user', JSON.stringify(data.user));
            return true;
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        }
    })();
    _refreshPromise.finally(() => { setTimeout(() => { _refreshPromise = null; }, 0); });
    return _refreshPromise;
}

// =============================================================================
// API REQUESTS
// =============================================================================

const API_TIMEOUT_MS = 15000;

/** Turn any error response (JSON, HTML 502 page, empty body) into a readable message. */
async function extractErrorMessage(response) {
    const text = await response.text().catch(() => '');
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { /* not JSON */ }
    if (data) {
        const detail = data.detail ?? data.message ?? data.error;
        if (Array.isArray(detail)) {
            const msg = detail.map(d => (d && typeof d === 'object') ? (d.msg || JSON.stringify(d)) : String(d)).join('; ');
            if (msg) return msg;
        } else if (detail && typeof detail === 'object') {
            return detail.message || detail.msg || JSON.stringify(detail);
        } else if (detail) {
            return String(detail);
        }
    }
    if (response.status === 404) return 'Not found (404).';
    if (response.status === 403) return "You don't have permission to do that.";
    if (response.status === 429) return 'Too many requests. Wait a moment and try again.';
    if (response.status >= 500) return `The server is having trouble (${response.status}). Try again in a minute.`;
    return `Request failed (${response.status}).`;
}

/**
 * apiRequest(endpoint, method, data, opts)
 * opts: { timeout (ms, default 15000), signal (AbortSignal), retry (default true) }.
 * A boolean 4th argument is accepted as the legacy `retry` flag.
 */
async function apiRequest(endpoint, method = 'GET', data = null, opts = {}) {
    if (typeof opts === 'boolean') opts = { retry: opts };
    const { timeout = API_TIMEOUT_MS, signal = null, retry = true } = opts || {};
    const headers = { 'Content-Type': 'application/json' };
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const controller = new AbortController();
    let timedOut = false;
    const timer = timeout ? setTimeout(() => { timedOut = true; controller.abort(); }, timeout) : null;
    const onOuterAbort = () => controller.abort();
    if (signal) {
        if (signal.aborted) controller.abort();
        else signal.addEventListener('abort', onOuterAbort, { once: true });
    }

    const options = { method, headers, signal: controller.signal };
    if (data !== null && data !== undefined && method !== 'GET') options.body = JSON.stringify(data);

    let response;
    try {
        response = await fetch(`${API_BASE}${endpoint}`, options);
    } catch (err) {
        if (timedOut) throw new Error('The server is slow to respond. Try again in a moment.');
        if (err && err.name === 'AbortError') throw err;
        throw new Error("Can't reach the Cariara API. Check your connection and try again.");
    } finally {
        if (timer) clearTimeout(timer);
        if (signal) signal.removeEventListener('abort', onOuterAbort);
    }

    if (response.status === 401 && retry) {
        const refreshed = await refreshAccessToken();
        if (refreshed) return apiRequest(endpoint, method, data, { timeout, signal, retry: false });
        rememberCurrentPage();
        logout();
        throw new Error('Session expired. Please sign in again.');
    }

    if (!response.ok) {
        const err = new Error(await extractErrorMessage(response));
        err.status = response.status;
        throw err;
    }

    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch (e) {
        throw new Error('The server returned an unexpected response.');
    }
}

// =============================================================================
// SAFE RENDERING HELPERS
// =============================================================================

/** Escape a value for use inside HTML text or a quoted attribute. */
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** Return an http(s) URL (escaped for an attribute) or '' for anything else (javascript:, data:, ...). */
function safeUrl(value) {
    const raw = String(value ?? '').trim();
    if (!raw) return '';
    try {
        const u = new URL(raw, window.location.origin);
        if (u.protocol !== 'http:' && u.protocol !== 'https:') return '';
        return escapeHtml(u.href);
    } catch (e) {
        return '';
    }
}

/** Escape a string for use inside a single-quoted JS string in an inline handler attribute. */
function jsAttr(value) {
    return escapeHtml(String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, ' '));
}

/**
 * Classify /api/scrapers/status entries (a bare list of
 * {company_slug, company_name, is_enabled, consecutive_failures, total_runs,
 *  last_success_at, last_failure_at, last_error, active_jobs, total_jobs}).
 * Mirrors the backend's run-warning rules:
 *   critical: 5+ consecutive failures (incl. auto-disabled by failures)
 *   warning:  2-4 failures, last success > 7 days ago, or never succeeded
 *   disabled: switched off in code (disabled_reason set), or manually with fewer than 5 failures
 * Also accepts a pre-aggregated object {scrapers:[...], healthy, warning, critical}.
 */
function classifyScraper(s) {
    const failures = Number(s.consecutive_failures || 0);
    const enabled = s.is_enabled !== false && s.enabled !== false;
    // Disabled in code (board gone, no supported ATS) - its old failure streak isn't actionable
    if (!enabled && s.disabled_reason) return 'disabled';
    if (failures >= 5) return 'critical';
    if (!enabled) return 'disabled';
    if (failures >= 2) return 'warning';
    const lastSuccess = s.last_success_at || s.last_success;
    if (!lastSuccess) return 'warning';
    const t = Date.parse(lastSuccess.endsWith && !/[zZ]|[+-]\d\d:?\d\d$/.test(lastSuccess) ? lastSuccess + 'Z' : lastSuccess);
    if (!isNaN(t) && Date.now() - t > 7 * 24 * 3600 * 1000) return 'warning';
    return 'healthy';
}

function summarizeScraperHealth(data) {
    const list = Array.isArray(data) ? data : (data && (data.scrapers || data.items)) || [];
    const scrapers = list.map(s => ({ ...s, health: s.health || s.status_level || classifyScraper(s) }));
    const count = level => scrapers.filter(s => s.health === level).length;
    return {
        scrapers,
        total: Array.isArray(data) ? scrapers.length : (data?.total ?? scrapers.length),
        healthy: count('healthy'),
        warning: count('warning'),
        critical: count('critical'),
        disabled: count('disabled'),
    };
}

/** Transient message in the bottom corner. type: success | error | info */
function showToast(message, type = 'success', ms = 5000) {
    let host = document.getElementById('admin-toast-host');
    if (!host) {
        host = document.createElement('div');
        host.id = 'admin-toast-host';
        host.setAttribute('role', 'status');
        host.setAttribute('aria-live', 'polite');
        host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:10000;display:flex;flex-direction:column;gap:8px;max-width:min(420px,calc(100vw - 32px));';
        document.body.appendChild(host);
    }
    const toast = document.createElement('div');
    const palette = {
        success: ['var(--c-green-tint)', 'var(--c-green)'],
        error: ['var(--c-red-tint)', 'var(--c-red)'],
        info: ['var(--c-surface)', 'var(--c-ink)'],
    }[type] || ['var(--c-surface)', 'var(--c-ink)'];
    toast.style.cssText = `background:${palette[0]};color:${palette[1]};border:1px solid var(--c-line);border-radius:10px;padding:12px 14px;font-size:14px;line-height:1.4;box-shadow:0 4px 16px rgba(0,0,0,.12);`;
    toast.textContent = message;
    host.appendChild(toast);
    setTimeout(() => toast.remove(), ms);
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatSalary(min, max) {
    if (!min && !max) return '-';
    const formatter = new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0
    });
    if (min && max) {
        return `${formatter.format(min)} - ${formatter.format(max)}`;
    }
    if (min) return `${formatter.format(min)}+`;
    return `Up to ${formatter.format(max)}`;
}

function getStatusBadge(status) {
    const safe = escapeHtml(status || '');
    return `<span class="status-badge status-${safe.replace(/[^a-z_-]/gi, '')}">${safe}</span>`;
}

function showAlert(message, type = 'success') {
    const existingAlerts = document.querySelectorAll('.alert');
    existingAlerts.forEach(alert => alert.remove());

    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;

    // Support both regular pages (.container) and admin pages (.admin-content)
    const container = document.querySelector('.admin-content') || document.querySelector('.container');
    if (!container) {
        console.warn('showAlert: No container found, appending to body');
        document.body.prepend(alert);
    } else {
        const pageHeader = container.querySelector('.page-header, .admin-page-header');
        if (pageHeader) {
            pageHeader.after(alert);
        } else {
            container.prepend(alert);
        }
    }

    setTimeout(() => alert.remove(), 5000);
}

function getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

async function loadCompanyOptions(selectId, selectedId = null) {
    try {
        const companies = await apiRequest('/companies');
        const select = document.getElementById(selectId);

        select.innerHTML = '<option value="">Select a company</option>';
        companies.forEach(company => {
            const option = document.createElement('option');
            option.value = company.id;
            option.textContent = company.name;
            if (selectedId && company.id === selectedId) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load companies:', error);
    }
}

// Theme Toggle Functions — one preference ("theme", legacy "jobtrails-theme"), light by default.
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || localStorage.getItem('jobtrails-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    localStorage.setItem('jobtrails-theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const moon = document.getElementById('theme-icon-moon');
    const sun = document.getElementById('theme-icon-sun');
    if (moon && sun) {
        moon.style.display = theme === 'dark' ? 'none' : 'block';
        sun.style.display = theme === 'dark' ? 'block' : 'none';
    }
    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) toggleBtn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
}

// Apply the saved theme immediately (before first paint of the page body), then sync icons.
try {
    document.documentElement.setAttribute('data-theme', localStorage.getItem('theme') || localStorage.getItem('jobtrails-theme') || 'light');
} catch (e) { /* storage blocked */ }
document.addEventListener('DOMContentLoaded', initTheme);

// =============================================================================
// USER INTERFACE HELPERS
// =============================================================================

function renderUserMenu() {
    // Skip if page has its own #user-menu element (handled by page-specific initUserMenu)
    if (document.getElementById('user-menu')) return;
    // The shared admin shell renders its own account block and sign-out.
    if (document.querySelector('.admin-sidebar, .sidebar')) return;

    const user = getCurrentUser();
    const navContainer = document.querySelector('nav');

    if (!navContainer) return;

    // Remove existing user menu if any
    const existingMenu = document.querySelector('.user-menu');
    if (existingMenu) existingMenu.remove();

    if (user) {
        const userMenu = document.createElement('div');
        userMenu.className = 'user-menu';
        userMenu.innerHTML = `
            <span class="user-name">${String(user.name || user.email || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))}</span>
            <button onclick="logout()" class="btn btn-small">Logout</button>
        `;
        navContainer.appendChild(userMenu);
    } else {
        const authLinks = document.createElement('div');
        authLinks.className = 'user-menu';
        authLinks.innerHTML = `
            <a href="login.html" class="btn btn-small">Login</a>
        `;
        navContainer.appendChild(authLinks);
    }
}

// Initialize user menu on page load
document.addEventListener('DOMContentLoaded', () => {
    renderUserMenu();
});

// =============================================================================
// EXPORTS
// =============================================================================

window.apiRequest = apiRequest;
window.formatDate = formatDate;
window.formatDateTime = formatDateTime;
window.formatSalary = formatSalary;
window.getStatusBadge = getStatusBadge;
window.showAlert = showAlert;
window.getUrlParam = getUrlParam;
window.loadCompanyOptions = loadCompanyOptions;
window.initTheme = initTheme;
window.toggleTheme = toggleTheme;
window.isAuthenticated = isAuthenticated;
window.getCurrentUser = getCurrentUser;
window.logout = logout;
window.renderUserMenu = renderUserMenu;
window.requireAuth = requireAuth;
window.requireAdmin = requireAdmin;
window.ADMIN_ROLES = ADMIN_ROLES;
window.isAdminUser = isAdminUser;
window.escapeHtml = escapeHtml;
window.safeUrl = safeUrl;
window.jsAttr = jsAttr;
window.showToast = showToast;
window.classifyScraper = classifyScraper;
window.summarizeScraperHealth = summarizeScraperHealth;
window.refreshAccessToken = refreshAccessToken;
window.updateThemeIcon = updateThemeIcon;
