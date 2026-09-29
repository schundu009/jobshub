/**
 * Subscription Gate for Cariara Jobs Portal
 *
 * Checks if the current user has an active Quarterly Pro subscription.
 * If not, redirects to the upgrade page.
 */

const CARIARA_API = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://cariara-backend.up.railway.app';

/**
 * Check if user has access to the jobs portal
 * @returns {Promise<boolean>} True if user has access, false otherwise
 */
async function checkSubscriptionAccess() {
    // Subscription gate disabled - allow all authenticated users
    // TODO: Re-enable when subscription service is properly configured
    return true;
}

/**
 * Get cached subscription status
 * @returns {Object|null} Cached status or null if expired/missing
 */
function getSubscriptionCache() {
    try {
        const cached = localStorage.getItem('subscription_status');
        if (!cached) return null;

        const data = JSON.parse(cached);
        const cacheAge = Date.now() - data.timestamp;

        // Cache valid for 5 minutes (300000ms)
        if (cacheAge > 300000) {
            localStorage.removeItem('subscription_status');
            return null;
        }

        return data;
    } catch (e) {
        return null;
    }
}

/**
 * Cache subscription status
 * @param {Object} data Subscription data from API
 */
function setSubscriptionCache(data) {
    try {
        localStorage.setItem('subscription_status', JSON.stringify({
            ...data,
            timestamp: Date.now()
        }));
    } catch (e) {
        console.error('Failed to cache subscription status:', e);
    }
}

/**
 * Clear subscription cache (call on logout or when subscription changes)
 */
function clearSubscriptionCache() {
    localStorage.removeItem('subscription_status');
}

/**
 * Show upgrade modal when user doesn't have access
 * @param {Object} data Subscription status data
 */
function showUpgradeModal(data) {
    // Remove any existing modal
    const existingModal = document.getElementById('subscription-upgrade-modal');
    if (existingModal) existingModal.remove();

    const modal = document.createElement('div');
    modal.id = 'subscription-upgrade-modal';
    modal.innerHTML = `
        <style>
            #subscription-upgrade-modal {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.85);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10000;
                backdrop-filter: blur(4px);
            }
            .upgrade-modal-content {
                background: var(--bg-secondary, #1e293b);
                border: 1px solid var(--border-color, #334155);
                border-radius: 16px;
                padding: 40px;
                max-width: 480px;
                width: 90%;
                text-align: center;
                box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
            }
            .upgrade-modal-icon {
                width: 64px;
                height: 64px;
                background: linear-gradient(135deg, #4285f4 0%, #1967d2 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
            }
            .upgrade-modal-icon svg {
                width: 32px;
                height: 32px;
                color: white;
            }
            .upgrade-modal-title {
                font-family: 'Playfair Display', Georgia, serif;
                font-size: 28px;
                font-weight: 600;
                color: var(--text-primary, #f8fafc);
                margin: 0 0 12px;
            }
            .upgrade-modal-subtitle {
                font-size: 16px;
                color: var(--text-secondary, #cbd5e1);
                margin: 0 0 24px;
                line-height: 1.6;
            }
            .upgrade-modal-features {
                background: var(--bg-tertiary, #334155);
                border-radius: 12px;
                padding: 20px;
                margin-bottom: 24px;
                text-align: left;
            }
            .upgrade-modal-feature {
                display: flex;
                align-items: center;
                gap: 12px;
                color: var(--text-secondary, #cbd5e1);
                font-size: 14px;
                margin-bottom: 12px;
            }
            .upgrade-modal-feature:last-child {
                margin-bottom: 0;
            }
            .upgrade-modal-feature svg {
                width: 20px;
                height: 20px;
                color: #4285f4;
                flex-shrink: 0;
            }
            .upgrade-modal-btn {
                display: inline-block;
                padding: 14px 32px;
                background: linear-gradient(135deg, #4285f4 0%, #1967d2 100%);
                color: white;
                font-size: 16px;
                font-weight: 600;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                text-decoration: none;
                transition: transform 0.2s, box-shadow 0.2s;
                margin-bottom: 16px;
            }
            .upgrade-modal-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(66, 133, 244, 0.4);
            }
            .upgrade-modal-secondary {
                display: block;
                color: var(--text-muted, #64748b);
                font-size: 14px;
                text-decoration: none;
                transition: color 0.2s;
            }
            .upgrade-modal-secondary:hover {
                color: var(--text-secondary, #cbd5e1);
            }
            .upgrade-modal-price {
                font-size: 14px;
                color: var(--text-muted, #64748b);
                margin-top: 8px;
            }
        </style>
        <div class="upgrade-modal-content">
            <div class="upgrade-modal-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                    <path d="M2 17l10 5 10-5"></path>
                    <path d="M2 12l10 5 10-5"></path>
                </svg>
            </div>
            <h2 class="upgrade-modal-title">Upgrade to Quarterly Pro</h2>
            <p class="upgrade-modal-subtitle">
                Get full access to the Cariara Jobs Portal with AI-powered job discovery, resume tailoring, and more.
            </p>
            <div class="upgrade-modal-features">
                <div class="upgrade-modal-feature">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>AI-powered job matching for your target roles</span>
                </div>
                <div class="upgrade-modal-feature">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>Tailored cover letters and resume optimization</span>
                </div>
                <div class="upgrade-modal-feature">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>Real-time job alerts from 100+ top companies</span>
                </div>
                <div class="upgrade-modal-feature">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    <span>Ascend Interview Prep included ($99/mo value)</span>
                </div>
            </div>
            <a href="https://capra.cariara.com" class="upgrade-modal-btn">
                Get Quarterly Pro
            </a>
            <p class="upgrade-modal-price">$300/quarter (3 months)</p>
            <a href="login.html" class="upgrade-modal-secondary" onclick="clearAuthData(); return true;">
                Sign in with a different account
            </a>
        </div>
    `;

    document.body.appendChild(modal);
}

/**
 * Redirect to login page with return URL
 */
function redirectToLogin() {
    const currentPath = window.location.pathname + window.location.search;
    window.location.href = `/login.html?redirect=${encodeURIComponent(currentPath)}`;
}

/**
 * Clear all auth data
 */
function clearAuthData() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('subscription_status');
}

// Export for use in other modules
window.SubscriptionGate = {
    checkAccess: checkSubscriptionAccess,
    clearCache: clearSubscriptionCache,
    showUpgradeModal: showUpgradeModal,
    clearAuthData: clearAuthData
};
