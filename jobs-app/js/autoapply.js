/**
 * Auto Apply page (autoapply.html).
 * Needs js/app.js (authFetch, escapeHtml, requireAuth, requireOnboarding) loaded first.
 * All data comes from /api/apply/*. Every interpolated value goes through h().
 */
(function () {
    'use strict';

    // ── Constants ──────────────────────────────────────────────────────
    const PRICING_URL = 'https://cariara.com/pricing';
    const SUPPORTED_ATS = ['greenhouse', 'lever', 'ashby'];
    const ATS_LABEL = {
        greenhouse: 'Greenhouse', lever: 'Lever', ashby: 'Ashby', workday: 'Workday',
        smartrecruiters: 'SmartRecruiters', icims: 'iCIMS', taleo: 'Taleo', jobvite: 'Jobvite',
        brassring: 'BrassRing', apple: 'Apple', manual: 'Company site',
    };
    const TABS = ['matches', 'review', 'ready', 'submitted', 'preferences', 'profile'];
    const LIST_STATUSES = {
        review: ['drafting', 'needs_input', 'ready_for_review', 'failed', 'unsupported'],
        ready: ['approved'],
        submitted: ['handed_off', 'submitted', 'confirmed'],
    };
    const STATUS_LABEL = {
        suggested: 'Suggested', drafting: 'Preparing', needs_input: 'Needs your input',
        ready_for_review: 'Ready for review', approved: 'Approved', handed_off: 'Opened',
        submitted: 'Submitted', confirmed: 'Confirmed', skipped: 'Skipped', failed: 'Couldn’t prepare',
        unsupported: 'Manual apply only', withdrawn: 'Withdrawn',
    };
    const STATUS_CHIP = {
        drafting: 'aa-chip-blue', needs_input: 'aa-chip-warn', ready_for_review: 'aa-chip-blue',
        approved: 'aa-chip-ok', handed_off: 'aa-chip-blue', submitted: 'aa-chip-ok', confirmed: 'aa-chip-ok',
        failed: 'aa-chip-bad', skipped: '', unsupported: 'aa-chip-warn', withdrawn: '',
    };
    const CATEGORY_GROUPS = [
        { title: 'About you', cats: ['identity', 'links'] },
        { title: 'Resume and cover letter', cats: ['resume', 'cover_letter'] },
        { title: 'Work eligibility and logistics', cats: ['work_auth', 'sponsorship', 'relocation', 'salary', 'start_date'] },
        { title: 'Application questions', cats: ['custom'] },
        { title: 'Attestations', cats: ['attestation'] },
    ];
    // [stored value, label]; values match the users table vocabulary (see backend/models.py).
    const EEO_OPTIONS = {
        gender: [['female', 'Female'], ['male', 'Male'], ['non_binary', 'Non-binary'], ['other', 'Another gender identity'], ['decline', 'Decline to answer']],
        race: [['american_indian', 'American Indian or Alaska Native'], ['asian', 'Asian'], ['black', 'Black or African American'],
            ['hispanic', 'Hispanic or Latino'], ['pacific_islander', 'Native Hawaiian or Other Pacific Islander'], ['white', 'White'],
            ['two_or_more', 'Two or more races'], ['decline', 'Decline to answer']],
        veteran: [['protected_veteran', 'I am a protected veteran'], ['veteran', 'I am a veteran, but not a protected veteran'],
            ['not_veteran', 'I am not a veteran'], ['decline', 'Decline to answer']],
        disability: [['yes', 'Yes, I have a disability'], ['no', 'No, I don’t have a disability'], ['decline', 'Decline to answer']],
    };
    const PROFILE_FIELD_IDS = {
        first_name: 'pf-first_name', last_name: 'pf-last_name', email: 'pf-email', phone: 'pf-phone',
        city: 'pf-city', state: 'pf-state', country: 'pf-country', linkedin: 'pf-linkedin', github: 'pf-github',
        portfolio: 'pf-portfolio', work_authorized_us: 'pf-work_authorized_us', requires_sponsorship: 'pf-requires_sponsorship',
        willing_to_relocate: 'pf-willing_to_relocate', earliest_start_date: 'pf-earliest_start_date',
        salary_expectation: 'pf-salary_expectation', notice_period: 'pf-notice_period',
    };
    const PREF_FIELDS = ['target_roles', 'locations', 'min_match_score', 'daily_cap', 'mode', 'salary_floor', 'excluded_companies', 'ats_allowlist', 'remote_ok'];

    // ── Icons (24x24, stroke 1.8) ──────────────────────────────────────
    const svg = (d, extra = '') => `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}>${d}</svg>`;
    const I = {
        check: svg('<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'),
        todo: svg('<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>'),
        alert: svg('<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17h.01"/>'),
        info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
        spark: svg('<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>'),
        inbox: svg('<path d="M4 13h4l2 3h4l2-3h4"/><path d="M5 5h14l1 8v6H4v-6z"/>'),
        external: svg('<path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>'),
        refresh: svg('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>'),
        copy: svg('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/>'),
        send: svg('<path d="M4 12 20 4l-6 16-3-7z"/><path d="m11 13 9-9"/>'),
        doc: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>'),
        puzzle: svg('<path d="M9 4h6v3a2 2 0 1 0 4 0h1v6h-3a2 2 0 1 0 0 4h3v3H4V4h3a2 2 0 1 0 4 0z"/>'),
    };

    // ── State ──────────────────────────────────────────────────────────
    const S = {
        prefs: null, profile: null, readiness: null, stats: null,
        queue: null, queueError: null,
        lists: { review: null, ready: null, submitted: null },
        listErrors: {},
        docs: null, bank: null, bankError: null,
        loaded: {}, planBlocked: false, tab: 'matches',
    };
    let D = null; // open drawer state

    // ── Helpers ────────────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const h = (v) => escapeHtml(v);
    function safeUrl(value) {
        if (!value) return null;
        try {
            const u = new URL(String(value).trim(), window.location.href);
            return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : null;
        } catch (e) { return null; }
    }
    function atsKey(v) { return String(v || '').toLowerCase().trim(); }
    function atsLabel(v) { const k = atsKey(v); return ATS_LABEL[k] || (k ? k.charAt(0).toUpperCase() + k.slice(1) : 'Unknown'); }
    function isEmpty(v) { return v == null || v === '' || (Array.isArray(v) && v.length === 0); }
    // The API sends naive ISO timestamps in UTC; without a zone JS would read them as local time.
    function parseDate(v) {
        if (!v) return new Date(NaN);
        const s = String(v);
        return new Date(/T\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(s) ? s + 'Z' : s);
    }
    function fmtDate(v, withTime) {
        if (!v) return '';
        const d = parseDate(v);
        if (isNaN(d)) return '';
        return withTime
            ? d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
            : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    function relTime(v) {
        if (!v) return '';
        const d = parseDate(v);
        if (isNaN(d)) return '';
        const mins = Math.round((Date.now() - d.getTime()) / 60000);
        if (mins < 1) return 'just now';
        if (mins < 60) return mins + ' min ago';
        const hrs = Math.round(mins / 60);
        if (hrs < 24) return hrs + (hrs === 1 ? ' hour ago' : ' hours ago');
        const days = Math.round(hrs / 24);
        if (days < 30) return days + (days === 1 ? ' day ago' : ' days ago');
        return fmtDate(v);
    }
    function userKey() {
        try { const u = JSON.parse(localStorage.getItem('user') || 'null'); return (u && (u.id || u.email)) || 'anon'; } catch (e) { return 'anon'; }
    }

    class ApiError extends Error {
        constructor(status, message, data) { super(message); this.status = status; this.data = data || {}; }
    }
    function flatten(body) {
        if (!body || typeof body !== 'object' || Array.isArray(body)) return {};
        const d = body.detail;
        if (d && typeof d === 'object' && !Array.isArray(d)) return Object.assign({}, body, d);
        return body;
    }
    function errorText(status, body) {
        const b = flatten(body);
        if (typeof b.message === 'string' && b.message) return b.message;
        if (typeof b.detail === 'string' && b.detail) return b.detail;
        if (body && Array.isArray(body.detail)) {
            return body.detail.map(it => (it && it.msg) ? ((Array.isArray(it.loc) ? it.loc.filter(p => p !== 'body').join('.') + ': ' : '') + it.msg) : String(it)).join('; ');
        }
        if (status >= 500) return 'Cariara is having trouble right now. Please try again in a moment.';
        if (status === 404) return 'Not found.';
        return 'Request failed (' + status + ').';
    }
    async function api(path, method = 'GET', body) {
        const opts = { method, headers: {} };
        if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
        let res = await authFetch('/apply' + path, opts);
        // One quiet retry for reads that hit a transient server error.
        if (method === 'GET' && res.status >= 500) {
            await new Promise(r => setTimeout(r, 700));
            res = await authFetch('/apply' + path, opts);
        }
        let data = null;
        try { const t = await res.text(); if (t) { try { data = JSON.parse(t); } catch (e) { data = t; } } } catch (e) { data = null; }
        if (!res.ok) throw new ApiError(res.status, errorText(res.status, data), flatten(data));
        return data;
    }
    function listOf(data) {
        if (Array.isArray(data)) return data;
        if (data && Array.isArray(data.items)) return data.items;
        return [];
    }

    // ── Toast and banners ──────────────────────────────────────────────
    let toastTimer = null;
    function toast(msg, { type = 'info', actionLabel, onAction, href } = {}) {
        const t = $('aa-toast');
        t.className = 'aa-toast' + (type === 'error' ? ' is-error' : '');
        t.setAttribute('role', type === 'error' ? 'alert' : 'status');
        t.innerHTML = `<span>${h(msg)}</span>` +
            (href ? `<a href="${h(href)}" target="_blank" rel="noopener noreferrer">${h(actionLabel || 'Open')}</a>` :
                actionLabel ? `<button type="button">${h(actionLabel)}</button>` : '');
        if (actionLabel && onAction && !href) t.querySelector('button').onclick = () => { t.classList.remove('show'); onAction(); };
        requestAnimationFrame(() => t.classList.add('show'));
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => t.classList.remove('show'), type === 'error' ? 7000 : 4000);
    }
    function banner(type, html, { dismiss = true } = {}) {
        const icon = type === 'error' ? I.alert : type === 'success' ? I.check : I.info;
        $('aa-banner').innerHTML = `<div class="aa-banner is-${type}" role="${type === 'error' ? 'alert' : 'status'}">${icon}<div class="aa-banner-body">${html}</div>${dismiss ? '<button type="button" class="aa-banner-close" aria-label="Dismiss">&times;</button>' : ''}</div>`;
        const c = $('aa-banner').querySelector('.aa-banner-close');
        if (c) c.onclick = () => { $('aa-banner').innerHTML = ''; };
    }
    function clearBanner() { $('aa-banner').innerHTML = ''; }

    function handleCommonError(e, fallback) {
        if (e && e.status === 402) { showUpgrade(true); toast('Auto Apply is part of Cariara Pro.', { type: 'error', actionLabel: 'See plans', href: PRICING_URL }); return; }
        if (e && e.status === 429) { showDailyLimit(e.data); return; }
        toast((e && e.message) || fallback || 'Something went wrong.', { type: 'error' });
    }
    function showDailyLimit(data) {
        const at = data && data.resets_at ? fmtDate(data.resets_at, true) : '';
        const cap = S.stats && S.stats.daily_cap;
        banner('warn', `<strong>You've reached today's limit${cap ? ' of ' + h(cap) + ' applications' : ''}.</strong> ${at ? 'It resets ' + h(at) + '.' : 'It resets tomorrow.'} You can raise your daily cap in <a href="#preferences">Preferences</a>.`);
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── Header, upgrade, checklist ─────────────────────────────────────
    function planOk() {
        if (S.planBlocked) return false;
        if (S.prefs && S.prefs.plan_ok === false) return false;
        if (S.readiness && S.readiness.plan_ok === false) return false;
        return true;
    }
    function renderHeader() {
        const p = S.prefs;
        const pill = $('aa-status-pill');
        const sw = $('aa-enable');
        if (!p) {
            $('aa-status-text').textContent = S.prefsError ? 'Unavailable' : 'Loading…';
            pill.classList.remove('is-on');
            sw.disabled = true;
        } else {
            const on = !!p.enabled;
            const modeText = p.mode === 'auto' ? 'Automatic' : 'Review first';
            $('aa-status-text').textContent = on ? 'On · ' + modeText : 'Off';
            pill.classList.toggle('is-on', on);
            sw.setAttribute('aria-checked', on ? 'true' : 'false');
            $('aa-enable-label').textContent = on ? 'On' : 'Turn on';
            sw.setAttribute('aria-label', 'Auto Apply ' + (on ? 'on' : 'off'));
            sw.disabled = false;
        }
        const st = S.stats;
        if (st && Number(st.daily_cap) > 0) {
            $('aa-today').innerHTML = `<strong>${h(st.today_count ?? 0)}</strong> of ${h(st.daily_cap)} today`;
        } else {
            $('aa-today').textContent = '';
        }
    }
    function showUpgrade(force) {
        if (force) S.planBlocked = true;
        const el = $('aa-upgrade');
        if (planOk()) { el.innerHTML = ''; return; }
        el.innerHTML = `<section class="aa-card aa-upgrade" aria-labelledby="aa-up-title">
            <div style="flex:1 1 320px;min-width:0">
                <h2 id="aa-up-title">Auto Apply is part of Cariara Pro</h2>
                <p>You can browse your matches for free. Upgrade to have Cariara prepare applications, draft answers and track every submission.</p>
            </div>
            <a class="btn btn-primary" href="${PRICING_URL}" target="_blank" rel="noopener noreferrer">See plans</a>
        </section>`;
    }
    function missingTarget(field) {
        const f = String(field || '');
        const root = f.split('.')[0];
        if (PREF_FIELDS.includes(root)) return '#preferences';
        if (root === 'resume' || root === 'resume_doc_id' || root === 'resume_ok') return 'documents.html';
        return '#profile?field=' + encodeURIComponent(f.split('.').pop());
    }
    function renderChecklist() {
        const el = $('aa-checklist');
        const r = S.readiness;
        if (!r || r.ready) { el.innerHTML = ''; return; }
        const items = [];
        items.push({ done: r.plan_ok !== false, label: 'Cariara Pro plan', href: PRICING_URL, ext: true, cta: 'See plans' });
        items.push({ done: !!r.resume_ok, label: 'Upload a resume', href: 'documents.html', cta: 'Open Resumes' });
        listOf(r.missing).forEach(m => {
            const f = m && typeof m === 'object' ? m.field : m;
            const label = m && typeof m === 'object' ? (m.label || m.field) : m;
            if (f === 'resume' || f === 'plan') return;
            items.push({ done: false, label: 'Add ' + String(label || '').replace(/^./, c => c.toLowerCase()), href: missingTarget(f), cta: 'Add' });
        });
        const done = items.filter(i => i.done).length;
        el.innerHTML = `<section class="aa-card aa-checklist" aria-labelledby="aa-cl-title">
            <div class="aa-checklist-head"><h2 id="aa-cl-title">Finish setting up Auto Apply</h2><span class="aa-progress">${done} of ${items.length} done</span></div>
            <p>Cariara needs these before it can prepare applications for you.</p>
            <ul>${items.map(i => `<li class="${i.done ? 'done' : 'todo'}">${i.done ? I.check : I.todo}
                <span style="flex:1;min-width:0">${h(i.label)}${i.done ? '<span class="sr-only"> (done)</span>' : ''}</span>
                ${i.done ? '' : `<a class="aa-text-btn" href="${h(i.href)}"${i.ext ? ' target="_blank" rel="noopener noreferrer"' : ''}>${h(i.cta)}</a>`}</li>`).join('')}</ul>
        </section>`;
    }
    function renderCounts() {
        const by = (S.stats && S.stats.by_status) || null;
        const sum = (keys) => keys.reduce((n, k) => n + (Number(by && by[k]) || 0), 0);
        ['review', 'ready', 'submitted'].forEach(tab => {
            const el = $('count-' + tab);
            const list = S.lists[tab];
            const n = list ? (list.total ?? list.items.length) : (by ? sum(LIST_STATUSES[tab]) : null);
            el.hidden = !n;
            el.textContent = n || '';
            el.setAttribute('aria-label', (n || 0) + ' items');
        });
        const m = $('count-matches');
        const q = S.queue ? visibleQueue().length : 0;
        m.hidden = !q; m.textContent = q || '';
    }

    async function loadCore() {
        const [prefs, readiness, stats, profile] = await Promise.allSettled([api('/preferences'), api('/readiness'), api('/stats'), S.profile ? Promise.resolve(S.profile) : api('/profile')]);
        if (profile.status === 'fulfilled' && profile.value) S.profile = S.profile || profile.value;
        if (prefs.status === 'fulfilled') { S.prefs = prefs.value || {}; S.prefsError = null; }
        else {
            S.prefsError = prefs.reason;
            if (prefs.reason && prefs.reason.status === 402) S.planBlocked = true;
            else banner('error', `We couldn't load your Auto Apply settings. ${h(prefs.reason && prefs.reason.message || '')} <button type="button" class="aa-text-btn" id="aa-retry-core">Try again</button>`, { dismiss: false });
            const rb = $('aa-retry-core');
            if (rb) rb.onclick = () => { clearBanner(); loadCore(); };
        }
        if (readiness.status === 'fulfilled') S.readiness = readiness.value;
        if (stats.status === 'fulfilled') S.stats = stats.value;
        renderHeader(); showUpgrade(); renderChecklist(); renderCounts();
    }
    async function refreshStats() {
        try { S.stats = await api('/stats'); } catch (e) { /* keep last */ }
        renderHeader(); renderCounts();
    }
    async function refreshReadiness() {
        try { S.readiness = await api('/readiness'); } catch (e) { /* keep last */ }
        showUpgrade(); renderChecklist();
    }

    async function toggleEnabled() {
        if (!S.prefs) return;
        const sw = $('aa-enable');
        const next = !S.prefs.enabled;
        sw.disabled = true;
        try {
            S.prefs = await api('/preferences', 'PUT', prefsPayload(Object.assign({}, S.prefs, { enabled: next }))) || Object.assign({}, S.prefs, { enabled: next });
            toast(next ? (S.prefs.mode === 'auto' ? 'Auto Apply is on. Matches above your score are prepared and approved automatically.' : 'Auto Apply is on. We’ll prepare applications for you to review.') : 'Auto Apply is off.');
            refreshReadiness(); refreshStats();
            if (S.loaded.preferences) renderPreferences();
        } catch (e) {
            if (e.status === 402) {
                showUpgrade(true);
                toast('Turning on Auto Apply needs Cariara Pro.', { type: 'error', actionLabel: 'See plans', href: PRICING_URL });
                $('aa-upgrade').scrollIntoView({ behavior: 'smooth', block: 'center' });
            } else handleCommonError(e, 'Could not update Auto Apply.');
        } finally {
            renderHeader();
        }
    }

    // ── Routing / tabs ─────────────────────────────────────────────────
    function parseHash() {
        const raw = (window.location.hash || '').replace(/^#/, '');
        const [tabPart, query] = raw.split('?');
        const tab = TABS.includes(tabPart) ? tabPart : 'matches';
        return { tab, params: new URLSearchParams(query || '') };
    }
    function setHash(tab, params) {
        const q = params && String(params) ? '?' + params : '';
        const url = window.location.pathname + window.location.search + '#' + tab + q;
        history.replaceState(null, '', url);
    }
    function selectTab(tab, { focus = false } = {}) {
        S.tab = tab;
        document.querySelectorAll('#aa-tabs .tab-btn').forEach(b => {
            const on = b.dataset.tab === tab;
            b.classList.toggle('active', on);
            b.setAttribute('aria-selected', on ? 'true' : 'false');
            b.tabIndex = on ? 0 : -1;
            if (on && focus) b.focus();
        });
        TABS.forEach(t => { $('panel-' + t).hidden = t !== tab; });
        loadTab(tab);
    }
    function route() {
        const { tab, params } = parseHash();
        if (tab !== S.tab || !S.loaded[tab]) selectTab(tab);
        const appId = params.get('app');
        if (appId && (!D || String(D.id) !== appId)) openDrawer(appId, { fromRoute: true });
        if (!appId && D) closeDrawer({ fromRoute: true });
        const field = params.get('field');
        if (tab === 'profile' && field) focusProfileField(field);
    }
    function bindTabs() {
        const bar = $('aa-tabs');
        bar.addEventListener('click', (e) => {
            const b = e.target.closest('.tab-btn');
            if (!b) return;
            setHash(b.dataset.tab);
            selectTab(b.dataset.tab);
        });
        bar.addEventListener('keydown', (e) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
            e.preventDefault();
            let i = TABS.indexOf(S.tab);
            if (e.key === 'ArrowRight') i = (i + 1) % TABS.length;
            if (e.key === 'ArrowLeft') i = (i - 1 + TABS.length) % TABS.length;
            if (e.key === 'Home') i = 0;
            if (e.key === 'End') i = TABS.length - 1;
            setHash(TABS[i]);
            selectTab(TABS[i], { focus: true });
        });
        window.addEventListener('hashchange', route);
    }
    function loadTab(tab) {
        if (tab === 'matches') { if (!S.loaded.matches) loadQueue(); else renderMatches(); }
        else if (tab === 'review' || tab === 'ready' || tab === 'submitted') { if (!S.loaded[tab]) loadList(tab); else renderList(tab); }
        else if (tab === 'preferences') loadPreferences();
        else if (tab === 'profile') loadProfile();
    }

    function skeleton(n = 3) { return `<div class="aa-list" aria-busy="true" aria-label="Loading">${'<div class="aa-skel"></div>'.repeat(n)}</div>`; }
    function emptyState(icon, title, text, actionHtml = '') {
        return `<div class="aa-empty">${icon}<h3>${h(title)}</h3><p>${text}</p>${actionHtml}</div>`;
    }
    function errorState(panel, message, retry) {
        panel.innerHTML = `<div class="aa-banner is-error" role="alert">${I.alert}<div class="aa-banner-body">${h(message)}</div><button type="button" class="btn btn-secondary aa-sm" data-retry>Try again</button></div>`;
        panel.querySelector('[data-retry]').onclick = retry;
    }
    function ring(score) {
        const s = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
        const c = 2 * Math.PI * 21;
        const cls = s >= 80 ? 'hi' : s < 60 ? 'lo' : '';
        return `<div class="aa-ring ${cls}" role="img" aria-label="Match ${s}%"><svg viewBox="0 0 52 52"><circle class="track" cx="26" cy="26" r="21" fill="none" stroke-width="5"/><circle class="bar" cx="26" cy="26" r="21" fill="none" stroke-width="5" stroke-linecap="round" stroke-dasharray="${c.toFixed(2)}" stroke-dashoffset="${(c * (1 - s / 100)).toFixed(2)}"/></svg><span aria-hidden="true">${s}</span></div>`;
    }

    // ── Matches ────────────────────────────────────────────────────────
    function hiddenKey() { return 'cariara_aa_skipped:' + userKey(); }
    function hiddenIds() { try { return new Set(JSON.parse(localStorage.getItem(hiddenKey()) || '[]').map(String)); } catch (e) { return new Set(); } }
    function hideJob(id) {
        const set = hiddenIds(); set.add(String(id));
        try { localStorage.setItem(hiddenKey(), JSON.stringify([...set].slice(-500))); } catch (e) { /* storage off */ }
    }
    function unhideJob(id) {
        const set = hiddenIds(); set.delete(String(id));
        try { localStorage.setItem(hiddenKey(), JSON.stringify([...set])); } catch (e) { /* storage off */ }
    }
    function visibleQueue() {
        const hidden = hiddenIds();
        return listOf(S.queue).filter(it => it && it.job && !hidden.has(String(it.job.id)));
    }
    async function loadQueue() {
        const panel = $('panel-matches');
        S.loaded.matches = true;
        if (!S.queue) panel.innerHTML = skeleton(4);
        try {
            S.queue = await api('/queue?limit=50');
            S.queueError = null;
        } catch (e) {
            S.queueError = e;
            if (e.status === 402) showUpgrade(true);
        }
        renderMatches(); renderCounts();
    }
    function renderMatches() {
        const panel = $('panel-matches');
        if (S.queueError && !S.queue) { errorState(panel, 'We couldn’t load your matches. ' + S.queueError.message, loadQueue); return; }
        if (!S.queue) { panel.innerHTML = skeleton(4); return; }
        const items = visibleQueue();
        const gen = S.queue.generated_at ? 'Updated ' + relTime(S.queue.generated_at) : '';
        const minScore = S.prefs && S.prefs.min_match_score != null ? S.prefs.min_match_score : null;
        let html = `<div class="aa-toolbar"><p>${items.length ? `${items.length} ${items.length === 1 ? 'job matches' : 'jobs match'} your preferences${minScore != null ? ' (score ' + h(minScore) + '+)' : ''}.` : 'Jobs that fit your preferences show up here.'} <span class="aa-meta">${h(gen)}</span></p>
            <button type="button" class="btn btn-secondary aa-sm" id="aa-refresh-queue">${I.refresh}Refresh matches</button></div>`;
        if (!items.length) {
            html += emptyState(I.inbox, 'No matches right now',
                'Try widening your target roles or locations, or lowering the minimum match score in <a href="#preferences">Preferences</a>.',
                hiddenIds().size ? '<button type="button" class="aa-text-btn" id="aa-unskip-all">Show skipped jobs</button>' : '');
        } else {
            html += '<div class="aa-list">' + items.map(matchCard).join('') + '</div>';
        }
        panel.innerHTML = html;
        $('aa-refresh-queue').onclick = refreshQueue;
        const un = $('aa-unskip-all');
        if (un) un.onclick = () => { try { localStorage.removeItem(hiddenKey()); } catch (e) { /* noop */ } renderMatches(); renderCounts(); };
        panel.querySelectorAll('[data-prepare]').forEach(b => { b.onclick = () => prepareApp(b.dataset.prepare, b); });
        panel.querySelectorAll('[data-skip]').forEach(b => {
            b.onclick = () => {
                const id = b.dataset.skip;
                hideJob(id); renderMatches(); renderCounts();
                toast('Job skipped.', { actionLabel: 'Undo', onAction: () => { unhideJob(id); renderMatches(); renderCounts(); } });
            };
        });
    }
    function matchCard(it) {
        const j = it.job || {};
        const ats = atsKey(j.ats || j.source);
        const supported = SUPPORTED_ATS.includes(ats);
        const url = safeUrl(j.job_url);
        const sub = [j.company_name, j.location].filter(Boolean).join(' · ');
        const reasons = listOf(it.reasons).slice(0, 5);
        const posted = j.posted_date ? 'Posted ' + relTime(j.posted_date) : '';
        return `<article class="aa-item">
            ${ring(it.match_score)}
            <div class="aa-item-main">
                <h3 class="aa-item-title"><a href="job_detail.html?id=${encodeURIComponent(j.id)}">${h(j.title || 'Untitled role')}</a></h3>
                <p class="aa-item-sub">${h(sub)}${posted ? ` <span class="aa-meta">· ${h(posted)}</span>` : ''}</p>
                <div class="aa-chips">
                    <span class="chip aa-chip-ats">${h(atsLabel(ats))}</span>
                    ${reasons.map(r => typeof r === 'string' ? r : (r && (r.label || r.text || r.reason)) || '').filter(Boolean).map(r => `<span class="chip aa-chip-reason">${h(r)}</span>`).join('')}
                </div>
            </div>
            <div class="aa-item-actions">
                ${supported
                    ? `<button type="button" class="btn btn-primary aa-sm" data-prepare="${h(j.id)}">Prepare application</button>`
                    : (url ? `<a class="btn btn-secondary aa-sm" href="${h(url)}" target="_blank" rel="noopener noreferrer" title="Auto Apply doesn't support ${h(atsLabel(ats))} yet">Manual apply ${I.external}</a>` : `<span class="aa-meta">Manual apply only</span>`)}
                <button type="button" class="aa-text-btn" data-skip="${h(j.id)}" aria-label="Skip ${h(j.title || 'this job')}">Skip</button>
            </div>
        </article>`;
    }
    async function refreshQueue() {
        const b = $('aa-refresh-queue');
        if (b) { b.disabled = true; b.lastChild.textContent = 'Refreshing…'; }
        try {
            const r = await api('/queue/refresh', 'POST');
            const status = r && r.status;
            if (status && /queued|running|pending|started/i.test(status)) {
                toast('Looking for new matches…');
                for (let i = 0; i < 5; i++) {
                    await new Promise(res => setTimeout(res, 3000));
                    await loadQueue();
                    if (S.queue && S.queue.generated_at && (Date.now() - parseDate(S.queue.generated_at).getTime()) < 60000) break;
                }
            } else {
                await loadQueue();
                toast('Matches refreshed.');
            }
        } catch (e) {
            handleCommonError(e, 'Could not refresh matches.');
            renderMatches();
        }
    }
    async function prepareApp(jobId, btn) {
        if (btn) { btn.disabled = true; btn.textContent = 'Preparing…'; }
        try {
            const app = await api('/applications', 'POST', { job_id: Number(jobId) });
            invalidateLists();
            refreshStats();
            if (S.queue) { S.queue.items = listOf(S.queue).filter(it => String(it.job && it.job.id) !== String(jobId)); renderMatches(); renderCounts(); }
            toast('Application started. Review the answers before approving.');
            goToApp('review', app && app.id, app);
        } catch (e) {
            if (e.status === 409 && e.data && e.data.id != null) {
                toast('You already have an application for this job.');
                goToApp('review', e.data.id);
            } else handleCommonError(e, 'Could not prepare this application.');
            if (btn && btn.isConnected) { btn.disabled = false; btn.textContent = 'Prepare application'; }
        }
    }
    function goToApp(tab, id, preloaded) {
        if (id == null) { setHash(tab); selectTab(tab); return; }
        setHash(tab, new URLSearchParams({ app: id }));
        if (S.tab !== tab) selectTab(tab);
        openDrawer(id, { preloaded });
    }

    // ── Application lists ──────────────────────────────────────────────
    function invalidateLists() { ['review', 'ready', 'submitted'].forEach(t => { S.loaded[t] = false; }); }
    async function loadList(tab) {
        const panel = $('panel-' + tab);
        S.loaded[tab] = true;
        if (!S.lists[tab]) panel.innerHTML = skeleton(3);
        try {
            const data = await api('/applications?status=' + encodeURIComponent(LIST_STATUSES[tab].join(',')) + '&limit=50&offset=0');
            S.lists[tab] = { items: listOf(data), total: data && data.total != null ? data.total : listOf(data).length };
            S.listErrors[tab] = null;
        } catch (e) {
            S.listErrors[tab] = e;
            if (e.status === 402) showUpgrade(true);
        }
        if (S.tab === tab) renderList(tab);
        renderCounts();
        if (tab === 'review' && S.lists.review && S.lists.review.items.some(a => a.status === 'drafting')) scheduleListPoll();
    }
    let listPollTimer = null;
    function scheduleListPoll() {
        clearTimeout(listPollTimer);
        listPollTimer = setTimeout(() => { if (S.tab === 'review' && !D) loadList('review'); }, 5000);
    }
    function refreshLists() { invalidateLists(); loadList(S.tab === 'ready' || S.tab === 'submitted' ? S.tab : 'review'); ['review', 'ready', 'submitted'].filter(t => t !== S.tab).forEach(t => loadList(t)); refreshStats(); }

    function appSub(a) { const j = a.job || {}; return [j.company_name, j.location].filter(Boolean).join(' · '); }
    function statusChip(s) { return `<span class="chip ${STATUS_CHIP[s] || ''}">${h(STATUS_LABEL[s] || s || 'Unknown')}</span>`; }
    function renderList(tab) {
        const panel = $('panel-' + tab);
        const list = S.lists[tab];
        if (S.listErrors[tab] && !list) {
            if (S.listErrors[tab].status === 402) {
                panel.innerHTML = emptyState(I.spark, 'Upgrade to prepare applications', 'Auto Apply is part of Cariara Pro. Your matches stay free to browse.', `<a class="btn btn-primary" href="${PRICING_URL}" target="_blank" rel="noopener noreferrer">See plans</a>`);
                return;
            }
            errorState(panel, 'We couldn’t load your applications. ' + S.listErrors[tab].message, () => loadList(tab));
            return;
        }
        if (!list) { panel.innerHTML = skeleton(3); return; }
        const items = list.items;
        let intro = '';
        if (tab === 'review') intro = 'Check each answer, fix anything that needs you, then approve.';
        if (tab === 'ready') intro = 'Approved applications. Open each one, paste your answers and submit it on the company’s site.';
        if (tab === 'submitted') intro = 'Applications you’ve sent. Open one to see its history.';
        let html = `<div class="aa-toolbar"><p>${h(intro)}</p></div>`;
        if (tab === 'ready') html += `<div class="aa-note" style="margin:0 0 12px">${I.puzzle}<span>The Cariara browser extension (coming soon) will do this automatically.</span></div>`;
        if (!items.length) {
            const empties = {
                review: ['Nothing to review', 'When you prepare an application from <a href="#matches">Matches</a>, it shows up here for you to check.'],
                ready: ['Nothing waiting to submit', 'Approved applications appear here, ready to open and send.'],
                submitted: ['No submissions yet', 'After you submit an application, you can follow it here.'],
            };
            html += emptyState(I.inbox, empties[tab][0], empties[tab][1]);
        } else {
            html += '<div class="aa-list">' + items.map(a => appCard(tab, a)).join('') + '</div>';
            if (list.total > items.length) html += `<p class="aa-meta" style="margin-top:8px">Showing ${items.length} of ${h(list.total)}.</p>`;
        }
        panel.innerHTML = html;
        panel.querySelectorAll('article[data-open]').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('a,button:not([data-open])')) return;
                goToApp(tab, el.dataset.open);
            });
        });
        panel.querySelectorAll('[data-handoff]').forEach(b => { b.onclick = (e) => { e.stopPropagation(); goToApp(tab, b.dataset.handoff); startHandoff(b.dataset.handoff); }; });
    }
    function appCard(tab, a) {
        const j = a.job || {};
        const needs = Number(a.needs_user_count) || 0;
        const chips = [statusChip(a.status), `<span class="chip aa-chip-ats">${h(atsLabel(a.ats))}</span>`];
        if (tab === 'review' && needs) chips.push(`<span class="chip aa-chip-warn">${needs} ${needs === 1 ? 'answer needs' : 'answers need'} you</span>`);
        const updated = a.updated_at ? 'Updated ' + relTime(a.updated_at) : '';
        let actions = '';
        if (tab === 'review') actions = `<button type="button" class="btn ${a.status === 'drafting' ? 'btn-secondary' : 'btn-primary'} aa-sm" data-open="${h(a.id)}">${a.status === 'drafting' ? 'View' : 'Review'}</button>`;
        if (tab === 'ready') actions = `<button type="button" class="btn btn-primary aa-sm" data-handoff="${h(a.id)}">${I.external}Open application</button>`;
        if (tab === 'submitted') actions = a.status === 'handed_off'
            ? `<button type="button" class="btn btn-primary aa-sm" data-open="${h(a.id)}">Mark as submitted</button>`
            : `<button type="button" class="btn btn-secondary aa-sm" data-open="${h(a.id)}">Details</button>`;
        return `<article class="aa-item is-click" data-open="${h(a.id)}">
            ${a.match_score != null ? ring(a.match_score) : ''}
            <div class="aa-item-main">
                <h3 class="aa-item-title">${h(j.title || 'Untitled role')}</h3>
                <p class="aa-item-sub">${h(appSub(a))} ${updated ? `<span class="aa-meta">· ${h(updated)}</span>` : ''}</p>
                <div class="aa-chips">${chips.join('')}</div>
                ${tab === 'submitted' ? stepper(a.status) : ''}
            </div>
            <div class="aa-item-actions">${actions}</div>
        </article>`;
    }
    function stepper(status) {
        const steps = ['Prepared', 'Approved', 'Opened', 'Submitted', 'Confirmed'];
        const idx = { handed_off: 2, submitted: 3, confirmed: 4 }[status] ?? 1;
        return `<ol class="aa-steps" aria-label="Progress">${steps.map((s, i) => `<li class="${i < idx ? 'done' : i === idx ? 'cur' : ''}"${i === idx ? ' aria-current="step"' : ''}><span class="b" aria-hidden="true"></span>${h(s)}</li>`).join('')}</ol>`;
    }

    // ── Drawer ─────────────────────────────────────────────────────────
    let lastFocus = null;
    let drawerPoll = null;
    function showDrawerShell() {
        const dr = $('aa-drawer'); const sc = $('aa-scrim');
        if (dr.hidden) {
            lastFocus = document.activeElement;
            dr.hidden = false; sc.hidden = false;
            document.body.style.overflow = 'hidden';
            requestAnimationFrame(() => { dr.classList.add('show'); sc.classList.add('show'); });
        }
    }
    async function openDrawer(id, { preloaded, fromRoute } = {}) {
        clearTimeout(drawerPoll);
        D = { id: String(id), app: null, local: {}, dirty: new Set(), confirmed: new Set(), auto: new Set(), missing: new Set(), missingMsg: '', cover: null, resume: null, handoff: null, busy: false };
        showDrawerShell();
        $('aa-drawer-title').textContent = 'Loading application…';
        $('aa-drawer-sub').textContent = '';
        $('aa-drawer-body').innerHTML = skeleton(4);
        $('aa-drawer-foot').hidden = true;
        $('aa-drawer-title').focus();
        try {
            const app = (preloaded && preloaded.questions) ? preloaded : await api('/applications/' + encodeURIComponent(id));
            if (!D || D.id !== String(id)) return;
            setApp(app);
            if (!S.docs) loadDocs();
        } catch (e) {
            if (!D || D.id !== String(id)) return;
            $('aa-drawer-title').textContent = 'Application';
            $('aa-drawer-body').innerHTML = `<div class="aa-banner is-error" role="alert">${I.alert}<div class="aa-banner-body">${h(e.status === 404 ? 'This application no longer exists.' : 'We couldn’t load this application. ' + e.message)}</div></div>`;
            if (e.status !== 404) {
                $('aa-drawer-foot').hidden = false;
                $('aa-drawer-foot').innerHTML = '<button type="button" class="btn btn-secondary" id="aa-d-retry">Try again</button>';
                $('aa-d-retry').onclick = () => openDrawer(id);
            }
        }
    }
    function closeDrawer({ fromRoute } = {}) {
        clearTimeout(drawerPoll);
        if (D && D.dirty.size && !fromRoute) {
            if (!window.confirm('Discard your unsaved answers?')) return;
        }
        D = null;
        const dr = $('aa-drawer'); const sc = $('aa-scrim');
        dr.classList.remove('show'); sc.classList.remove('show');
        document.body.style.overflow = '';
        setTimeout(() => { if (!D) { dr.hidden = true; sc.hidden = true; } }, 220);
        if (!fromRoute) setHash(S.tab);
        if (lastFocus && lastFocus.isConnected) lastFocus.focus();
        if (!S.loaded[S.tab]) loadTab(S.tab);
    }
    function trapFocus(e) {
        if (!D || e.key !== 'Tab') return;
        const f = [...$('aa-drawer').querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),summary,[tabindex="0"]')].filter(el => el.offsetParent !== null);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }

    function setApp(app) {
        D.app = app;
        D.local = {}; D.dirty = new Set(); D.confirmed = new Set(); D.auto = new Set();
        D.cover = app.cover_letter_text || '';
        D.resume = app.resume_doc_id ?? null;
        const j = app.job || {};
        $('aa-drawer-title').textContent = j.title || 'Application';
        $('aa-drawer-sub').textContent = [j.company_name, j.location, atsLabel(app.ats)].filter(Boolean).join(' · ');
        // Default EEO answers to "Decline" when the customer hasn't opted in.
        const optIn = !!(S.profile && S.profile.eeo && S.profile.eeo.opt_in);
        listOf(app.questions).forEach(q => {
            if (q.category === 'eeo' && isEmpty(q.answer) && !optIn) {
                const dec = listOf(q.options).find(o => /decline|don.?t wish|prefer not|not to (say|answer|disclose)/i.test(optLabel(o)));
                if (dec != null) { D.local[q.id] = optValue(dec); D.auto.add(q.id); }
            }
        });
        renderDrawer();
        if (app.status === 'drafting') drawerPoll = setTimeout(() => pollDrawer(app.id), 3000);
    }
    async function pollDrawer(id) {
        if (!D || D.id !== String(id)) return;
        try {
            const app = await api('/applications/' + encodeURIComponent(id));
            if (!D || D.id !== String(id)) return;
            if (app.status !== 'drafting') { setApp(app); invalidateLists(); loadList('review'); return; }
        } catch (e) { /* keep polling */ }
        drawerPoll = setTimeout(() => pollDrawer(id), 4000);
    }

    function optLabel(o) { return o && typeof o === 'object' ? String(o.label ?? o.value ?? '') : String(o ?? ''); }
    function optValue(o) { return o && typeof o === 'object' ? (o.value ?? o.label) : o; }
    function currentValue(q) { return Object.prototype.hasOwnProperty.call(D.local, q.id) ? D.local[q.id] : q.answer; }
    // Attestations count only when the customer answered them here (never from profile/AI).
    function attestTicked(q) {
        if (Object.prototype.hasOwnProperty.call(D.local, q.id)) return !isEmpty(D.local[q.id]) && D.local[q.id] !== false;
        return q.source === 'user' && !isEmpty(q.answer) && q.answer !== false;
    }
    function aiUnconfirmed(q) { return q.source === 'ai_draft' && !q.confirmed && !D.confirmed.has(q.id) && !D.dirty.has(q.id); }
    function isFileQ(q) { return q.type === 'file' || q.category === 'resume' || (q.category === 'cover_letter' && q.type === 'file'); }
    function blockers() {
        const out = { needs: [], ai: [], attest: [] };
        listOf(D.app && D.app.questions).forEach(q => {
            if (q.category === 'attestation') { if (q.required !== false && !attestTicked(q)) out.attest.push(q); return; }
            if (isFileQ(q)) {
                if (q.required && q.category === 'resume' && D.resume == null) out.needs.push(q);
                return;
            }
            const v = currentValue(q);
            if ((q.needs_user || q.required) && isEmpty(v)) out.needs.push(q);
            else if (aiUnconfirmed(q)) out.ai.push(q);
        });
        return out;
    }

    function sourceBadge(q) {
        if (D.dirty.has(q.id) && q.category !== 'eeo') return '<span class="aa-badge src-user">You</span>';
        switch (q.source) {
            case 'profile': return '<span class="aa-badge src-profile">Profile</span>';
            case 'bank': return '<span class="aa-badge src-bank">Saved answer</span>';
            case 'ai_draft': return (q.confirmed || D.confirmed.has(q.id)) ? '<span class="aa-badge src-user">AI draft · reviewed</span>' : '<span class="aa-badge src-ai">AI draft — needs your review</span>';
            case 'user': return '<span class="aa-badge src-user">You</span>';
            default: return '';
        }
    }
    function qInput(q, inputId) {
        const v = currentValue(q);
        const ro = !editable() ? ' disabled' : '';
        const req = q.required ? ' aria-required="true"' : '';
        const opts = listOf(q.options);
        switch (q.type) {
            case 'textarea':
                return `<textarea class="form-control" id="${inputId}" data-q="${h(q.id)}" rows="${String(v || '').length > 280 ? 7 : 4}"${req}${ro}>${h(v ?? '')}</textarea>`;
            case 'select': {
                const has = opts.some(o => String(optValue(o)) === String(v ?? ''));
                return `<select class="form-control" id="${inputId}" data-q="${h(q.id)}"${req}${ro}>
                    <option value="">Select…</option>
                    ${!has && !isEmpty(v) ? `<option value="${h(v)}" selected>${h(v)}</option>` : ''}
                    ${opts.map(o => `<option value="${h(optValue(o))}"${String(optValue(o)) === String(v ?? '') ? ' selected' : ''}>${h(optLabel(o))}</option>`).join('')}
                </select>`;
            }
            case 'multiselect': {
                const set = new Set((Array.isArray(v) ? v : (isEmpty(v) ? [] : String(v).split(/\s*[,;]\s*/))).map(String));
                return `<div class="aa-checks" role="group" id="${inputId}" aria-labelledby="${inputId}-l">${opts.map((o, i) => `<label class="aa-check"><input type="checkbox" data-q="${h(q.id)}" data-multi value="${h(optValue(o))}"${set.has(String(optValue(o))) ? ' checked' : ''}${ro}> ${h(optLabel(o))}</label>`).join('')}</div>`;
            }
            case 'boolean': {
                if (opts.length) return qInput(Object.assign({}, q, { type: 'select' }), inputId);
                const val = v === true || v === 'true' || v === 'yes' ? 'true' : (v === false || v === 'false' || v === 'no') ? 'false' : '';
                return `<select class="form-control" id="${inputId}" data-q="${h(q.id)}" data-bool${req}${ro}>
                    <option value="">Select…</option><option value="true"${val === 'true' ? ' selected' : ''}>Yes</option><option value="false"${val === 'false' ? ' selected' : ''}>No</option></select>`;
            }
            case 'date':
                return `<input type="date" class="form-control" id="${inputId}" data-q="${h(q.id)}" value="${h(String(v ?? '').slice(0, 10))}"${req}${ro}>`;
            case 'number':
                return `<input type="number" class="form-control" id="${inputId}" data-q="${h(q.id)}" value="${h(v ?? '')}"${req}${ro}>`;
            default:
                return `<input type="text" class="form-control" id="${inputId}" data-q="${h(q.id)}" value="${h(v ?? '')}"${req}${ro}>`;
        }
    }
    // Mirrors the API's editable statuses for the review form (approved/handed_off are shown read-only here).
    function editable() { return D && D.app && ['needs_input', 'ready_for_review'].includes(D.app.status); }
    function renderQuestion(q) {
        const inputId = 'q-' + String(q.id).replace(/[^\w-]/g, '_');
        const v = currentValue(q);
        const needs = (q.needs_user || q.required) && isEmpty(v);
        const cls = ['aa-q'];
        if (needs && (q.needs_user || D.missing.has(String(q.id)))) cls.push('is-needs');
        if (D.missing.has(String(q.id))) cls.push('is-missing');
        const reqMark = q.required ? '<span class="aa-req" aria-hidden="true">*</span><span class="sr-only"> (required)</span>' : '';
        if (q.category === 'attestation') {
            const ticked = attestTicked(q);
            const opts = listOf(q.options);
            const dis = editable() ? '' : ' disabled';
            const desc = q.description ? `<p class="aa-help aa-attest-desc">${h(q.description)}</p>` : '';
            const cur = ticked ? currentValue(q) : null;
            let control;
            if (opts.length > 1) {
                // Several choices (e.g. "Yes, I consent" / "No, I do not consent"): explicit radio choice, nothing preselected.
                control = `<fieldset class="aa-attest-set"><legend class="aa-q-label">${h(q.label)}${reqMark}</legend>${desc}
                    ${opts.map((o, i) => `<label class="aa-attest"><input type="radio" name="${inputId}" id="${inputId}-${i}" data-q="${h(q.id)}" data-attest-opt value="${h(optValue(o))}"${ticked && String(cur) === String(optValue(o)) ? ' checked' : ''}${dis}><span>${h(optLabel(o))}</span></label>`).join('')}
                </fieldset>`;
            } else {
                // One statement to agree to: a checkbox with the statement's own words.
                const agree = opts.length === 1 ? optValue(opts[0]) : '';
                const words = opts.length === 1 && optLabel(opts[0]) !== q.label ? `<span class="aa-attest-opt">${h(optLabel(opts[0]))}</span>` : '';
                control = `<label class="aa-attest"><input type="checkbox" id="${inputId}" data-q="${h(q.id)}" data-attest data-agree="${h(agree)}"${ticked ? ' checked' : ''}${dis}>
                    <span>${h(q.label)}${reqMark}${words ? '<br>' + words : ''}</span></label>${desc ? desc.replace('aa-attest-desc', 'aa-attest-desc is-indented') : ''}`;
            }
            return `<div class="${cls.join(' ')}${!ticked && q.required !== false ? ' is-needs' : ''}" id="wrap-${inputId}" data-qwrap="${h(q.id)}">
                ${control}
                ${!ticked && editable() ? '<div class="aa-q-foot"><span class="aa-q-needs">' + I.alert + 'Please read and answer this yourself. Cariara never agrees on your behalf.</span></div>' : ''}
            </div>`;
        }
        if (isFileQ(q)) {
            const what = q.category === 'cover_letter' ? 'Uses the cover letter below.' : 'Uses the resume you pick below.';
            return `<div class="${cls.join(' ')}" id="wrap-${inputId}" data-qwrap="${h(q.id)}"><div class="aa-q-head"><span class="aa-q-label">${h(q.label)}${reqMark}</span></div><p class="aa-help">${what}</p></div>`;
        }
        const labelTag = q.type === 'multiselect' ? `<span class="aa-q-label" id="${inputId}-l">` : `<label for="${inputId}">`;
        const labelEnd = q.type === 'multiselect' ? '</span>' : '</label>';
        const unconf = aiUnconfirmed(q) && !isEmpty(v);
        return `<div class="${cls.join(' ')}" id="wrap-${inputId}" data-qwrap="${h(q.id)}">
            <div class="aa-q-head">${labelTag}${h(q.label)}${reqMark}${labelEnd}${sourceBadge(q)}</div>
            ${q.description ? `<p class="aa-help" style="margin:-4px 0 8px">${h(q.description)}</p>` : ''}
            ${qInput(q, inputId)}
            ${needs ? `<div class="aa-q-foot"><span class="aa-q-needs">${I.alert}Needs your answer</span></div>` : ''}
            ${unconf && editable() ? `<div class="aa-q-foot"><span>Read the draft and edit it, or keep it as is.</span><button type="button" class="btn btn-secondary aa-sm" data-confirm="${h(q.id)}">Looks good</button></div>` : ''}
        </div>`;
    }

    function renderDrawer() {
        const app = D.app;
        const status = app.status;
        const body = $('aa-drawer-body');
        const foot = $('aa-drawer-foot');
        let html = '';
        const top = `<div class="aa-chips" style="margin:0 0 12px">${statusChip(status)}${app.match_score != null ? `<span class="chip">Match ${h(Math.round(app.match_score))}%</span>` : ''}${app.updated_at ? `<span class="chip">Updated ${h(relTime(app.updated_at))}</span>` : ''}${app.confirmation ? `<span class="chip aa-chip-ok">Confirmation: ${h(app.confirmation)}</span>` : ''}</div>`;
        html += top;

        if (status === 'drafting') {
            body.innerHTML = html + `<div class="aa-banner is-info" role="status">${I.spark}<div class="aa-banner-body"><strong>Preparing your answers…</strong> Cariara is filling in this application from your profile and drafting any free-text answers. This usually takes under a minute.</div></div>` + skeleton(3);
            foot.hidden = false;
            foot.innerHTML = `<span class="aa-foot-note">You can close this; it keeps working.</span><button type="button" class="btn btn-secondary" data-act="close">Close</button>`;
            bindFoot();
            return;
        }
        if (status === 'failed') {
            const last = listOf(app.events).slice(-1)[0];
            html += `<div class="aa-banner is-error" role="alert">${I.alert}<div class="aa-banner-body"><strong>We couldn’t prepare this application.</strong> ${h(last && last.message || '')}</div></div>`;
        }
        if (D.handoff) { body.innerHTML = html + handoffHtml(); renderHandoffFoot(); bindDrawerBody(); return; }

        if (['handed_off', 'submitted', 'confirmed', 'skipped', 'withdrawn', 'unsupported'].includes(status) || status === 'approved') {
            if (status === 'approved') html += `<div class="aa-banner is-success" role="status">${I.check}<div class="aa-banner-body">Approved. Open the application, paste your answers and submit it on the company’s site.</div></div>`;
            if (status === 'handed_off') html += `<div class="aa-banner is-info" role="status">${I.info}<div class="aa-banner-body">You opened this application. Once you’ve submitted it on the company’s site, mark it as submitted here.</div></div>`;
            if (status === 'unsupported') {
                const u = safeUrl(app.apply_url);
                html += `<div class="aa-banner is-warn" role="status">${I.info}<div class="aa-banner-body">Auto Apply doesn’t support ${h(atsLabel(app.ats))} yet. ${u ? `<a href="${h(u)}" target="_blank" rel="noopener noreferrer">Apply on the company site</a>.` : ''}</div></div>`;
            }
            if (['handed_off', 'unsupported', 'submitted', 'confirmed'].includes(status)) html += markSubmittedHtml(status);
            html += `<h3 class="aa-section-h">History</h3>` + timelineHtml(app.events);
            html += `<details class="aa-details"><summary>Answers sent (${listOf(app.questions).length})</summary><div class="aa-details-body">${answersReadonly(app)}</div></details>`;
            body.innerHTML = html;
            foot.hidden = false;
            if (status === 'approved') {
                foot.innerHTML = `<span class="aa-foot-note">The Cariara browser extension (coming soon) will do this automatically.</span><button type="button" class="btn btn-secondary" data-act="close">Close</button><button type="button" class="btn btn-primary" data-act="handoff">${I.external}Open application</button>`;
            } else {
                foot.innerHTML = `<span class="aa-foot-note"></span><button type="button" class="btn btn-secondary" data-act="close">Close</button>`;
            }
            bindFoot(); bindDrawerBody();
            return;
        }

        // Editable review form
        if (app.status !== 'failed') {
            const b = blockers();
            const n = b.needs.length + b.attest.length;
            if (n) html += `<div class="aa-banner is-warn" role="status">${I.alert}<div class="aa-banner-body">${n} ${n === 1 ? 'item needs' : 'items need'} your answer before you can approve. They're highlighted below.</div></div>`;
        }
        if (D.missingMsg) html += `<div class="aa-banner is-error" role="alert" id="aa-missing">${I.alert}<div class="aa-banner-body">${D.missingMsg}</div></div>`;

        const qs = listOf(app.questions);
        const used = new Set();
        CATEGORY_GROUPS.forEach(g => {
            const list = qs.filter(q => g.cats.includes(q.category) || (g.cats.includes('custom') && !q.category));
            list.forEach(q => used.add(q.id));
            if (!list.length) return;
            html += `<h3 class="aa-section-h">${h(g.title)}</h3>` + list.map(renderQuestion).join('');
        });
        const eeo = qs.filter(q => q.category === 'eeo');
        eeo.forEach(q => used.add(q.id));
        const rest = qs.filter(q => !used.has(q.id));
        if (rest.length) html += `<h3 class="aa-section-h">Other questions</h3>` + rest.map(renderQuestion).join('');
        if (eeo.length) {
            const optIn = !!(S.profile && S.profile.eeo && S.profile.eeo.opt_in);
            const eeoNeeds = eeo.some(q => (q.needs_user || D.missing.has(String(q.id))) && isEmpty(currentValue(q)));
            html += `<details class="aa-details"${eeoNeeds ? ' open' : ''}><summary>Voluntary self-identification (${eeo.length})</summary><div class="aa-details-body">
                <p class="aa-help" style="margin-bottom:8px">${optIn ? 'Filled from your Answers profile.' : 'You haven’t opted in to sharing this, so we answer “Decline to answer” where the form allows it.'} Employers can’t use these answers in hiring decisions.</p>
                ${eeo.map(renderQuestion).join('')}</div></details>`;
        }

        // Resume + cover letter
        const docs = S.docs;
        const docList = listOf(docs);
        const appDocs = listOf(app.documents);
        const all = docList.length ? docList : appDocs;
        html += `<h3 class="aa-section-h">Resume</h3>
            <div class="aa-q"><div class="aa-field">
                <label for="aa-resume">Resume to attach</label>
                ${all.length ? `<select class="form-control" id="aa-resume"${editable() ? '' : ' disabled'}>
                    ${D.resume == null ? '<option value="">Select a resume…</option>' : ''}
                    ${all.map(d => `<option value="${h(d.id)}"${String(d.id) === String(D.resume) ? ' selected' : ''}>${h(d.filename || 'Resume ' + d.id)}${d.is_default ? ' (default)' : ''}</option>`).join('')}
                </select>` : `<p class="aa-help">${docs === null ? 'Loading your resumes…' : 'No resumes yet. <a href="documents.html">Upload one in Resumes</a>.'}</p>`}
            </div></div>
            <h3 class="aa-section-h">Cover letter</h3>
            <div class="aa-q"><div class="aa-field">
                <label for="aa-cover">Cover letter${(D.app.cover_letter_text || '').trim() ? ' <span class="aa-badge src-ai" style="margin-left:6px">AI draft — please review</span>' : ''}</label>
                <textarea class="form-control" id="aa-cover" rows="9"${editable() ? '' : ' disabled'} placeholder="Optional. Leave empty if the company doesn't ask for one.">${h(D.cover)}</textarea>
            </div></div>
            <label class="aa-check" style="margin-top:8px"><input type="checkbox" id="aa-save-bank"> Save my edited answers for future applications</label>`;
        body.innerHTML = html;
        renderReviewFoot();
        bindDrawerBody();
    }
    function answersReadonly(app) {
        const qs = listOf(app.questions);
        if (!qs.length) return '<p class="aa-help">No questions recorded.</p>';
        return `<div class="aa-prefill">${qs.map(q => {
            const v = q.answer;
            const text = Array.isArray(v) ? v.join(', ') : v === true ? 'Yes' : v === false ? 'No' : (v ?? '—');
            return `<div class="aa-prefill-row"><div><div class="aa-prefill-label">${h(q.label)}</div><div class="aa-prefill-value">${h(text)}</div></div></div>`;
        }).join('')}</div>`;
    }
    function timelineHtml(events) {
        const ev = listOf(events).slice().sort((a, b) => parseDate(a.created_at) - parseDate(b.created_at));
        if (!ev.length) return '<p class="aa-help">No history yet.</p>';
        const label = (t) => String(t || '').replace(/[_.]/g, ' ').replace(/^./, c => c.toUpperCase());
        return `<ol class="aa-timeline">${ev.map(e => `<li><div class="t-type">${h(label(e.type))}</div>${e.message ? `<div class="t-msg">${h(e.message)}</div>` : ''}<div class="t-time">${h(fmtDate(e.created_at, true))}</div></li>`).join('')}</ol>`;
    }
    function markSubmittedHtml(status) {
        if (status !== 'handed_off' && status !== 'unsupported') return '';
        return `<div class="aa-q" style="margin-bottom:12px"><div class="aa-field">
            <label for="aa-confirmation">Confirmation (optional)</label>
            <input type="text" class="form-control" id="aa-confirmation" placeholder="e.g. confirmation number or email subject">
            <div class="aa-actions-row" style="margin-top:8px">
                <button type="button" class="btn btn-primary" data-act="mark-submitted">${I.check}Mark as submitted</button>
                ${status === 'handed_off' ? '<button type="button" class="btn btn-secondary" data-act="handoff">Show my answers again</button>' : ''}
            </div></div></div>`;
    }
    function renderReviewFoot() {
        const foot = $('aa-drawer-foot');
        foot.hidden = false;
        const app = D.app;
        if (app.status === 'failed') {
            foot.innerHTML = `<span class="aa-foot-note"></span><button type="button" class="btn btn-secondary" data-act="skip">Skip</button><button type="button" class="btn btn-primary" data-act="retry">${I.refresh}Try again</button>`;
            bindFoot(); return;
        }
        const b = blockers();
        const parts = [];
        if (b.needs.length) parts.push(`${b.needs.length} ${b.needs.length === 1 ? 'answer needs' : 'answers need'} you`);
        if (b.ai.length) parts.push(`${b.ai.length} AI ${b.ai.length === 1 ? 'draft' : 'drafts'} to review`);
        if (b.attest.length) parts.push(`${b.attest.length} ${b.attest.length === 1 ? 'statement' : 'statements'} to tick`);
        const ok = !parts.length;
        foot.innerHTML = `<span class="aa-foot-note" id="aa-foot-note" aria-live="polite">${ok ? (D.dirty.size ? 'Unsaved changes. Approving saves them too.' : 'Everything is answered.') : h(parts.join(' · '))}</span>
            <button type="button" class="btn btn-secondary" data-act="skip">Skip</button>
            <button type="button" class="btn btn-secondary" data-act="save"${D.dirty.size || D.confirmed.size || coverDirty() || resumeDirty() ? '' : ' disabled'}>Save</button>
            <button type="button" class="btn btn-primary" data-act="approve"${ok ? '' : ' disabled aria-disabled="true"'}>${I.check}Approve</button>`;
        bindFoot();
    }
    function coverDirty() { return D && D.app && (D.cover || '') !== (D.app.cover_letter_text || ''); }
    function resumeDirty() { return D && D.app && String(D.resume ?? '') !== String(D.app.resume_doc_id ?? ''); }
    function bindFoot() {
        $('aa-drawer-foot').querySelectorAll('[data-act]').forEach(b => { b.onclick = () => footAction(b.dataset.act, b); });
    }
    function bindDrawerBody() {
        const body = $('aa-drawer-body');
        body.querySelectorAll('[data-act]').forEach(b => { b.onclick = () => footAction(b.dataset.act, b); });
        body.querySelectorAll('[data-q]').forEach(el => {
            const ev = (el.tagName === 'SELECT' || el.type === 'checkbox' || el.type === 'radio' || el.type === 'date') ? 'change' : 'input';
            el.addEventListener(ev, () => onAnswer(el));
        });
        body.querySelectorAll('[data-confirm]').forEach(b => {
            b.onclick = () => { D.confirmed.add(b.dataset.confirm); rerenderKeepingFocus(); };
        });
        const cov = $('aa-cover');
        if (cov) cov.addEventListener('input', () => { D.cover = cov.value; renderReviewFoot(); });
        const res = $('aa-resume');
        if (res) res.addEventListener('change', () => { D.resume = res.value === '' ? null : Number(res.value); renderReviewFoot(); });
        body.querySelectorAll('[data-copy]').forEach(b => { b.onclick = () => copyText(b); });
        body.querySelectorAll('.aa-missing-list a').forEach(a => {
            a.onclick = (e) => {
                e.preventDefault();
                const w = document.getElementById(a.getAttribute('href').slice(1));
                if (w) { const d = w.closest('details'); if (d) d.open = true; w.scrollIntoView({ behavior: 'smooth', block: 'center' }); const inp = w.querySelector('input,select,textarea'); if (inp) inp.focus({ preventScroll: true }); }
            };
        });
    }
    function onAnswer(el) {
        const qid = el.dataset.q;
        const q = listOf(D.app.questions).find(x => String(x.id) === String(qid));
        if (!q) return;
        let val;
        if (el.dataset.attest != null) val = el.checked ? (el.dataset.agree || true) : null;
        else if (el.dataset.attestOpt != null) val = el.value;
        else if (el.dataset.multi != null) val = [...$('aa-drawer-body').querySelectorAll(`[data-multi][data-q="${CSS.escape(qid)}"]`)].filter(c => c.checked).map(c => c.value);
        else if (el.dataset.bool != null) val = el.value === '' ? null : el.value === 'true';
        else if (q.type === 'number') val = el.value === '' ? null : (isNaN(Number(el.value)) ? el.value : Number(el.value));
        else val = el.value;
        D.local[q.id] = val;
        D.dirty.add(q.id);
        D.missing.delete(String(q.id));
        // Selects and checkboxes re-render (hints, badges); typing only patches the question in place.
        const structural = el.tagName === 'SELECT' || el.type === 'checkbox' || el.type === 'radio' || el.type === 'date';
        if (structural) rerenderKeepingFocus();
        else {
            const wrap = el.closest('[data-qwrap]');
            if (wrap && !isEmpty(val)) { wrap.classList.remove('is-needs', 'is-missing'); const nf = wrap.querySelector('.aa-q-needs'); if (nf) nf.parentElement.remove(); const cf = wrap.querySelector('[data-confirm]'); if (cf) cf.parentElement.remove(); }
            const badge = wrap && wrap.querySelector('.aa-q-head .aa-badge');
            if (badge && q.category !== 'eeo') { badge.className = 'aa-badge src-user'; badge.textContent = 'You'; }
            renderReviewFoot();
        }
    }
    function rerenderKeepingFocus() {
        const active = document.activeElement;
        const id = active && active.id;
        const body = $('aa-drawer-body');
        const scroll = body.scrollTop;
        const openDetails = [...body.querySelectorAll('details')].map(d => d.open);
        renderDrawer();
        body.querySelectorAll('details').forEach((d, i) => { if (openDetails[i]) d.open = true; });
        body.scrollTop = scroll;
        if (id) { const el = document.getElementById(id); if (el) el.focus({ preventScroll: true }); }
    }

    async function saveAnswers({ quiet = false } = {}) {
        const answers = {};
        const ids = new Set([...D.dirty, ...D.confirmed, ...D.auto]);
        listOf(D.app.questions).forEach(q => { if (ids.has(q.id) || ids.has(String(q.id))) answers[q.id] = currentValue(q); });
        let app = D.app;
        const saveBank = !!($('aa-save-bank') && $('aa-save-bank').checked);
        if (Object.keys(answers).length) {
            app = await api('/applications/' + encodeURIComponent(D.id) + '/answers', 'PATCH', { answers, save_to_bank: saveBank });
        }
        const patch = {};
        if (coverDirty()) patch.cover_letter_text = D.cover;
        if (resumeDirty() && D.resume != null) patch.resume_doc_id = D.resume;
        if (Object.keys(patch).length) app = await api('/applications/' + encodeURIComponent(D.id), 'PATCH', patch);
        if (app && app.questions) {
            // Keep local "Looks good" marks for drafts the server didn't flag as confirmed.
            const keep = new Set(D.confirmed);
            setApp(app);
            listOf(app.questions).forEach(q => { if (keep.has(q.id) && q.source === 'ai_draft' && !q.confirmed) D.confirmed.add(q.id); });
            renderDrawer();
        }
        if (!quiet) toast('Saved.');
        if (saveBank) S.bank = null;
        return app;
    }
    async function footAction(act, btn) {
        if (!D || D.busy) return;
        if (act === 'close') { closeDrawer(); return; }
        const label = btn.innerHTML;
        const busy = (text) => { D.busy = true; btn.disabled = true; btn.textContent = text; };
        const done = () => { if (D) D.busy = false; if (btn.isConnected) { btn.disabled = false; btn.innerHTML = label; } };
        try {
            if (act === 'save') { busy('Saving…'); await saveAnswers(); done(); return; }
            if (act === 'approve') {
                busy('Approving…');
                if (D.dirty.size || D.confirmed.size || D.auto.size || coverDirty() || resumeDirty()) await saveAnswers({ quiet: true });
                try {
                    const app = await api('/applications/' + encodeURIComponent(D.id) + '/approve', 'POST');
                    D.busy = false;
                    D.missing = new Set(); D.missingMsg = '';
                    toast('Approved. It’s ready to submit.', { actionLabel: 'Go to Ready to submit', onAction: () => { closeDrawer(); setHash('ready'); selectTab('ready'); } });
                    if (app && app.id) { setApp(app); }
                    invalidateLists(); loadList('review'); loadList('ready'); refreshStats();
                } catch (e) {
                    if (e.status === 400) {
                        const miss = listOf(e.data && e.data.missing).map(String);
                        D.missing = new Set(miss);
                        const qs = listOf(D.app.questions);
                        const links = miss.map(id => { const q = qs.find(x => String(x.id) === id); return q ? `<li><a href="#wrap-q-${h(String(q.id).replace(/[^\w-]/g, '_'))}">${h(q.label)}</a></li>` : ''; }).join('');
                        D.missingMsg = `<strong>${h(e.message || 'Some answers are still missing.')}</strong>${links ? `<ul class="aa-missing-list">${links}</ul>` : ''}`;
                        D.busy = false;
                        renderDrawer();
                        $('aa-drawer-body').scrollTop = 0;
                        const m = $('aa-missing');
                        if (m) { m.setAttribute('tabindex', '-1'); m.focus(); }
                    } else throw e;
                }
                return;
            }
            if (act === 'skip') {
                if (!window.confirm('Skip this application? It will be removed from your queue.')) return;
                busy('Skipping…');
                await api('/applications/' + encodeURIComponent(D.id) + '/skip', 'POST', { reason: 'user_skipped' });
                D.dirty.clear();
                toast('Application skipped.');
                invalidateLists(); closeDrawer(); refreshStats();
                return;
            }
            if (act === 'retry') {
                busy('Retrying…');
                const app = await api('/applications/' + encodeURIComponent(D.id) + '/retry-draft', 'POST');
                D.busy = false;
                if (app && app.id) setApp(app); else openDrawer(D.id);
                invalidateLists();
                return;
            }
            if (act === 'handoff') { D.busy = false; await startHandoff(D.id, btn); return; }
            if (act === 'mark-submitted') {
                busy('Saving…');
                const conf = $('aa-confirmation') ? $('aa-confirmation').value.trim() : '';
                await api('/applications/' + encodeURIComponent(D.id) + '/mark-submitted', 'POST', conf ? { confirmation: conf } : {});
                toast('Marked as submitted. Good luck!');
                D.handoff = null;
                invalidateLists(); refreshStats();
                const id = D.id;
                D.busy = false;
                goToApp('submitted', id);
                return;
            }
        } catch (e) {
            done();
            handleCommonError(e, 'Something went wrong. Please try again.');
        }
    }

    // ── Handoff ────────────────────────────────────────────────────────
    async function startHandoff(id, btn) {
        if (btn) { btn.disabled = true; btn.textContent = 'Opening…'; }
        try {
            const data = await api('/applications/' + encodeURIComponent(id) + '/handoff', 'POST');
            const url = safeUrl(data && data.apply_url);
            // With noopener, window.open returns null even on success, so the panel always offers "Open it again".
            if (url) window.open(url, '_blank', 'noopener');
            if (!D || D.id !== String(id)) await openDrawer(id);
            if (!D) return;
            D.handoff = Object.assign({}, data, { apply_url: url });
            // Refresh the app so status moves to handed_off.
            try { const app = await api('/applications/' + encodeURIComponent(id)); if (D && D.id === String(id)) { D.app = app; } } catch (e) { /* ignore */ }
            renderDrawer();
            invalidateLists(); refreshStats();
            if (S.tab === 'ready') loadList('ready');
        } catch (e) {
            if (btn && btn.isConnected) { btn.disabled = false; btn.innerHTML = I.external + 'Open application'; }
            handleCommonError(e, 'Could not open this application.');
        }
    }
    function handoffHtml() {
        const hd = D.handoff;
        const url = hd.apply_url;
        const rows = listOf(hd.prefill);
        let html = `<div class="aa-banner is-info" role="status">${I.external}<div class="aa-banner-body"><strong>The application opened in a new tab.</strong> Copy each answer below into the form, then submit it there. ${url ? `<a href="${h(url)}" target="_blank" rel="noopener noreferrer">Open it again</a>` : ''}</div></div>`;
        html += `<div class="aa-note" style="margin:0 0 12px">${I.puzzle}<span>The Cariara browser extension (coming soon) will do this automatically.</span></div>`;
        html += `<h3 class="aa-section-h">Your answers</h3>`;
        html += rows.length ? `<div class="aa-prefill">${rows.map((r, i) => {
            const v = Array.isArray(r.value) ? r.value.join(', ') : r.value === true ? 'Yes' : r.value === false ? 'No' : (r.value ?? '');
            return `<div class="aa-prefill-row"><div><div class="aa-prefill-label" id="pf-l-${i}">${h(r.label)}</div><div class="aa-prefill-value" id="pf-v-${i}">${h(v || '—')}</div></div>
                ${v ? `<button type="button" class="btn btn-secondary aa-sm aa-copy" data-copy="pf-v-${i}" aria-describedby="pf-l-${i}">${I.copy}Copy</button>` : ''}</div>`;
        }).join('')}</div>` : '<p class="aa-help">No answers to copy.</p>';
        if (hd.cover_letter_text) {
            html += `<h3 class="aa-section-h">Cover letter</h3><div class="aa-prefill-row"><div><div class="aa-prefill-value" id="pf-cover" style="max-height:240px">${h(hd.cover_letter_text)}</div></div>
                <button type="button" class="btn btn-secondary aa-sm aa-copy" data-copy="pf-cover" aria-label="Copy cover letter">${I.copy}Copy</button></div>`;
        }
        html += `<h3 class="aa-section-h">Done?</h3>` + `<div class="aa-q"><div class="aa-field">
            <label for="aa-confirmation">Confirmation (optional)</label>
            <input type="text" class="form-control" id="aa-confirmation" placeholder="e.g. confirmation number or email subject"></div></div>`;
        return html;
    }
    function renderHandoffFoot() {
        const foot = $('aa-drawer-foot');
        foot.hidden = false;
        foot.innerHTML = `<span class="aa-foot-note">Submitted it on the company’s site?</span><button type="button" class="btn btn-secondary" data-act="close">Not yet</button><button type="button" class="btn btn-primary" data-act="mark-submitted">${I.check}Mark as submitted</button>`;
        bindFoot();
    }
    async function copyText(btn) {
        const el = document.getElementById(btn.dataset.copy);
        const text = el ? el.textContent : '';
        let ok = false;
        try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
            const ta = document.createElement('textarea');
            ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
            document.body.appendChild(ta); ta.select();
            try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
            ta.remove();
        }
        const orig = btn.innerHTML;
        btn.innerHTML = ok ? I.check + 'Copied' : 'Copy failed';
        setTimeout(() => { if (btn.isConnected) btn.innerHTML = orig; }, 1600);
    }

    // ── Documents ──────────────────────────────────────────────────────
    async function loadDocs() {
        try {
            const r = await authFetch('/users/documents?type=resume');
            S.docs = r.ok ? listOf(await r.json()) : [];
        } catch (e) { S.docs = []; }
        if (D && D.app && editable() && !D.handoff) {
            if (D.resume == null) { const def = S.docs.find(d => d.is_default); if (def) D.resume = def.id; }
            rerenderKeepingFocus();
        }
    }

    // ── Preferences ────────────────────────────────────────────────────
    let prefDraft = null;
    function prefsPayload(p) {
        const out = {};
        ['enabled', 'mode', 'min_match_score', 'daily_cap', 'target_roles', 'locations', 'remote_ok', 'salary_floor', 'excluded_companies', 'ats_allowlist']
            .forEach(k => { if (p[k] !== undefined) out[k] = p[k]; });
        return out;
    }
    async function loadPreferences() {
        const panel = $('panel-preferences');
        S.loaded.preferences = true;
        if (!S.prefs) {
            panel.innerHTML = skeleton(3);
            try { S.prefs = await api('/preferences'); S.prefsError = null; renderHeader(); }
            catch (e) { if (e.status === 402) { showUpgrade(true); } errorState(panel, 'We couldn’t load your preferences. ' + e.message, loadPreferences); return; }
        }
        renderPreferences();
    }
    function chipsField(key, label, help, placeholder) {
        const vals = listOf(prefDraft[key]);
        return `<div class="aa-field full">
            <label for="chips-${key}">${h(label)}</label>
            <div class="aa-chipsbox" data-chips="${key}">
                ${vals.map((v, i) => `<span class="aa-tag"><span>${h(v)}</span><button type="button" data-chip-del="${i}" aria-label="Remove ${h(v)}">&times;</button></span>`).join('')}
                <input type="text" class="aa-chips-input" id="chips-${key}" placeholder="${h(placeholder)}" autocomplete="off" aria-describedby="help-${key}">
            </div>
            <p class="aa-help" id="help-${key}">${h(help)}</p>
        </div>`;
    }
    function renderPreferences() {
        const panel = $('panel-preferences');
        const p = S.prefs || {};
        prefDraft = JSON.parse(JSON.stringify(Object.assign({ mode: 'review', min_match_score: 70, daily_cap: 10, target_roles: [], locations: [], remote_ok: true, salary_floor: null, excluded_companies: [], ats_allowlist: SUPPORTED_ATS.slice() }, p)));
        const capMax = Number(p.daily_cap_max) || Math.max(25, Number(p.daily_cap) || 0);
        const allow = new Set(listOf(prefDraft.ats_allowlist).map(atsKey));
        panel.innerHTML = `<form class="aa-form" id="aa-pref-form" novalidate>
            <fieldset class="aa-fieldset">
                <legend>How Auto Apply works for you</legend>
                <div class="aa-radios" role="radiogroup" aria-label="Mode">
                    <label class="aa-radio-card"><input type="radio" name="mode" value="review"${prefDraft.mode !== 'auto' ? ' checked' : ''}>
                        <div><strong>Review first (recommended)</strong><span>Cariara prepares each application and you check every answer before approving it.</span></div></label>
                    <label class="aa-radio-card"><input type="radio" name="mode" value="auto"${prefDraft.mode === 'auto' ? ' checked' : ''}>
                        <div><strong>Automatic</strong><span>Applications for jobs at or above your minimum match score are prepared and approved for you. Answers still come only from your profile, and anything that needs you still waits for you.</span></div></label>
                </div>
            </fieldset>
            <fieldset class="aa-fieldset">
                <legend>Which jobs</legend>
                <div class="aa-grid">
                    ${chipsField('target_roles', 'Target roles', 'Press Enter or comma to add. For example: Backend Engineer.', 'Add a role')}
                    ${chipsField('locations', 'Locations', 'Cities, states or countries you’d work in.', 'Add a location')}
                    <div class="aa-field full">
                        <label for="pf-min-score">Minimum match score</label>
                        <div class="aa-range-row"><input type="range" id="pf-min-score" min="0" max="100" step="5" value="${h(prefDraft.min_match_score ?? 70)}" aria-describedby="help-min-score"><output id="pf-min-score-out" for="pf-min-score">${h(prefDraft.min_match_score ?? 70)}%</output></div>
                        <p class="aa-help" id="help-min-score">Only jobs that match your resume at least this well are suggested.</p>
                    </div>
                    <div class="aa-field">
                        <span class="aa-label" id="remote-l">Remote jobs</span>
                        <label class="aa-check"><input type="checkbox" id="pf-remote"${prefDraft.remote_ok ? ' checked' : ''} aria-labelledby="remote-l remote-t"> <span id="remote-t">Include remote roles</span></label>
                    </div>
                    <div class="aa-field">
                        <label for="pf-salary-floor">Minimum salary (USD / year)</label>
                        <input type="number" class="form-control" id="pf-salary-floor" min="0" step="1000" inputmode="numeric" value="${h(prefDraft.salary_floor ?? '')}" placeholder="No minimum">
                        <p class="aa-help">Jobs that list a lower salary are skipped.</p>
                    </div>
                    ${chipsField('excluded_companies', 'Companies to skip', 'We’ll never prepare applications for these companies.', 'Add a company')}
                </div>
            </fieldset>
            <fieldset class="aa-fieldset">
                <legend>Limits</legend>
                <div class="aa-grid">
                    <div class="aa-field">
                        <label for="pf-daily-cap">Applications per day</label>
                        <input type="number" class="form-control" id="pf-daily-cap" min="1" max="${capMax}" step="1" value="${h(prefDraft.daily_cap ?? 10)}" aria-describedby="help-cap">
                        <p class="aa-help" id="help-cap">Up to ${capMax} on your plan.</p>
                    </div>
                    <div class="aa-field">
                        <span class="aa-label" id="ats-l">Application systems</span>
                        <div class="aa-checks" role="group" aria-labelledby="ats-l">
                            ${SUPPORTED_ATS.map(a => `<label class="aa-check"><input type="checkbox" name="ats" value="${a}"${allow.has(a) ? ' checked' : ''}> ${h(ATS_LABEL[a])}</label>`).join('')}
                        </div>
                        <p class="aa-help">Auto Apply works with these job sites today.</p>
                    </div>
                </div>
            </fieldset>
            <div class="aa-actions-row">
                <button type="submit" class="btn btn-primary" id="aa-pref-save">Save preferences</button>
                <span class="aa-save-state" id="aa-pref-state" role="status" aria-live="polite"></span>
            </div>
        </form>`;
        bindChips(panel);
        const range = $('pf-min-score');
        range.oninput = () => { $('pf-min-score-out').textContent = range.value + '%'; };
        $('aa-pref-form').onsubmit = savePreferences;
    }
    function bindChips(root) {
        root.querySelectorAll('[data-chips]').forEach(box => {
            const key = box.dataset.chips;
            const input = box.querySelector('input');
            const add = () => {
                const parts = input.value.split(',').map(s => s.trim()).filter(Boolean);
                if (!parts.length) return;
                const cur = listOf(prefDraft[key]);
                parts.forEach(p => { if (!cur.some(c => c.toLowerCase() === p.toLowerCase())) cur.push(p.slice(0, 120)); });
                prefDraft[key] = cur;
                redrawChips(box, key);
            };
            box.addEventListener('click', (e) => {
                const del = e.target.closest('[data-chip-del]');
                if (del) {
                    const cur = listOf(prefDraft[key]); cur.splice(Number(del.dataset.chipDel), 1); prefDraft[key] = cur;
                    redrawChips(box, key); return;
                }
                if (e.target === box) input.focus();
            });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(); }
                else if (e.key === 'Backspace' && !input.value && listOf(prefDraft[key]).length) { prefDraft[key].pop(); redrawChips(box, key); }
            });
            input.addEventListener('blur', add);
        });
    }
    function redrawChips(box, key) {
        const input = box.querySelector('input');
        box.querySelectorAll('.aa-tag').forEach(t => t.remove());
        const html = listOf(prefDraft[key]).map((v, i) => `<span class="aa-tag"><span>${h(v)}</span><button type="button" data-chip-del="${i}" aria-label="Remove ${h(v)}">&times;</button></span>`).join('');
        input.insertAdjacentHTML('beforebegin', html);
        input.value = '';
        input.focus();
    }
    async function savePreferences(e) {
        e.preventDefault();
        const form = $('aa-pref-form');
        form.querySelectorAll('.aa-chips-input').forEach(i => i.dispatchEvent(new Event('blur')));
        const capMax = Number(S.prefs && S.prefs.daily_cap_max) || Math.max(25, Number(S.prefs && S.prefs.daily_cap) || 0);
        const cap = Math.round(Number($('pf-daily-cap').value));
        const state = $('aa-pref-state');
        if (!cap || cap < 1 || cap > capMax) { state.textContent = `Applications per day must be between 1 and ${capMax}.`; $('pf-daily-cap').focus(); return; }
        const floorRaw = $('pf-salary-floor').value.trim();
        const ats = [...form.querySelectorAll('input[name="ats"]:checked')].map(i => i.value);
        if (!ats.length) { state.textContent = 'Pick at least one application system.'; return; }
        const payload = prefsPayload(Object.assign({}, S.prefs, {
            mode: form.querySelector('input[name="mode"]:checked').value,
            min_match_score: Number($('pf-min-score').value),
            daily_cap: cap,
            target_roles: listOf(prefDraft.target_roles),
            locations: listOf(prefDraft.locations),
            remote_ok: $('pf-remote').checked,
            salary_floor: floorRaw === '' ? null : Math.max(0, Math.round(Number(floorRaw))),
            excluded_companies: listOf(prefDraft.excluded_companies),
            ats_allowlist: ats,
        }));
        const btn = $('aa-pref-save');
        btn.disabled = true; btn.textContent = 'Saving…'; state.textContent = '';
        try {
            const saved = await api('/preferences', 'PUT', payload);
            S.prefs = saved && typeof saved === 'object' ? saved : Object.assign({}, S.prefs, payload);
            renderHeader(); renderPreferences();
            $('aa-pref-state').textContent = 'Saved.';
            toast('Preferences saved. Refresh matches to see the effect.', { actionLabel: 'Refresh matches', onAction: () => { setHash('matches'); selectTab('matches'); refreshQueue(); } });
            refreshReadiness(); refreshStats();
        } catch (err) {
            btn.disabled = false; btn.textContent = 'Save preferences';
            if (err.status === 402) { showUpgrade(true); state.textContent = 'Auto Apply needs Cariara Pro.'; }
            else state.textContent = err.message || 'Could not save.';
            handleCommonError(err, 'Could not save preferences.');
        }
    }

    // ── Answers profile ────────────────────────────────────────────────
    async function loadProfile() {
        const panel = $('panel-profile');
        S.loaded.profile = true;
        if (!S.profile) {
            panel.innerHTML = skeleton(4);
            try { S.profile = await api('/profile'); }
            catch (e) { if (e.status === 402) showUpgrade(true); errorState(panel, 'We couldn’t load your answers profile. ' + e.message, loadProfile); return; }
        }
        renderProfile();
        loadBank();
    }
    function tri(id, label, value, help) {
        const v = value === true ? 'yes' : value === false ? 'no' : '';
        return `<div class="aa-field"><label for="${id}">${h(label)}</label>
            <select class="form-control" id="${id}"><option value=""${v === '' ? ' selected' : ''}>Not set</option><option value="yes"${v === 'yes' ? ' selected' : ''}>Yes</option><option value="no"${v === 'no' ? ' selected' : ''}>No</option></select>
            ${help ? `<p class="aa-help">${h(help)}</p>` : ''}</div>`;
    }
    function textField(id, label, value, { type = 'text', full = false, help = '', auto = '', placeholder = '' } = {}) {
        return `<div class="aa-field${full ? ' full' : ''}"><label for="${id}">${h(label)}</label>
            <input type="${type}" class="form-control" id="${id}" value="${h(value ?? '')}"${auto ? ` autocomplete="${auto}"` : ''}${placeholder ? ` placeholder="${h(placeholder)}"` : ''}>
            ${help ? `<p class="aa-help">${h(help)}</p>` : ''}</div>`;
    }
    function eeoSelect(key, label, value) {
        const opts = EEO_OPTIONS[key].slice();
        if (value && !opts.some(o => o[0] === value)) opts.unshift([value, value]);
        return `<div class="aa-field"><label for="pf-eeo-${key}">${h(label)}</label><select class="form-control" id="pf-eeo-${key}">
            <option value="">Not set</option>${opts.map(o => `<option value="${h(o[0])}"${o[0] === value ? ' selected' : ''}>${h(o[1])}</option>`).join('')}</select></div>`;
    }
    function renderProfile() {
        const panel = $('panel-profile');
        const p = S.profile || {};
        const loc = p.location || {};
        const eeo = p.eeo || {};
        panel.innerHTML = `<form class="aa-form" id="aa-profile-form" novalidate>
            <p class="aa-help" style="margin:0">Factual answers on your applications come only from here, never from AI. Keep them accurate.</p>
            <fieldset class="aa-fieldset"><legend>Contact</legend><div class="aa-grid">
                ${textField('pf-first_name', 'First name', p.first_name, { auto: 'given-name' })}
                ${textField('pf-last_name', 'Last name', p.last_name, { auto: 'family-name' })}
                ${textField('pf-email', 'Email', p.email, { type: 'email', auto: 'email' })}
                ${textField('pf-phone', 'Phone', p.phone, { type: 'tel', auto: 'tel' })}
            </div></fieldset>
            <fieldset class="aa-fieldset"><legend>Location</legend><div class="aa-grid aa-grid-3">
                ${textField('pf-city', 'City', loc.city, { auto: 'address-level2' })}
                ${textField('pf-state', 'State / region', loc.state, { auto: 'address-level1' })}
                ${textField('pf-country', 'Country', loc.country, { auto: 'country-name' })}
            </div></fieldset>
            <fieldset class="aa-fieldset"><legend>Links</legend><div class="aa-grid aa-grid-3">
                ${textField('pf-linkedin', 'LinkedIn', p.linkedin, { type: 'url', placeholder: 'https://linkedin.com/in/…' })}
                ${textField('pf-github', 'GitHub', p.github, { type: 'url', placeholder: 'https://github.com/…' })}
                ${textField('pf-portfolio', 'Portfolio or website', p.portfolio, { type: 'url', placeholder: 'https://…' })}
            </div></fieldset>
            <fieldset class="aa-fieldset"><legend>Work eligibility</legend><div class="aa-grid aa-grid-3">
                ${tri('pf-work_authorized_us', 'Authorized to work in the US?', p.work_authorized_us)}
                ${tri('pf-requires_sponsorship', 'Need visa sponsorship now or later?', p.requires_sponsorship)}
                ${tri('pf-willing_to_relocate', 'Willing to relocate?', p.willing_to_relocate)}
            </div></fieldset>
            <fieldset class="aa-fieldset"><legend>Availability and pay</legend><div class="aa-grid aa-grid-3">
                ${textField('pf-earliest_start_date', 'Earliest start date', p.earliest_start_date ? String(p.earliest_start_date).slice(0, 10) : '', { type: 'date' })}
                ${textField('pf-notice_period', 'Notice period', p.notice_period, { placeholder: 'e.g. 2 weeks' })}
                ${textField('pf-salary_expectation', 'Salary expectation', p.salary_expectation, { placeholder: 'e.g. $150,000' })}
            </div></fieldset>
            <fieldset class="aa-fieldset"><legend>Voluntary self-identification</legend>
                <p class="aa-help">Optional. If you don’t opt in, we answer “Decline to answer” wherever a form allows it.</p>
                <label class="aa-check" style="margin-top:8px"><input type="checkbox" id="pf-eeo-opt"${eeo.opt_in ? ' checked' : ''}> Share my answers on applications</label>
                <div class="aa-grid" id="pf-eeo-fields" style="margin-top:12px"${eeo.opt_in ? '' : ' hidden'}>
                    ${eeoSelect('gender', 'Gender', eeo.gender)}
                    ${eeoSelect('race', 'Race / ethnicity', eeo.race)}
                    ${eeoSelect('veteran', 'Veteran status', eeo.veteran)}
                    ${eeoSelect('disability', 'Disability status', eeo.disability)}
                </div>
            </fieldset>
            <div class="aa-actions-row">
                <button type="submit" class="btn btn-primary" id="aa-profile-save">Save profile</button>
                <span class="aa-save-state" id="aa-profile-state" role="status" aria-live="polite"></span>
            </div>
        </form>
        <section class="aa-fieldset" id="aa-bank-section" aria-labelledby="aa-bank-title" style="margin-top:20px">
            <h2 id="aa-bank-title" style="font:500 16px/24px var(--c-display);margin:0 0 4px">Saved answers</h2>
            <p class="aa-help">Answers you’ve saved from past applications. Cariara reuses them when the same question comes up.</p>
            <div id="aa-bank" style="margin-top:12px">${skeleton(1)}</div>
        </section>`;
        $('pf-eeo-opt').onchange = (e) => { $('pf-eeo-fields').hidden = !e.target.checked; };
        $('aa-profile-form').onsubmit = saveProfile;
        const f = parseHash().params.get('field');
        if (f) focusProfileField(f);
    }
    function focusProfileField(field) {
        const id = PROFILE_FIELD_IDS[field] || PROFILE_FIELD_IDS[String(field).replace(/^location\./, '')];
        const el = id && document.getElementById(id);
        if (!el) return;
        setTimeout(() => { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); el.focus({ preventScroll: true }); }, 50);
    }
    async function saveProfile(e) {
        e.preventDefault();
        const val = (id) => $(id).value.trim();
        const triVal = (id) => ({ yes: true, no: false })[$(id).value] ?? null;
        const state = $('aa-profile-state');
        for (const id of ['pf-linkedin', 'pf-github', 'pf-portfolio']) {
            const v = val(id);
            if (v && !safeUrl(v.includes('://') ? v : 'https://' + v)) { state.textContent = 'Please enter a valid web address.'; $(id).focus(); return; }
        }
        const optIn = $('pf-eeo-opt').checked;
        const payload = {
            first_name: val('pf-first_name'), last_name: val('pf-last_name'), email: val('pf-email'), phone: val('pf-phone'),
            location: { city: val('pf-city'), state: val('pf-state'), country: val('pf-country') },
            linkedin: val('pf-linkedin'), github: val('pf-github'), portfolio: val('pf-portfolio'),
            work_authorized_us: triVal('pf-work_authorized_us'), requires_sponsorship: triVal('pf-requires_sponsorship'),
            willing_to_relocate: triVal('pf-willing_to_relocate'),
            earliest_start_date: val('pf-earliest_start_date') || null,
            salary_expectation: val('pf-salary_expectation'), notice_period: val('pf-notice_period'),
            eeo: {
                opt_in: optIn,
                gender: optIn ? (val('pf-eeo-gender') || null) : null,
                race: optIn ? (val('pf-eeo-race') || null) : null,
                veteran: optIn ? (val('pf-eeo-veteran') || null) : null,
                disability: optIn ? (val('pf-eeo-disability') || null) : null,
            },
        };
        const btn = $('aa-profile-save');
        btn.disabled = true; btn.textContent = 'Saving…'; state.textContent = '';
        try {
            const saved = await api('/profile', 'PUT', payload);
            S.profile = saved && typeof saved === 'object' ? saved : payload;
            state.textContent = 'Saved.';
            toast('Answers profile saved.');
            refreshReadiness();
        } catch (err) {
            state.textContent = err.message || 'Could not save.';
            handleCommonError(err, 'Could not save your profile.');
        } finally {
            btn.disabled = false; btn.textContent = 'Save profile';
        }
    }

    // ── Answer bank ────────────────────────────────────────────────────
    const bankQ = (it) => it.label || it.question || it.question_key || '';
    const bankA = (it) => { const a = it.answer ?? it.value; return Array.isArray(a) ? a.join(', ') : (a === true ? 'Yes' : a === false ? 'No' : (a ?? '')); };
    async function loadBank() {
        const box = $('aa-bank');
        if (!box) return;
        try { S.bank = listOf(await api('/answer-bank')); S.bankError = null; }
        catch (e) { S.bankError = e; }
        renderBank();
    }
    let bankEditing = null;
    function renderBank() {
        const box = $('aa-bank');
        if (!box) return;
        if (S.bankError && !S.bank) { box.innerHTML = `<p class="aa-help">Couldn’t load saved answers. ${h(S.bankError.message)} <button type="button" class="aa-text-btn" id="aa-bank-retry">Try again</button></p>`; $('aa-bank-retry').onclick = loadBank; return; }
        const items = S.bank || [];
        const row = (it) => bankEditing === it.id
            ? `<tr><td><label class="sr-only" for="bank-q-${h(it.id)}">Question</label><input type="text" class="form-control" id="bank-q-${h(it.id)}" value="${h(bankQ(it))}"></td>
                <td><label class="sr-only" for="bank-a-${h(it.id)}">Answer</label><textarea class="form-control" id="bank-a-${h(it.id)}" rows="3">${h(bankA(it))}</textarea></td>
                <td class="aa-td-actions"><button type="button" class="btn btn-primary aa-sm" data-bank-save="${h(it.id)}">Save</button> <button type="button" class="aa-text-btn" data-bank-cancel>Cancel</button></td></tr>`
            : `<tr><td>${h(bankQ(it))}</td><td style="white-space:pre-wrap">${h(bankA(it))}</td>
                <td class="aa-td-actions"><button type="button" class="aa-text-btn" data-bank-edit="${h(it.id)}" aria-label="Edit answer to ${h(bankQ(it))}">Edit</button><button type="button" class="aa-text-btn" data-bank-del="${h(it.id)}" aria-label="Delete answer to ${h(bankQ(it))}" style="color:var(--c-red)">Delete</button></td></tr>`;
        box.innerHTML = `${items.length ? `<div class="aa-table-wrap"><table class="aa-table"><thead><tr><th scope="col" style="width:40%">Question</th><th scope="col">Answer</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead><tbody>${items.map(row).join('')}</tbody></table></div>` : '<p class="aa-help">No saved answers yet. Tick “Save my edited answers” while reviewing an application, or add one here.</p>'}
            <div class="aa-grid" style="margin-top:16px">
                <div class="aa-field"><label for="bank-new-q">Question</label><input type="text" class="form-control" id="bank-new-q" placeholder="e.g. Why do you want to work here?"></div>
                <div class="aa-field"><label for="bank-new-a">Answer</label><textarea class="form-control" id="bank-new-a" rows="2"></textarea></div>
            </div>
            <div class="aa-actions-row" style="margin-top:12px"><button type="button" class="btn btn-secondary" id="bank-add">Add saved answer</button><span class="aa-save-state" id="bank-state" role="status" aria-live="polite"></span></div>`;
        $('bank-add').onclick = async () => {
            const q = $('bank-new-q').value.trim(); const a = $('bank-new-a').value.trim();
            if (!q || !a) { $('bank-state').textContent = 'Add both a question and an answer.'; return; }
            try { await api('/answer-bank', 'POST', { label: q, value: a }); toast('Saved answer added.'); await loadBank(); }
            catch (e) { $('bank-state').textContent = e.message; }
        };
        box.querySelectorAll('[data-bank-edit]').forEach(b => { b.onclick = () => { bankEditing = S.bank.find(x => String(x.id) === b.dataset.bankEdit).id; renderBank(); const i = $('bank-q-' + bankEditing); if (i) i.focus(); }; });
        box.querySelectorAll('[data-bank-cancel]').forEach(b => { b.onclick = () => { bankEditing = null; renderBank(); }; });
        box.querySelectorAll('[data-bank-save]').forEach(b => {
            b.onclick = async () => {
                const id = b.dataset.bankSave;
                try {
                    await api('/answer-bank/' + encodeURIComponent(id), 'PUT', { label: $('bank-q-' + id).value.trim(), value: $('bank-a-' + id).value.trim() });
                    bankEditing = null; toast('Saved answer updated.'); await loadBank();
                } catch (e) { handleCommonError(e, 'Could not update this answer.'); }
            };
        });
        box.querySelectorAll('[data-bank-del]').forEach(b => {
            b.onclick = async () => {
                if (!window.confirm('Delete this saved answer?')) return;
                try { await api('/answer-bank/' + encodeURIComponent(b.dataset.bankDel), 'DELETE'); toast('Saved answer deleted.'); await loadBank(); }
                catch (e) { handleCommonError(e, 'Could not delete this answer.'); }
            };
        });
    }

    // ── Init ───────────────────────────────────────────────────────────
    async function init() {
        if (!requireAuth()) return;
        const ok = await requireOnboarding();
        if (ok === false) return;
        $('aa-enable').onclick = toggleEnabled;
        $('aa-drawer-close').onclick = () => closeDrawer();
        $('aa-scrim').onclick = () => closeDrawer();
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && D) { e.preventDefault(); closeDrawer(); }
            trapFocus(e);
        });
        window.addEventListener('beforeunload', (e) => { if (D && D.dirty.size) { e.preventDefault(); e.returnValue = ''; } });
        bindTabs();
        renderHeader();
        selectTab(parseHash().tab);
        await loadCore();
        route();
        ['review', 'ready', 'submitted'].filter(t => t !== S.tab).forEach(t => loadList(t));
        if (S.tab === 'matches' && S.queue) renderMatches();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
