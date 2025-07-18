from typing import Optional
from fastapi import HTTPException, Depends, Header
from config.supabase_client import get_user_client

# FastAPI dependency functions
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