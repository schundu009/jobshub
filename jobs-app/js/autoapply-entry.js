/**
 * Auto Apply entry point shared by discover.html and job_detail.html.
 * Needs js/app.js (authFetch, escapeHtml) loaded first.
 *
 *   CariaraAutoApply.isSupported(job)        -> true for Greenhouse / Lever / Ashby jobs
 *   CariaraAutoApply.prepare(jobId)          -> { ok, id } or { ok:false, status, message, upgrade }
 *   CariaraAutoApply.prepareAndOpen(jobId, onError)
 */
(function () {
    'use strict';

    const SUPPORTED = ['greenhouse', 'lever', 'ashby'];
    const PRICING_URL = 'https://cariara.com/pricing';

    // Same order as the API (services/apply/ats.py): the job URL first, then the source that produced the job.
    function atsFromUrl(url) {
        const u = String(url || '').toLowerCase();
        if (/(^|\/\/|\.)greenhouse\.io\//.test(u) || /[?&]gh_jid=/.test(u)) return 'greenhouse';
        if (/\/\/jobs\.lever\.co\//.test(u)) return 'lever';
        if (/\/\/jobs\.ashbyhq\.com\//.test(u)) return 'ashby';
        return '';
    }

    function atsOf(job) {
        if (!job) return '';
        const explicit = String(job.ats || '').toLowerCase().trim();
        if (explicit) return explicit;
        return atsFromUrl(job.job_url) || String(job.source || '').toLowerCase().trim();
    }

    function isSupported(job) {
        return SUPPORTED.includes(atsOf(job));
    }

    function reviewUrl(id) {
        return 'autoapply.html#review?app=' + encodeURIComponent(id);
    }

    async function readBody(res) {
        try {
            const text = await res.text();
            if (!text) return null;
            try { return JSON.parse(text); } catch (e) { return null; }
        } catch (e) {
            return null;
        }
    }

    // FastAPI puts dict details under "detail"; flatten so callers see {message, id, ...}.
    function flatten(body) {
        if (!body || typeof body !== 'object') return {};
        const d = body.detail;
        if (d && typeof d === 'object' && !Array.isArray(d)) return Object.assign({}, body, d);
        return body;
    }

    function messageOf(body, fallback) {
        const b = flatten(body);
        if (typeof b.message === 'string' && b.message) return b.message;
        if (typeof b.detail === 'string' && b.detail) return b.detail;
        return fallback;
    }

    function formatReset(value) {
        if (!value) return '';
        const d = new Date(value);
        if (isNaN(d)) return '';
        return d.toLocaleString('en-US', { weekday: 'short', hour: 'numeric', minute: '2-digit' });
    }

    async function prepare(jobId) {
        let res;
        try {
            res = await authFetch('/apply/applications', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: Number(jobId) }),
            });
        } catch (e) {
            return { ok: false, status: 0, message: e.message || 'Could not reach Cariara.' };
        }
        const body = flatten(await readBody(res));
        if (res.ok) return { ok: true, id: body.id, app: body };
        if (res.status === 409 && body.id != null) return { ok: true, id: body.id, existing: true };
        if (res.status === 402) {
            return { ok: false, status: 402, upgrade: true, pricingUrl: PRICING_URL,
                message: 'Auto Apply is part of Cariara Pro. Upgrade to have Cariara prepare applications for you.' };
        }
        if (res.status === 429) {
            const at = formatReset(body.resets_at);
            return { ok: false, status: 429,
                message: messageOf(body, "You've reached today's Auto Apply limit.") + (at ? ' Resets ' + at + '.' : '') };
        }
        if (res.status === 404) {
            return { ok: false, status: 404, message: messageOf(body, 'Auto Apply is not available for this job.') };
        }
        return { ok: false, status: res.status, message: messageOf(body, 'Could not prepare this application. Please try again.') };
    }

    async function prepareAndOpen(jobId, onError) {
        const result = await prepare(jobId);
        if (result.ok && result.id != null) {
            window.location.href = reviewUrl(result.id);
            return result;
        }
        if (typeof onError === 'function') onError(result);
        return result;
    }

    window.CariaraAutoApply = { SUPPORTED, PRICING_URL, atsOf, atsFromUrl, isSupported, prepare, prepareAndOpen, reviewUrl };
})();
