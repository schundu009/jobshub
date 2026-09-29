# Jobshub: Google sign-in and search visibility

Jobshub currently uses https://jobs.cariara.com. Renaming the GitHub repository does not change the website domain.

## Google sign-in

The existing Authlib authorization-code flow requests only `openid email profile`. Google verifies the identity token; Jobshub requires a verified email and rejects disabled or locked accounts. The browser uses `/auth/providers` to show an unavailable state when credentials are missing.

Set these backend environment variables:

- `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: a Google Cloud **Web application** OAuth client. Never put its secret in frontend files.
- `BACKEND_URL`: the externally reachable backend origin. The callback is exactly `${BACKEND_URL}/auth/google/callback`.
- `JOBS_FRONTEND_URL`: `https://jobs.cariara.com` in production, or `http://localhost:3000` locally.
- `SECRET_KEY`: a strong, stable session/JWT signing secret.
- `ENV=production` for HTTPS session cookies in production.
- `ALLOWED_ORIGINS`: include the frontend origin for local or custom-domain requests.

In Google Cloud, register the callback `https://cariara-backend.up.railway.app/auth/google/callback` for the current production backend. Add `http://localhost:8000/auth/google/callback` to the development client. Configure the OAuth consent screen and authorized domains, and add test users if the app is in testing mode. Verify a real sign-in with an authorized Google account after deployment; mocked automated tests do not establish that Google Cloud configuration is correct.

Reference: https://developers.google.com/identity/protocols/oauth2/web-server

## Search visibility

The public homepage is served at `/` with a canonical URL, description, social metadata, and `WebSite` structured data. `sitemap.xml` lists this public URL. Personal/account pages and the admin portal have `noindex` metadata. They are not blocked in robots.txt, so crawlers can read the noindex instruction. No private jobs are advertised as public JobPosting structured data.

After deployment, verify `https://jobs.cariara.com/` as a property in Google Search Console. Use a verification method available to the domain owner (such as a DNS TXT record), then submit `https://jobs.cariara.com/sitemap.xml`. Use URL Inspection to request indexing of the homepage. Search Console verification and actual indexing are external steps; they are not performed by committing the code.

If the public domain changes, update the homepage canonical, Open Graph URL, JSON-LD URL, sitemap, robots sitemap reference, `JOBS_FRONTEND_URL`, CORS origins, and Google Cloud settings together.

References:
- https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag
- https://developers.google.com/search/docs/crawling-indexing/ask-google-to-recrawl

## Local verification

```sh
source venv/bin/activate
python -m pytest backend/tests -q
python -m http.server 3000 --directory jobs-app
# Separate terminal; uses the configured database:
cd backend
../venv/bin/uvicorn main:app --reload --port 8000
```

The jobs frontend remains plain HTML/CSS/JavaScript. No build tool or new frontend dependencies are required. Static assets use revalidation rather than year-long immutable caching because their filenames are not content-hashed.
