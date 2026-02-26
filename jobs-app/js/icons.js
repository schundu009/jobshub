/**
 * Cariara Premium Icon Library
 *
 * Enterprise-grade icons inspired by Databricks, Azure, and GCP design systems.
 * Features: clean geometry, subtle fills, consistent 1.5px strokes, modern aesthetic.
 *
 * All icons use a 24x24 viewBox with 1.5px stroke weight for a refined look.
 *
 * Usage:
 *   element.innerHTML = CariaraIcons.devops;
 *   CariaraIcons.get('devops', { class: 'w-6 h-6', style: 'color: blue' });
 */

const CariaraIcons = {
    // =========================================================================
    // ROLE / CATEGORY ICONS - Premium enterprise designs
    // =========================================================================

    devops: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L3 7v10l9 5 9-5V7l-9-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M12 22V12" stroke="currentColor" stroke-width="1.5"/>
        <path d="M21 7l-9 5-9-5" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="2" fill="currentColor"/>
    </svg>`,

    sre: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L4 5v6.09c0 5.05 3.41 9.76 8 10.91 4.59-1.15 8-5.86 8-10.91V5l-8-3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M12 8v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="14" r="1" fill="currentColor"/>
        <path d="M8 11h1m6 0h1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    cloudArchitect: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M6.5 19a4.5 4.5 0 01-.42-8.98 6.002 6.002 0 0111.84 0A4.5 4.5 0 0117.5 19h-11z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M12 13v4m-2-2h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    platform: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <rect x="14" y="3" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <rect x="3" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <rect x="14" y="14" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="2" fill="currentColor"/>
    </svg>`,

    backend: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="4" width="18" height="5" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <rect x="3" y="15" width="18" height="5" rx="1.5" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="6" cy="6.5" r="1" fill="currentColor"/>
        <circle cx="6" cy="17.5" r="1" fill="currentColor"/>
        <path d="M12 9v6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-dasharray="2 2"/>
    </svg>`,

    fullstack: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M3 9h18" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 9v12" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="5.5" cy="6" r="1" fill="currentColor"/>
        <circle cx="8.5" cy="6" r="1" fill="currentColor"/>
        <path d="M14 14l2 2-2 2M18 14l2 2-2 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    data: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="12" cy="6" rx="8" ry="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M4 6v6c0 1.66 3.58 3 8 3s8-1.34 8-3V6" stroke="currentColor" stroke-width="1.5"/>
        <path d="M4 12v6c0 1.66 3.58 3 8 3s8-1.34 8-3v-6" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
    </svg>`,

    ml: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="3" r="2" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="21" cy="12" r="2" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="21" r="2" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="3" cy="12" r="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 5v4m4-2.5L13.5 9M19 12h-4m2.5 4L15 13.5M12 19v-4m-4 2.5L10.5 15M5 12h4m-2.5-4L9 10.5" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="1" fill="currentColor"/>
    </svg>`,

    security: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M8 11V7a4 4 0 118 0v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="15" r="1.5" fill="currentColor"/>
        <path d="M12 16.5v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    frontend: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="4" width="20" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M8 21h8M12 18v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M6 9l3 3-3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M12 15h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    mobile: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="6" y="2" width="12" height="20" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="18" r="1" fill="currentColor"/>
        <path d="M9 5h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // NAVIGATION ICONS
    // =========================================================================

    home: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 10.5L12 3l9 7.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1v-9.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M9 21v-7h6v7" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    discover: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M16.24 7.76l-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12z" fill="currentColor"/>
    </svg>`,

    search: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="10.5" cy="10.5" r="7" stroke="currentColor" stroke-width="1.5"/>
        <path d="M21 21l-5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    searchPlus: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="10.5" cy="10.5" r="7" stroke="currentColor" stroke-width="1.5"/>
        <path d="M21 21l-5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M10.5 7.5v6M7.5 10.5h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    filter: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 6h18M7 12h10M10 18h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="8" cy="6" r="2" fill="currentColor"/>
        <circle cx="16" cy="12" r="2" fill="currentColor"/>
        <circle cx="12" cy="18" r="2" fill="currentColor"/>
    </svg>`,

    menu: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    close: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    chevronDown: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    chevronUp: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M18 15l-6-6-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    chevronLeft: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M15 6l-6 6 6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    chevronRight: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 6l6 6-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    arrowLeft: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M19 12H5m0 0l6 6m-6-6l6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    arrowRight: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 12h14m0 0l-6-6m6 6l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    externalLink: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M15 3h6v6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M10 14L21 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // USER / PROFILE ICONS
    // =========================================================================

    user: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="8" r="4" stroke="currentColor" stroke-width="1.5"/>
        <path d="M4 21v-1a4 4 0 014-4h8a4 4 0 014 4v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    userCircle: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M6 19.5a6 6 0 0112 0" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    users: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="9" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M3 21v-1a4 4 0 014-4h4a4 4 0 014 4v1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="17" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M21 21v-1a4 4 0 00-3-3.87" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    settings: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 1v4m0 14v4M4.22 4.22l2.83 2.83m9.9 9.9l2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9l2.83-2.83" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    settingsGear: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09a1.65 1.65 0 00-1.08-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09a1.65 1.65 0 001.51-1.08 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.26.6.83 1 1.51 1.08H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    logout: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M16 17l5-5-5-5M21 12H9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    login: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M10 17l5-5-5-5M15 12H3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    // =========================================================================
    // ACTION ICONS
    // =========================================================================

    save: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M17 21v-8H7v8" stroke="currentColor" stroke-width="1.5"/>
        <path d="M7 3v5h8" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    bookmark: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M19 21l-7-4-7 4V5a2 2 0 012-2h10a2 2 0 012 2v16z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    bookmarkFilled: `<svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M19 21l-7-4-7 4V5a2 2 0 012-2h10a2 2 0 012 2v16z"/>
    </svg>`,

    heart: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    heartFilled: `<svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>
    </svg>`,

    star: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    starFilled: `<svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
    </svg>`,

    share: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="18" cy="5" r="3" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="6" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="18" cy="19" r="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    copy: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    edit: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M18.5 2.5a2.121 2.121 0 113 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    trash: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6" stroke="currentColor" stroke-width="1.5"/>
        <path d="M10 11v6M14 11v6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    download: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M7 10l5 5 5-5M12 15V3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    upload: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M17 8l-5-5-5 5M12 3v12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    refresh: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M23 4v6h-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M1 20v-6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    plus: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    minus: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 12h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    check: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M20 6L9 17l-5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    x: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // STATUS ICONS
    // =========================================================================

    checkCircle: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    alertCircle: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 8v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="16" r="1" fill="currentColor"/>
    </svg>`,

    alertTriangle: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M12 9v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="17" r="1" fill="currentColor"/>
    </svg>`,

    info: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 16v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="8" r="1" fill="currentColor"/>
    </svg>`,

    helpCircle: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 9a3 3 0 115.83 1c0 2-3 3-3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="17" r="1" fill="currentColor"/>
    </svg>`,

    loader: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // DOCUMENT ICONS
    // =========================================================================

    document: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M16 13H8M16 17H8M10 9H8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    resume: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <circle cx="10" cy="11" r="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M14 15h2M14 18h2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M8 18v-.5a2 2 0 012-2 2 2 0 012 2v.5" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    coverLetter: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8l-6-6z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M14 2v6h6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    folder: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    folderOpen: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2v11z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M2 10h20" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    // =========================================================================
    // THEME ICONS
    // =========================================================================

    sun: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    moon: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    // =========================================================================
    // SOCIAL / AUTH ICONS
    // =========================================================================

    google: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>`,

    linkedin: `<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M20.45 20.45h-3.55v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.29zM5.34 7.43a2.06 2.06 0 110-4.12 2.06 2.06 0 010 4.12zm1.78 13.02H3.56V9h3.56v11.45zM22.23 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.23 0z" fill="#0A66C2"/>
    </svg>`,

    github: `<svg viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.79-.26.79-.58v-2.23c-3.34.73-4.03-1.42-4.03-1.42-.55-1.39-1.33-1.76-1.33-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.49 1 .11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 016.01 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.87.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.48 5.93.43.37.81 1.1.81 2.22v3.29c0 .32.19.7.8.58C20.57 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z"/>
    </svg>`,

    email: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="4" width="20" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M22 6l-10 7L2 6" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    // =========================================================================
    // JOB / WORK ICONS
    // =========================================================================

    briefcase: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="7" width="20" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 12v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M2 12h20" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    building: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="4" y="2" width="16" height="20" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 22v-4h6v4" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="8" cy="6" r="1" fill="currentColor"/>
        <circle cx="12" cy="6" r="1" fill="currentColor"/>
        <circle cx="16" cy="6" r="1" fill="currentColor"/>
        <circle cx="8" cy="10" r="1" fill="currentColor"/>
        <circle cx="12" cy="10" r="1" fill="currentColor"/>
        <circle cx="16" cy="10" r="1" fill="currentColor"/>
        <circle cx="8" cy="14" r="1" fill="currentColor"/>
        <circle cx="16" cy="14" r="1" fill="currentColor"/>
    </svg>`,

    mapPin: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="10" r="3" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    clock: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 7v5l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    calendar: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M16 2v4M8 2v4M3 10h18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <rect x="7" y="14" width="3" height="3" rx="0.5" fill="currentColor"/>
    </svg>`,

    dollarSign: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2v20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M17 5H9.5a3.5 3.5 0 100 7h5a3.5 3.5 0 110 7H6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    rocket: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 00-2.91-.09z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M12 15l-3-3a22 22 0 012-3.95A12.88 12.88 0 0122 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 01-4 2z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    target: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="2" fill="currentColor"/>
    </svg>`,

    trophy: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M6 9H4.5a2.5 2.5 0 010-5H6M18 9h1.5a2.5 2.5 0 000-5H18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M4 22h16" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22" stroke="currentColor" stroke-width="1.5"/>
        <path d="M18 2H6v7a6 6 0 0012 0V2z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    zap: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    sparkles: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 3l1.91 5.81a2 2 0 001.28 1.28L21 12l-5.81 1.91a2 2 0 00-1.28 1.28L12 21l-1.91-5.81a2 2 0 00-1.28-1.28L3 12l5.81-1.91a2 2 0 001.28-1.28L12 3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M5 3v4M19 17v4M3 5h4M17 19h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // INTERVIEW PREP ICONS
    // =========================================================================

    brain: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 4.5V19a2.5 2.5 0 01-4.96.44 2.5 2.5 0 01-2.96-3.08 3 3 0 01-.34-5.58 2.5 2.5 0 011.32-4.24A2.5 2.5 0 019.5 2.5 2.5 2.5 0 0112 4.5z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 4.5V19a2.5 2.5 0 004.96.44 2.5 2.5 0 002.96-3.08 3 3 0 00.34-5.58 2.5 2.5 0 00-1.32-4.24A2.5 2.5 0 0014.5 2.5 2.5 2.5 0 0012 4.5z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    microphone: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="9" y="2" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.5"/>
        <path d="M19 10v1a7 7 0 01-14 0v-1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M12 18v4M8 22h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    video: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="5" width="15" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M17 9l5-3v12l-5-3V9z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    play: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M5 4.5v15a1 1 0 001.5.86l12-7.5a1 1 0 000-1.72l-12-7.5A1 1 0 005 4.5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`,

    pause: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="6" y="4" width="4" height="16" rx="1" stroke="currentColor" stroke-width="1.5"/>
        <rect x="14" y="4" width="4" height="16" rx="1" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    timer: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="14" r="8" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 10v4l2 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M9 2h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M12 2v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    code: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M16 18l6-6-6-6M8 6l-6 6 6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    terminal: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M7 9l3 3-3 3M12 15h5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    book: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 19.5A2.5 2.5 0 016.5 17H20" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M8 7h8M8 11h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    lightbulb: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M9 18h6M10 22h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0018 8a6 6 0 00-12 0c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 018.91 14" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 2v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    award: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/>
        <path d="M15.48 12.89L17 22l-5-3-5 3 1.52-9.11" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 6v4M10 8h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    badge: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 15l-2 5-1-1-1 1 3.5-7 3.5 7-1-1-1 1-2-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <circle cx="12" cy="9" r="6" stroke="currentColor" stroke-width="1.5"/>
        <path d="M10 9l1.5 1.5L14 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    // =========================================================================
    // MISCELLANEOUS ICONS
    // =========================================================================

    eye: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    eyeOff: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M1 1l22 22" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    lock: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M7 11V7a5 5 0 0110 0v4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="16" r="1" fill="currentColor"/>
    </svg>`,

    unlock: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" stroke-width="1.5"/>
        <path d="M7 11V7a5 5 0 019.9-1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <circle cx="12" cy="16" r="1" fill="currentColor"/>
    </svg>`,

    globe: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.5"/>
        <path d="M3 12h18" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 3a15.3 15.3 0 014 9 15.3 15.3 0 01-4 9 15.3 15.3 0 01-4-9 15.3 15.3 0 014-9z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    link: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    phone: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.13.96.36 1.9.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0122 16.92z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    tag: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" stroke="currentColor" stroke-width="1.5"/>
        <circle cx="7" cy="7" r="1.5" fill="currentColor"/>
    </svg>`,

    crown: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M2 4l4 8 6-6 6 6 4-8v12a2 2 0 01-2 2H4a2 2 0 01-2-2V4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <circle cx="12" cy="6" r="1.5" fill="currentColor"/>
    </svg>`,

    gift: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="8" width="18" height="4" rx="1" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 8v13M3 12h18v8a2 2 0 01-2 2H5a2 2 0 01-2-2v-8z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 8H7.5a2.5 2.5 0 110-5C11 3 12 8 12 8z" stroke="currentColor" stroke-width="1.5"/>
        <path d="M12 8h4.5a2.5 2.5 0 100-5C13 3 12 8 12 8z" stroke="currentColor" stroke-width="1.5"/>
    </svg>`,

    // Branding
    cariara: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 2L4 6v6c0 5.55 3.84 10.74 8 12 4.16-1.26 8-6.45 8-12V6l-8-4z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        <path d="M9 12l2 2 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,

    ascend: `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 19V5m0 0l-7 7m7-7l7 7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M5 21h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`,

    // =========================================================================
    // HELPER METHODS
    // =========================================================================

    get(name, attrs = {}) {
        const icon = this[name];
        if (!icon) {
            console.warn(`Icon "${name}" not found`);
            return '';
        }

        if (Object.keys(attrs).length === 0) {
            return icon;
        }

        let svg = icon;
        for (const [key, value] of Object.entries(attrs)) {
            if (key === 'class') {
                svg = svg.replace('<svg', `<svg class="${value}"`);
            } else if (key === 'style') {
                svg = svg.replace('<svg', `<svg style="${value}"`);
            } else if (key === 'width' || key === 'height') {
                svg = svg.replace('<svg', `<svg ${key}="${value}"`);
            }
        }
        return svg;
    },

    list() {
        return Object.keys(this).filter(key =>
            typeof this[key] === 'string' && key !== 'get' && key !== 'list'
        );
    }
};

// Role icons mapping
const RoleIcons = {
    'devops': CariaraIcons.devops,
    'sre': CariaraIcons.sre,
    'cloud_architect': CariaraIcons.cloudArchitect,
    'platform': CariaraIcons.platform,
    'backend': CariaraIcons.backend,
    'fullstack': CariaraIcons.fullstack,
    'data': CariaraIcons.data,
    'ml': CariaraIcons.ml,
    'security': CariaraIcons.security,
    'frontend': CariaraIcons.frontend,
    'mobile': CariaraIcons.mobile
};

// Export for module usage
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CariaraIcons, RoleIcons };
}

// Make available globally
window.CariaraIcons = CariaraIcons;
window.RoleIcons = RoleIcons;
