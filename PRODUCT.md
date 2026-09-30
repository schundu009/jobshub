# Cariara: Product Context

## Register

product

## Users and purpose

- **Admin portal (admin.cariara.com):** used by the owner (super admin) for ops and triage: checking scraped jobs, fixing data, watching scraper health, running AI tools on a job. One expert user, on a desktop monitor, often in dark mode, moving fast between list and detail.
- **Jobs portal (jobs.cariara.com):** job seekers (US-first, per-country visibility) browsing scraped jobs, matching against their resume, and applying (Auto Apply on paid plans).

## Brand personality

Calm, precise tool. Quiet tinted neutrals, one accent, strong type hierarchy, generous reading width for long text (job descriptions). Confidence comes from typography and spacing, not decoration. Reference feel: Linear, Stripe dashboard.

## Anti-references

- Generic AI/SaaS look: gradients, glass cards, icon-card grids, big-number heroes.
- Decorative color. Color is for status and the single accent only.
- Tiny or cramped text (no walls of 11px labels).
- Boxes around everything. Prefer spacing and type over borders; no nested cards.

## Principles

1. Information first: the job's title, company, location, status and description are the page; chrome recedes.
2. Readable long-form text: descriptions cap at ~70ch with real paragraph and list rhythm.
3. One accent, used for the primary action and links only.
4. Both themes are first-class (light and dark), using the shared tokens in `css/cariara.css`.

## Accessibility

WCAG 2.2 AA contrast in both themes, visible focus states, full keyboard operation, respects reduced motion.
