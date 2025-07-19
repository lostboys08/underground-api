import os
import base64
from cryptography.fernet import Fernet
from typing import Optional
import logging

def get_encryption_key() -> bytes:
    """Get or generate encryption key for Bluestakes passwords"""
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        # In production, you should set this as an environment variable
        # For now, we'll use a default key (NOT secure for production)
        logging.warning("No ENCRYPTION_KEY found, using default (not secure for production)")
        key = "default-key-change-in-production-please"
    
    # Ensure key is 32 bytes for Fernet
    key_bytes = key.encode()
    if len(key_bytes) < 32:
        key_bytes = key_bytes.ljust(32, b'0')
    else:
        key_bytes = key_bytes[:32]
    
    return base64.urlsafe_b64encode(key_bytes)

def encrypt_password(password: str) -> Optional[bytes]:
    """Encrypt a password for storage"""
    if not password:
        return None
    
    fernet = Fernet(get_encryption_key())
    return fernet.encrypt(password.encode())

def decrypt_password(encrypted_password: bytes) -> Optional[str]:
    """Decrypt a password from storage"""
    if not encrypted_password:
        return None
    
    try:
        fernet = Fernet(get_encryption_key())
        return fernet.decrypt(encrypted_password).decode()
    except Exception as e:
        logging.error(f"Decryption failed: {str(e)}")
        logging.error(f"Encryption key exists: {bool(os.getenv('ENCRYPTION_KEY'))}")
        logging.error(f"Using default key: {not bool(os.getenv('ENCRYPTION_KEY'))}")
        logging.error(f"Encrypted password type: {type(encrypted_password)}")
        logging.error(f"Encrypted password length: {len(encrypted_password) if encrypted_password else 'None'}")
        logging.error(f"Encrypted password preview: {str(encrypted_password)[:50] if encrypted_password else 'None'}")
        raise 