/**
 * The admin shell, in cariara.com's Waymo register (css/waymo.css): one header
 * row (the Cariara lockup and "Admin", the sections as plain ink links with the
 * current one marked by a bar on the window's top edge, then theme, the job
 * board and your account), then the page title over the page's own content.
 * No side drawer; on phones the sections drop down from a menu button.
 * Include this file in all admin pages; each calls initAdminLayout(pageId, title).
 */

const ADMIN_NAV_ITEMS = [
    { id: 'dashboard', label: 'Dashboard', href: '/jobs/admin/index.html' },
    { id: 'jobs', label: 'Jobs', href: '/jobs/admin/jobs.html' },
    { id: 'companies', label: 'Companies', href: '/jobs/admin/companies.html' },
    { id: 'analytics', label: 'Analytics', href: '/jobs/admin/analytics.html' },
    { id: 'settings', label: 'Settings', href: '/jobs/admin/settings.html' },
];

const NAV_ICONS = {
    logout: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>',
    menu: '<path stroke-linecap="round" stroke-width="1.6" d="M4 7h16M4 12h16M4 17h16"/>',
    external: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/>',
};

function getNavIcon(iconName, size = 20) {
    return `<svg class="nav-icon" width="${size}" height="${size}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">${NAV_ICONS[iconName] || ''}</svg>`;
}

const escAdmin = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function renderAdminHeader(activePageId) {
    const links = ADMIN_NAV_ITEMS.map(item => `
        <a href="${item.href}" class="wm-nav-a"${item.id === activePageId ? ' aria-current="page"' : ''}>${item.label}</a>`).join('');
    return `
        <header class="wm-head" id="admin-header">
            <div class="wm-head-in">
                <a href="/jobs/admin/index.html" class="wm-brand" aria-label="Cariara Admin home">
                    <img class="wm-logo-light" src="/jobs/admin/images/cariara-lockup.svg" alt="Cariara" height="34">
                    <img class="wm-logo-dark" src="/jobs/admin/images/cariara-lockup-dark.svg" alt="" height="34">
                    <span class="wm-brand-tag">Admin</span>
                </a>
                <nav class="wm-nav" aria-label="Admin sections">${links}</nav>
                <div class="wm-head-right">
                    <button type="button" class="wm-icon-btn" onclick="toggleTheme()" title="Toggle theme" id="theme-toggle-btn">
                        <svg id="theme-icon-moon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
                        </svg>
                        <svg id="theme-icon-sun" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="20" height="20" style="display:none;" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
                        </svg>
                    </button>
                    <a href="https://cariara.com/jobs" class="wm-icon-btn" title="Job board" target="_blank" rel="noopener">${getNavIcon('external')}</a>
                    <div class="wm-account" id="admin-user-info-section"></div>
                    <button type="button" class="wm-icon-btn wm-menu-btn" onclick="toggleSidebar()" aria-label="Sections" aria-expanded="false" aria-controls="admin-header">${getNavIcon('menu')}</button>
                </div>
            </div>
        </header>
    `;
}

function renderAdminPageHead(title, breadcrumb = null) {
    return `
        <div class="wm-page-head">
            ${breadcrumb ? `<div class="admin-topbar-breadcrumb">${breadcrumb}</div>` : ''}
            <h1 class="admin-topbar-title">${escAdmin(title)}</h1>
        </div>
    `;
}

/* Phones: the sections drop down under the header. The names stay for pages
   that called the old drawer's functions. */
function toggleSidebar() {
    const head = document.getElementById('admin-header');
    if (head && head.classList.contains('is-open')) closeSidebar(); else openSidebar();
}

function openSidebar() {
    const head = document.getElementById('admin-header');
    if (!head) return;
    head.classList.add('is-open');
    head.querySelector('.wm-menu-btn')?.setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
    const head = document.getElementById('admin-header');
    if (!head) return;
    head.classList.remove('is-open');
    head.querySelector('.wm-menu-btn')?.setAttribute('aria-expanded', 'false');
}

window.addEventListener('resize', () => {
    if (window.innerWidth > 900) closeSidebar();
});

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
});

// Admin logout: clears the local session only (never calls /auth/logout-all).
function adminLogout() {
    if (typeof logout === 'function') return logout();
    ['access_token', 'refresh_token', 'token', 'user', 'redirect_after_login'].forEach(k => localStorage.removeItem(k));
    window.location.href = '/jobs/admin/login.html';
}

// The header's account: your initials (name and email on hover) and Sign out.
function updateAdminUserInfo() {
    const userInfoSection = document.getElementById('admin-user-info-section');
    if (!userInfoSection) return;

    let user = {};
    try { user = JSON.parse(localStorage.getItem('user') || '{}') || {}; } catch (e) { user = {}; }
    const name = user.name || user.full_name || 'Admin';
    const email = user.email || '';
    const initials = name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'A';

    userInfoSection.innerHTML = `
        <span class="wm-avatar" title="${escAdmin(email ? `${name} · ${email}` : name)}">${escAdmin(initials)}</span>
        <button type="button" class="wm-signout" onclick="adminLogout()">Sign out</button>
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
            <div class="admin-layout wm-layout">
                ${renderAdminHeader(pageId)}
                <div class="admin-main">
                    ${renderAdminPageHead(pageTitle, breadcrumb)}
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
