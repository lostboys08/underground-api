from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import httpx
import asyncio
from config.supabase_client import get_service_client
from utils.auth import get_current_user_id
from utils.encryption import decrypt_password
import logging

router = APIRouter(prefix="/tickets", tags=["Tickets"])

# BlueStakes API configuration
BLUESTAKES_BASE_URL = "https://newtiny-api.bluestakes.org/api"

# Pydantic models for request/response
class TicketCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: Optional[str] = "open"  # open, in_progress, closed, cancelled
    priority: Optional[str] = "medium"  # low, medium, high, urgent
    assigned_to: Optional[UUID] = None
    company_id: Optional[int] = None

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[UUID] = None
    company_id: Optional[int] = None

class TicketResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: str
    priority: str
    assigned_to: Optional[UUID]
    created_by: UUID
    company_id: Optional[int]
    created_at: str
    updated_at: str

class TicketWithDetails(TicketResponse):
    company_name: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_by_name: Optional[str] = None

# Project Tickets models for BlueStakes integration
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

@router.post("/", response_model=TicketResponse)
async def create_ticket(
    ticket: TicketCreate,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Create a new ticket
    """
    try:
        # Prepare data for insertion
        insert_data = {
            "title": ticket.title,
            "description": ticket.description,
            "status": ticket.status,
            "priority": ticket.priority,
            "assigned_to": str(ticket.assigned_to) if ticket.assigned_to else None,
            "created_by": current_user_id,
            "company_id": ticket.company_id
        }
        
        result = get_service_client().table("tickets").insert(insert_data).execute()
        
        if not result.data:
            raise HTTPException(status_code=400, detail="Failed to create ticket")
        
        created_ticket = result.data[0]
        return TicketResponse(**created_ticket)
        
    except Exception as e:
        logging.error(f"Error creating ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/{ticket_id}", response_model=TicketWithDetails)
async def get_ticket(ticket_id: int):
    """
    Get a ticket by ID with related information
    """
    try:
        result = (get_service_client().table("tickets")
                 .select("""
                     *,
                     companies(name),
                     assigned_profile:profiles!tickets_assigned_to_fkey(display_name),
                     creator_profile:profiles!tickets_created_by_fkey(display_name)
                 """)
                 .eq("id", ticket_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        ticket = result.data[0]
        
        # Format the response
        response_data = {
            **ticket,
            "company_name": ticket.get("companies", {}).get("name") if ticket.get("companies") else None,
            "assigned_to_name": ticket.get("assigned_profile", {}).get("display_name") if ticket.get("assigned_profile") else None,
            "created_by_name": ticket.get("creator_profile", {}).get("display_name") if ticket.get("creator_profile") else None
        }
        
        # Remove nested objects
        for key in ["companies", "assigned_profile", "creator_profile"]:
            if key in response_data:
                del response_data[key]
        
        return TicketWithDetails(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching ticket {ticket_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/", response_model=List[TicketWithDetails])
async def list_tickets(
    limit: int = Query(default=10, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    company_id: Optional[int] = Query(default=None),
    assigned_to: Optional[UUID] = Query(default=None)
):
    """
    List tickets with optional filtering
    """
    try:
        query = (get_service_client().table("tickets")
                .select("""
                    *,
                    companies(name),
                    assigned_profile:profiles!tickets_assigned_to_fkey(display_name),
                    creator_profile:profiles!tickets_created_by_fkey(display_name)
                """)
                .range(offset, offset + limit - 1)
                .order("created_at", desc=True))
        
        # Add filters if provided
        if status:
            query = query.eq("status", status)
        if priority:
            query = query.eq("priority", priority)
        if company_id:
            query = query.eq("company_id", company_id)
        if assigned_to:
            query = query.eq("assigned_to", str(assigned_to))
        
        result = query.execute()
        
        # Format the response
        tickets = []
        for ticket in result.data:
            response_data = {
                **ticket,
                "company_name": ticket.get("companies", {}).get("name") if ticket.get("companies") else None,
                "assigned_to_name": ticket.get("assigned_profile", {}).get("display_name") if ticket.get("assigned_profile") else None,
                "created_by_name": ticket.get("creator_profile", {}).get("display_name") if ticket.get("creator_profile") else None
            }
            
            # Remove nested objects
            for key in ["companies", "assigned_profile", "creator_profile"]:
                if key in response_data:
                    del response_data[key]
            
            tickets.append(TicketWithDetails(**response_data))
        
        return tickets
        
    except Exception as e:
        logging.error(f"Error listing tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: int, ticket_update: TicketUpdate):
    """
    Update a ticket by ID
    """
    try:
        # Build update data (only include non-None fields)
        update_data = {}
        if ticket_update.title is not None:
            update_data["title"] = ticket_update.title
        if ticket_update.description is not None:
            update_data["description"] = ticket_update.description
        if ticket_update.status is not None:
            update_data["status"] = ticket_update.status
        if ticket_update.priority is not None:
            update_data["priority"] = ticket_update.priority
        if ticket_update.assigned_to is not None:
            update_data["assigned_to"] = str(ticket_update.assigned_to)
        if ticket_update.company_id is not None:
            update_data["company_id"] = ticket_update.company_id
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        result = (get_service_client().table("tickets")
                 .update(update_data)
                 .eq("id", ticket_id)
                 .execute())
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
        updated_ticket = result.data[0]
        return TicketResponse(**updated_ticket)
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error updating ticket {ticket_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

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

@router.get("/my/tickets", response_model=List[TicketWithDetails])
async def get_my_tickets(
    current_user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=10, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    Get tickets assigned to the current user
    """
    try:
        result = (get_service_client().table("tickets")
                 .select("""
                     *,
                     companies(name),
                     assigned_profile:profiles!tickets_assigned_to_fkey(display_name),
                     creator_profile:profiles!tickets_created_by_fkey(display_name)
                 """)
                 .eq("assigned_to", current_user_id)
                 .range(offset, offset + limit - 1)
                 .order("created_at", desc=True)
                 .execute())
        
        # Format the response
        tickets = []
        for ticket in result.data:
            response_data = {
                **ticket,
                "company_name": ticket.get("companies", {}).get("name") if ticket.get("companies") else None,
                "assigned_to_name": ticket.get("assigned_profile", {}).get("display_name") if ticket.get("assigned_profile") else None,
                "created_by_name": ticket.get("creator_profile", {}).get("display_name") if ticket.get("creator_profile") else None
            }
            
            # Remove nested objects
            for key in ["companies", "assigned_profile", "creator_profile"]:
                if key in response_data:
                    del response_data[key]
            
            tickets.append(TicketWithDetails(**response_data))
        
        return tickets
        
    except Exception as e:
        logging.error(f"Error fetching user tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/created/by-me", response_model=List[TicketWithDetails])
async def get_tickets_created_by_me(
    current_user_id: str = Depends(get_current_user_id),
    limit: int = Query(default=10, le=100),
    offset: int = Query(default=0, ge=0)
):
    """
    Get tickets created by the current user
    """
    try:
        result = (get_service_client().table("tickets")
                 .select("""
                     *,
                     companies(name),
                     assigned_profile:profiles!tickets_assigned_to_fkey(display_name),
                     creator_profile:profiles!tickets_created_by_fkey(display_name)
                 """)
                 .eq("created_by", current_user_id)
                 .range(offset, offset + limit - 1)
                 .order("created_at", desc=True)
                 .execute())
        
        # Format the response
        tickets = []
        for ticket in result.data:
            response_data = {
                **ticket,
                "company_name": ticket.get("companies", {}).get("name") if ticket.get("companies") else None,
                "assigned_to_name": ticket.get("assigned_profile", {}).get("display_name") if ticket.get("assigned_profile") else None,
                "created_by_name": ticket.get("creator_profile", {}).get("display_name") if ticket.get("creator_profile") else None
            }
            
            # Remove nested objects
            for key in ["companies", "assigned_profile", "creator_profile"]:
                if key in response_data:
                    del response_data[key]
            
            tickets.append(TicketWithDetails(**response_data))
        
        return tickets
        
    except Exception as e:
        logging.error(f"Error fetching created tickets: {str(e)}")
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
    if not replace_by_date:
        # If no replace_by_date, use expires or work_date as fallback
        replace_by_date = (
            parse_bluestakes_datetime(ticket_data.get("expires")) or
            parse_bluestakes_datetime(ticket_data.get("work_date")) or
            datetime.now(timezone.utc)
        )
    
    legal_date = parse_bluestakes_datetime(ticket_data.get("legal_date"))
    
    # Determine if ticket should continue updates based on expiration
    expires = parse_bluestakes_datetime(ticket_data.get("expires"))
    now = datetime.now(timezone.utc)
    is_continue_update = True
    
    if expires and expires < now:
        is_continue_update = False
    
    return ProjectTicketCreate(
        project_id=None,  # Keep null for now as requested
        ticket_number=ticket_data.get("ticket", ""),
        replace_by_date=replace_by_date,
        old_ticket=ticket_data.get("original_ticket"),
        is_continue_update=is_continue_update,
        legal_date=legal_date,
        company_id=company_id  # TODO: This should be updated in the future to use proper company mapping
    )

@router.post("/search", response_model=List[ProjectTicketResponse])
async def search_and_insert_bluestakes_tickets(
    search_request: BlueStakesSearchRequest,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Search BlueStakes tickets and insert them into the project_tickets table
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
            password = decrypt_password(encrypted_password)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail="Error decrypting BlueStakes credentials"
            )
        
        # Get BlueStakes auth token
        token = await get_bluestakes_auth_token(username, password)
        
        # Prepare search parameters
        search_params = {
            "limit": search_request.limit or 10,
            "offset": search_request.offset or 0,
            "sort": search_request.sort,
            "start": search_request.start,
            "end": search_request.end,
            "state": search_request.state,
            "county": search_request.county
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