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

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for better error responses"""
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "path": str(request.url)
    }