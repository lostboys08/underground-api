from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

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
async def generate_pdf(text: str = Query(default="Hello World", description="Text to display in the PDF")):
    """
    Generate a PDF with custom text - no authentication required
    """
    # Create a buffer to store the PDF
    buffer = BytesIO()
    
    # Create the PDF object using the buffer
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Get the page dimensions
    width, height = letter
    
    # Add the custom text to the PDF
    p.setFont("Helvetica", 24)
    
    # Calculate text width to center it
    text_width = p.stringWidth(text, "Helvetica", 24)
    x_position = (width - text_width) / 2
    y_position = height / 2
    
    p.drawString(x_position, y_position, text)
    
    # Add timestamp to the PDF
    from datetime import datetime
    p.setFont("Helvetica", 12)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p.drawString(50, height - 100, f"Generated on: {timestamp}")
    
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
        headers={"Content-Disposition": f"attachment; filename=pdf_with_text.pdf"}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom exception handler for better error responses"""
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "path": str(request.url)
    }