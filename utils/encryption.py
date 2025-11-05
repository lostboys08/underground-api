"""
Encryption utilities for securing sensitive data like passwords.
Uses Fernet symmetric encryption from the cryptography library.
"""

import os
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Custom exception for encryption-related errors"""
    pass


def get_encryption_key() -> bytes:
    """
    Get the encryption key from environment variables.
    
    Returns:
        bytes: The encryption key
        
    Raises:
        EncryptionError: If the key is missing or invalid
    """
    key_str = os.getenv("ENCRYPTION_KEY")
    
    if not key_str:
        raise EncryptionError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    
    try:
        # Validate that it's a proper Fernet key by trying to create a Fernet instance
        key_bytes = key_str.encode()
        Fernet(key_bytes)
        return key_bytes
    except Exception as e:
        raise EncryptionError(
            f"Invalid ENCRYPTION_KEY format. Must be a valid Fernet key (32 bytes, base64-encoded). "
            f"Generate a new one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\". "
            f"Error: {str(e)}"
        )


def encrypt_password(password: str) -> str:
    """
    Encrypt a password using Fernet encryption.
    
    Args:
        password: The plain text password to encrypt
        
    Returns:
        str: The encrypted password as a base64-encoded string
        
    Raises:
        EncryptionError: If encryption fails
    """
    if not password:
        return password  # Don't encrypt empty passwords
    
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        encrypted_bytes = fernet.encrypt(password.encode())
        return encrypted_bytes.decode()
    except Exception as e:
        logger.error(f"Failed to encrypt password: {str(e)}")
        raise EncryptionError(f"Password encryption failed: {str(e)}")


def decrypt_password(encrypted_password: str) -> str:
    """
    Decrypt a password using Fernet encryption.
    
    Args:
        encrypted_password: The encrypted password as a base64-encoded string
        
    Returns:
        str: The decrypted plain text password
        
    Raises:
        EncryptionError: If decryption fails
    """
    if not encrypted_password:
        return encrypted_password  # Don't decrypt empty passwords
    
    try:
        key = get_encryption_key()
        fernet = Fernet(key)
        decrypted_bytes = fernet.decrypt(encrypted_password.encode())
        return decrypted_bytes.decode()
    except InvalidToken:
        # This might be a plain text password that hasn't been encrypted yet
        logger.warning("Failed to decrypt password - might be plain text")
        raise EncryptionError("Password decryption failed - invalid encrypted format")
    except Exception as e:
        logger.error(f"Failed to decrypt password: {str(e)}")
        raise EncryptionError(f"Password decryption failed: {str(e)}")


def is_encrypted_password(password: str) -> bool:
    """
    Check if a password appears to be encrypted (Fernet format).
    
    Args:
        password: The password string to check
        
    Returns:
        bool: True if the password appears to be encrypted, False otherwise
    """
    if not password:
        return False
    
    try:
        # Fernet tokens are base64-encoded and start with 'gAAAAA'
        # This is a heuristic check - not 100% reliable but good enough
        if password.startswith('gAAAAA') and len(password) > 40:
            # Try to decrypt to verify it's actually encrypted
            decrypt_password(password)
            return True
    except EncryptionError:
        pass
    
    return False


def safe_decrypt_password(password: str) -> str:
    """
    Safely decrypt a password, handling both encrypted and plain text passwords.
    This is useful during migration when some passwords might still be plain text.
    
    Args:
        password: The password (either encrypted or plain text)
        
    Returns:
        str: The plain text password
        
    Raises:
        EncryptionError: If encryption key is missing or invalid
    """
    if not password:
        return password
    
    # Check if it looks like an encrypted password
    if is_encrypted_password(password):
        try:
            return decrypt_password(password)
        except EncryptionError:
            logger.warning("Password appears encrypted but decryption failed")
            raise
    else:
        # Assume it's plain text (for backward compatibility during migration)
        logger.info("Password appears to be plain text")
        return password
