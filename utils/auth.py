import os
import jwt
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, Header
from datetime import datetime, timezone
from config.supabase_client import supabase_config

class SupabaseJWTVerifier:
    """JWT verification for Supabase authentication"""
    
    def __init__(self):
        self.jwt_secret = supabase_config.jwt_secret
        self.algorithms = ["HS256"]
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a Supabase JWT token
        Returns the decoded payload if valid
        """
        try:
            # Decode and verify the JWT
            payload = jwt.decode(
                token, 
                self.jwt_secret, 
                algorithms=self.algorithms,
                audience="authenticated"
            )
            
            # Check if token is expired
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Token expired")
            
            return payload
            
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")
    
    def get_user_id(self, token: str) -> str:
        """Extract user ID from JWT token"""
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
        return user_id
    
    def get_user_email(self, token: str) -> Optional[str]:
        """Extract user email from JWT token"""
        payload = self.verify_token(token)
        return payload.get("email")
    
    def get_user_metadata(self, token: str) -> Dict[str, Any]:
        """Extract user metadata from JWT token"""
        payload = self.verify_token(token)
        return payload.get("user_metadata", {})

# Global JWT verifier instance
jwt_verifier = SupabaseJWTVerifier()

# FastAPI dependency functions
async def get_jwt_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract JWT token from Authorization header"""
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() == "bearer":
            return token
    except ValueError:
        pass
    
    return None

async def get_current_user_id(token: Optional[str] = Depends(get_jwt_token)) -> str:
    """
    FastAPI dependency to get current user ID from JWT token
    Raises 401 if token is missing or invalid
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    return jwt_verifier.get_user_id(token)

async def get_current_user_optional(token: Optional[str] = Depends(get_jwt_token)) -> Optional[str]:
    """
    FastAPI dependency to get current user ID from JWT token
    Returns None if token is missing or invalid (doesn't raise error)
    """
    if not token:
        return None
    
    try:
        return jwt_verifier.get_user_id(token)
    except HTTPException:
        return None

async def verify_jwt_token(token: Optional[str] = Depends(get_jwt_token)) -> Dict[str, Any]:
    """
    FastAPI dependency to verify JWT token and return payload
    Raises 401 if token is missing or invalid
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token required")
    
    return jwt_verifier.verify_token(token) 