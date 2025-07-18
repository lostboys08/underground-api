from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
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

@app.get("/")
async def root():
    return {
        "greeting": "Hello, World!", 
        "message": "Welcome to Underground API!",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
        "loaded_routers": routers_loaded,
        "available_endpoints": {
            "docs": "/docs",
            "health": "/health", 
            "pdf_generation": "/pdf/generate" if "PDF Generator" in routers_loaded else "unavailable",
            "user_profiles": "/profiles/" if "User Profiles" in routers_loaded else "unavailable",
            "companies": "/companies/" if "Companies" in routers_loaded else "unavailable"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint that works even without Supabase configuration"""
    health_status = {
        "status": "healthy", 
        "service": "underground-api",
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
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

@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment configuration (Railway only)"""
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        raise HTTPException(status_code=404, detail="Debug endpoint only available in Railway")
    
    env_status = {
        "railway_env": os.getenv("RAILWAY_ENVIRONMENT"),
        "has_supabase_url": bool(os.getenv("SUPABASE_URL")),
        "has_service_role_key": bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        "has_anon_key": bool(os.getenv("SUPABASE_ANON_KEY")),
        "has_jwt_secret": bool(os.getenv("SUPABASE_JWT_SECRET")),
        "has_encryption_key": bool(os.getenv("ENCRYPTION_KEY")),
        "supabase_url_preview": os.getenv("SUPABASE_URL", "")[:30] + "..." if os.getenv("SUPABASE_URL") else None
    }
    
    return env_status

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