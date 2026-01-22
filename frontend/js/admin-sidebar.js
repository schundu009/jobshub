/**
 * Admin Sidebar Navigation
 * Include this file in all admin pages for consistent navigation
 */

const ADMIN_NAV_ITEMS = [
    {
        section: 'Main',
        items: [
            { id: 'dashboard', label: 'Dashboard', href: 'index.html', icon: 'dashboard' },
            { id: 'jobs', label: 'Jobs', href: 'jobs.html', icon: 'briefcase' },
            { id: 'companies', label: 'Companies', href: 'companies.html', icon: 'building' },
        ]
    },
    {
        section: 'Analytics',
        items: [
            { id: 'analytics', label: 'Analytics', href: 'analytics.html', icon: 'chart' },
        ]
    },
    {
        section: 'System',
        items: [
            { id: 'settings', label: 'Settings', href: 'settings.html', icon: 'settings' },
        ]
    }
];

const NAV_ICONS = {
    dashboard: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>',
    briefcase: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>',
    building: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>',
    chart: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>',
    settings: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
};

function getNavIcon(iconName) {
    return `<svg class="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">${NAV_ICONS[iconName] || ''}</svg>`;
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
                <a href="index.html" class="admin-logo">
                    <svg width="32" height="32" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="sidebarLogoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#c4b5fd"/>
                                <stop offset="50%" style="stop-color:#a78bfa"/>
                                <stop offset="100%" style="stop-color:#7c3aed"/>
                            </linearGradient>
                        </defs>
                        <path d="M24 6C14.059 6 6 14.059 6 24C6 33.941 14.059 42 24 42C27.8 42 31.3 40.8 34 38.8" stroke="url(#sidebarLogoGradient)" stroke-width="3.5" stroke-linecap="round" fill="none"/>
                        <line x1="26" y1="18" x2="40" y2="18" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <line x1="26" y1="25" x2="36" y2="25" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <line x1="26" y1="32" x2="32" y2="32" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <circle cx="42" cy="32" r="2.5" stroke="url(#sidebarLogoGradient)" stroke-width="1.5" fill="none"/>
                    </svg>
                    <span class="admin-logo-text">Cariara</span>
                </a>
            </div>
            <nav class="admin-nav">
                ${navHtml}
            </nav>
            <div class="admin-sidebar-footer">
                <div class="admin-user">
                    <div class="admin-user-avatar">A</div>
                    <div class="admin-user-info">
                        <div class="admin-user-name">Admin</div>
                        <div class="admin-user-role">Administrator</div>
                    </div>
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
                <button class="admin-topbar-btn" onclick="toggleTheme()" title="Toggle theme">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
                    </svg>
                </button>
                <a href="../jobs/discover.html" class="admin-topbar-btn" title="Job Seeker Portal">
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
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
}

function initAdminLayout(pageId, pageTitle, breadcrumb = null) {
    // Remove existing header if present
    const existingHeader = document.querySelector('header');
    if (existingHeader) {
        existingHeader.remove();
    }

    // Remove existing main and wrap content
    const existingMain = document.querySelector('main');
    const mainContent = existingMain ? existingMain.innerHTML : '';

    // Create new layout structure
    const layoutHtml = `
        <div class="admin-layout">
            ${renderAdminSidebar(pageId)}
            <div class="admin-main">
                ${renderAdminTopbar(pageTitle, breadcrumb)}
                <div class="admin-content">
                    ${mainContent}
                </div>
            </div>
        </div>
    `;

    // Replace body content (keeping scripts)
    const scripts = document.body.querySelectorAll('script');
    document.body.innerHTML = layoutHtml;
    scripts.forEach(script => document.body.appendChild(script.cloneNode(true)));
}
