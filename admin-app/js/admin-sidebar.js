/**
 * Admin Sidebar Navigation
 * Include this file in all admin pages for consistent navigation
 */

const ADMIN_NAV_ITEMS = [
    {
        section: 'Main',
        items: [
            { id: 'dashboard', label: 'Dashboard', href: '/index.html', icon: 'dashboard' },
            { id: 'jobs', label: 'Jobs', href: '/jobs.html', icon: 'briefcase' },
            { id: 'companies', label: 'Companies', href: '/companies.html', icon: 'building' },
        ]
    },
    {
        section: 'Analytics',
        items: [
            { id: 'analytics', label: 'Analytics', href: '/analytics.html', icon: 'chart' },
        ]
    },
    {
        section: 'System',
        items: [
            { id: 'settings', label: 'Settings', href: '/settings.html', icon: 'settings' },
        ]
    }
];

const NAV_ICONS = {
    dashboard: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>',
    briefcase: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>',
    building: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>',
    chart: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>',
    settings: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
    logout: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>',
};

function getNavIcon(iconName, size = 20) {
    return `<svg class="nav-icon" width="${size}" height="${size}" fill="none" stroke="currentColor" viewBox="0 0 24 24">${NAV_ICONS[iconName] || ''}</svg>`;
}

function renderAdminSidebar(activePageId) {
    let navHtml = '';

    ADMIN_NAV_ITEMS.forEach(section => {
        navHtml += `<div class="admin-nav-section">`;
        navHtml += `<div class="admin-nav-label">${section.section}</div>`;

        section.items.forEach(item => {
            const isActive = item.id === activePageId;
            navHtml += `
                <a href="${item.href}" class="admin-nav-item ${isActive ? 'active' : ''}">
                    ${getNavIcon(item.icon)}
                    <span>${item.label}</span>
                </a>
            `;
        });

        navHtml += `</div>`;
    });

    return `
        <aside class="admin-sidebar" id="admin-sidebar">
            <div class="admin-sidebar-header">
                <a href="/index.html" class="c-brand admin-logo" aria-label="Cariara Admin home"><img class="c-brand-mark" src="/images/cariara-mark.svg" alt="" width="28" height="28"><img class="c-brand-word" src="/images/cariara-wordmark.svg" alt="Cariara" height="22"><span class="c-brand-product">Admin</span></a>
            </div>
            <nav class="admin-nav">
                ${navHtml}
            </nav>
            <div class="admin-sidebar-footer">
                <div class="admin-user-info-section" id="admin-user-info-section">
                    <!-- User info will be populated by JS -->
                </div>
            </div>
        </aside>
        <div class="admin-sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>
    `;
}

function renderAdminTopbar(title, breadcrumb = null) {
    const breadcrumbHtml = breadcrumb
        ? `<div class="admin-topbar-breadcrumb">${breadcrumb}</div>`
        : '';

    return `
        <div class="admin-topbar">
            <div class="admin-topbar-left">
                <button class="admin-mobile-toggle" onclick="toggleSidebar()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                    </svg>
                </button>
                <h1 class="admin-topbar-title">${title}</h1>
                ${breadcrumbHtml}
            </div>
            <div class="admin-topbar-right">
                <button class="admin-topbar-btn" onclick="toggleTheme()" title="Toggle theme" id="theme-toggle-btn">
                    <svg id="theme-icon-moon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
                    </svg>
                    <svg id="theme-icon-sun" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="display:none;">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
                    </svg>
                </button>
                <button class="admin-signout-btn" onclick="adminLogout()" title="Sign Out">
                    ${getNavIcon('logout', 18)}
                    <span>Sign Out</span>
                </button>
                <a href="https://jobs.cariara.com/" class="admin-topbar-btn" title="Job Seeker Portal" target="_blank">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>
                    </svg>
                </a>
            </div>
        </div>
    `;
}

