/**
 * Enterprise Sidebar Navigation JavaScript
 * Shared across all job seeker portal pages
 * Version: 2.0
 */

// =============================================================================
// MOBILE MENU FUNCTIONS
// =============================================================================

function initMobileSidebar() {
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');

    if (!mobileMenuBtn || !sidebar) return;

    // Mobile menu toggle
    mobileMenuBtn.addEventListener('click', toggleMobileSidebar);

    // Backdrop click closes sidebar
    if (backdrop) {
        backdrop.addEventListener('click', closeMobileSidebar);
    }

    // Close on nav link click (mobile)
    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                closeMobileSidebar();
            }
        });
    });

    // Close on window resize to desktop
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            closeMobileSidebar();
        }
    });

    // Handle escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('mobile-open')) {
            closeMobileSidebar();
        }
    });
}

function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar.classList.contains('mobile-open')) {
        closeMobileSidebar();
    } else {
        openMobileSidebar();
    }
}

function openMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btn = document.getElementById('mobile-menu-btn');

    sidebar.classList.add('mobile-open');
    if (backdrop) backdrop.classList.add('active');
    if (btn) btn.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    const btn = document.getElementById('mobile-menu-btn');

    sidebar.classList.remove('mobile-open');
    if (backdrop) backdrop.classList.remove('active');
    if (btn) btn.classList.remove('active');
    document.body.style.overflow = '';
}

// =============================================================================
// USER MENU INITIALIZATION
// =============================================================================

function escapeSidebarText(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function initSidebarUserMenu() {
    const userMenu = document.getElementById('user-menu');
    if (!userMenu) return;

    const icon = name => (typeof CariaraIcons !== 'undefined' ? CariaraIcons.mark(name, { width: 20 }) : '');
    let user = null;
    try { user = JSON.parse(localStorage.getItem('user') || 'null'); } catch (e) { user = null; }

    if (!user) {
        userMenu.innerHTML = `<a href="login.html" class="sidebar-logout-btn">${icon('login')}<span>Sign in</span></a>`;
        return;
    }

    const name = user.name || user.full_name || (user.email || '').split('@')[0] || 'You';
    const initials = name.split(/\s+/).filter(Boolean).map(x => x[0]).join('').toUpperCase().slice(0, 2) || '?';
    const isAdmin = user.role === 'admin' || user.is_admin === true;

    userMenu.innerHTML = `
        <div class="sidebar-user-info" title="${escapeSidebarText(user.email || '')}">
            <div class="sidebar-user-avatar">${escapeSidebarText(initials)}</div>
            <div class="sidebar-user-details">
                <div class="sidebar-user-name">${escapeSidebarText(name)}</div>
                <div class="sidebar-user-email">${escapeSidebarText(user.email || '')}</div>
            </div>
        </div>
        ${isAdmin ? `<a href="https://admin.cariara.com/" class="sidebar-admin-link" target="_blank" rel="noopener">${icon('settingsGear') || icon('settings')}<span>Admin portal</span></a>` : ''}
        <button type="button" class="sidebar-logout-btn" onclick="handleLogout()">${icon('logout')}<span>Sign out</span></button>
    `;
}

const SESSION_KEYS = ['access_token', 'refresh_token', 'token', 'user', 'subscription_status', 'cariara_resume_draft', 'redirect_after_login'];

function handleLogout() {
    SESSION_KEYS.forEach(key => localStorage.removeItem(key));
    // Per-user drafts are keyed "cariara_resume_draft:<userId>".
    Object.keys(localStorage).filter(key => key.startsWith('cariara_resume_draft:')).forEach(key => localStorage.removeItem(key));
    window.location.href = 'login.html';
}

// =============================================================================
// ACTIVE LINK HIGHLIGHTING
// =============================================================================

function highlightActiveNavLink() {
    const pageName = path => (path.split('?')[0].split('#')[0].split('/').pop() || 'index').replace(/\.html$/, '');
    const currentPage = pageName(window.location.pathname);

    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        const href = link.getAttribute('href') || '';
        if (/^https?:/.test(href)) return;
        if (pageName(href) === currentPage) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
}

// =============================================================================
// NAVIGATION WITH LOADING STATE
// =============================================================================

function navigateTo(url) {
    // Add subtle loading indicator
    document.body.style.opacity = '0.8';
    document.body.style.transition = 'opacity 0.2s ease';

    setTimeout(() => {
        window.location.href = url;
    }, 100);
}

// =============================================================================
// KEYBOARD NAVIGATION
// =============================================================================

function initKeyboardNavigation() {
    const navLinks = document.querySelectorAll('.sidebar-nav a');

    navLinks.forEach((link, index) => {
        link.setAttribute('tabindex', '0');

        link.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                const next = navLinks[index + 1] || navLinks[0];
                next.focus();
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                const prev = navLinks[index - 1] || navLinks[navLinks.length - 1];
                prev.focus();
            } else if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                link.click();
            }
        });
    });
}

