"""
Token Management API endpoints for Bluestakes token caching system.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
from config.supabase_client import get_service_client
from utils.auth import verify_api_key
from utils.encryption import encrypt_password, EncryptionError
from utils.bluestakes import get_bluestakes_auth_token_raw
from utils.bluestakes_token_manager import (
    get_token_stats,
    cleanup_expired_tokens,
    clear_token,
    is_token_valid
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tokens", tags=["Token Management"])


# Pydantic models for credential management
class CredentialsTestData(BaseModel):
    company_id: int
    username: str
    credentials_tested: bool
    credentials_valid: bool
    credentials_stored: bool
    test_error: Optional[str] = None
    storage_error: Optional[str] = None
    company_name: Optional[str] = None

class CredentialsStoreResponse(BaseModel):
    success: bool
    message: str
    data: CredentialsTestData
    error: Optional[str] = None


# Credential Management Endpoints

@router.post("/credentials/{company_id}", response_model=CredentialsStoreResponse)
async def store_bluestakes_credentials(
    company_id: int,
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password"),
    api_key: str = Depends(verify_api_key)
):
    """
    Store BlueStakes credentials for a company after testing them.
    
    This endpoint:
    1. Tests credentials against BlueStakes API
    2. Encrypts password if credentials are valid
    3. Stores encrypted credentials in database
    4. Returns frontend-friendly response with validation results
    """
    # Initialize response structure for frontend
    response = {
        "success": False,
        "message": "",
        "data": {
            "company_id": company_id,
            "username": username,
            "credentials_tested": False,
            "credentials_valid": False,
            "credentials_stored": False,
            "test_error": None,
            "storage_error": None
        },
        "error": None
    }
    
    try:
        # Step 1: Validate input
        if not username or not password:
            response["error"] = "USERNAME_PASSWORD_REQUIRED"
            response["message"] = "Both username and password are required"
            raise HTTPException(status_code=400, detail=response)
        
        # Step 2: Verify company exists
        company_check = (get_service_client()
                        .schema("public")
                        .table("companies")
                        .select("id, name")
                        .eq("id", company_id)
                        .execute())
        
        if not company_check.data:
            response["error"] = "COMPANY_NOT_FOUND"
            response["message"] = f"Company with ID {company_id} not found"
            raise HTTPException(status_code=404, detail=response)
        
        company_name = company_check.data[0]["name"]
        logger.info(f"Testing credentials for company {company_id} ({company_name})")
        
        # Step 3: Test credentials against BlueStakes API
        response["data"]["credentials_tested"] = True
        
        try:
            logger.info(f"Testing BlueStakes authentication for company {company_id}")
            token = await get_bluestakes_auth_token_raw(username, password)
            
            if token:
                response["data"]["credentials_valid"] = True
                logger.info(f"✓ Credentials valid for company {company_id}")
            else:
                response["data"]["credentials_valid"] = False
                response["data"]["test_error"] = "Authentication returned empty token"
                response["error"] = "INVALID_CREDENTIALS"
                response["message"] = "BlueStakes credentials are invalid - authentication failed"
                raise HTTPException(status_code=401, detail=response)
                
        except HTTPException as auth_error:
            # BlueStakes API returned an error (likely invalid credentials)
            response["data"]["credentials_valid"] = False
            response["data"]["test_error"] = str(auth_error.detail) if hasattr(auth_error, 'detail') else str(auth_error)
            response["error"] = "INVALID_CREDENTIALS"
            response["message"] = "BlueStakes credentials are invalid - please check username and password"
            logger.warning(f"❌ Invalid credentials for company {company_id}: {response['data']['test_error']}")
            raise HTTPException(status_code=401, detail=response)
            
        except Exception as auth_error:
            # Network or other error during authentication
            response["data"]["test_error"] = str(auth_error)
            response["error"] = "AUTHENTICATION_ERROR"
            response["message"] = "Unable to test credentials - BlueStakes API may be unavailable"
            logger.error(f"❌ Authentication error for company {company_id}: {str(auth_error)}")
            raise HTTPException(status_code=503, detail=response)
        
        # Step 4: Encrypt password (credentials are valid)
        try:
            encrypted_password = encrypt_password(password)
            logger.info(f"✓ Password encrypted successfully for company {company_id}")
        except EncryptionError as e:
            response["data"]["storage_error"] = str(e)
            response["error"] = "ENCRYPTION_ERROR"
            response["message"] = "Failed to encrypt password - server configuration issue"
            logger.error(f"❌ Password encryption failed for company {company_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=response)
        
        # Step 5: Store encrypted credentials in database
        try:
            result = (get_service_client()
                     .schema("public")
                     .table("companies")
                     .update({
                         "bluestakes_username": username,
                         "bluestakes_password": encrypted_password
                     })
                     .eq("id", company_id)
                     .execute())
            
            if not result.data:
                response["data"]["storage_error"] = "Database update returned no data"
                response["error"] = "STORAGE_ERROR"
                response["message"] = "Failed to store credentials in database"
                raise HTTPException(status_code=500, detail=response)
            
            response["data"]["credentials_stored"] = True
            logger.info(f"✓ Encrypted credentials stored successfully for company {company_id}")
            
        except Exception as storage_error:
            response["data"]["storage_error"] = str(storage_error)
            response["error"] = "STORAGE_ERROR"
            response["message"] = "Failed to store credentials in database"
            logger.error(f"❌ Database storage failed for company {company_id}: {str(storage_error)}")
            raise HTTPException(status_code=500, detail=response)
        
        # Step 6: Success response
        response["success"] = True
        response["message"] = f"BlueStakes credentials successfully tested and stored for {company_name}"
        response["data"]["company_name"] = company_name
        
        logger.info(f"🎉 Complete success for company {company_id}: credentials tested, encrypted, and stored")
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions with our custom response format
        raise
    except Exception as e:
        # Catch any unexpected errors
        response["error"] = "UNEXPECTED_ERROR"
        response["message"] = "An unexpected error occurred while processing credentials"
        response["data"]["storage_error"] = str(e)
        logger.error(f"❌ Unexpected error for company {company_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=response)


@router.post("/credentials/test", response_model=CredentialsStoreResponse)
async def test_bluestakes_credentials(
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password"),
    api_key: str = Depends(verify_api_key)
):
    """
    Test BlueStakes credentials without storing them.
    
    This endpoint only validates credentials against the BlueStakes API
    and returns the test results. Useful for frontend validation before
    actually storing credentials.
    """
    # Initialize response structure
    response = {
        "success": False,
        "message": "",
        "data": {
            "company_id": 0,  # Not applicable for test-only
            "username": username,
            "credentials_tested": False,
            "credentials_valid": False,
            "credentials_stored": False,  # Always false for test-only
            "test_error": None,
            "storage_error": None
        },
        "error": None
    }
    
    try:
        # Validate input
        if not username or not password:
            response["error"] = "USERNAME_PASSWORD_REQUIRED"
            response["message"] = "Both username and password are required"
            raise HTTPException(status_code=400, detail=response)
        
        # Test credentials against BlueStakes API
        response["data"]["credentials_tested"] = True
        
        try:
            logger.info(f"Testing BlueStakes authentication for username: {username}")
            token = await get_bluestakes_auth_token_raw(username, password)
            
            if token:
                response["data"]["credentials_valid"] = True
                response["success"] = True
                response["message"] = "BlueStakes credentials are valid"
                logger.info(f"✓ Credentials valid for username: {username}")
            else:
                response["data"]["credentials_valid"] = False
                response["data"]["test_error"] = "Authentication returned empty token"
                response["error"] = "INVALID_CREDENTIALS"
                response["message"] = "BlueStakes credentials are invalid - authentication failed"
                
        except HTTPException as auth_error:
            # BlueStakes API returned an error (likely invalid credentials)
            response["data"]["credentials_valid"] = False
            response["data"]["test_error"] = str(auth_error.detail) if hasattr(auth_error, 'detail') else str(auth_error)
            response["error"] = "INVALID_CREDENTIALS"
            response["message"] = "BlueStakes credentials are invalid - please check username and password"
            logger.warning(f"❌ Invalid credentials for username: {username}")
            
        except Exception as auth_error:
            # Network or other error during authentication
            response["data"]["test_error"] = str(auth_error)
            response["error"] = "AUTHENTICATION_ERROR"
            response["message"] = "Unable to test credentials - BlueStakes API may be unavailable"
            logger.error(f"❌ Authentication error for username {username}: {str(auth_error)}")
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions with our custom response format
        raise
    except Exception as e:
        # Catch any unexpected errors
        response["error"] = "UNEXPECTED_ERROR"
        response["message"] = "An unexpected error occurred while testing credentials"
        response["data"]["test_error"] = str(e)
        logger.error(f"❌ Unexpected error testing credentials for username {username}: {str(e)}")
        raise HTTPException(status_code=500, detail=response)


# Token Management Endpoints

@router.get("/stats")
async def get_token_statistics(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """
    Get statistics about cached Bluestakes tokens.
    
    Returns:
        Dictionary with token cache statistics
    """
    try:
        stats = await get_token_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting token stats: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving token statistics: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_expired_tokens_endpoint(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """
    Manually clean up expired tokens from the database.
    
    Returns:
        Number of tokens cleaned up
    """
    try:
        cleaned_count = await cleanup_expired_tokens()
        return {
            "success": True,
            "message": f"Cleaned up {cleaned_count} expired tokens",
            "tokens_cleaned": cleaned_count
        }
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up tokens: {str(e)}"
        )


@router.delete("/{company_id}")
async def clear_company_token(company_id: int, api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """
    Clear/invalidate a cached token for a specific company.
    
    Args:
        company_id: Company ID to clear token for
        
    Returns:
        Success confirmation
    """
    try:
        success = await clear_token(company_id)
        if success:
            return {
                "success": True,
                "message": f"Token cleared for company {company_id}",
                "company_id": company_id
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No token found for company {company_id} or failed to clear"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing token for company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing token: {str(e)}"
        )


@router.get("/{company_id}/status")
async def check_token_status(company_id: int, api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    """
    Check if a company has a valid cached token.
    
    Args:
        company_id: Company ID to check
        
    Returns:
        Token validity status
    """
    try:
        is_valid = await is_token_valid(company_id)
        return {
            "success": True,
            "company_id": company_id,
            "has_valid_token": is_valid
        }
    except Exception as e:
        logger.error(f"Error checking token status for company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking token status: {str(e)}"
        )
