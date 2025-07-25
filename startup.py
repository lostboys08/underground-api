#!/usr/bin/env python3
"""
Startup script for Underground API on Railway
Handles environment validation and graceful startup
"""

import os
import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def check_environment():
    """Check and log environment configuration"""
    logger.info("=" * 50)
    logger.info("Underground API Startup")
    logger.info("=" * 50)
    
    # Environment info
    env_type = "Railway" if os.getenv("RAILWAY_ENVIRONMENT") else "Local"
    logger.info(f"Environment: {env_type}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    # Check required environment variables
    required_vars = ["PORT"]
    optional_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY", 
        "SUPABASE_ANON_KEY",
        "SUPABASE_JWT_SECRET",
        "ENCRYPTION_KEY"
    ]
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
        else:
            logger.info(f"✓ {var} is set")
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
        else:
            logger.info(f"✓ {var} is set")
    
    if missing_required:
        logger.error(f"❌ Missing required environment variables: {missing_required}")
        return False
    
    if missing_optional:
        logger.warning(f"⚠️  Missing optional environment variables: {missing_optional}")
        logger.warning("   Some features may not be available")
    
    logger.info("=" * 50)
    return True

def main():
    """Main startup function"""
    try:
        # Check environment
        if not check_environment():
            logger.error("Environment check failed")
            sys.exit(1)
        
        # Import and start the app
        logger.info("Starting FastAPI application...")
        
        # Set default port if not set
        port = int(os.getenv("PORT", "8000"))
        host = os.getenv("HOST", "0.0.0.0")
        
        # Import uvicorn and the app
        import uvicorn
        from main import app
        
        logger.info(f"Starting server on {host}:{port}")
        
        # Start the server
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main() 