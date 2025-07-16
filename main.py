from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
from typing import Dict, Any
from config import settings
from auth import get_current_user, require_user, require_admin, require_role

# Validate environment variables on startup
if not settings.validate():
    raise ValueError("Missing required environment variables. Please check your .env file.")

app = FastAPI(title="Underground API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"greeting": "Hello, World!", "message": "Welcome to FastAPI!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "underground-api"}

@app.get("/generate-pdf")
async def generate_pdf(current_user: Dict[str, Any] = Depends(require_user)):
    """
    Generate a PDF with "Hello World" - requires authentication
    """
    # Create a buffer to store the PDF
    buffer = BytesIO()
    
    # Create the PDF object using the buffer
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Get the page dimensions
    width, height = letter
    
    # Add "Hello World" text to the PDF
    p.setFont("Helvetica", 24)
    p.drawString(width/2 - 50, height/2, "Hello World")
    
    # Add user information to the PDF
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 100, f"Generated for: {current_user.get('email', 'Unknown')}")
    p.drawString(50, height - 120, f"User ID: {current_user.get('id', 'Unknown')}")
    
    # Save the PDF
    p.showPage()
    p.save()
    
    # Get the PDF content from the buffer
    pdf_content = buffer.getvalue()
    buffer.close()
    
    # Return the PDF as a response
    return Response(
        content=pdf_content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=hello_world_{current_user.get('id', 'user')}.pdf"}
    )

@app.get("/admin/dashboard")
async def admin_dashboard(current_user: Dict[str, Any] = Depends(require_admin)):
    """
    Admin dashboard - requires admin role
    """
    return {
        "message": "Welcome to Admin Dashboard",
        "user": current_user,
        "admin_features": ["user_management", "analytics", "system_settings"]
    }

@app.get("/user/profile")
async def user_profile(current_user: Dict[str, Any] = Depends(require_user)):
    """
    Get current user profile - requires authentication
    """
    return {
        "message": "User Profile",
        "user": {
            "id": current_user.get("id"),
            "email": current_user.get("email"),
            "role": current_user.get("role"),
            "metadata": current_user.get("metadata")
        }
    }

@app.get("/premium/content")
async def premium_content(current_user: Dict[str, Any] = Depends(require_role("premium"))):
    """
    Premium content - requires premium role
    """
    return {
        "message": "Premium Content",
        "content": "This is exclusive premium content",
        "user": current_user
    }

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for better error responses"""
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "path": str(request.url)
    }