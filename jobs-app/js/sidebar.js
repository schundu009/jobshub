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

function initSidebarUserMenu() {
    const userMenu = document.getElementById('user-menu');
    if (!userMenu) return;

    // Get login icon from CariaraIcons or fallback to inline SVG
    const loginIcon = typeof CariaraIcons !== 'undefined'
        ? CariaraIcons.login
        : `<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path></svg>`;

    const userJson = localStorage.getItem('user');
    if (!userJson) {
        userMenu.innerHTML = `
            <a href="login.html" class="sidebar-logout-btn">
                ${loginIcon}
                Sign In
            </a>
        `;
        return;
    }

    try {
        const user = JSON.parse(userJson);
        const name = user.name || user.email?.split('@')[0] || 'User';
        const initials = name.split(' ').map(x => x[0]).join('').toUpperCase().slice(0, 2);
        const email = user.email || '';

        userMenu.innerHTML = `
            <div class="sidebar-user-info">
                <div class="sidebar-user-avatar">${initials}</div>
                <div class="sidebar-user-details">
                    <div class="sidebar-user-name">${name}</div>
                    <div class="sidebar-user-email">${email}</div>
                </div>
            </div>
        `;
    } catch (e) {
        console.error('Error parsing user data:', e);
    }
}

function handleLogout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    window.location.href = 'login.html';
}

// =============================================================================
// ACTIVE LINK HIGHLIGHTING
// =============================================================================

function highlightActiveNavLink() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';

    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPage) {
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
        const icon = CariaraIcons.mark(iconName, { class: 'cariara-mark', width: 24 });
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

    // Inject filter section icons
    document.querySelectorAll('.filter-icon[data-icon], .companies-icon[data-icon]').forEach(el => {
        const iconName = el.dataset.icon;
        const icon = CariaraIcons.mark(iconName, { class: 'cariara-mark', width: 24 });
        if (icon && !el.querySelector('svg')) {
            el.insertAdjacentHTML('afterbegin', icon);
        }
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
