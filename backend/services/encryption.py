"""
Encryption utilities for sensitive data storage.

Uses Fernet symmetric encryption with a key derived from the ENCRYPTION_KEY
environment variable. There is deliberately no fallback key: if ENCRYPTION_KEY
is unset, every encrypt/decrypt call raises EncryptionNotConfigured (fail
closed) instead of silently using a well-known default.
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionNotConfigured(RuntimeError):
    """Raised when ENCRYPTION_KEY is missing or too short."""


MIN_KEY_LENGTH = 16


def _get_fernet() -> Fernet:
    """Get a Fernet instance for ENCRYPTION_KEY; raise if it is not configured."""
    key_source = (os.getenv("ENCRYPTION_KEY") or "").strip()
    if len(key_source) < MIN_KEY_LENGTH:
        raise EncryptionNotConfigured(
            "ENCRYPTION_KEY is not set (or shorter than 16 characters); refusing to encrypt/decrypt."
        )

    salt = b"jobtrails_salt_v1"  # Fixed salt for consistent key derivation
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_source.encode()))
    return Fernet(key)


def encrypt_value(value: str) -> str:
    """Encrypt a secret for storage. Empty input returns ""."""
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a stored secret. Empty input returns ""."""
    if not encrypted:
        return ""
    return _get_fernet().decrypt(encrypted.encode()).decode()


# Backwards-compatible names
encrypt_password = encrypt_value
decrypt_password = decrypt_value
