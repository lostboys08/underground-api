#!/usr/bin/env python3
"""
Startup script for Underground API on Railway
Handles environment validation and graceful startup
"""

import os
import logging
import sys
from datetime import datetime

# Configure logging with standard format for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

def install_playwright():
    """Install Playwright browsers if needed"""
    try:
        logger.info("Checking Playwright installation...")
        import subprocess
        
        # Try to import playwright
        try:
            from playwright.async_api import async_playwright
            logger.info("✓ Playwright is installed")
            
            # Check if browsers are installed
            result = subprocess.run(["playwright", "list"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("✓ Playwright browsers are installed")
                return True
            else:
                logger.info("Installing Playwright browsers...")
                subprocess.run(["playwright", "install", "chromium"], check=True)
                logger.info("✓ Playwright browsers installed successfully")
                return True
                
        except ImportError:
            logger.warning("⚠️  Playwright not installed - ticket update functionality will be disabled")
            return False
            
    except Exception as e:
        logger.warning(f"⚠️  Failed to install Playwright: {e}")
        logger.warning("   Ticket update functionality will be disabled")
        return False

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
        
        # Start the server with standard logging configuration
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=True,
            use_colors=False  # Disable colors for Railway
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        logger.exception("Full traceback:")
        sys.exit(1)

if __name__ == "__main__":
    main() 