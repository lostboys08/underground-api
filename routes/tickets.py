from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import httpx
import asyncio
import os
from config.supabase_client import get_service_client

from utils.encryption import decrypt_password
import logging

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# BlueStakes API configuration
BLUESTAKES_BASE_URL = "https://newtiny-api.bluestakes.org/api"

@router.get("/debug-decryption/{company_id}")
async def debug_decryption(company_id: int):
    """
    Debug endpoint to test decryption without making API calls
    """
    try:
        # Get company's BlueStakes credentials
        company_result = (get_service_client().table("companies")
                         .select("bluestakes_username, bluestakes_password_encrypted")
                         .eq("id", company_id)
                         .execute())
        
        if not company_result.data:
            return {"error": f"Company {company_id} not found"}
        
        company = company_result.data[0]
        username = company.get("bluestakes_username")
        encrypted_password = company.get("bluestakes_password_encrypted")
        
        debug_info = {
            "company_id": company_id,
            "has_username": bool(username),
            "username": username,
            "has_encrypted_password": bool(encrypted_password),
            "encrypted_password_type": type(encrypted_password).__name__ if encrypted_password else None,
            "encrypted_password_length": len(encrypted_password) if encrypted_password else None,
            "encryption_key_exists": bool(os.getenv("ENCRYPTION_KEY")),
            "using_default_key": not bool(os.getenv("ENCRYPTION_KEY"))
        }
        
        # Try to decrypt the password
        if encrypted_password:
            try:
                # Handle different storage formats
                if isinstance(encrypted_password, str):
                    # If it's a string, try to decode it as bytes
                    try:
                        # Check if it's a string representation of bytes (like "b'\\x716b6d3232362a'")
                        if encrypted_password.startswith("b'") and encrypted_password.endswith("'"):
                            debug_info["note"] = "Password is hex-encoded, decoding directly"
                            # Remove the b'' wrapper and decode the hex
                            hex_string = encrypted_password[2:-1].replace('\\x', '')
                            # This is actually the plain password, not encrypted
                            decrypted_password = bytes.fromhex(hex_string).decode()
                            debug_info["decryption_success"] = True
                            debug_info["decrypted_password_length"] = len(decrypted_password)
                            debug_info["decrypted_password_preview"] = decrypted_password[:10] + "..." if len(decrypted_password) > 10 else decrypted_password
                            return debug_info
                        else:
                            debug_info["note"] = "Encrypted password is stored as string, converting to bytes"
                            encrypted_password = encrypted_password.encode()
                    except Exception as e:
                        debug_info["note"] = f"Failed to convert string to bytes: {str(e)}"
                        encrypted_password = None
                elif isinstance(encrypted_password, bytes):
                    debug_info["note"] = "Encrypted password is already in bytes format"
                else:
                    debug_info["note"] = f"Unknown format: {type(encrypted_password)}"
                    encrypted_password = None
                
                if encrypted_password:
                    decrypted_password = decrypt_password(encrypted_password)
                    debug_info["decryption_success"] = True
                    debug_info["decrypted_password_length"] = len(decrypted_password) if decrypted_password else 0
                    debug_info["decrypted_password_preview"] = decrypted_password[:10] + "..." if decrypted_password else None
                else:
                    debug_info["decryption_success"] = False
                    debug_info["decryption_error"] = "Could not process encrypted password format"
                    debug_info["decryption_error_type"] = "FormatError"
            except Exception as e:
                debug_info["decryption_success"] = False
                debug_info["decryption_error"] = str(e)
                debug_info["decryption_error_type"] = type(e).__name__
                debug_info["encrypted_password_preview"] = str(encrypted_password)[:50] if encrypted_password else None
        
        return debug_info
        
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__
        }

