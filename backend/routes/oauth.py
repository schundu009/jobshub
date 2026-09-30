"""
OAuth authentication routes for Google, LinkedIn, and GitHub.

Handles social login flow:
1. User clicks social login button
2. Redirect to provider's authorization page
3. Provider redirects back with code
4. Exchange code for tokens and user info
5. Create/update user and return JWT tokens
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from starlette.requests import Request
import httpx
import secrets
from typing import Literal
from urllib.parse import urlencode
from utils.security import as_utc

try:
    from database import get_db
    from models import User
    from utils.security import create_access_token, create_refresh_token
    from config import settings
except ImportError:
    from database import get_db
    from models import User
    from utils.security import create_access_token, create_refresh_token
    from config import settings


router = APIRouter(prefix="/auth", tags=["OAuth"])

# Initialize OAuth
oauth = OAuth()

# Register Google OAuth
if settings.google_client_id:
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# Register GitHub OAuth
if settings.github_client_id:
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )

# LinkedIn OAuth - handled manually due to JWKS issues with authlib


def get_or_create_oauth_user(
    db: Session,
    email: str,
    name: str,
    provider: str,
    provider_id: str
) -> User:
    """Get existing user or create new one from OAuth data."""
    # Try to find user by email
    user = db.query(User).filter(User.email == email.lower()).first()

    if user:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account is disabled")
        if user.locked_until and as_utc(user.locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Account is temporarily locked")
        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        # Mark email as verified since OAuth provider verified it
        user.is_email_verified = True
        db.commit()
        return user

    # Create new user
    user = User(
        email=email.lower(),
        name=name,
        is_email_verified=True,  # OAuth providers verify email
        role="user",
        is_active=True,
        # No password_hash - user can set one later if they want
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def aiapply_callback_url() -> str:
    """Fixed AIApply landing page for OAuth results (never caller-supplied)."""
    return f"{settings.aiapply_url.rstrip('/')}/auth/callback"


async def create_frontend_redirect(user: User, portal: str = "admin") -> RedirectResponse:
    """Create redirect to frontend with tokens in URL fragment."""
    import json
    access_token, _ = create_access_token(user.id, user.email, user.role)
    refresh_token, _ = create_refresh_token(user.id)

    # Determine redirect URL based on portal (separate domains)
    if portal == "jobs":
        base_url = f"{settings.jobs_frontend_url.rstrip('/')}/login.html"
    elif portal == "aiapply":
        base_url = aiapply_callback_url()
    elif portal == "ascend":
        base_url = "https://capra.cariara.com/login"
    else:
        base_url = "https://cariara.com/jobs/admin/login.html"

    # Encode each value once so names and email addresses cannot alter the fragment.
    fragment = urlencode({
        "access_token": access_token, "refresh_token": refresh_token,
        "user_id": user.id, "user_email": user.email, "user_name": user.name or "",
        "user_role": user.role or "user",
        "onboarding_completed": str(bool(user.onboarding_completed)).lower(),
        "roles_confirmed": str(bool(user.roles_confirmed_at)).lower(),
        "job_roles": json.dumps(user.job_roles or []),
        "has_jobs_access": "true", "plan_type": "pro",
    })
    response = RedirectResponse(url=f"{base_url}#{fragment}")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/providers")
def available_providers():
    """Expose availability, never OAuth credentials."""
    return {
        "google": bool(settings.google_client_id and settings.google_client_secret),
        "github": bool(settings.github_client_id and settings.github_client_secret),
        "linkedin": bool(settings.linkedin_client_id and settings.linkedin_client_secret),
    }


# =============================================================================
# GOOGLE OAUTH
# =============================================================================

@router.get("/google/login")
async def google_login(request: Request, redirect: Literal["jobs", "admin", "ascend", "aiapply"] = "jobs"):
    """Initiate Google OAuth login."""
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth not configured"
        )
    # Store portal redirect in session
    request.session["oauth_portal"] = redirect
    redirect_uri = f"{settings.backend_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback."""
    portal = request.session.pop("oauth_portal", "jobs")
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if not user_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google"
            )

        email = user_info.get("email")
        google_id = user_info.get("sub")
        if not email or not google_id or user_info.get("email_verified") is not True:
            raise HTTPException(status_code=400, detail="A verified Google email is required")
        name = user_info.get("name") or email.split("@")[0]

        user = get_or_create_oauth_user(db, email, name, "google", google_id)
        return await create_frontend_redirect(user, portal)

    except Exception as e:
        # Redirect to login with error
        if portal == "jobs":
            error_base = f"{settings.jobs_frontend_url.rstrip('/')}/login.html"
        elif portal == "aiapply":
            error_base = aiapply_callback_url()
        elif portal == "ascend":
            error_base = "https://ascend.cariara.com/login"
        else:
            error_base = "https://cariara.com/jobs/admin/login.html"
        error_url = f"{error_base}#" + urlencode({"error": "oauth_failed", "message": "Google sign-in could not be completed. Try again or sign in with your email."})
        return RedirectResponse(url=error_url)


