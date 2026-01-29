// Auto-detect environment: production or local development
const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
const BACKEND_URL = isProduction ? 'https://cariara-production.up.railway.app' : 'http://localhost:8000';
const API_BASE = `${BACKEND_URL}/api`;
const AUTH_BASE = `${BACKEND_URL}/auth`;

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
    const userJson = localStorage.getItem('user');
    return userJson ? JSON.parse(userJson) : null;
}

function isAuthenticated() {
    return !!getAccessToken();
}

/**
 * Require authentication - redirects to login if not authenticated.
 * Call this at the top of protected pages.
 */
function requireAuth() {
    if (!isAuthenticated()) {
        // Store the intended destination for redirect after login
        const currentPage = window.location.pathname.split('/').pop() || 'index.html';
        if (currentPage !== 'login.html' && currentPage !== 'register.html') {
            localStorage.setItem('redirect_after_login', currentPage);
        }
        // Use correct path for pages in different folders
        const basePath = window.location.pathname.includes('/admin/') ? '../jobs/' : '';
        window.location.href = basePath + 'login.html';
        return false;
    }
    return true;
}

/**
 * Require onboarding completion - redirects to onboarding if not completed.
 * Call this after requireAuth() on pages that require onboarding to be completed.
 * Excludes: onboarding.html, login.html, register.html
 */
async function requireOnboarding() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    // Skip check for pages that don't require onboarding
    const excludedPages = ['onboarding.html', 'login.html', 'register.html'];
    if (excludedPages.includes(currentPage)) {
        return true;
    }

    // Skip check for admin pages
    if (window.location.pathname.includes('/admin/')) {
        return true;
    }

    const token = getAccessToken();
    if (!token) return false;

    try {
        const response = await fetch(`${API_BASE}/users/onboarding-status`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            const status = await response.json();
            if (!status.onboarding_completed) {
                window.location.href = 'onboarding.html';
                return false;
            }
        }
    } catch (e) {
        console.error('Failed to check onboarding status:', e);
    }
    return true;
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    // Use absolute path to handle pages in different folders (e.g., /admin/)
    const basePath = window.location.pathname.includes('/admin/') ? '../jobs/' : '';
    window.location.href = basePath + 'login.html';
}

async function refreshAccessToken() {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
        return false;
    }

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
        localStorage.setItem('refresh_token', data.refresh_token);
        localStorage.setItem('user', JSON.stringify(data.user));
        return true;
    } catch (error) {
        console.error('Token refresh failed:', error);
        return false;
    }
}

// =============================================================================
// API REQUESTS
// =============================================================================

async function apiRequest(endpoint, method = 'GET', data = null, retry = true) {
    const token = getAccessToken();
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };

    // Add authorization header if token exists
    if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
    }

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    const response = await fetch(`${API_BASE}${endpoint}`, options);

    // Handle 401 - try to refresh token
    if (response.status === 401 && retry) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            // Retry the request with new token
            return apiRequest(endpoint, method, data, false);
        } else {
            // Refresh failed, redirect to login
            logout();
            throw new Error('Session expired. Please login again.');
        }
    }

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Request failed');
    }

    return response.json();
}

async function uploadDocument(formData) {
    const token = getAccessToken();
    const options = {
        method: 'POST',
        body: formData,
    };

    // Add authorization header if token exists
    if (token) {
        options.headers = {
            'Authorization': `Bearer ${token}`,
        };
    }

    const response = await fetch(`${API_BASE}/documents`, options);

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
    }

    return response.json();
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
    const savedTheme = localStorage.getItem('jobtrails-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('jobtrails-theme', newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) {
        toggleBtn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
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
            <span class="user-name">${user.name || user.email}</span>
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
