"""
Bluestakes Token Management System

Handles caching and automatic refresh of Bluestakes API authentication tokens
to reduce redundant login calls and respect API rate limits.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from config.supabase_client import get_service_client
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Default token TTL (1 hour)
DEFAULT_TOKEN_TTL_HOURS = 1


async def get_or_refresh_token(company_id: int, username: str, password: str) -> str:
    """
    Get a valid Bluestakes token for the company, refreshing if necessary.
    
    Args:
        company_id: Company ID to get token for
        username: Bluestakes username (for refresh if needed)
        password: Bluestakes password (for refresh if needed)
        
    Returns:
        Valid authentication token
        
    Raises:
        HTTPException: If authentication fails
    """
    try:
        # First, check if we have a valid cached token
        cached_token = await get_cached_token(company_id)
        if cached_token:
            logger.info(f"Using cached token for company {company_id}")
            return cached_token
        
        # No valid cached token, authenticate and store new token
        logger.info(f"No valid cached token for company {company_id}, authenticating...")
        from utils.bluestakes import get_bluestakes_auth_token_raw
        
        new_token = await get_bluestakes_auth_token_raw(username, password)
        await store_token(company_id, new_token)
        
        logger.info(f"Successfully authenticated and cached new token for company {company_id}")
        return new_token
        
    except Exception as e:
        logger.error(f"Error getting token for company {company_id}: {str(e)}")
        raise


async def get_cached_token(company_id: int) -> Optional[str]:
    """
    Get a cached token if it exists and is still valid.
    
    Args:
        company_id: Company ID to check
        
    Returns:
        Valid token or None if no valid token exists
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("bluestakes_token, bluestakes_token_expires_at")
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            return None
            
        company_data = result.data[0]
        token = company_data.get("bluestakes_token")
        expires_at_str = company_data.get("bluestakes_token_expires_at")
        
        if not token or not expires_at_str:
            return None
            
        # Parse expiration time
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        current_time = datetime.now(timezone.utc)
        
        # Check if token is still valid (with 5 minute buffer)
        buffer_time = timedelta(minutes=5)
        if current_time + buffer_time < expires_at:
            return token
        else:
            logger.info(f"Cached token for company {company_id} has expired")
            await clear_token(company_id)
            return None
            
    except Exception as e:
        logger.error(f"Error checking cached token for company {company_id}: {str(e)}")
        return None


async def store_token(company_id: int, token: str, ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS) -> bool:
    """
    Store a token with expiration time.
    
    Args:
        company_id: Company ID to store token for
        token: Authentication token to store
        ttl_hours: Time to live in hours (default: 1 hour)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        
        result = (get_service_client()
                 .table("companies")
                 .update({
                     "bluestakes_token": token,
                     "bluestakes_token_expires_at": expires_at.isoformat()
                 })
                 .eq("id", company_id)
                 .execute())
        
        success = bool(result.data)
        if success:
            logger.info(f"Stored token for company {company_id}, expires at {expires_at}")
        else:
            logger.warning(f"Failed to store token for company {company_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error storing token for company {company_id}: {str(e)}")
        return False


async def is_token_valid(company_id: int) -> bool:
    """
    Check if a company has a valid cached token.
    
    Args:
        company_id: Company ID to check
        
    Returns:
        True if valid token exists, False otherwise
    """
    cached_token = await get_cached_token(company_id)
    return cached_token is not None


async def clear_token(company_id: int) -> bool:
    """
    Clear/invalidate a stored token.
    
    Args:
        company_id: Company ID to clear token for
        
    Returns:
        True if successful, False otherwise
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .update({
                     "bluestakes_token": None,
                     "bluestakes_token_expires_at": None
                 })
                 .eq("id", company_id)
                 .execute())
        
        success = bool(result.data)
        if success:
            logger.info(f"Cleared token for company {company_id}")
        else:
            logger.warning(f"Failed to clear token for company {company_id}")
            
        return success
        
    except Exception as e:
        logger.error(f"Error clearing token for company {company_id}: {str(e)}")
        return False


async def cleanup_expired_tokens() -> int:
    """
    Clean up all expired tokens from the database.
    
    Returns:
        Number of tokens cleaned up
    """
    try:
        current_time = datetime.now(timezone.utc)
        
        # Find companies with expired tokens
        result = (get_service_client()
                 .table("companies")
                 .select("id")
                 .not_.is_("bluestakes_token", "null")
                 .lt("bluestakes_token_expires_at", current_time.isoformat())
                 .execute())
        
        if not result.data:
            return 0
            
        expired_company_ids = [row["id"] for row in result.data]
        
        # Clear expired tokens
        clear_result = (get_service_client()
                       .table("companies")
                       .update({
                           "bluestakes_token": None,
                           "bluestakes_token_expires_at": None
                       })
                       .in_("id", expired_company_ids)
                       .execute())
        
        cleaned_count = len(clear_result.data) if clear_result.data else 0
        logger.info(f"Cleaned up {cleaned_count} expired tokens")
        
        return cleaned_count
        
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {str(e)}")
        return 0


async def get_token_stats() -> Dict[str, Any]:
    """
    Get statistics about cached tokens.
    
    Returns:
        Dictionary with token statistics
    """
    try:
        current_time = datetime.now(timezone.utc)
        
        # Get all companies with tokens
        result = (get_service_client()
                 .table("companies")
                 .select("id, bluestakes_token, bluestakes_token_expires_at")
                 .not_.is_("bluestakes_token", "null")
                 .execute())
        
        if not result.data:
            return {
                "total_cached": 0,
                "valid_tokens": 0,
                "expired_tokens": 0,
                "expiring_soon": 0  # within 10 minutes
            }
        
        total_cached = len(result.data)
        valid_tokens = 0
        expired_tokens = 0
        expiring_soon = 0
        
        for row in result.data:
            expires_at_str = row.get("bluestakes_token_expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                
                if current_time >= expires_at:
                    expired_tokens += 1
                elif current_time + timedelta(minutes=10) >= expires_at:
                    expiring_soon += 1
                else:
                    valid_tokens += 1
        
        return {
            "total_cached": total_cached,
            "valid_tokens": valid_tokens,
            "expired_tokens": expired_tokens,
            "expiring_soon": expiring_soon
        }
        
    except Exception as e:
        logger.error(f"Error getting token stats: {str(e)}")
        return {
            "total_cached": 0,
            "valid_tokens": 0,
            "expired_tokens": 0,
            "expiring_soon": 0,
            "error": str(e)
        }