function toggleSidebar() {
    const sidebar = document.getElementById('admin-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const isOpen = sidebar.classList.contains('open');

    if (isOpen) {
        closeSidebar();
    } else {
        openSidebar();
    }
}

function openSidebar() {
    const sidebar = document.getElementById('admin-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.add('open');
    overlay.classList.add('open');
    document.body.style.overflow = 'hidden';
}

function closeSidebar() {
    const sidebar = document.getElementById('admin-sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.remove('open');
    overlay.classList.remove('open');
    document.body.style.overflow = '';
}

// Close sidebar on window resize to desktop
window.addEventListener('resize', () => {
    if (window.innerWidth > 1024) {
        closeSidebar();
    }
});

// Close sidebar when clicking a nav link on mobile
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 1024 && e.target.closest('.admin-nav-item')) {
        setTimeout(closeSidebar, 150);
    }
});

// Admin logout: clears the local session only (never calls /auth/logout-all).
function adminLogout() {
    if (typeof logout === 'function') return logout();
    ['access_token', 'refresh_token', 'token', 'user', 'redirect_after_login'].forEach(k => localStorage.removeItem(k));
    window.location.href = '/login.html';
}

// Update user info in sidebar (signout is in topbar)
function updateAdminUserInfo() {
    const userInfoSection = document.getElementById('admin-user-info-section');
    if (!userInfoSection) return;

    let user = {};
    try { user = JSON.parse(localStorage.getItem('user') || '{}') || {}; } catch (e) { user = {}; }
    const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const name = user.name || user.full_name || 'Admin';
    const email = user.email || '';
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'A';
    const role = String(user.role || 'admin');
    const roleDisplay = role === 'admin' ? 'Administrator' : role.charAt(0).toUpperCase() + role.slice(1);

    userInfoSection.innerHTML = `
        <div class="admin-user-info">
            <div class="admin-user-avatar">${esc(initials)}</div>
            <div class="admin-user-details">
                <div class="admin-user-name">${esc(name)}</div>
                <div class="admin-user-email">${esc(email || roleDisplay)}</div>
            </div>
        </div>
        <button type="button" class="admin-logout-btn" onclick="adminLogout()">${getNavIcon('logout', 20)}<span>Sign out</span></button>
    `;
}

/**
 * Build the shared admin shell around the page's existing content.
 * Existing DOM nodes are MOVED (not re-serialized), so event listeners bound
 * before this call and elements outside <main> (modals, toasts) keep working.
 * Theme handling lives in app.js (initTheme/toggleTheme/updateThemeIcon).
 */
function initAdminLayout(pageId, pageTitle, breadcrumb = null) {
    try {
        if (document.querySelector('.admin-layout')) return;

        document.querySelectorAll('body > header').forEach(h => h.remove());

        const tpl = document.createElement('template');
        tpl.innerHTML = `
            <div class="admin-layout">
                ${renderAdminSidebar(pageId)}
                <div class="admin-main">
                    ${renderAdminTopbar(pageTitle, breadcrumb)}
                    <div class="admin-content"></div>
                </div>
            </div>
        `.trim();
        const layout = tpl.content.firstElementChild;
        const content = layout.querySelector('.admin-content');

        const existingMain = document.querySelector('main');
        if (existingMain) {
            while (existingMain.firstChild) content.appendChild(existingMain.firstChild);
            existingMain.remove();
        }

        // Other visible page content outside <main> goes into the content area;
        // fixed overlays (modals, toasts) stay at body level so positioning is unaffected.
        Array.from(document.body.children).forEach(el => {
            if (['SCRIPT', 'STYLE', 'TEMPLATE', 'LINK', 'NOSCRIPT'].includes(el.tagName)) return;
            if (/modal|overlay|toast|dialog/i.test(`${el.id} ${el.className}`)) return;
            content.appendChild(el);
        });

        document.body.insertBefore(layout, document.body.firstChild);

        if (typeof initTheme === 'function') initTheme();
        updateAdminUserInfo();
    } catch (error) {
        console.error('Failed to initialize admin layout:', error);
    }
}
