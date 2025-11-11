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
    
    # Location & Maps
    place: Optional[str] = None
    street: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    work_area: Optional[Dict[str, Any]] = None  # GeoJSON data
    
    # Date Fields
    expires: Optional[datetime] = None
    original_date: Optional[datetime] = None
    
    # Work Details
    done_for: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    
    # Address Details
    st_from_address: Optional[str] = None
    st_to_address: Optional[str] = None
    cross1: Optional[str] = None
    cross2: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    
    # Contact Information
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    
    # Ticket Management
    revision: Optional[str] = None
    
    # Metadata
    bluestakes_data_updated_at: Optional[datetime] = None
    bluestakes_data: Optional[Dict[str, Any]] = None


async def get_bluestakes_auth_token(username: str, password: str, company_id: Optional[int] = None) -> str:
    """
    Get authentication token from BlueStakes API with caching support.
    
    Args:
        username: BlueStakes username
        password: BlueStakes password  
        company_id: Company ID for token caching (optional)
        
    Returns:
        Authentication token
    """
    # If company_id is provided, use token caching
    if company_id:
        from utils.bluestakes_token_manager import get_or_refresh_token
        return await get_or_refresh_token(company_id, username, password)
    
    # Otherwise, authenticate directly (legacy behavior)
    return await get_bluestakes_auth_token_raw(username, password)


async def get_bluestakes_auth_token_raw(username: str, password: str) -> str:
    """
    Get authentication token from BlueStakes API using the /login-json endpoint (no caching).
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


async def search_bluestakes_tickets(token: str, search_params: Dict[str, Any], company_id: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Search tickets from BlueStakes API using the /tickets/search endpoint.
    
    Args:
        token: Authentication token
        search_params: Search parameters for the API
        company_id: Company ID for token refresh (optional)
        username: Username for token refresh (optional) 
        password: Password for token refresh (optional)
    """
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
    
    # Use authenticated request with retry if company credentials are provided
    if company_id and username and password:
        return await make_authenticated_request(
            "GET",
            f"{BLUESTAKES_BASE_URL}/tickets/search",
            company_id,
            username,
            password,
            params=params
        )
    
    # Fallback to direct request (legacy behavior)
    try:
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


async def get_ticket_details(token: str, ticket_number: str) -> Dict[str, Any]:
    """
    Get full ticket details for a specific ticket from BlueStakes API.
    
    Args:
        token: BlueStakes authentication token
        ticket_number: The ticket number to fetch
        
    Returns:
        Dict containing the full ticket data
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{BLUESTAKES_BASE_URL}/tickets/{ticket_number}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "accept": "application/json"
                }
            )
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to BlueStakes API timed out"
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            # Ticket not found
            return {
                "ticket": ticket_number,
                "error": "Ticket not found"
            }
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"BlueStakes API ticket request failed: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to BlueStakes API: {str(e)}"
        )


async def get_ticket_secondary_functions(token: str, ticket_number: str) -> Dict[str, Any]:
    """
    Get secondary functions (update availability) for a specific ticket from BlueStakes API.
    
    Args:
        token: BlueStakes authentication token
        ticket_number: The ticket number to check
        
    Returns:
        Dict containing the secondary functions response
    """
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{BLUESTAKES_BASE_URL}/tickets/{ticket_number}/secondary-functions",
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
        if e.response.status_code == 404:
            # Ticket not found - return a structure indicating no update available
            return {
                "ticket": ticket_number,
                "update": False,
                "error": "Ticket not found"
            }
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"BlueStakes API secondary functions request failed: {e.response.text}"
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
    Transform BlueStakes ticket data to ProjectTicketCreate model with all fields
    """
    # Parse required dates
    replace_by_date = parse_bluestakes_datetime(ticket_data.get("replace_by_date"))
    legal_date = parse_bluestakes_datetime(ticket_data.get("legal_date"))
    expires = parse_bluestakes_datetime(ticket_data.get("expires"))
    original_date = parse_bluestakes_datetime(ticket_data.get("original_date"))
    
    # Determine if ticket should continue updates based on expiration
    now = datetime.now(timezone.utc)
    is_continue_update = True
    
    if expires and expires < now:
        is_continue_update = False
    
    # Handle work_area GeoJSON data
    work_area = None
    if ticket_data.get("work_area"):
        try:
            # Ensure work_area is valid GeoJSON
            work_area_data = ticket_data.get("work_area")
            if isinstance(work_area_data, dict):
                # Validate basic GeoJSON structure
                if work_area_data.get("type") in ["Feature", "FeatureCollection", "Polygon", "MultiPolygon"]:
                    work_area = work_area_data
                else:
                    logger.warning(f"Invalid GeoJSON type in work_area: {work_area_data.get('type')}")
            elif isinstance(work_area_data, str):
                # Try to parse JSON string
                import json
                try:
                    work_area = json.loads(work_area_data)
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse work_area JSON string: {work_area_data}")
        except Exception as e:
            logger.warning(f"Error processing work_area data: {str(e)}")
    
    # Helper function to clean string values (convert empty strings to None)
    def clean_string(value):
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned if cleaned and cleaned != "" else None
        return value
    
    return ProjectTicketCreate(
        project_id=None,
        ticket_number=ticket_data.get("ticket", ""),
        replace_by_date=replace_by_date,
        old_ticket=clean_string(ticket_data.get("original_ticket")),
        is_continue_update=is_continue_update,
        legal_date=legal_date,
        company_id=company_id,
        
        # Location & Maps
        place=clean_string(ticket_data.get("place")),
        street=clean_string(ticket_data.get("street")),
        latitude=clean_string(ticket_data.get("latitude")),
        longitude=clean_string(ticket_data.get("longitude")),
        work_area=work_area,
        
        # Date Fields
        expires=expires,
        original_date=original_date,
        
        # Work Details
        done_for=clean_string(ticket_data.get("done_for")),
        type=clean_string(ticket_data.get("type")),
        priority=clean_string(ticket_data.get("priority")),
        category=clean_string(ticket_data.get("category")),
        
        # Address Details
        st_from_address=clean_string(ticket_data.get("st_from_address")),
        st_to_address=clean_string(ticket_data.get("st_to_address")),
        cross1=clean_string(ticket_data.get("cross1")),
        cross2=clean_string(ticket_data.get("cross2")),
        county=clean_string(ticket_data.get("county")),
        state=clean_string(ticket_data.get("state")),
        zip=clean_string(ticket_data.get("zip")),
        
        # Contact Information
        name=clean_string(ticket_data.get("name")),
        phone=clean_string(ticket_data.get("phone")),
        email=clean_string(ticket_data.get("email")),
        
        # Ticket Management
        revision=clean_string(ticket_data.get("revision")),
        
        # Metadata
        bluestakes_data_updated_at=datetime.now(timezone.utc),
        bluestakes_data=ticket_data  # Store full raw response as backup
    )


