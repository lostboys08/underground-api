"""
Updatable tickets management functions.
These functions handle the identification and management of tickets that can be updated,
including syncing with BlueStakes API to check for update availability.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from config.supabase_client import get_service_client
from utils.bluestakes import get_bluestakes_auth_token, get_ticket_secondary_functions
from utils.encryption import safe_decrypt_password, EncryptionError

logger = logging.getLogger(__name__)


async def sync_updateable_tickets(company_id: int = None) -> Dict[str, Any]:
    """
    Sync updatable tickets - query database for tickets meeting criteria,
    check BlueStakes API for update availability, and populate the updatable_tickets table.
    
    Args:
        company_id: Optional company ID to sync. If not provided, syncs all companies.
        
    Returns:
        Dict containing sync statistics
    """
    logger.info(f"Starting updatable tickets sync for company_id: {company_id}")
    
    stats = {
        "companies_processed": 0,
        "companies_failed": 0,
        "tickets_processed": 0,
        "tickets_checked": 0,
        "tickets_added": 0,
        "api_failures": 0,
        "errors": []
    }
    
    try:
        # Get companies to process
        companies = await get_companies_for_updateable_sync(company_id)
        
        for company in companies:
            company_stats = {"tickets_processed": 0, "tickets_checked": 0, "tickets_added": 0, "api_failures": 0}
            
            try:
                # Get tickets that meet updatable criteria for this company
                updatable_tickets = await get_updatable_ticket_candidates(company["id"])
                company_stats["tickets_processed"] = len(updatable_tickets)
                
                try:
                    # Decrypt the password before using it
                    decrypted_password = safe_decrypt_password(company["bluestakes_password"])
                except EncryptionError as e:
                    logger.error(f"Failed to decrypt password for company {company['id']}: {str(e)}")
                    company_stats["api_failures"] += 1
                    continue
                
                # Get BlueStakes auth token (with caching)
                token = await get_bluestakes_auth_token(
                    company["bluestakes_username"], 
                    decrypted_password,
                    company["id"]  # Pass company_id for token caching
                )
                
                # Process each ticket
                for ticket in updatable_tickets:
                    try:
                        # Check if ticket has updates available via BlueStakes API
                        secondary_functions = await get_ticket_secondary_functions(
                            token,
                            ticket["ticket_number"]
                        )
                        
                        company_stats["tickets_checked"] += 1
                        
                        # Check if ticket has update=true
                        if secondary_functions.get("update") is True:
                            # Add ticket to updatable_tickets table
                            await insert_updatable_ticket(ticket["ticket_number"])
                            company_stats["tickets_added"] += 1
                            
                    except Exception as e:
                        company_stats["api_failures"] += 1
                        error_msg = f"Error processing ticket {ticket.get('ticket_number', 'unknown')} for company {company['id']}: {str(e)}"
                        logger.error(error_msg)
                        stats["errors"].append(error_msg)
                
                # Update overall stats
                stats["tickets_processed"] += company_stats["tickets_processed"]
                stats["tickets_checked"] += company_stats["tickets_checked"]
                stats["tickets_added"] += company_stats["tickets_added"]
                stats["api_failures"] += company_stats["api_failures"]
                stats["companies_processed"] += 1
                
            except Exception as e:
                stats["companies_failed"] += 1
                error_msg = f"Failed to sync company {company['id']}: {str(e)}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
        
        logger.info(f"Updatable tickets sync completed: {stats}")
        return stats
        
    except Exception as e:
        error_msg = f"Fatal error in updatable tickets sync: {str(e)}"
        logger.error(error_msg)
        stats["errors"].append(error_msg)
        return stats


async def get_companies_for_updateable_sync(company_id: int = None) -> List[Dict[str, Any]]:
    """
    Get companies that have BlueStakes credentials configured for updateable tickets sync.
    """
    try:
        query = get_service_client().table("companies").select("id, name, bluestakes_username, bluestakes_password")
        
        # Filter for companies with BlueStakes credentials
        query = query.not_.is_("bluestakes_username", "null").not_.is_("bluestakes_password", "null")
        
        if company_id:
            query = query.eq("id", company_id)
        
        result = query.execute()
        
        if not result.data:
            return []
        
        return result.data
        
    except Exception as e:
        logger.error(f"Error fetching companies for updateable sync: {str(e)}")
        raise


async def get_updatable_ticket_candidates(company_id: int) -> List[Dict[str, Any]]:
    """
    Query the database for tickets that meet the criteria for being updatable.
    
    Criteria:
    - Tickets with is_continue_update = True
    - Tickets where replace_by_date is no more than 7 days in the future
    - Tickets not already in the updatable_tickets table
    """
    try:
        # Calculate cutoff date (7 days from now)
        future_cutoff = datetime.now() + timedelta(days=7)
        
        # Query project_tickets for updatable candidates
        result = (get_service_client()
                 .table("project_tickets")
                 .select("id, ticket_number, project_id, replace_by_date, legal_date, company_id")
                 .eq("company_id", company_id)
                 .eq("is_continue_update", True)
                 .lte("replace_by_date", future_cutoff.isoformat())
                 .gte("replace_by_date", datetime.now().isoformat())
                 .execute())
        
        if not result.data:
            return []
        
        # Filter out tickets that are already in updatable_tickets table
        ticket_numbers = [ticket["ticket_number"] for ticket in result.data]
        
        existing_updatable = (get_service_client()
                            .table("updatable_tickets")
                            .select("ticket_number")
                            .in_("ticket_number", ticket_numbers)
                            .execute())
        
        existing_numbers = set(ticket["ticket_number"] for ticket in existing_updatable.data or [])
        
        # Return only tickets that aren't already in the updatable_tickets table
        candidates = [ticket for ticket in result.data if ticket["ticket_number"] not in existing_numbers]
        
        return candidates
        
    except Exception as e:
        logger.error(f"Error getting updatable ticket candidates for company {company_id}: {str(e)}")
        raise


async def insert_updatable_ticket(ticket_number: str) -> bool:
    """
    Insert a ticket into the updatable_tickets table.
    
    Args:
        ticket_number: The ticket number to insert
        
    Returns:
        bool: True if insertion was successful
    """
    try:
        # Check if ticket already exists (prevent duplicates)
        existing = (get_service_client()
                   .table("updatable_tickets")
                   .select("id")
                   .eq("ticket_number", ticket_number)
                   .execute())
        
        if existing.data:
            return False
        
        # Insert new record
        insert_data = {
            "ticket_number": ticket_number
            # created_at will be automatically set by the database default
        }
        
        result = (get_service_client()
                 .table("updatable_tickets")
                 .insert(insert_data)
                 .execute())
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error inserting updatable ticket {ticket_number}: {str(e)}")
        raise
