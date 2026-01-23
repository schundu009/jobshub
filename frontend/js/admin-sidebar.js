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

// Job type filters with their query parameters
const JOB_TYPE_FILTERS = [
    { id: 'all', label: 'All Jobs', icon: 'stack', query: '' },
    { id: 'devops', label: 'DevOps', icon: 'server', query: 'search=devops' },
    { id: 'backend', label: 'Backend', icon: 'code', query: 'search=backend' },
    { id: 'frontend', label: 'Frontend', icon: 'layout', query: 'search=frontend' },
    { id: 'fullstack', label: 'Full Stack', icon: 'layers', query: 'search=fullstack' },
    { id: 'data', label: 'Data/ML', icon: 'database', query: 'search=data+engineer,machine+learning' },
];

const NAV_ICONS = {
    dashboard: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/>',
    briefcase: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>',
    building: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>',
    chart: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>',
    settings: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
    // Quick filter icons
    stack: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>',
    server: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"/>',
    code: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/>',
    layout: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"/>',
    layers: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>',
    database: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"/>',
    star: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>',
    filter: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"/>',
};

// Cache for sidebar data
let sidebarDataCache = {
    jobCounts: null,
    topCompanies: null,
    lastFetch: 0
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

    // Quick Filters Section
    const quickFiltersHtml = `
        <div class="admin-nav-section sidebar-filters-section">
            <div class="admin-nav-label">${getNavIcon('filter', 14)} Quick Filters</div>
            <div id="quick-filters-list" class="quick-filters-list">
                ${JOB_TYPE_FILTERS.map(filter => `
                    <a href="jobs.html${filter.query ? '?' + filter.query : ''}"
                       class="sidebar-filter-item"
                       data-filter="${filter.id}">
                        ${getNavIcon(filter.icon, 16)}
                        <span class="filter-label">${filter.label}</span>
                        <span class="filter-count" id="count-${filter.id}">-</span>
                    </a>
                `).join('')}
            </div>
        </div>
    `;

    // Top Companies Section
    const companiesHtml = `
        <div class="admin-nav-section sidebar-companies-section">
            <div class="admin-nav-label">${getNavIcon('star', 14)} Top Companies</div>
            <div id="top-companies-list" class="top-companies-list">
                <div class="sidebar-loading">Loading...</div>
            </div>
        </div>
    `;

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
            <div class="admin-sidebar-divider"></div>
            <div class="admin-sidebar-filters">
                ${quickFiltersHtml}
                ${companiesHtml}
            </div>
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

async function loadSidebarData() {
    // Check cache (refresh every 5 minutes)
    const now = Date.now();
    if (sidebarDataCache.lastFetch && (now - sidebarDataCache.lastFetch) < 300000) {
        updateSidebarWithData(sidebarDataCache);
        return;
    }

    try {
        // Fetch job counts and top companies in parallel
        const [jobsResponse, companiesResponse] = await Promise.all([
            fetch(`${API_BASE}/jobs?active_only=true&all=true&no_cache=true`).then(r => r.json()).catch(() => []),
            fetch(`${API_BASE}/analytics/by-company`).then(r => r.json()).catch(() => [])
        ]);

        // Calculate counts by job type
        const jobs = Array.isArray(jobsResponse) ? jobsResponse : (jobsResponse.jobs || []);
        const jobCounts = {
            all: jobs.length,
            devops: 0,
            backend: 0,
            frontend: 0,
            fullstack: 0,
            data: 0
        };

        jobs.forEach(job => {
            const title = (job.title || '').toLowerCase();
            const desc = (job.job_description || '').toLowerCase();
            const combined = title + ' ' + desc;

            if (combined.includes('devops') || combined.includes('sre') || combined.includes('infrastructure') || combined.includes('platform')) {
                jobCounts.devops++;
            }
            if (combined.includes('backend') || combined.includes('server') || (combined.includes('engineer') && !combined.includes('frontend'))) {
                jobCounts.backend++;
            }
            if (combined.includes('frontend') || combined.includes('ui ') || combined.includes('react') || combined.includes('vue')) {
                jobCounts.frontend++;
            }
            if (combined.includes('full stack') || combined.includes('fullstack') || combined.includes('full-stack')) {
                jobCounts.fullstack++;
            }
            if (combined.includes('data') || combined.includes('machine learning') || combined.includes('ml ') || combined.includes('ai ')) {
                jobCounts.data++;
            }
        });

        // Get top companies by job count
        const companies = Array.isArray(companiesResponse) ? companiesResponse : [];
        const topCompanies = companies
            .filter(c => c.active_jobs > 0)
            .sort((a, b) => b.active_jobs - a.active_jobs)
            .slice(0, 8);

        // Update cache
        sidebarDataCache = {
            jobCounts,
            topCompanies,
            lastFetch: now
        };

        updateSidebarWithData(sidebarDataCache);
    } catch (error) {
        console.error('Error loading sidebar data:', error);
    }
}

function updateSidebarWithData(data) {
    // Update job counts
    if (data.jobCounts) {
        Object.keys(data.jobCounts).forEach(key => {
            const countEl = document.getElementById(`count-${key}`);
            if (countEl) {
                countEl.textContent = data.jobCounts[key];
            }
        });
    }

    // Update top companies
    if (data.topCompanies) {
        const companiesList = document.getElementById('top-companies-list');
        if (companiesList) {
            if (data.topCompanies.length === 0) {
                companiesList.innerHTML = '<div class="sidebar-empty">No companies yet</div>';
            } else {
                companiesList.innerHTML = data.topCompanies.map(company => `
                    <a href="jobs.html?company=${encodeURIComponent(company.company_name)}"
                       class="sidebar-company-item">
                        <span class="company-initial">${(company.company_name || 'C')[0].toUpperCase()}</span>
                        <span class="company-name">${company.company_name}</span>
                        <span class="company-count">${company.active_jobs}</span>
                    </a>
                `).join('');
            }
        }
    }
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

    // Load sidebar data after layout is initialized
    setTimeout(loadSidebarData, 100);
}