async def get_ticket_responses(token: str, ticket_number: str, company_id: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
    """
    Get responses for a specific ticket from BlueStakes API.

    Args:
        token: BlueStakes authentication token
        ticket_number: The ticket number to fetch responses for
        company_id: Company ID for token refresh (optional)
        username: Username for token refresh (optional)
        password: Password for token refresh (optional)

    Returns:
        Dict containing the responses data
    """
    # Use authenticated request with retry if company credentials are provided
    if company_id and username and password:
        return await make_authenticated_request(
            "GET",
            f"{BLUESTAKES_BASE_URL}/tickets/{ticket_number}/responses",
            company_id,
            username,
            password
        )

    # Fallback to direct request (legacy behavior)
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{BLUESTAKES_BASE_URL}/tickets/{ticket_number}/responses",
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
        if e.response.status_code == 404:
            # Ticket not found or no responses
            return {
                "ticket": ticket_number,
                "responses": [],
                "error": "Ticket not found or no responses available"
            }
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"BlueStakes API responses request failed: {e.response.text}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to BlueStakes API: {str(e)}"
        )


async def make_authenticated_request(
    method: str,
    url: str,
    company_id: int,
    username: str,
    password: str,
    **kwargs
) -> Dict[str, Any]:
    """
    Make an authenticated request to Bluestakes API with automatic token refresh.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL to request
        company_id: Company ID for token caching
        username: Bluestakes username
        password: Bluestakes password
        **kwargs: Additional arguments for httpx request
        
    Returns:
        Response JSON data
        
    Raises:
        HTTPException: If request fails after retry
    """
    from utils.bluestakes_token_manager import get_or_refresh_token, clear_token
    
    # Get token (cached or fresh)
    token = await get_or_refresh_token(company_id, username, password)
    
    # Prepare headers
    headers = kwargs.get("headers", {})
    headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    })
    kwargs["headers"] = headers
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await getattr(client, method.lower())(url, **kwargs)
            response.raise_for_status()
            return response.json()
            
    except httpx.HTTPStatusError as e:
        # If we get 401/403, token might be expired - try once more with fresh token
        if e.response.status_code in [401, 403]:
            logger.warning(f"Token expired for company {company_id}, refreshing and retrying...")
            
            # Clear the cached token and get a fresh one
            await clear_token(company_id)
            fresh_token = await get_or_refresh_token(company_id, username, password)
            
            # Update headers with fresh token
            headers["Authorization"] = f"Bearer {fresh_token}"
            kwargs["headers"] = headers
            
            # Retry the request
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await getattr(client, method.lower())(url, **kwargs)
                    response.raise_for_status()
                    return response.json()
            except Exception as retry_e:
                logger.error(f"Request failed even after token refresh: {str(retry_e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"BlueStakes API request failed after token refresh: {str(retry_e)}"
                )
        else:
            # Re-raise non-auth errors
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"BlueStakes API request failed: {e.response.text}"
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Request to BlueStakes API timed out"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to BlueStakes API: {str(e)}"
        )
