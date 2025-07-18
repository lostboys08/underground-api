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

async def get_bluestakes_auth_token(username: str, password: str) -> str:
    """
    Get authentication token from Bluestakes API using the /login-json endpoint
    """
    if not username or not password:
        raise HTTPException(
            status_code=400, 
            detail="Username and password are required for Bluestakes API authentication"
        )
    
    async with httpx.AsyncClient() as client:
        try:
            # Use the correct endpoint and format from the API documentation
            auth_data = {
                "username": username,
                "password": password
            }
            
            response = await client.post(
                f"{BLUESTAKES_BASE_URL}/login-json",
                json=auth_data,
                headers={"Content-Type": "application/json"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                data = response.json()
                # Look for common token field names in the response
                token_fields = ["token", "access_token", "auth_token", "bearer_token", "jwt", "session_token"]
                for field in token_fields:
                    if field in data:
                        return data[field]
                
                # If no standard token field found, check if the whole response contains auth info
                if "authenticated" in str(data).lower() or "success" in str(data).lower():
                    # Return the whole response data for now - we'll need to check what the actual response looks like
                    return json.dumps(data)
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Authentication successful but no token found in response: {data}"
                )
            
            elif response.status_code == 400:
                raise HTTPException(status_code=400, detail="Bad Request - Invalid request format")
            elif response.status_code == 401:
                raise HTTPException(status_code=401, detail="No user found, wrong password, or account disabled/expired")
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Authentication failed with status {response.status_code}: {response.text}"
                )
                
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=408,
                detail="Request to Bluestakes API timed out"
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Error connecting to Bluestakes API: {str(e)}"
            )

async def fetch_bluestakes_data(token: str, ticket: str, revision: Optional[str] = None, phone: Optional[str] = None, all_prior_revs: bool = False) -> Dict[str, Any]:
    """
    Fetch ticket data from Bluestakes API using the authentication token
    """
    async with httpx.AsyncClient() as client:
        # Set up headers with the authentication token
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Build query parameters
        params = {}
        if revision:
            params["revision"] = revision
        if phone:
            params["phone"] = phone
        if all_prior_revs:
            params["allPriorRevs"] = "true"
        
        try:
            # Call the specific tickets endpoint
            response = await client.get(
                f"{BLUESTAKES_BASE_URL}/tickets/{ticket}",
                headers=headers,
                params=params,
                timeout=10.0
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Try with different auth header format
                alt_headers = {
                    "X-Auth-Token": token,
                    "Content-Type": "application/json"
                }
                alt_response = await client.get(
                    f"{BLUESTAKES_BASE_URL}/tickets/{ticket}",
                    headers=alt_headers,
                    params=params,
                    timeout=10.0
                )
                if alt_response.status_code == 200:
                    return alt_response.json()
                else:
                    return {
                        "error": "Unauthorized - Invalid or expired token",
                        "status_code": 401
                    }
            elif response.status_code == 404:
                return {
                    "error": f"Ticket {ticket} not found",
                    "status_code": 404
                }
            else:
                return {
                    "error": f"API request failed with status {response.status_code}",
                    "status_code": response.status_code,
                    "response_text": response.text
                }
                
        except Exception as e:
            return {
                "error": f"Request failed: {str(e)}",
                "ticket": ticket,
                "suggestion": "Check network connection and API availability"
            }

@router.get("/generate")
async def generate_pdf(
    ticket: str = Query(..., description="Ticket number for which to get details (required)"),
    text: str = Query(default="Ticket Report", description="Custom title text to display in the PDF"),
    company_id: Optional[int] = Query(default=None, description="Company ID to use stored Bluestakes credentials"),
    username: Optional[str] = Query(default=None, description="Bluestakes username (required if not using company_id)"),
    password: Optional[str] = Query(default=None, description="Bluestakes password (required if not using company_id)"),
    revision: Optional[str] = Query(default=None, description="Specific revision for the ticket, gets latest if omitted"),
    phone: Optional[str] = Query(default=None, description="Phone number associated with the ticket (required for anonymous users)"),
    all_prior_revs: bool = Query(default=False, description="Return responses for prior ticket revisions")
):
    """
    Generate a PDF with custom text and Bluestakes API ticket data
    Can use either stored company credentials or provided username/password
    """
    # Determine which credentials to use
    bluestakes_username = username
    bluestakes_password = password
    
    if company_id:
        try:
            # Get stored credentials from company
            from config.supabase_client import supabase_service
            from routes.companies import decrypt_password
            
            company_result = (supabase_service.table("companies")
                             .select("bluestakes_username, bluestakes_password_encrypted")
                             .eq("id", company_id)
                             .execute())
            
            if company_result.data:
                company = company_result.data[0]
                bluestakes_username = company.get("bluestakes_username")
                if company.get("bluestakes_password_encrypted"):
                    bluestakes_password = decrypt_password(company["bluestakes_password_encrypted"])
                
                if not bluestakes_username or not bluestakes_password:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Company {company_id} does not have complete Bluestakes credentials stored"
                    )
            else:
                raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
                
        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=500, detail=f"Error retrieving company credentials: {str(e)}")
    
    # Validate that we have credentials
    if not bluestakes_username or not bluestakes_password:
        raise HTTPException(
            status_code=400, 
            detail="Either provide company_id with stored credentials or username/password parameters"
        )
    
    # Create a buffer to store the PDF
    buffer = BytesIO()
    
    # Create the PDF object using the buffer
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Get the page dimensions
    width, height = letter
    
    bluestakes_data = None
    error_message = None
    credentials_source = "Company stored credentials" if company_id else "Provided credentials"
    
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
    
    if company_id:
        y_position -= 20
        p.drawString(50, y_position, f"Company ID: {company_id}")
    
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