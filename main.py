from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from utils.auth import check_api_key_middleware

# Configure logging with standard format for Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
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


@app.get("/")
async def root():
    return { 
        "message": "Welcome to Underground API!",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
        "loaded_routers": routers_loaded,
        "available_endpoints": {
            "docs": "/docs",
            "health": "/health", 
            "tickets": "/tickets/" if "Tickets" in routers_loaded else "unavailable",
            "cron_jobs": "/cron/" if "Cron Jobs" in routers_loaded else "unavailable"
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