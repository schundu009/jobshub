"""
Security utilities for authentication and input validation.

Provides password hashing, JWT tokens, SSRF protection, and URL validation.
"""

import ipaddress
import socket
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import Tuple, Optional

import re
from passlib.context import CryptContext
from jose import JWTError, jwt

try:
    from config import settings
except ImportError:
    from backend.config import settings


# =============================================================================
# PASSWORD HASHING
# =============================================================================

import bcrypt as _bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    # Encode password to bytes
    password_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = _bcrypt.gensalt()
    hashed = _bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return _bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# =============================================================================
# JWT TOKENS
# =============================================================================

def create_access_token(user_id: int, email: str, role: str = "user") -> Tuple[str, str]:
    """
    Create a JWT access token.

    Args:
        user_id: The user's ID
        email: The user's email
        role: The user's role (user, admin)

    Returns:
        Tuple of (encoded JWT token string, token ID for revocation)
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    token_id = secrets.token_urlsafe(16)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "type": "access",
        "jti": token_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_id


def create_refresh_token(user_id: int) -> Tuple[str, str]:
    """
    Create a JWT refresh token.

    Args:
        user_id: The user's ID

    Returns:
        Tuple of (encoded JWT token, token ID for revocation tracking)
    """
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_expire_days
    )
    token_id = secrets.token_urlsafe(32)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": token_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, token_id


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None


def generate_verification_token() -> str:
    """Generate a secure random token for email verification."""
    return secrets.token_urlsafe(32)


def generate_password_reset_token() -> str:
    """Generate a secure random token for password reset."""
    return secrets.token_urlsafe(32)


# =============================================================================
# SSRF PROTECTION
# =============================================================================


# Blocked hostnames (internal/metadata endpoints)
BLOCKED_HOSTNAMES = {
    'localhost',
    '127.0.0.1',
    '::1',
    '0.0.0.0',
    '169.254.169.254',  # AWS/GCP/Azure metadata
    'metadata.google.internal',
    'metadata.google',
    '100.100.100.200',  # Alibaba Cloud metadata
}

# Blocked hostname patterns
BLOCKED_HOSTNAME_PATTERNS = [
    r'^10\.\d+\.\d+\.\d+$',  # 10.x.x.x
    r'^172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+$',  # 172.16-31.x.x
    r'^192\.168\.\d+\.\d+$',  # 192.168.x.x
    r'^127\.\d+\.\d+\.\d+$',  # 127.x.x.x loopback
    r'^169\.254\.\d+\.\d+$',  # Link-local
    r'^::1$',  # IPv6 loopback
    r'^fc\d{2}:',  # IPv6 private
    r'^fd\d{2}:',  # IPv6 private
]


def is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private/internal."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_link_local or
            ip.is_reserved or
            ip.is_multicast
        )
    except ValueError:
        return False


def validate_url_ssrf_safe(url: str) -> Tuple[bool, str]:
    """
    Validate a URL is safe from SSRF attacks.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url:
        return False, "URL is required"

    # Must start with http:// or https://
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return False, "URL must start with http:// or https://"

    try:
        parsed = urlparse(url)

        # Must have a hostname
        if not parsed.hostname:
            return False, "URL must have a valid hostname"

        hostname = parsed.hostname.lower()

        # Check against blocked hostnames
        if hostname in BLOCKED_HOSTNAMES:
            return False, f"Access to {hostname} is not allowed"

        # Check against blocked patterns
        for pattern in BLOCKED_HOSTNAME_PATTERNS:
            if re.match(pattern, hostname):
                return False, f"Access to internal IP ranges is not allowed"

        # Check if hostname is an IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if is_private_ip(hostname):
                return False, "Access to private/internal IPs is not allowed"
        except ValueError:
            # Not an IP, it's a hostname - try to resolve it
            try:
                resolved_ips = socket.getaddrinfo(hostname, None)
                for result in resolved_ips:
                    ip_str = result[4][0]
                    if is_private_ip(ip_str):
                        return False, f"Hostname {hostname} resolves to private IP"
            except socket.gaierror:
                # Can't resolve - might be valid, let the request fail naturally
                pass

        # Block dangerous ports
        dangerous_ports = {22, 23, 25, 110, 143, 993, 995, 3306, 5432, 6379, 27017}
        if parsed.port and parsed.port in dangerous_ports:
            return False, f"Port {parsed.port} is not allowed"

        return True, ""

    except Exception as e:
        return False, f"Invalid URL: {str(e)}"


def validate_url_format(url: str) -> Tuple[bool, str]:
    """
    Basic URL format validation (without SSRF checks).

    For use in validators where SSRF check happens at request time.
    """
    if not url:
        return False, "URL is required"

    if not re.match(r'^https?://', url, re.IGNORECASE):
        return False, "URL must start with http:// or https://"

    try:
        parsed = urlparse(url)
        if not parsed.hostname:
            return False, "URL must have a valid hostname"
        return True, ""
    except Exception as e:
        return False, f"Invalid URL: {str(e)}"
