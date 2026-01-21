"""
Encryption utilities for sensitive data storage.

Uses Fernet symmetric encryption with a key derived from environment variable.
"""

import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _get_fernet() -> Fernet:
    """Get Fernet instance using encryption key from environment."""
    # Get encryption key from environment or use a default for development
    key_source = os.getenv("ENCRYPTION_KEY", "jobtrails-dev-encryption-key-change-in-prod")

    # Derive a proper Fernet key from the source
    salt = b"jobtrails_salt_v1"  # Fixed salt for consistent key derivation
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_source.encode()))

    return Fernet(key)


def encrypt_password(password: str) -> str:
    """
    Encrypt a password for storage.

    Args:
        password: Plain text password

    Returns:
        Encrypted password as base64 string
    """
    if not password:
        return ""

    fernet = _get_fernet()
    encrypted = fernet.encrypt(password.encode())
    return encrypted.decode()


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt a stored password.

    Args:
        encrypted_password: Encrypted password from storage

    Returns:
        Plain text password
    """
    if not encrypted_password:
        return ""

    fernet = _get_fernet()
    decrypted = fernet.decrypt(encrypted_password.encode())
    return decrypted.decode()
