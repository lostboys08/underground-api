from typing import Optional
from fastapi import HTTPException, Depends, Header, Request
from config.supabase_client import get_user_client
import os

# API Key Authentication
async def get_api_key(x_api_key: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from X-API-Key header"""
    return x_api_key

async def verify_api_key(api_key: Optional[str] = Depends(get_api_key)) -> str:
    """
    FastAPI dependency to verify API key
    Raises 401 if API key is missing or invalid
    """
    if not api_key:
        raise HTTPException(
            status_code=401, 
            detail="Missing API key. Include X-API-Key header."
        )
    
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key not configured"
        )
    
    if api_key != expected_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key

def is_public_endpoint(path: str) -> bool:
    """Check if an endpoint should be publicly accessible without API key"""
    public_paths = [
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/debug/env"  # Allow debug endpoint for troubleshooting
    ]
    
    # Cron endpoints use X-CRON-SECRET instead of API key
    cron_paths = [
        "/cron/daily-update",
        "/cron/sync-bluestakes", 
        "/cron/refresh-todo",
        "/cron/send-emails",
        "/cron/status"
    ]
    
    return path in public_paths or path in cron_paths

async def check_api_key_middleware(request: Request) -> Optional[str]:
    """
    Middleware helper to check API key for protected endpoints
    Returns None for public endpoints, API key for protected ones
    """
    # Allow public endpoints without API key
    if is_public_endpoint(request.url.path):
        return None
    
    # Extract API key from header
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Include X-API-Key header."
        )
    
    # Verify API key
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key not configured"
        )
    
    if api_key != expected_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return api_key

# FastAPI dependency functions (existing Supabase auth)
async def get_auth_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract auth token from Authorization header"""
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() == "bearer":
            return token
    except ValueError:
        pass
    
    return None

async def get_current_user_id(token: Optional[str] = Depends(get_auth_token)) -> str:
    """
    FastAPI dependency to get current user ID from Supabase auth token
    Raises 401 if token is missing or invalid
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    try:
        # Create authenticated Supabase client with the JWT token
        client = get_user_client(token)
        
        # Test the token by making a simple authenticated request
        # This will fail if the token is invalid/expired
        user_response = client.auth.get_user()
        
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        
        return user_response.user.id
        
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

async def get_current_user_optional(token: Optional[str] = Depends(get_auth_token)) -> Optional[str]:
    """
    FastAPI dependency to get current user ID from Supabase auth token
    Returns None if token is missing or invalid (doesn't raise error)
    """
    if not token:
        return None
    
    try:
        client = get_user_client(token)
        user_response = client.auth.get_user()
        
        if user_response.user:
            return user_response.user.id
        return None
        
    except Exception:
        return None

async def get_authenticated_client(token: Optional[str] = Depends(get_auth_token)):
    """
    FastAPI dependency to get an authenticated Supabase client
    This client will respect RLS policies for the authenticated user
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    try:
        return get_user_client(token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}") 