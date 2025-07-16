from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from jose import JWTError, jwt
from typing import Optional, Dict, Any
from config import settings

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# Security scheme for JWT tokens
security = HTTPBearer()

class AuthError(Exception):
    """Custom authentication error"""
    pass

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(
            token, 
            settings.SUPABASE_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        raise AuthError("Invalid token")

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """Get current authenticated user from JWT token"""
    try:
        token = credentials.credentials
        payload = verify_jwt_token(token)
        
        # Extract user information from token
        user_id = payload.get("sub")
        if not user_id:
            raise AuthError("Invalid token payload")
        
        # Get user details from Supabase
        user_response = supabase.auth.get_user(token)
        user = user_response.user
        
        if not user:
            raise AuthError("User not found")
        
        return {
            "id": user.id,
            "email": user.email,
            "role": payload.get("role", "user"),
            "metadata": user.user_metadata or {}
        }
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_role(required_role: str):
    """Decorator to require specific user role"""
    def role_checker(current_user: Dict[str, Any] = Depends(get_current_user)):
        user_role = current_user.get("role", "user")
        if user_role != required_role and user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required"
            )
        return current_user
    return role_checker

# Convenience functions for common roles
def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Require admin role"""
    user_role = current_user.get("role", "user")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    return current_user

def require_user(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Require any authenticated user"""
    return current_user 