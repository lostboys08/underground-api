import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv
import logging

# Load environment variables from .env file (only in development)
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_dotenv()

class SupabaseConfig:
    """Supabase configuration and client management"""
    
    def __init__(self):
        # Get environment variables but don't validate them at init time
        self.url: str = os.getenv("SUPABASE_URL", "")
        self.service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
        self.jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "")
        
        # Initialize clients as None - they'll be created on first access
        self._service_client: Optional[Client] = None
        self._anon_client: Optional[Client] = None
        self._config_validated: bool = False
    
    def _validate_config(self) -> None:
        """Validate configuration and raise helpful error if missing variables"""
        if self._config_validated:
            return
            
        missing_vars = []
        if not self.url:
            missing_vars.append("SUPABASE_URL")
        if not self.service_role_key:
            missing_vars.append("SUPABASE_SERVICE_ROLE_KEY")
        
        if missing_vars:
            env_info = "Railway" if os.getenv("RAILWAY_ENVIRONMENT") else "Local"
            raise ValueError(
                f"Missing required Supabase environment variables for {env_info} environment:\n" +
                "\n".join([f"- {var}" for var in missing_vars]) +
                "\n\nFor Railway deployment, set these in your Railway project settings."
            )
        
        self._config_validated = True
    
    @property
    def service_client(self) -> Client:
        """
        Service role client - has full access to database
        Use for server-side operations, admin tasks
        """
        if not self._service_client:
            self._validate_config()
            self._service_client = create_client(self.url, self.service_role_key)
        return self._service_client
    
    @property
    def anon_client(self) -> Client:
        """
        Anonymous client - respects RLS policies
        Use for user-facing operations
        """
        if not self._anon_client:
            self._validate_config()
            if not self.anon_key:
                logging.warning("SUPABASE_ANON_KEY not set - some features may not work")
                # Use service role key as fallback for anon operations
                self._anon_client = create_client(self.url, self.service_role_key)
            else:
                self._anon_client = create_client(self.url, self.anon_key)
        return self._anon_client
    
    def get_authenticated_client(self, jwt_token: str) -> Client:
        """
        Get a client authenticated with a user's JWT token
        Use for user-specific operations with RLS
        """
        self._validate_config()
        anon_key = self.anon_key or self.service_role_key
        client = create_client(self.url, anon_key)
        client.auth.set_session(access_token=jwt_token, refresh_token="")
        return client
    
    def is_configured(self) -> bool:
        """Check if Supabase is properly configured"""
        return bool(self.url and self.service_role_key)

# Global Supabase configuration instance (lazy initialization)
_supabase_config: Optional[SupabaseConfig] = None

def get_supabase_config() -> SupabaseConfig:
    """Get the global Supabase configuration instance"""
    global _supabase_config
    if _supabase_config is None:
        _supabase_config = SupabaseConfig()
    return _supabase_config

# Convenient exports for different use cases (lazy-loaded)
def get_service_client() -> Client:
    """Get service role client for admin operations"""
    return get_supabase_config().service_client

def get_anon_client() -> Client:
    """Get anonymous client for public operations"""
    return get_supabase_config().anon_client

# Helper function to get authenticated client
def get_user_client(jwt_token: str) -> Client:
    """Get a Supabase client authenticated with user's JWT"""
    return get_supabase_config().get_authenticated_client(jwt_token)

# For backward compatibility, create lazy properties that work like the old globals
class _LazySupabaseAccess:
    def __getattr__(self, name):
        if name == "service_client":
            return get_service_client()
        elif name == "anon_client": 
            return get_anon_client()
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

# Backward compatibility exports - these won't trigger loading at import time
supabase_service = _LazySupabaseAccess()
supabase_anon = _LazySupabaseAccess() 