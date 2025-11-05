#!/usr/bin/env python3
"""
Test script for password encryption functionality.

This script tests:
1. Encryption key validation
2. Password encryption/decryption roundtrip
3. Safe decryption with mixed encrypted/plain-text passwords
4. Error handling for invalid keys/passwords

Usage:
    python test_encryption.py
"""

import os
import sys
import logging
from datetime import datetime

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.encryption import (
    encrypt_password, 
    decrypt_password, 
    safe_decrypt_password,
    is_encrypted_password,
    get_encryption_key,
    EncryptionError
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_encryption_key():
    """Test encryption key validation."""
    logger.info("Testing encryption key validation...")
    
    try:
        key = get_encryption_key()
        logger.info("✓ Encryption key is valid and accessible")
        return True
    except EncryptionError as e:
        logger.error(f"❌ Encryption key error: {str(e)}")
        return False


def test_password_roundtrip():
    """Test password encryption/decryption roundtrip."""
    logger.info("Testing password encryption/decryption roundtrip...")
    
    test_passwords = [
        "simple_password",
        "complex_P@ssw0rd!123",
        "password with spaces",
        "unicode_password_🔐",
        "",  # Empty password
    ]
    
    success_count = 0
    
    for i, original_password in enumerate(test_passwords, 1):
        try:
            logger.info(f"Test {i}: Testing password encryption/decryption")
            
            # Encrypt
            encrypted = encrypt_password(original_password)
            logger.info(f"  Original: '{original_password}' (length: {len(original_password)})")
            logger.info(f"  Encrypted: '{encrypted[:50]}...' (length: {len(encrypted)})")
            
            # Verify it looks encrypted
            if original_password and not is_encrypted_password(encrypted):
                logger.error(f"  ❌ Encrypted password doesn't look encrypted")
                continue
            
            # Decrypt
            decrypted = decrypt_password(encrypted)
            logger.info(f"  Decrypted: '{decrypted}' (length: {len(decrypted)})")
            
            # Verify roundtrip
            if original_password == decrypted:
                logger.info(f"  ✓ Roundtrip successful")
                success_count += 1
            else:
                logger.error(f"  ❌ Roundtrip failed: '{original_password}' != '{decrypted}'")
                
        except Exception as e:
            logger.error(f"  ❌ Test {i} failed: {str(e)}")
    
    logger.info(f"Password roundtrip tests: {success_count}/{len(test_passwords)} passed")
    return success_count == len(test_passwords)


def test_safe_decryption():
    """Test safe decryption with mixed encrypted/plain-text passwords."""
    logger.info("Testing safe decryption with mixed password types...")
    
    # Test with plain-text password
    plain_password = "plain_text_password"
    try:
        result = safe_decrypt_password(plain_password)
        if result == plain_password:
            logger.info("✓ Safe decryption of plain-text password successful")
        else:
            logger.error(f"❌ Safe decryption failed: expected '{plain_password}', got '{result}'")
            return False
    except Exception as e:
        logger.error(f"❌ Safe decryption of plain-text failed: {str(e)}")
        return False
    
    # Test with encrypted password
    encrypted_password = encrypt_password("test_password")
    try:
        result = safe_decrypt_password(encrypted_password)
        if result == "test_password":
            logger.info("✓ Safe decryption of encrypted password successful")
        else:
            logger.error(f"❌ Safe decryption failed: expected 'test_password', got '{result}'")
            return False
    except Exception as e:
        logger.error(f"❌ Safe decryption of encrypted password failed: {str(e)}")
        return False
    
    # Test with empty password
    try:
        result = safe_decrypt_password("")
        if result == "":
            logger.info("✓ Safe decryption of empty password successful")
        else:
            logger.error(f"❌ Safe decryption of empty password failed: expected '', got '{result}'")
            return False
    except Exception as e:
        logger.error(f"❌ Safe decryption of empty password failed: {str(e)}")
        return False
    
    return True


def test_is_encrypted_detection():
    """Test encrypted password detection."""
    logger.info("Testing encrypted password detection...")
    
    # Test plain-text passwords
    plain_passwords = ["password123", "simple", "", "not_encrypted"]
    for password in plain_passwords:
        if is_encrypted_password(password):
            logger.error(f"❌ Plain-text password '{password}' detected as encrypted")
            return False
    
    logger.info("✓ Plain-text passwords correctly identified")
    
    # Test encrypted passwords
    test_password = "test_for_encryption"
    encrypted = encrypt_password(test_password)
    
    if not is_encrypted_password(encrypted):
        logger.error(f"❌ Encrypted password not detected as encrypted")
        return False
    
    logger.info("✓ Encrypted password correctly identified")
    return True


def test_error_handling():
    """Test error handling for invalid scenarios."""
    logger.info("Testing error handling...")
    
    # Test decryption of invalid encrypted data
    try:
        decrypt_password("invalid_encrypted_data")
        logger.error("❌ Should have failed to decrypt invalid data")
        return False
    except EncryptionError:
        logger.info("✓ Invalid encrypted data properly rejected")
    except Exception as e:
        logger.error(f"❌ Unexpected error type: {str(e)}")
        return False
    
    # Test with missing encryption key (temporarily)
    original_key = os.environ.get("ENCRYPTION_KEY")
    try:
        if "ENCRYPTION_KEY" in os.environ:
            del os.environ["ENCRYPTION_KEY"]
        
        encrypt_password("test")
        logger.error("❌ Should have failed with missing encryption key")
        return False
    except EncryptionError:
        logger.info("✓ Missing encryption key properly detected")
    except Exception as e:
        logger.error(f"❌ Unexpected error type: {str(e)}")
        return False
    finally:
        # Restore encryption key
        if original_key:
            os.environ["ENCRYPTION_KEY"] = original_key
    
    return True


def main():
    """Run all encryption tests."""
    logger.info("=" * 60)
    logger.info("STARTING ENCRYPTION TESTS")
    logger.info("=" * 60)
    
    tests = [
        ("Encryption Key Validation", test_encryption_key),
        ("Password Roundtrip", test_password_roundtrip),
        ("Safe Decryption", test_safe_decryption),
        ("Encrypted Detection", test_is_encrypted_detection),
        ("Error Handling", test_error_handling),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n--- {test_name} ---")
        try:
            if test_func():
                logger.info(f"✓ {test_name} PASSED")
                passed += 1
            else:
                logger.error(f"❌ {test_name} FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} FAILED with exception: {str(e)}")
    
    logger.info("\n" + "=" * 60)
    logger.info("ENCRYPTION TEST RESULTS")
    logger.info("=" * 60)
    logger.info(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Encryption is working correctly.")
        return 0
    else:
        logger.error("❌ Some tests failed. Please check the encryption implementation.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
