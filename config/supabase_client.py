import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SupabaseConfig:
    """Supabase configuration and client management"""
    
    def __init__(self):
        # Required environment variables
        self.url: str = os.getenv("SUPABASE_URL", "")
        self.service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.anon_key: str = os.getenv("SUPABASE_ANON_KEY", "")
        self.jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "")
        
        # Validate required variables
        if not self.url or not self.service_role_key:
            raise ValueError(
                "Missing required environment variables. Please set:\n"
                "- SUPABASE_URL=https://your-project-id.supabase.co\n"
                "- SUPABASE_SERVICE_ROLE_KEY=your-service-role-key\n"
                "- SUPABASE_ANON_KEY=your-anon-key (optional)\n"
                "- SUPABASE_JWT_SECRET=your-jwt-secret (for auth)"
            )
        
        # Initialize clients
        self._service_client: Optional[Client] = None
        self._anon_client: Optional[Client] = None
    
    @property
    def service_client(self) -> Client:
        """
        Service role client - has full access to database
        Use for server-side operations, admin tasks
        """
        if not self._service_client:
            self._service_client = create_client(self.url, self.service_role_key)
        return self._service_client
    
    @property
    def anon_client(self) -> Client:
        """
        Anonymous client - respects RLS policies
        Use for user-facing operations
        """
        if not self._anon_client:
            if not self.anon_key:
                raise ValueError("SUPABASE_ANON_KEY not set - required for anonymous client")
            self._anon_client = create_client(self.url, self.anon_key)
        return self._anon_client
    
    def get_authenticated_client(self, jwt_token: str) -> Client:
        """
        Get a client authenticated with a user's JWT token
        Use for user-specific operations with RLS
        """
        client = create_client(self.url, self.anon_key)
        client.auth.set_session(access_token=jwt_token, refresh_token="")
        return client

# Global Supabase configuration instance
supabase_config = SupabaseConfig()

# Convenient exports for different use cases
supabase_service = supabase_config.service_client  # For admin/server operations
supabase_anon = supabase_config.anon_client        # For anonymous operations

# Helper function to get authenticated client
def get_user_client(jwt_token: str) -> Client:
    """Get a Supabase client authenticated with user's JWT"""
    return supabase_config.get_authenticated_client(jwt_token) 