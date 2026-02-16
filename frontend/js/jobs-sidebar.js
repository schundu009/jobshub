/**
 * Jobs Portal Sidebar Navigation
 * Include this file in all jobs portal pages for consistent navigation
 */

const JOBS_NAV_ITEMS = [
    { id: 'discover', label: 'Jobs', href: 'discover.html', icon: 'search' },
    { id: 'autoapply', label: 'AutoApply', href: 'autoapply.html', icon: 'lightning' },
    { id: 'contacts', label: 'Contacts', href: 'contacts.html', icon: 'users' },
    { id: 'analytics', label: 'Analytics', href: 'analytics.html', icon: 'chart' },
    { id: 'settings', label: 'Settings', href: 'settings.html', icon: 'settings' },
];

const JOBS_NAV_ICONS = {
    search: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>',
    lightning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/>',
    users: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/>',
    chart: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>',
    settings: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
};

function getJobsNavIcon(iconName) {
    return `<svg class="nav-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">${JOBS_NAV_ICONS[iconName] || ''}</svg>`;
}

function renderJobsSidebar(activePageId) {
    let navHtml = '';

    JOBS_NAV_ITEMS.forEach(item => {
        const isActive = item.id === activePageId;
        navHtml += `
            <a href="${item.href}" class="jobs-nav-item ${isActive ? 'active' : ''}">
                ${getJobsNavIcon(item.icon)}
                <span>${item.label}</span>
            </a>
        `;
    });

    return `
        <aside class="jobs-sidebar" id="jobs-sidebar">
            <div class="jobs-sidebar-header">
                <a href="discover.html" class="jobs-logo">
                    <svg width="32" height="32" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <defs>
                            <linearGradient id="sidebarLogoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#5eead4"/>
                                <stop offset="50%" style="stop-color:#14b8a6"/>
                                <stop offset="100%" style="stop-color:#0d9488"/>
                            </linearGradient>
                        </defs>
                        <path d="M24 6C14.059 6 6 14.059 6 24C6 33.941 14.059 42 24 42C27.8 42 31.3 40.8 34 38.8" stroke="url(#sidebarLogoGradient)" stroke-width="3.5" stroke-linecap="round" fill="none"/>
                        <line x1="26" y1="18" x2="40" y2="18" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <line x1="26" y1="25" x2="36" y2="25" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <line x1="26" y1="32" x2="32" y2="32" stroke="url(#sidebarLogoGradient)" stroke-width="2.5" stroke-linecap="round"/>
                        <circle cx="42" cy="32" r="2.5" stroke="url(#sidebarLogoGradient)" stroke-width="1.5" fill="none"/>
                    </svg>
                    <span class="jobs-logo-text">Cariara</span>
                </a>
            </div>
            <nav class="jobs-nav">
                ${navHtml}
            </nav>
            <div class="jobs-sidebar-footer">
                <a href="../admin/index.html" class="jobs-admin-link">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/>
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
                    </svg>
                    <span>Admin Portal</span>
                </a>
            </div>
        </aside>
        <div class="jobs-sidebar-overlay" id="jobs-sidebar-overlay" onclick="toggleJobsSidebar()"></div>
    `;
}

function renderJobsTopbar(title) {
    return `
        <div class="jobs-topbar">
            <div class="jobs-topbar-left">
                <button class="jobs-mobile-toggle" onclick="toggleJobsSidebar()">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
                    </svg>
                </button>
                <h1 class="jobs-topbar-title">${title}</h1>
            </div>
            <div class="jobs-topbar-right">
                <button class="jobs-topbar-btn" onclick="toggleTheme()" title="Toggle theme">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
                    </svg>
                </button>
            </div>
        </div>
    `;
}

function toggleJobsSidebar() {
    const sidebar = document.getElementById('jobs-sidebar');
    const overlay = document.getElementById('jobs-sidebar-overlay');
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('open');
}

function initJobsLayout(pageId, pageTitle) {
    // Remove existing header if present
    const existingHeader = document.querySelector('header');
    if (existingHeader) {
        existingHeader.remove();
    }

    // Remove existing sidebar if present
    const existingSidebar = document.querySelector('.sidebar');
    if (existingSidebar) {
        existingSidebar.remove();
    }

    // Get main content
    const existingMain = document.querySelector('main') || document.querySelector('.main-content');
    const mainContent = existingMain ? existingMain.innerHTML : '';

    // Create new layout structure
    const layoutHtml = `
        <div class="jobs-layout">
            ${renderJobsSidebar(pageId)}
            <div class="jobs-main">
                ${renderJobsTopbar(pageTitle)}
                <div class="jobs-content">
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