@router.post("/fix-encryption/{company_id}")
async def fix_company_encryption(company_id: int, new_password: str):
    """
    Fix encryption by re-encrypting the password with the current key
    """
    try:
        from utils.encryption import encrypt_password
        
        # Update the company with the new encrypted password
        result = (get_service_client().table("companies")
                 .update({"bluestakes_password_encrypted": encrypt_password(new_password)})
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            return {"error": f"Company {company_id} not found"}
        
        return {
            "success": True,
            "message": f"Password for company {company_id} has been re-encrypted",
            "company_id": company_id
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "error_type": type(e).__name__
        }

@router.post("/store-credentials/{company_id}")
async def store_bluestakes_credentials(
    company_id: int,
    username: str = Query(..., description="BlueStakes username"),
    password: str = Query(..., description="BlueStakes password")
):
    """
    Store BlueStakes credentials for a company with proper encryption
    """
    try:
        from utils.encryption import encrypt_password
        
        # Encrypt the password using our encryption utility
        encrypted_password = encrypt_password(password)
        
        if not encrypted_password:
            raise HTTPException(
                status_code=500,
                detail="Failed to encrypt password"
            )
        
        # Update the company with the encrypted credentials
        result = (get_service_client().table("companies")
                 .update({
                     "bluestakes_username": username,
                     "bluestakes_password_encrypted": encrypted_password
                 })
                 .eq("id", company_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail=f"Company {company_id} not found"
            )
        
        return {
            "success": True,
            "message": f"BlueStakes credentials stored for company {company_id}",
            "company_id": company_id,
            "username": username,
            "password_encrypted": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error storing credentials for company {company_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error storing credentials: {str(e)}"
        )

# Pydantic models for request/response

class ProjectTicketCreate(BaseModel):
    project_id: Optional[int] = None
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str] = None
    is_continue_update: bool = True
    legal_date: Optional[datetime] = None
    company_id: int = 1  # Default to 1 for now

class ProjectTicketResponse(BaseModel):
    id: int
    project_id: Optional[int]
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str]
    is_continue_update: bool
    legal_date: Optional[datetime]
    company_id: int

class BlueStakesSearchRequest(BaseModel):
    company_id: Optional[int] = 1  # Default to company 1 for now
    limit: Optional[int] = 10  # Limit to first 10 tickets
    offset: Optional[int] = 0
    # Add search parameters from the image
    sort: Optional[str] = None
    start: Optional[str] = None  # Start date
    end: Optional[str] = None    # End date
    state: Optional[str] = None  # Work area state
    county: Optional[str] = None # Work area county

@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: int):
    """
    Delete a ticket by ID
    """
    try:
        result = get_service_client().table("tickets").delete().eq("id", ticket_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        return {"message": f"Ticket {ticket_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error deleting ticket {ticket_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# BlueStakes API helper functions
async def get_bluestakes_auth_token(username: str, password: str) -> str:
    """
    Get authentication token from BlueStakes API using the /login-json endpoint
    """
    if not username or not password:
        raise HTTPException(
            status_code=400,
            detail="Username and password are required for BlueStakes API authentication"
        )
    
    auth_data = {
        "username": username,
        "password": password
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BLUESTAKES_BASE_URL}/login-json",
                json=auth_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # BlueStakes returns token in "Authorization" field as "Bearer [token]"
            if "Authorization" in data:
                auth_header = data["Authorization"]
                if auth_header.startswith("Bearer "):
                    return auth_header.split(" ", 1)[1]
                else:
                    return auth_header
            else:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication failed: No token received from BlueStakes API"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to BlueStakes API timed out"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"BlueStakes API authentication failed: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to BlueStakes API: {str(e)}"
        )

async def search_bluestakes_tickets(token: str, search_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search tickets from BlueStakes API using the /tickets/search endpoint
    """
    try:
        # Build query parameters for the search
        params = {}
        if search_params.get("limit"):
            params["limit"] = search_params["limit"]
        if search_params.get("offset"):
            params["offset"] = search_params["offset"]
        if search_params.get("sort"):
            params["sort"] = search_params["sort"]
        if search_params.get("start"):
            params["start"] = search_params["start"]
        if search_params.get("end"):
            params["end"] = search_params["end"]
        if search_params.get("state"):
            params["state"] = search_params["state"]
        if search_params.get("county"):
            params["county"] = search_params["county"]
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{BLUESTAKES_BASE_URL}/tickets/search",
                params=params,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to BlueStakes API timed out"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"BlueStakes API search failed: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to BlueStakes API: {str(e)}"
        )

def parse_bluestakes_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse BlueStakes datetime string to Python datetime object
    """
    if not date_str or date_str == "string":
        return None
    
    try:
        # Handle ISO format with timezone
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        return datetime.fromisoformat(date_str)
    except Exception:
        try:
            # Try common date formats
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        except Exception:
            logging.warning(f"Could not parse datetime: {date_str}")
            return None

def transform_bluestakes_ticket_to_project_ticket(ticket_data: Dict[str, Any], company_id: int = 1) -> ProjectTicketCreate:
    """
    Transform BlueStakes ticket data to ProjectTicketCreate model
    """
    # Parse required dates
    replace_by_date = parse_bluestakes_datetime(ticket_data.get("replace_by_date"))
    
    legal_date = parse_bluestakes_datetime(ticket_data.get("legal_date"))
    
    # Determine if ticket should continue updates based on expiration
    expires = parse_bluestakes_datetime(ticket_data.get("expires"))
    now = datetime.now(timezone.utc)
    is_continue_update = True
    
    if expires and expires < now:
        is_continue_update = False
    
    return ProjectTicketCreate(
        project_id=None,
        ticket_number=ticket_data.get("ticket", ""),
        replace_by_date=replace_by_date,
        old_ticket=ticket_data.get("original_ticket"),
        is_continue_update=is_continue_update,
        legal_date=legal_date,
        company_id=company_id  # TODO: This should be updated in the future to use proper company mapping
    )



@router.post("/sync", response_model=List[ProjectTicketResponse])
async def sync_bluestakes_tickets(
    search_request: BlueStakesSearchRequest,
    user_id: str = Query(..., description="User UUID for authentication")
):
    """
    Sync BlueStakes tickets and insert them into the project_tickets table
    Gets company BlueStakes credentials and fetches first 10 tickets by default
    """
    try:
        company_id = search_request.company_id or 1
        
        # Get company's BlueStakes credentials
        company_result = (get_service_client().table("companies")
                         .select("bluestakes_username, bluestakes_password_encrypted")
                         .eq("id", company_id)
                         .execute())
        
        if not company_result.data:
            raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
        
        company = company_result.data[0]
        username = company.get("bluestakes_username")
        encrypted_password = company.get("bluestakes_password_encrypted")
        
        if not username or not encrypted_password:
            raise HTTPException(
                status_code=400, 
                detail="Company does not have BlueStakes credentials configured"
            )
        
        # Decrypt the password
        try:
            password_ready = False
            # Handle different storage formats
            if isinstance(encrypted_password, str):
                # If it's a string, try to decode it as bytes
                try:
                    # Check if it's a string representation of bytes (like "b'\\x716b6d3232362a'")
                    if encrypted_password.startswith("b'") and encrypted_password.endswith("'"):
                        # Remove the b'' wrapper and decode the hex
                        hex_string = encrypted_password[2:-1].replace('\\x', '')
                        # This is actually the plain password, not encrypted
                        password = bytes.fromhex(hex_string).decode()
                        # Skip the decryption step since this is already the plain password
                        password_ready = True
                    else:
                        encrypted_password = encrypted_password.encode()
                        password_ready = False
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error converting encrypted password to bytes: {str(e)}"
                    )
            elif not isinstance(encrypted_password, bytes):
                raise HTTPException(
                    status_code=500,
                    detail=f"Unsupported encrypted password format: {type(encrypted_password)}"
                )
            
            if not password_ready:
                password = decrypt_password(encrypted_password)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error decrypting BlueStakes credentials: {str(e)}"
            )
        
        # Get BlueStakes auth token
        token = await get_bluestakes_auth_token(username, password)
        
        # Prepare search parameters
        search_params = {
            "limit": search_request.limit or 10,
            "start": search_request.start,
            "end": search_request.end
        }
        
        # Search tickets from BlueStakes
        bluestakes_response = await search_bluestakes_tickets(token, search_params)
        
        # Process the response - handle the nested structure shown in the example
        inserted_tickets = []
        
        if isinstance(bluestakes_response, list) and len(bluestakes_response) > 0:
            # Handle the structure: [{"count": 0, "total": 0, "data": [...]}]
            for response_item in bluestakes_response:
                if isinstance(response_item, dict) and "data" in response_item and isinstance(response_item.get("data"), list):
                    for ticket_data in response_item.get("data", []):
                        if isinstance(ticket_data, dict):
                            try:
                                # Transform BlueStakes ticket to project ticket
                                project_ticket = transform_bluestakes_ticket_to_project_ticket(
                                    ticket_data, company_id
                                )
                                
                                # Insert into database
                                insert_data = {
                                    "project_id": project_ticket.project_id,
                                    "ticket_number": project_ticket.ticket_number,
                                    "replace_by_date": project_ticket.replace_by_date.isoformat(),
                                    "old_ticket": project_ticket.old_ticket,
                                    "is_continue_update": project_ticket.is_continue_update,
                                    "legal_date": project_ticket.legal_date.isoformat() if project_ticket.legal_date else None,
                                    "company_id": project_ticket.company_id
                                }
                                
                                # Insert with conflict handling (upsert on ticket_number)
                                result = (get_service_client().table("project_tickets")
                                         .upsert(insert_data, on_conflict="ticket_number")
                                         .execute())
                                
                                if result.data:
                                    inserted_tickets.extend([ProjectTicketResponse(**ticket) for ticket in result.data])
                                    
                            except Exception as e:
                                logging.error(f"Error processing ticket {ticket_data.get('ticket', 'unknown')}: {str(e)}")
                                continue
        
        return inserted_tickets
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in search_and_insert_bluestakes_tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}") 