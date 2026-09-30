"""
cariara.com sign-in on the jobportal API (services/cariara_identity.py).

GET /auth/cariara/whoami: which jobportal account a cariara.com token maps to.
Debug-safe: returns only the caller's own id, email, plan and admin flag.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import _user_from_cariara, is_admin, security
from models import ApplyPreference
from services.apply.plans import resolve_plan
from utils.security import decode_token

router = APIRouter(prefix="/auth/cariara", tags=["Authentication"])


@router.get("/whoami")
def cariara_whoami(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_cariara_token: Optional[str] = Header(None, alias="X-Cariara-Token"),
    db: Session = Depends(get_db),
):
    token = (x_cariara_token or "").strip() or (credentials.credentials if credentials else None)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    if decode_token(token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This is a jobportal token; send a cariara.com token")
    user = _user_from_cariara(token, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})

    prefs = db.query(ApplyPreference).filter(ApplyPreference.user_id == user.id).first()
    plan = resolve_plan(user, prefs.plan_override if prefs else None)
    identity = getattr(user, "cariara_identity", None)
    return {
        "jobportal_user_id": user.id,
        "email": user.email,
        "identity_source": user.identity_source,
        "plan": plan.plan_type,
        "plan_ok": plan.plan_ok,
        "cariara_plan": identity.plan if identity else None,
        "is_admin": is_admin(user),
        "cariara_admin": bool(identity and identity.cariara_admin),
    }
