"""
BlueStakes API utility functions.
Shared functions for interacting with the BlueStakes API to avoid circular imports.
"""
import httpx
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# BlueStakes API configuration
BLUESTAKES_BASE_URL = "https://newtin-api.bluestakes.org/api"


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
    location_description: Optional[str] = None
    formatted_address: Optional[str] = None
    work_area: Optional[Dict[str, Any]] = None  # GeoJSON data

    # Date Fields
    expires: Optional[datetime] = None
    original_date: Optional[datetime] = None

    # Work Details
    done_for: Optional[str] = None
    type: Optional[str] = None
    
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

    # Responses from utility companies
    responses: Optional[List[Any]] = None


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


async def search_bluestakes_tickets(search_params: Dict[str, Any], company_id: int) -> Dict[str, Any]:
    """
    Search tickets from BlueStakes API using the /tickets/search endpoint.

    Args:
        search_params: Search parameters for the API
        company_id: Company ID for token caching and credential lookup

    Returns:
        Dict containing search results from Bluestakes API

    Note:
        Automatically uses cached tokens and handles token refresh/retry internally.
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

    # Use authenticated request with cached token + auto-retry
    return await make_authenticated_request(
        "GET",
        f"{BLUESTAKES_BASE_URL}/tickets/search",
        company_id,
        params=params
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
    # Strip whitespace from ticket_number to prevent URL encoding issues
    ticket_number = ticket_number.strip()

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
    # Strip whitespace from ticket_number to prevent URL encoding issues
    ticket_number = ticket_number.strip()

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


def format_address_from_bluestakes_data(ticket_data: Dict[str, Any]) -> str:
    """
    Format address string from Bluestakes ticket data.

    This function creates a human-readable address string using:
    - Street name with from/to addresses
    - Cross streets (if available)

    Examples:
    - "123-456 Main St at Oak Ave"
    - "Main St between Oak Ave and Elm St"
    - "Main St"

    Args:
        ticket_data: The Bluestakes ticket data dictionary

    Returns:
        Formatted address string
    """
    try:
        street = ticket_data.get("street")
        st_from_address = ticket_data.get("st_from_address")
        st_to_address = ticket_data.get("st_to_address")
        cross1 = ticket_data.get("cross1")
        cross2 = ticket_data.get("cross2")

        if not street:
            return "Address not available"

        address_parts = []

        # Handle street with from/to addresses
        if st_from_address and st_to_address and st_from_address != "0" and st_to_address != "0":
            if st_from_address == st_to_address:
                address_parts.append(f"{st_from_address} {street}")
            else:
                address_parts.append(f"{st_from_address}-{st_to_address} {street}")
        else:
            address_parts.append(street)

        # Add cross streets if available
        cross_streets = []
        if cross1 and cross1 != " ":
            cross_streets.append(cross1)
        if cross2 and cross2 != " ":
            cross_streets.append(cross2)

        if cross_streets:
            if len(cross_streets) == 1:
                address_parts.append(f"at {cross_streets[0]}")
            else:
                address_parts.append(f"between {cross_streets[0]} and {cross_streets[1]}")

        return " ".join(address_parts)

    except Exception as e:
        logger.warning(f"Error formatting address: {str(e)}")
        return "Address not available"


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
        ticket_number=clean_string(ticket_data.get("ticket", "")) or "",
        replace_by_date=replace_by_date,
        old_ticket=clean_string(ticket_data.get("original_ticket")),
        is_continue_update=is_continue_update,
        legal_date=legal_date,
        company_id=company_id,
        
        # Location & Maps
        place=clean_string(ticket_data.get("place")),
        street=clean_string(ticket_data.get("street")),
        location_description=clean_string(ticket_data.get("location")),
        formatted_address=format_address_from_bluestakes_data(ticket_data),
        work_area=work_area,

        # Date Fields
        expires=expires,
        original_date=original_date,

        # Work Details
        done_for=clean_string(ticket_data.get("done_for")),
        type=clean_string(ticket_data.get("type")),

        # Address Details
        st_from_address=clean_string(ticket_data.get("st_from_address")),
        st_to_address=clean_string(ticket_data.get("st_to_address")),
        cross1=clean_string(ticket_data.get("cross1")),
        cross2=clean_string(ticket_data.get("cross2")),
        county=clean_string(ticket_data.get("county")),
        state=clean_string(ticket_data.get("state")),
        zip=clean_string(ticket_data.get("zip")),

        # Contact Information
        name=clean_string(ticket_data.get("contact")),
        phone=clean_string(ticket_data.get("contact_phone")),
        email=clean_string(ticket_data.get("email")),
        
        # Ticket Management
        revision=clean_string(ticket_data.get("revision")),
        
        # Metadata
        bluestakes_data_updated_at=datetime.now(timezone.utc),
        bluestakes_data=ticket_data  # Store full raw response as backup
    )


async def get_ticket_responses(ticket_number: str, company_id: int) -> Dict[str, Any]:
    """
    Get responses for a specific ticket from BlueStakes API.

    Args:
        ticket_number: The ticket number to fetch responses for
        company_id: Company ID for token caching and credential lookup

    Returns:
        Dict containing the responses data

    Note:
        Automatically uses cached tokens and handles token refresh/retry internally.
    """
    # Strip whitespace from ticket_number to prevent URL encoding issues
    ticket_number = ticket_number.strip()

    # Use authenticated request with cached token + auto-retry
    return await make_authenticated_request(
        "GET",
        f"{BLUESTAKES_BASE_URL}/tickets/{ticket_number}/responses",
        company_id
    )


async def make_authenticated_request(
    method: str,
    url: str,
    company_id: int,
    **kwargs
) -> Dict[str, Any]:
    """
    Make an authenticated request to Bluestakes API with automatic token refresh.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Full URL to request
        company_id: Company ID for token caching and credential lookup
        **kwargs: Additional arguments for httpx request

    Returns:
        Response JSON data

    Raises:
        HTTPException: If request fails after retry
    """
    from utils.bluestakes_token_manager import get_token_for_company, clear_token

    # Get token (cached or fresh) - automatically fetches credentials
    token = await get_token_for_company(company_id)

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
            fresh_token = await get_token_for_company(company_id)

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
