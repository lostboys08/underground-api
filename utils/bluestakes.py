"""
BlueStakes API utility functions.
Shared functions for interacting with the BlueStakes API to avoid circular imports.
"""
import httpx
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# BlueStakes API configuration
BLUESTAKES_BASE_URL = "https://newtiny-api.bluestakes.org/api"


class ProjectTicketCreate(BaseModel):
    project_id: Optional[int] = None
    ticket_number: str
    replace_by_date: datetime
    old_ticket: Optional[str] = None
    is_continue_update: bool = True
    legal_date: Optional[datetime] = None
    company_id: int = 1  # Default to 1 for now


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
            logger.warning(f"Could not parse datetime: {date_str}")
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
