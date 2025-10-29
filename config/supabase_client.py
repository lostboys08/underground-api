import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file (only in development)
if not os.getenv("RAILWAY_ENVIRONMENT"):
    load_dotenv()

# Simple Supabase client creation following official docs
def get_supabase_client() -> Client:
    """Get a simple Supabase client following the official docs pattern"""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")  # Using service role for server-side operations
    
    if not url or not key:
        missing = []
        if not url:
            missing.append("SUPABASE_URL")
        if not key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return create_client(url, key)

# Create a single global client instance
_supabase_client = None

def get_service_client() -> Client:
    """Get the global Supabase service client"""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase_client()
    return _supabase_client

# Legacy compatibility
def get_supabase_config():
    """Legacy compatibility - returns a simple object with is_configured method"""
    class SimpleConfig:
        def __init__(self):
            self.url = os.environ.get("SUPABASE_URL", "")
            self.service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            self.anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
        
        def is_configured(self):
            return bool(self.url and self.service_role_key)
        
        @property
        def service_client(self):
            return get_service_client()
    
    return SimpleConfig() 