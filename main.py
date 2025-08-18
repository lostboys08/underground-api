from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
import logging
from utils.auth import check_api_key_middleware

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
            "companies": "/companies/" if "Companies" in routers_loaded else "unavailable",
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

        "supabase_url_preview": os.getenv("SUPABASE_URL", "")[:30] + "..." if os.getenv("SUPABASE_URL") else None
    }
    
    return env_status

@app.get("/debug/supabase")
async def debug_supabase():
    """Test Supabase database connectivity"""
    debug_info = {
        "environment": "railway" if os.getenv("RAILWAY_ENVIRONMENT") else "local",
        "config_status": {},
        "connection_test": {},
        "table_tests": {}
    }
    
    try:
        # Test 1: Configuration
        from config.supabase_client import get_supabase_config
        config = get_supabase_config()
        
        debug_info["config_status"] = {
            "is_configured": config.is_configured(),
            "has_url": bool(config.url),
            "has_service_key": bool(config.service_role_key),
            "has_anon_key": bool(config.anon_key),
            "url_preview": config.url[:30] + "..." if config.url else None
        }
        
        if not config.is_configured():
            debug_info["error"] = "Supabase not configured - missing required environment variables"
            return debug_info
        
        # Test 2: Basic connectivity - step by step
        try:
            debug_info["connection_test"]["step"] = "Creating client"
            client = config.service_client
            debug_info["connection_test"]["client_created"] = True
            debug_info["connection_test"]["step"] = "Client created successfully"
            
            # Test 3: Simple query (count companies) - break it down
            debug_info["connection_test"]["step"] = "Attempting table query"
            companies_table = client.table("companies")
            debug_info["connection_test"]["table_object_created"] = True
            
            debug_info["connection_test"]["step"] = "Executing select query"
            result = companies_table.select("*").limit(1).execute()
            debug_info["connection_test"]["query_executed"] = True
            
            debug_info["table_tests"]["companies"] = {
                "accessible": True,
                "has_data": bool(result.data),
                "data_count": len(result.data) if result.data else 0,
                "result_type": type(result).__name__
            }
            
        except Exception as e:
            debug_info["connection_test"]["error"] = str(e)
            debug_info["connection_test"]["error_type"] = type(e).__name__
            debug_info["connection_test"]["client_created"] = "client" in locals()
            debug_info["connection_test"]["failed_at_step"] = debug_info["connection_test"].get("step", "unknown")
        
        # Test 4: Try profiles table
        try:
            if "client" in locals():
                result = client.table("profiles").select("count", count="exact").execute()
                debug_info["table_tests"]["profiles"] = {
                    "accessible": True,
                    "count": result.count if hasattr(result, 'count') else "unknown",
                    "has_data": bool(result.data)
                }
        except Exception as e:
            debug_info["table_tests"]["profiles"] = {
                "accessible": False,
                "error": str(e)
            }
        
        # Test 5: Authentication table access
        try:
            if "client" in locals():
                # This might fail if RLS is enabled
                result = client.table("auth.users").select("count", count="exact").limit(1).execute()
                debug_info["table_tests"]["auth_users"] = {
                    "accessible": True,
                    "note": "Can access auth.users table"
                }
        except Exception as e:
            debug_info["table_tests"]["auth_users"] = {
                "accessible": False,
                "error": str(e),
                "note": "This is normal if RLS is enabled"
            }
            
    except Exception as e:
        debug_info["fatal_error"] = str(e)
        debug_info["error_type"] = type(e).__name__
    
    return debug_info

@app.get("/debug/companies")
async def debug_companies():
    """Check what companies exist in the database"""
    try:
        from config.supabase_client import get_service_client
        
        # Get all companies with password info (but don't show the actual password)
        result = get_service_client().table("companies").select("id, name, bluestakes_username, bluestakes_password").execute()
        
        # Format the response to show if password exists without exposing it
        companies_info = []
        for company in result.data if result.data else []:
            company_info = {
                "id": company.get("id"),
                "name": company.get("name"),
                "bluestakes_username": company.get("bluestakes_username"),
                "has_password": bool(company.get("bluestakes_password"))
            }
            companies_info.append(company_info)
        
        return {
            "companies_found": len(companies_info),
            "companies": companies_info[:5],  # Show first 5
            "query_successful": True
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "query_successful": False
        }

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