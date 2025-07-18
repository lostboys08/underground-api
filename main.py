from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from routes.pdf_generator import router as pdf_router
from routes.profiles import router as profiles_router
from routes.companies import router as companies_router

app = FastAPI(title="Underground API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(pdf_router)
app.include_router(profiles_router)
app.include_router(companies_router)

@app.get("/")
async def root():
    return {
        "greeting": "Hello, World!", 
        "message": "Welcome to Underground API!",
        "available_endpoints": {
            "docs": "/docs",
            "health": "/health", 
            "pdf_generation": "/pdf/generate",
            "user_profiles": "/profiles/",
            "companies": "/companies/"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "underground-api"}

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for better error responses"""
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "path": str(request.url)
    }