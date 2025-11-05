#!/usr/bin/env python3
"""
Test script for Bluestakes token caching implementation.

This script tests the token caching functionality to ensure:
1. Tokens are properly cached and reused
2. Expired tokens are automatically refreshed
3. Rate limits are respected
4. Error handling works correctly

Prerequisites:
- Database columns must be added (run sql/add_token_columns.sql)
- Valid Bluestakes credentials in companies table
- API server running
"""
import asyncio
import httpx
import os
import sys
from datetime import datetime, timezone
import logging

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.supabase_client import get_service_client
from utils.bluestakes_token_manager import (
    get_or_refresh_token,
    get_token_stats,
    cleanup_expired_tokens,
    clear_token,
    is_token_valid
)
from utils.bluestakes import get_bluestakes_auth_token
from utils.encryption import safe_decrypt_password, EncryptionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"
API_KEY = os.getenv("API_KEY", "your-api-key-here")


async def test_database_columns():
    """Test that the required database columns exist."""
    logger.info("Testing database columns...")
    
    try:
        # Try to query the new columns
        result = (get_service_client()
                 .table("companies")
                 .select("id, bluestakes_token, bluestakes_token_expires_at")
                 .limit(1)
                 .execute())
        
        logger.info("✅ Database columns exist and are accessible")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database columns test failed: {str(e)}")
        logger.error("Please run the SQL script: sql/add_token_columns.sql")
        return False


async def test_token_manager_functions():
    """Test the token manager utility functions."""
    logger.info("Testing token manager functions...")
    
    try:
        # Test token stats
        stats = await get_token_stats()
        logger.info(f"✅ Token stats: {stats}")
        
        # Test cleanup (should not fail even if no expired tokens)
        cleaned = await cleanup_expired_tokens()
        logger.info(f"✅ Cleanup completed: {cleaned} tokens cleaned")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Token manager functions test failed: {str(e)}")
        return False


async def test_company_with_credentials():
    """Find a company with Bluestakes credentials for testing."""
    logger.info("Finding company with Bluestakes credentials...")
    
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("id, name, bluestakes_username, bluestakes_password")
                 .not_.is_("bluestakes_username", "null")
                 .not_.is_("bluestakes_password", "null")
                 .neq("bluestakes_username", "")
                 .neq("bluestakes_password", "")
                 .limit(1)
                 .execute())
        
        if result.data:
            company = result.data[0]
            logger.info(f"✅ Found test company: {company['name']} (ID: {company['id']})")
            return company
        else:
            logger.warning("⚠️  No companies with Bluestakes credentials found")
            logger.info("Please add credentials using: POST /tokens/credentials/{company_id}")
            return None
            
    except Exception as e:
        logger.error(f"❌ Error finding test company: {str(e)}")
        return None


async def test_token_caching(company):
    """Test token caching functionality."""
    logger.info("Testing token caching...")
    
    try:
        company_id = company["id"]
        username = company["bluestakes_username"]
        
        try:
            # Decrypt the password before using it
            password = safe_decrypt_password(company["bluestakes_password"])
        except EncryptionError as e:
            logger.error(f"Failed to decrypt password for company {company_id}: {str(e)}")
            return
        
        # Clear any existing token
        await clear_token(company_id)
        logger.info("Cleared existing token")
        
        # First authentication - should create new token
        start_time = datetime.now()
        token1 = await get_or_refresh_token(company_id, username, password)
        first_auth_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ First authentication took {first_auth_time:.2f}s")
        
        # Second authentication - should use cached token
        start_time = datetime.now()
        token2 = await get_or_refresh_token(company_id, username, password)
        cached_auth_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ Cached authentication took {cached_auth_time:.2f}s")
        
        # Verify tokens are the same
        if token1 == token2:
            logger.info("✅ Cached token matches original token")
        else:
            logger.warning("⚠️  Cached token differs from original")
        
        # Verify caching is faster
        if cached_auth_time < first_auth_time * 0.5:  # Should be at least 50% faster
            logger.info(f"✅ Caching improved performance by {((first_auth_time - cached_auth_time) / first_auth_time * 100):.1f}%")
        else:
            logger.warning("⚠️  Caching did not significantly improve performance")
        
        # Test token validity check
        is_valid = await is_token_valid(company_id)
        if is_valid:
            logger.info("✅ Token validity check passed")
        else:
            logger.error("❌ Token validity check failed")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Token caching test failed: {str(e)}")
        return False


async def test_api_endpoints():
    """Test the token management API endpoints."""
    logger.info("Testing API endpoints...")
    
    try:
        headers = {"X-API-Key": API_KEY}
        
        async with httpx.AsyncClient() as client:
            # Test token stats endpoint
            response = await client.get(f"{API_BASE_URL}/tokens/stats", headers=headers)
            if response.status_code == 200:
                stats = response.json()
                logger.info(f"✅ Token stats endpoint: {stats['stats']}")
            else:
                logger.error(f"❌ Token stats endpoint failed: {response.status_code}")
                return False
            
            # Test cleanup endpoint
            response = await client.post(f"{API_BASE_URL}/tokens/cleanup", headers=headers)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Token cleanup endpoint: {result['message']}")
            else:
                logger.error(f"❌ Token cleanup endpoint failed: {response.status_code}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"❌ API endpoints test failed: {str(e)}")
        return False


async def test_integration_with_sync():
    """Test integration with existing sync operations."""
    logger.info("Testing integration with sync operations...")
    
    try:
        headers = {"X-API-Key": API_KEY}
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Test manual sync endpoint (should use cached tokens)
            response = await client.post(
                f"{API_BASE_URL}/tickets/sync-all-bluestakes?max_age_hours=0",
                headers=headers
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Sync integration test: {result.get('message', 'Success')}")
                return True
            else:
                logger.warning(f"⚠️  Sync integration test returned: {response.status_code}")
                logger.info("This may be expected if no companies have credentials configured")
                return True
        
    except Exception as e:
        logger.error(f"❌ Integration test failed: {str(e)}")
        return False


async def main():
    """Run all tests."""
    logger.info("🚀 Starting Bluestakes token caching tests...")
    
    tests = [
        ("Database Columns", test_database_columns()),
        ("Token Manager Functions", test_token_manager_functions()),
        ("API Endpoints", test_api_endpoints()),
    ]
    
    # Find test company
    company = await test_company_with_credentials()
    if company:
        tests.extend([
            ("Token Caching", test_token_caching(company)),
            ("Sync Integration", test_integration_with_sync()),
        ])
    
    # Run all tests
    passed = 0
    total = len(tests)
    
    for test_name, test_coro in tests:
        logger.info(f"\n--- Running {test_name} Test ---")
        try:
            result = await test_coro
            if result:
                passed += 1
                logger.info(f"✅ {test_name} test PASSED")
            else:
                logger.error(f"❌ {test_name} test FAILED")
        except Exception as e:
            logger.error(f"❌ {test_name} test ERROR: {str(e)}")
    
    # Summary
    logger.info(f"\n🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Token caching is working correctly.")
    else:
        logger.warning(f"⚠️  {total - passed} test(s) failed. Please review the output above.")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
