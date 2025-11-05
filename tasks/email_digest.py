"""
Email digest functions for weekly project reports.
These functions handle the generation and sending of weekly project digest emails
to assigned users, including data aggregation and formatting.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pytz
from config.supabase_client import get_service_client
from utils.bluestakes import get_bluestakes_auth_token, get_ticket_details
from utils.encryption import safe_decrypt_password, EncryptionError

logger = logging.getLogger(__name__)


async def send_weekly_project_digest():
    """
    Send weekly project digest emails to all assigned users using Next.js API.
    
    This function:
    1. Queries Supabase for all assigned users
    2. For each user, gets their assigned projects and active tickets
    3. Transforms the data to match the Next.js API format
    4. Sends individual weekly update emails using the 'weeklyUpdate' template
    5. Calculates new tickets (legal date within 7 days) and expiring tickets (expires within 7 days)
    
    This is the bulk email process that aggregates all users and sends emails one at a time.
    """
    logger.info("Starting weekly project digest job")
    
    try:
        from services.email_service import EmailService
        from .user_management import get_unique_assigned_users, get_assigned_projects_for_user
        
        # Get all unique assigned users
        users = await get_unique_assigned_users()
        
        if not users:
            logger.warning("No assigned users found for weekly digest")
            return {
                "status": "completed",
                "message": "No users to send digest to",
                "emails_sent": 0
            }
        
        # Calculate week range (Monday-Friday)
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=4)  # Friday
        
        # Format dates for template
        week_start_str = week_start.strftime("%B %d")
        week_end_str = week_end.strftime("%B %d")
        
        emails_sent = 0
        errors = []
        
        # Process each user
        for user in users:
            try:
                user_email = user["email"]
                user_name = user.get("name", "User").split(" ")[0]
                
                # Get projects assigned to this user
                user_projects = await get_assigned_projects_for_user(user_email)
                
                if not user_projects:
                    continue
                
                # Get tickets for each project
                projects_data = []
                total_tickets = 0
                
                for project in user_projects:
                    project_tickets = await get_project_tickets_for_digest(project["id"])
                    
                    if project_tickets:
                        projects_data.append({
                            "project_id": project["id"],
                            "project_name": project["name"],
                            "tickets": project_tickets,
                            "ticket_count": len(project_tickets)
                        })
                        total_tickets += len(project_tickets)
                
                if not projects_data:
                    continue
                
                # Get company information (assuming all projects belong to the same company)
                company_info = await get_company_info_for_digest(projects_data[0]["project_id"])
                
                # Transform data for new Next.js API format
                user_digest_data = await prepare_user_digest_data(
                    projects_data, 
                    company_info,
                    week_start_str,
                    week_end_str,
                    week_start.year
                )
                
                # Send email using new Next.js API
                result = await EmailService.send_weekly_update(
                    to=[user_email],
                    company_name=user_digest_data["company_name"],
                    projects=user_digest_data["projects"],
                    total_tickets=user_digest_data["total_tickets"],
                    new_tickets=user_digest_data["new_tickets"],
                    expiring_tickets=user_digest_data["expiring_tickets"],
                    report_date=user_digest_data["report_date"]
                )
                
                emails_sent += 1
                
            except Exception as e:
                error_msg = f"Error sending digest to {user.get('email', 'unknown')}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        logger.info(f"Weekly project digest job completed: {emails_sent} emails sent, {len(errors)} errors")
        
        return {
            "status": "completed",
            "message": "Weekly project digest job completed",
            "emails_sent": emails_sent,
            "errors": errors,
            "week_range": f"{week_start_str} - {week_end_str} (Mon-Fri)"
        }
        
    except Exception as e:
        logger.error(f"Critical error in weekly project digest job: {str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "Weekly project digest job failed"
        }


def format_location_from_bluestakes(bluestakes_data: Dict[str, Any]) -> str:
    """
    Format location information from bluestakes ticket data.
    
    Args:
        bluestakes_data: The bluestakes ticket data
        
    Returns:
        Formatted location string
    """
    try:
        street = bluestakes_data.get("street")
        st_from_address = bluestakes_data.get("st_from_address")
        st_to_address = bluestakes_data.get("st_to_address")
        cross1 = bluestakes_data.get("cross1")
        cross2 = bluestakes_data.get("cross2")
        
        if not street:
            return "Location not available"
        
        location_parts = []
        
        # Handle street with from/to addresses
        if st_from_address and st_to_address and st_from_address != "0" and st_to_address != "0":
            if st_from_address == st_to_address:
                location_parts.append(f"{st_from_address} {street}")
            else:
                location_parts.append(f"{st_from_address}-{st_to_address} {street}")
        else:
            location_parts.append(street)
        
        # Add cross streets if available
        cross_streets = []
        if cross1 and cross1 != " ":
            cross_streets.append(cross1)
        if cross2 and cross2 != " ":
            cross_streets.append(cross2)
        
        if cross_streets:
            if len(cross_streets) == 1:
                location_parts.append(f"at {cross_streets[0]}")
            else:
                location_parts.append(f"between {cross_streets[0]} and {cross_streets[1]}")
        
        return " ".join(location_parts)
        
    except Exception as e:
        logger.error(f"Error formatting location: {str(e)}")
        return "Location not available"


async def get_ticket_location_from_bluestakes(ticket_number: str) -> str:
    """
    Get location information for a ticket from bluestakes data.
    First checks local database, then fetches from bluestakes API if needed.
    
    Args:
        ticket_number: The ticket number
        
    Returns:
        Formatted location string
    """
    try:
        # Fetch directly from bluestakes API (no local database caching)
        # We need to get company credentials for this ticket
        company_result = (get_service_client()
                         .table("project_tickets")
                         .select("company_id")
                         .eq("ticket_number", ticket_number)
                         .limit(1)
                         .execute())
        
        if not company_result.data:
            return "Location not available"
        
        company_id = company_result.data[0]["company_id"]
        
        # Get company bluestakes credentials
        company_creds = (get_service_client()
                        .table("companies")
                        .select("bluestakes_username, bluestakes_password")
                        .eq("id", company_id)
                        .not_.is_("bluestakes_username", "null")
                        .not_.is_("bluestakes_password", "null")
                        .execute())
        
        if not company_creds.data:
            return "Location not available"
        
        try:
            # Decrypt the password before using it
            decrypted_password = safe_decrypt_password(company_creds.data[0]["bluestakes_password"])
        except EncryptionError as e:
            logger.error(f"Failed to decrypt password for company {company_id}: {str(e)}")
            return "Location not available"
        
        # Fetch from bluestakes API (with caching)
        token = await get_bluestakes_auth_token(
            company_creds.data[0]["bluestakes_username"],
            decrypted_password,
            company_id  # Pass company_id for token caching
        )
        
        # Get the specific ticket directly
        ticket_data = await get_ticket_details(token, ticket_number)
        
        if ticket_data and not ticket_data.get("error"):
            return format_location_from_bluestakes(ticket_data)
        
        return "Location not available"
        
    except Exception as e:
        logger.error(f"Error getting location for ticket {ticket_number}: {str(e)}")
        return "Location not available"


async def get_project_tickets_for_digest(project_id: int) -> List[Dict[str, Any]]:
    """
    Get active tickets for a project that should be included in the weekly digest.
    Fetches bluestakes data for location information.
    
    Args:
        project_id: The project ID to get tickets for
        
    Returns:
        List of ticket dictionaries with formatted data including location
    """
    try:
        # Query for active tickets in the project (only continue update tickets)
        result = (get_service_client()
                 .table("project_tickets")
                 .select("ticket_number, replace_by_date, legal_date, is_continue_update")
                 .eq("project_id", project_id)
                 .eq("is_continue_update", True)
                 .not_.is_("replace_by_date", "null")
                 .execute())
        
        if not result.data:
            return []
        
        # Format tickets for template
        formatted_tickets = []
        for ticket in result.data:
            # Format dates as "weekday, month date" (e.g., "Monday, January 15")
            replace_by_date = datetime.fromisoformat(ticket["replace_by_date"].replace("Z", "+00:00"))
            replace_by_formatted = replace_by_date.strftime("%A, %B %d")
            
            legal_date_formatted = "N/A"
            if ticket.get("legal_date"):
                legal_date = datetime.fromisoformat(ticket["legal_date"].replace("Z", "+00:00"))
                legal_date_formatted = legal_date.strftime("%A, %B %d")
            
            # All tickets in digest are continue update tickets
            ticket_meta = "Continue Update"
            
            # Get location from bluestakes data
            location = await get_ticket_location_from_bluestakes(ticket["ticket_number"])
            
            formatted_tickets.append({
                "ticket_number": ticket["ticket_number"],
                "replace_by_date_formatted": replace_by_formatted,
                "legal_date_formatted": legal_date_formatted,
                "ticket_meta": ticket_meta,
                "location": location,
                # Add raw datetime objects for new API
                "replace_by_date_raw": replace_by_date,
                "legal_date_raw": legal_date if ticket.get("legal_date") else None
            })
        
        # Sort by replace_by_date (soonest first)
        formatted_tickets.sort(key=lambda t: t["replace_by_date_formatted"])
        
        return formatted_tickets
        
    except Exception as e:
        logger.error(f"Error getting project tickets for digest (project {project_id}): {str(e)}")
        return []


async def get_company_info_for_digest(project_id: int) -> Dict[str, Any]:
    """
    Get company information for a project.
    
    Args:
        project_id: The project ID to get company info for
        
    Returns:
        Dictionary with company information
    """
    try:
        # Get project to find company
        project_result = (get_service_client()
                        .table("projects")
                        .select("company_id")
                        .eq("id", project_id)
                        .execute())
        
        if not project_result.data:
            return {"name": "UndergroundIQ"}
        
        company_id = project_result.data[0]["company_id"]
        
        # Get company details
        company_result = (get_service_client()
                         .table("companies")
                         .select("name")
                         .eq("id", company_id)
                         .execute())
        
        if company_result.data:
            return company_result.data[0]
        else:
            return {"name": "UndergroundIQ"}
            
    except Exception as e:
        logger.error(f"Error getting company info for digest (project {project_id}): {str(e)}")
        return {"name": "UndergroundIQ"}


async def prepare_user_digest_data(
    projects_data: List[Dict[str, Any]], 
    company_info: Dict[str, Any],
    week_start_str: str,
    week_end_str: str,
    year: int
) -> Dict[str, Any]:
    """
    Transform project data into the format required by the Next.js API.
    
    Args:
        projects_data: List of project data with tickets
        company_info: Company information
        week_start_str: Week start string (e.g., "January 15")
        week_end_str: Week end string (e.g., "January 19")
        year: Year for the report
        
    Returns:
        Dict with data formatted for send_weekly_update()
    """
    from services.email_service import Project, Ticket
    from datetime import datetime, timedelta
    
    # Convert projects data to new format
    new_projects = []
    new_tickets_count = 0
    expiring_tickets_count = 0
    total_tickets = 0
    
    # Use America/Denver timezone for all datetime comparisons
    denver_tz = pytz.timezone('America/Denver')
    today = datetime.now(denver_tz)
    seven_days_ago = today - timedelta(days=7)
    seven_days_from_now = today + timedelta(days=7)
    
    for project_data in projects_data:
        tickets = []
        for ticket_data in project_data["tickets"]:
            try:
                # Use the raw datetime objects we added
                legal_date_raw = ticket_data.get("legal_date_raw")
                replace_by_date_raw = ticket_data.get("replace_by_date_raw")
                
                # Convert database datetime objects to Denver timezone for comparison
                legal_date_denver = None
                if legal_date_raw:
                    # Convert UTC datetime to Denver timezone
                    if legal_date_raw.tzinfo is None:
                        legal_date_denver = pytz.utc.localize(legal_date_raw).astimezone(denver_tz)
                    else:
                        legal_date_denver = legal_date_raw.astimezone(denver_tz)
                
                replace_by_date_denver = None
                if replace_by_date_raw:
                    # Convert UTC datetime to Denver timezone
                    if replace_by_date_raw.tzinfo is None:
                        replace_by_date_denver = pytz.utc.localize(replace_by_date_raw).astimezone(denver_tz)
                    else:
                        replace_by_date_denver = replace_by_date_raw.astimezone(denver_tz)
                
                # Convert to YYYY-MM-DD format for the API
                legal_date = legal_date_denver.strftime("%Y-%m-%d") if legal_date_denver else today.strftime("%Y-%m-%d")
                expires_date = replace_by_date_denver.strftime("%Y-%m-%d") if replace_by_date_denver else today.strftime("%Y-%m-%d")
                
                # Count new tickets (legal date within 7 days) - now timezone-aware comparison
                if legal_date_denver and legal_date_denver >= seven_days_ago:
                    new_tickets_count += 1
                
                # Count expiring tickets (expires within 7 days) - now timezone-aware comparison
                if replace_by_date_denver and replace_by_date_denver <= seven_days_from_now:
                    expiring_tickets_count += 1
                
                ticket = Ticket(
                    ticket=ticket_data["ticket_number"],
                    legal=legal_date,
                    expires=expires_date,
                    place=ticket_data.get("location", "Location not available")
                )
                tickets.append(ticket)
                total_tickets += 1
                
            except Exception as e:
                logger.warning(f"Error processing ticket {ticket_data.get('ticket_number', 'unknown')}: {e}")
                continue
        
        if tickets:
            project = Project(
                id=str(project_data["project_id"]),
                name=project_data["project_name"],
                tickets=tickets
            )
            new_projects.append(project)
    
    return {
        "company_name": company_info.get("name", "UndergroundIQ"),
        "projects": new_projects,
        "total_tickets": total_tickets,
        "new_tickets": new_tickets_count,
        "expiring_tickets": expiring_tickets_count,
        "report_date": f"{week_start_str} - {week_end_str}, {year}"
    }
