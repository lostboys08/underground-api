from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from utils.auth import check_api_key_middleware

# Configure logging with proper formatting for Railway
import sys

# Create a custom formatter that ensures proper log level handling
class RailwayFormatter(logging.Formatter):
    """Custom formatter to ensure Railway correctly interprets log levels"""
    
    def format(self, record):
        # Ensure the log level is clearly indicated
        formatted = super().format(record)
        # Add explicit level prefix for Railway parsing
        level_prefix = f"[{record.levelname}]"
        return f"{level_prefix} {formatted}"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(message)s',  # Removed %(levelname)s since RailwayFormatter adds it as prefix
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,  # Explicitly use stdout instead of stderr
    force=True  # Override any existing configuration
)

# Apply custom formatter to root logger
root_logger = logging.getLogger()
if root_logger.handlers:
    for handler in root_logger.handlers:
        handler.setFormatter(RailwayFormatter(
            '%(asctime)s - %(name)s - %(message)s',  # Removed %(levelname)s since RailwayFormatter adds it as prefix
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
logger = logging.getLogger(__name__)

app = FastAPI(title="Underground API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Key Authentication Middleware
@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Middleware to check API key for protected endpoints"""
    try:
        # Check API key for protected endpoints
        await check_api_key_middleware(request)
        
        # If we get here, the request is either public or has valid API key
        response = await call_next(request)
        return response
        
    except HTTPException as e:
        # Return proper error response for authentication failures
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.detail,
                "status_code": e.status_code,
                "path": str(request.url.path)
            }
        )
    except Exception as e:
        # Handle unexpected errors in middleware
        logger.error(f"Middleware error: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "status_code": 500,
                "path": str(request.url.path)
            }
        )

# Include routers with error handling
routers_loaded = []

try:
    from routes.pdf_generator import router as pdf_router
    app.include_router(pdf_router)
    routers_loaded.append("PDF Generator")
    logger.info("PDF Generator router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load PDF Generator router: {e}")

try:
    from routes.profiles import router as profiles_router
    app.include_router(profiles_router)
    routers_loaded.append("User Profiles")
    logger.info("User Profiles router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load User Profiles router: {e}")

try:
    from routes.companies import router as companies_router
    app.include_router(companies_router)
    routers_loaded.append("Companies")
    logger.info("Companies router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Companies router: {e}")

try:
    from routes.tickets import router as tickets_router
    app.include_router(tickets_router)
    routers_loaded.append("Tickets")
    logger.info("Tickets router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Tickets router: {e}")

try:
    from routes.cron import cron_router
    app.include_router(cron_router)
    routers_loaded.append("Cron Jobs")
    logger.info("Cron Jobs router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Cron Jobs router: {e}")

try:
    from routes.emails import router as emails_router
    app.include_router(emails_router)
    routers_loaded.append("Emails")
    logger.info("Emails router loaded successfully")
except Exception as e:
    logger.error(f"Failed to load Emails router: {e}")

@app.get("/")
async def root():
    return { 
        "message": "Welcome to Underground API!",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
        "loaded_routers": routers_loaded,
        "available_endpoints": {
            "docs": "/docs",
            "health": "/health", 
            "pdf_generation": "/pdf/generate" if "PDF Generator" in routers_loaded else "unavailable",
            "user_profiles": "/profiles/" if "User Profiles" in routers_loaded else "unavailable",
            "companies": "/companies/" if "Companies" in routers_loaded else "unavailable",
            "tickets": "/tickets/" if "Tickets" in routers_loaded else "unavailable",
            "cron_jobs": "/cron/" if "Cron Jobs" in routers_loaded else "unavailable",
            "emails": "/emails/" if "Emails" in routers_loaded else "unavailable"
        },
        "authentication": {
            "type": "API Key",
            "header": "X-API-Key",
            "note": "All endpoints except /, /health, and /docs require API key"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint that works even without Supabase configuration"""
    health_status = {
        "status": "healthy", 
        "service": "underground-api",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
        "api_key_configured": bool(os.getenv("API_KEY")),
        "supabase_configured": False,
        "supabase_connected": False
    }
    
    # Check Supabase connectivity (don't fail if not configured)
    try:
        from config.supabase_client import get_supabase_config
        config = get_supabase_config()
        health_status["supabase_configured"] = config.is_configured()
        
        if config.is_configured():
            # Test basic connectivity
            result = config.service_client.table("companies").select("count").limit(1).execute()
            health_status["supabase_connected"] = True
        else:
            health_status["note"] = "Supabase not configured - some features unavailable"
            
    except Exception as e:
        health_status["supabase_error"] = str(e)
    
    return health_status

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for better error responses"""
    from fastapi.responses import JSONResponse
    
    # Log the error for debugging
    logger.error(f"HTTPException at {request.url}: {exc.status_code} - {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "path": str(request.url)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions"""
    from fastapi.responses import JSONResponse
    
    # Log the full error for debugging
    logger.error(f"Unhandled exception at {request.url}: {type(exc).__name__}: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "path": str(request.url),
            "type": type(exc).__name__
        }
    )