// =============================================================================
// TOOLTIP FOR COLLAPSED STATE (FUTURE USE)
// =============================================================================

function showNavTooltip(element, text) {
    const tooltip = document.createElement('div');
    tooltip.className = 'nav-tooltip';
    tooltip.textContent = text;
    tooltip.style.cssText = `
        position: absolute;
        left: 100%;
        top: 50%;
        transform: translateY(-50%);
        margin-left: 10px;
        padding: 6px 12px;
        background: var(--bg-elevated);
        border: 1px solid var(--border-color);
        border-radius: 6px;
        font-size: 12px;
        white-space: nowrap;
        z-index: 1000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    element.appendChild(tooltip);
}

function hideNavTooltip(element) {
    const tooltip = element.querySelector('.nav-tooltip');
    if (tooltip) tooltip.remove();
}

// =============================================================================
// ICON INJECTION
// =============================================================================

function injectNavigationIcons() {
    if (typeof CariaraIcons === 'undefined') return;

    // Inject icons for nav links with data-icon attribute
    document.querySelectorAll('.nav-link[data-icon]').forEach(link => {
        const iconName = link.dataset.icon;
        const icon = CariaraIcons.mark(iconName, { width: 20 });
        if (icon && !link.querySelector('svg')) {
            link.insertAdjacentHTML('afterbegin', icon);
        }
    });

    // Inject mobile menu icons
    const menuOpen = document.querySelector('.menu-open');
    const menuClose = document.querySelector('.menu-close');
    if (menuOpen && !menuOpen.querySelector('svg')) menuOpen.innerHTML = CariaraIcons.menu;
    if (menuClose && !menuClose.querySelector('svg')) menuClose.innerHTML = CariaraIcons.close;

    // Inject theme icons
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    if (sunIcon && !sunIcon.querySelector('svg')) sunIcon.innerHTML = CariaraIcons.sun;
    if (moonIcon && !moonIcon.querySelector('svg')) moonIcon.innerHTML = CariaraIcons.moon;

    // Inject logout icons
    document.querySelectorAll('.logout-icon').forEach(el => {
        if (!el.querySelector('svg')) el.innerHTML = CariaraIcons.logout;
    });
}

// =============================================================================
// INITIALIZATION
// =============================================================================

function initSidebar() {
    injectNavigationIcons();
    initMobileSidebar();
    initSidebarUserMenu();
    highlightActiveNavLink();
    initKeyboardNavigation();
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebar);
} else {
    initSidebar();
}

// Export functions
window.initSidebar = initSidebar;
window.toggleMobileSidebar = toggleMobileSidebar;
window.openMobileSidebar = openMobileSidebar;
window.closeMobileSidebar = closeMobileSidebar;
window.handleLogout = handleLogout;
window.navigateTo = navigateTo;
