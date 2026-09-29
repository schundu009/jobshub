// Auto-detect environment: production or local development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const BACKEND_URL = isProduction ? 'https://cariara-backend.up.railway.app' : 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api`;
const AUTH_BASE = `${BACKEND_URL}/auth`;

// Keys that make up a signed-in session. Kept in sync with js/sidebar.js handleLogout().
const CARIARA_SESSION_KEYS = ['access_token', 'refresh_token', 'token', 'user', 'subscription_status', 'cariara_resume_draft', 'redirect_after_login'];
const NETWORK_ERROR_MESSAGE = "Can't reach Cariara right now. Check your connection and try again.";

function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

// Global error handler to prevent black screens
window.onerror = function(message, source, lineno, colno, error) {
    console.error('Global error:', message, 'at', source, lineno, colno);
    // Show error to user if page appears blank
    if (document.body && document.body.innerHTML.trim() === '') {
        document.body.innerHTML = `
            <div style="padding: 40px; text-align: center;">
                <h2 style="color: var(--c-red, #d93025);">Something went wrong</h2>
                <p style="color: var(--c-ink-2, #5f6368);">${escapeHtml(message)}</p>
                <button onclick="window.location.reload()" class="btn btn-secondary" style="margin-top: 16px;">Reload page</button>
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

/**
 * Validate a post-login redirect target. Only same-origin relative page paths
 * are allowed (no schemes, no protocol-relative URLs, no auth/onboarding pages).
 */
function sanitizeRedirectPath(raw) {
    if (!raw) return null;
    const value = String(raw).trim();
    if (!value || value.startsWith('//') || value.includes('\\') || /^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value)) return null;
    try {
        const url = new URL(value, window.location.origin + '/');
        if (url.origin !== window.location.origin) return null;
        const page = url.pathname.split('/').pop();
        if (['login.html', 'register.html', 'onboarding.html', 'select-roles.html'].includes(page)) return null;
        return url.pathname + url.search + url.hash;
    } catch (e) {
        return null;
    }
}

/** Return (and clear) a stored, validated post-login redirect. */
function consumeRedirectAfterLogin() {
    const stored = localStorage.getItem('redirect_after_login');
    localStorage.removeItem('redirect_after_login');
    return sanitizeRedirectPath(stored);
}

/**
 * Require authentication - redirects to login if not authenticated.
 * Call this at the top of protected pages.
 */
function requireAuth() {
    const search = new URLSearchParams(window.location.search).get('q');
    if (search && window.location.pathname.includes('discover')) {
        sessionStorage.setItem('jobshub_search', search.slice(0, 200));
    }
    if (!isAuthenticated()) {
        // Store the intended destination (including query, e.g. job_detail.html?id=1)
        const currentPage = window.location.pathname.split('/').pop() || 'discover.html';
        const target = sanitizeRedirectPath(currentPage + window.location.search + window.location.hash);
        if (target) {
            localStorage.setItem('redirect_after_login', target);
        }
        window.location.href = '/login.html';
        return false;
    }
    return true;
}

function clearSession() {
    CARIARA_SESSION_KEYS.forEach(key => localStorage.removeItem(key));
}

function logout() {
    if (typeof window.handleLogout === 'function' && window.handleLogout !== logout) {
        window.handleLogout();
        return;
    }
    clearSession();
    window.location.href = '/login.html';
}

/**
 * Check onboarding / role-selection state and redirect when incomplete.
 * Resolves to true when the user may stay on the current page.
 * Never blocks on network/server errors (fails open).
 */
let onboardingCheckPromise = null;
function requireOnboarding(options = {}) {
    if (onboardingCheckPromise) return onboardingCheckPromise;
    const checkRoles = options.checkRoles !== false;
    onboardingCheckPromise = (async () => {
        if (!isAuthenticated()) return requireAuth();
        const page = window.location.pathname.split('/').pop();
        const user = getCurrentUser();
        if (user && user.onboarding_completed && (!checkRoles || user.roles_confirmed)) {
            return true;
        }
        let status;
        try {
            status = await apiRequest('/users/onboarding-status');
        } catch (error) {
            console.error('Error checking onboarding status:', error);
            return true; // Don't block on error
        }
        if (!status || typeof status !== 'object') return true;
        const updated = Object.assign({}, getCurrentUser() || {}, {
            onboarding_completed: !!status.onboarding_completed,
            roles_confirmed: !!status.roles_confirmed,
        });
        if (Array.isArray(status.job_roles)) updated.job_roles = status.job_roles;
        localStorage.setItem('user', JSON.stringify(updated));

        if (!status.onboarding_completed) {
            if (page !== 'onboarding.html') window.location.href = '/onboarding.html';
            return false;
        }
        if (checkRoles && !status.roles_confirmed) {
            if (page !== 'select-roles.html') window.location.href = '/select-roles.html';
            return false;
        }
        return true;
    })();
    return onboardingCheckPromise;
}

let refreshPromise = null;
async function refreshAccessToken() {
    // Share a single in-flight refresh between concurrent 401s
    if (refreshPromise) return refreshPromise;
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
        return false;
    }

    refreshPromise = (async () => {
        try {
            const response = await fetch(`${AUTH_BASE}/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ refresh_token: refreshToken }),
            });

            if (!response.ok) {
                return false;
            }

            const data = await response.json();
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('token', data.access_token);
            if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
            if (data.user) {
                // Keep locally cached gating flags the token response may not carry
                const previous = getCurrentUser() || {};
                localStorage.setItem('user', JSON.stringify(Object.assign({}, previous, data.user)));
            }
            return true;
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        } finally {
            setTimeout(() => { refreshPromise = null; }, 0);
        }
    })();
    return refreshPromise;
}