# =============================================================================
# GITHUB OAUTH
# =============================================================================

@router.get("/github/login")
async def github_login(request: Request, redirect: str = "admin"):
    """Initiate GitHub OAuth login."""
    if not settings.github_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="GitHub OAuth not configured"
        )
    # Store portal redirect in session
    request.session["oauth_portal"] = redirect
    redirect_uri = f"{settings.backend_url}/auth/github/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/github/callback")
async def github_callback(request: Request, db: Session = Depends(get_db)):
    """Handle GitHub OAuth callback."""
    portal = request.session.get("oauth_portal", "admin")
    try:
        token = await oauth.github.authorize_access_token(request)
        access_token = token.get("access_token")

        # Get user info from GitHub API
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # Get user profile
            user_resp = await client.get("https://api.github.com/user", headers=headers)
            user_data = user_resp.json()

            # Get user emails (primary email might not be in profile)
            emails_resp = await client.get("https://api.github.com/user/emails", headers=headers)
            emails_data = emails_resp.json()

            # Find primary email
            email = None
            for email_obj in emails_data:
                if email_obj.get("primary"):
                    email = email_obj.get("email")
                    break

            if not email:
                email = user_data.get("email") or emails_data[0].get("email") if emails_data else None

            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not get email from GitHub"
                )

            name = user_data.get("name") or user_data.get("login")
            github_id = str(user_data.get("id"))

            user = get_or_create_oauth_user(db, email, name, "github", github_id)
            return await create_frontend_redirect(user, portal)

    except Exception as e:
        error_base = "https://jobs.cariara.com/login.html" if portal == "jobs" else ("https://ascend.cariara.com/login" if portal == "ascend" else "https://cariara.com/jobs/admin/login.html")
        error_url = f"{error_base}#error=oauth_failed&message={str(e)}"
        return RedirectResponse(url=error_url)


# =============================================================================
# LINKEDIN OAUTH (Manual implementation - LinkedIn doesn't support full OIDC)
# =============================================================================

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"

@router.get("/linkedin/login")
async def linkedin_login(request: Request, redirect: str = "admin"):
    """Initiate LinkedIn OAuth login."""
    if not settings.linkedin_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LinkedIn OAuth not configured"
        )

    # Generate state for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session["linkedin_oauth_state"] = state
    # Store portal redirect in session
    request.session["oauth_portal"] = redirect

    redirect_uri = f"{settings.backend_url}/auth/linkedin/callback"
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "openid profile email",
    }

    auth_url = f"{LINKEDIN_AUTH_URL}?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url=auth_url)


@router.get("/linkedin/callback")
async def linkedin_callback(request: Request, db: Session = Depends(get_db)):
    """Handle LinkedIn OAuth callback."""
    portal = request.session.get("oauth_portal", "admin")
    try:
        # Verify state
        code = request.query_params.get("code")
        state = request.query_params.get("state")
        stored_state = request.session.get("linkedin_oauth_state")

        if not code:
            error = request.query_params.get("error_description", "Authorization failed")
            raise Exception(error)

        if state != stored_state:
            raise Exception("Invalid state parameter")

        # Exchange code for token
        redirect_uri = f"{settings.backend_url}/auth/linkedin/callback"
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                LINKEDIN_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.linkedin_client_id,
                    "client_secret": settings.linkedin_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if token_resp.status_code != 200:
                raise Exception(f"Token exchange failed: {token_resp.text}")

            token_data = token_resp.json()
            access_token = token_data.get("access_token")

        # Get user info from LinkedIn API using OpenID Connect userinfo endpoint
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {access_token}"}

            # Use OpenID Connect userinfo endpoint
            userinfo_resp = await client.get(
                "https://api.linkedin.com/v2/userinfo",
                headers=headers
            )
            user_data = userinfo_resp.json()

            email = user_data.get("email")
            name = user_data.get("name")
            linkedin_id = user_data.get("sub")

            if not email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not get email from LinkedIn"
                )

            if not name:
                given_name = user_data.get("given_name", "")
                family_name = user_data.get("family_name", "")
                name = f"{given_name} {family_name}".strip() or email.split("@")[0]

            user = get_or_create_oauth_user(db, email, name, "linkedin", linkedin_id)
            return await create_frontend_redirect(user, portal)

    except Exception as e:
        error_base = "https://jobs.cariara.com/login.html" if portal == "jobs" else ("https://ascend.cariara.com/login" if portal == "ascend" else "https://cariara.com/jobs/admin/login.html")
        error_url = f"{error_base}#error=oauth_failed&message={str(e)}"
        return RedirectResponse(url=error_url)
