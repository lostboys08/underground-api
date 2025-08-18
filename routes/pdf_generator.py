from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import httpx
import json
from datetime import datetime
from typing import Dict, Any, Optional

router = APIRouter(prefix="/pdf", tags=["PDF Generation"])

# Bluestakes API configuration
BLUESTAKES_BASE_URL = "https://newtiny-api.bluestakes.org/api"

@router.get("/generate")
async def generate_pdf(
    ticket: str = Query(..., description="Ticket number for which to get details (required)"),
    username: str = Query(..., description="Bluestakes username (required)"),
    password: str = Query(..., description="Bluestakes password (required)"),
    text: str = Query(default="Ticket Report", description="Custom title text to display in the PDF"),
    revision: Optional[str] = Query(default=None, description="Specific revision for the ticket, gets latest if omitted"),
    phone: Optional[str] = Query(default=None, description="Phone number associated with the ticket (required for anonymous users)"),
    all_prior_revs: bool = Query(default=False, description="Return responses for prior ticket revisions")
):
    """
    Generate a PDF with custom text and Bluestakes API ticket data
    Requires direct username and password credentials
    """
    # Use the provided credentials directly
    bluestakes_username = username
    bluestakes_password = password
    
    # Validate that we have credentials
    if not bluestakes_username or not bluestakes_password:
        raise HTTPException(
            status_code=400, 
            detail="Username and password are required"
        )
    
    # Create a buffer to store the PDF
    buffer = BytesIO()
    
    # Create the PDF object using the buffer
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Get the page dimensions
    width, height = letter
    
    bluestakes_data = None
    error_message = None
    credentials_source = "Provided credentials"
    
    # Try to fetch data from Bluestakes API
    try:
        # Get authentication token
        token = await get_bluestakes_auth_token(bluestakes_username, bluestakes_password)
        
        # Fetch data using the token
        bluestakes_data = await fetch_bluestakes_data(token, ticket, revision, phone, all_prior_revs)
        
    except Exception as e:
        error_message = f"Bluestakes API Error: {str(e)}"
    
    # Add the custom text to the PDF
    p.setFont("Helvetica-Bold", 24)
    text_width = p.stringWidth(text, "Helvetica-Bold", 24)
    x_position = (width - text_width) / 2
    y_position = height - 100
    p.drawString(x_position, y_position, text)
    
    # Add ticket information
    y_position -= 40
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y_position, f"Ticket: {ticket}")
    
    # Add credentials source
    y_position -= 25
    p.setFont("Helvetica", 12)
    p.drawString(50, y_position, f"Credentials: {credentials_source}")
    
    # Removed company ID section as we're using direct credentials
    
    if revision:
        y_position -= 20
        p.drawString(50, y_position, f"Revision: {revision}")
    
    if phone:
        y_position -= 20
        p.drawString(50, y_position, f"Phone: {phone}")
    
    if all_prior_revs:
        y_position -= 20
        p.drawString(50, y_position, "Including all prior revisions")
    
    # Add Bluestakes API data section
    y_position -= 40
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y_position, "Ticket Details:")
    
    y_position -= 30
    p.setFont("Helvetica", 12)
    
    if error_message:
        # Display error if API call failed
        p.drawString(50, y_position, error_message)
        y_position -= 20
        p.drawString(50, y_position, "Note: Please check your credentials and ticket number.")
    elif bluestakes_data:
        # Check if there's an error in the response
        if "error" in bluestakes_data:
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y_position, f"Error: {bluestakes_data['error']}")
            y_position -= 20
            if "status_code" in bluestakes_data:
                p.setFont("Helvetica", 10)
                p.drawString(50, y_position, f"Status Code: {bluestakes_data['status_code']}")
        else:
            # Display the ticket data in a structured format
            data_str = json.dumps(bluestakes_data, indent=2)
            
            # Split the data into lines and add to PDF
            lines = data_str.split('\n')
            for line in lines:
                if y_position < 50:  # Start a new page if we're near the bottom
                    p.showPage()
                    y_position = height - 50
                    p.setFont("Helvetica", 12)
                
                # Truncate long lines to fit on the page
                if len(line) > 90:
                    line = line[:87] + "..."
                
                p.drawString(50, y_position, line)
                y_position -= 15
    else:
        p.drawString(50, y_position, "No ticket data retrieved from Bluestakes API")
    
    # Add timestamp to the PDF
    if y_position < 100:
        p.showPage()
        y_position = height - 50
    
    y_position -= 30
    p.setFont("Helvetica", 10)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p.drawString(50, y_position, f"Generated on: {timestamp}")
    
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
        headers={"Content-Disposition": f"attachment; filename=ticket_{ticket}_report.pdf"}
    ) 