/**
 * Turn an error response into a readable message. Never throws, even when the
 * body is HTML (e.g. a Railway 502 page) or empty.
 */
async function extractErrorMessage(response, fallback = 'Request failed') {
    let body = null;
    try {
        const text = await response.text();
        if (text) {
            try { body = JSON.parse(text); } catch (e) { body = null; }
        }
    } catch (e) {
        body = null;
    }
    const detail = body && (body.detail ?? body.message ?? body.error);
    if (Array.isArray(detail)) {
        const parts = detail.map(item => {
            if (item && typeof item === 'object') {
                const field = Array.isArray(item.loc) ? item.loc.filter(p => p !== 'body').join('.') : '';
                return field ? `${field}: ${item.msg || 'invalid'}` : (item.msg || JSON.stringify(item));
            }
            return String(item);
        }).filter(Boolean);
        if (parts.length) return parts.join('; ');
    } else if (detail && typeof detail === 'object') {
        return detail.message || JSON.stringify(detail);
    } else if (detail) {
        return String(detail);
    }
    if (response.status >= 500) return 'Cariara is having trouble right now. Please try again in a moment.';
    return response.statusText || fallback;
}

async function parseResponseBody(response) {
    if (response.status === 204) return null;
    const text = await response.text();
    if (!text) return null;
    try {
        return JSON.parse(text);
    } catch (e) {
        return text;
    }
}

/**
 * Low-level authenticated fetch with one refresh-and-retry on 401.
 * `url` may be absolute or an /api-relative endpoint (starting with '/').
 * Returns the Response. Throws Error with a friendly message on network failure
 * or when the session cannot be refreshed (after logging out).
 */
async function authFetch(url, options = {}, retry = true) {
    const fullUrl = /^https?:\/\//.test(url) ? url : `${API_BASE}${url}`;
    const headers = Object.assign({}, options.headers || {});
    const token = getAccessToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    let response;
    try {
        response = await fetch(fullUrl, Object.assign({}, options, { headers }));
    } catch (error) {
        throw new Error(NETWORK_ERROR_MESSAGE);
    }
    if (response.status === 401 && retry) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            return authFetch(url, options, false);
        }
        // Remember where the user was so login can bring them back.
        const here = sanitizeRedirectPath((window.location.pathname.split('/').pop() || '') + window.location.search);
        logout();
        if (here) localStorage.setItem('redirect_after_login', here);
        throw new Error('Session expired. Please sign in again.');
    }
    return response;
}

// =============================================================================
// API REQUESTS
// =============================================================================

async function apiRequest(endpoint, method = 'GET', data = null, retry = true) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    const response = await authFetch(endpoint, options, retry);

    if (!response.ok) {
        throw new Error(await extractErrorMessage(response));
    }

    return parseResponseBody(response);
}

async function uploadDocument(formData, documentType = 'resume') {
    const response = await authFetch(`/users/documents?document_type=${encodeURIComponent(documentType)}`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        throw new Error(await extractErrorMessage(response, 'Upload failed'));
    }

    return parseResponseBody(response);
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
    return `<span class="status-badge status-${status}">${status}</span>`;
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

async function loadJobOptions(selectId, selectedId = null) {
    try {
        const response = await apiRequest('/jobs?all=true');
        // Handle both old (array) and new (object with jobs array) response formats
        const jobs = Array.isArray(response) ? response : (response.jobs || []);
        const select = document.getElementById(selectId);

        select.innerHTML = '<option value="">Select a job</option>';
        jobs.forEach(job => {
            const option = document.createElement('option');
            option.value = job.id;
            option.textContent = `${job.title}${job.company_name ? ' at ' + job.company_name : ''}`;
            if (selectedId && job.id === selectedId) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load jobs:', error);
    }
}

// Theme Toggle Functions
function initTheme() {
    const savedTheme = localStorage.getItem('jobtrails-theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('jobtrails-theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    // Pages ship their own sun/moon SVGs; just toggle them (no emoji swaps).
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    if (sunIcon && moonIcon) {
        sunIcon.style.display = theme === 'dark' ? 'block' : 'none';
        moonIcon.style.display = theme === 'dark' ? 'none' : 'block';
    }
    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) {
        toggleBtn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    }
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', initTheme);

// =============================================================================
// USER INTERFACE HELPERS
// =============================================================================

function renderUserMenu() {
    // Skip if page has its own #user-menu element (handled by page-specific initUserMenu)
    if (document.getElementById('user-menu')) return;

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
            <span class="user-name">${escapeHtml(user.name || user.email)}</span>
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
window.uploadDocument = uploadDocument;
window.formatDate = formatDate;
window.formatDateTime = formatDateTime;
window.formatSalary = formatSalary;
window.getStatusBadge = getStatusBadge;
window.showAlert = showAlert;
window.getUrlParam = getUrlParam;
window.loadCompanyOptions = loadCompanyOptions;
window.loadJobOptions = loadJobOptions;
window.initTheme = initTheme;
window.toggleTheme = toggleTheme;
window.isAuthenticated = isAuthenticated;
window.getCurrentUser = getCurrentUser;
window.logout = logout;
window.renderUserMenu = renderUserMenu;
window.requireAuth = requireAuth;
window.requireOnboarding = requireOnboarding;
window.authFetch = authFetch;
window.refreshAccessToken = refreshAccessToken;
window.extractErrorMessage = extractErrorMessage;
window.escapeHtml = escapeHtml;
window.clearSession = clearSession;
window.sanitizeRedirectPath = sanitizeRedirectPath;
window.consumeRedirectAfterLogin = consumeRedirectAfterLogin;
window.getAccessToken = getAccessToken;
window.BACKEND_URL = BACKEND_URL;
