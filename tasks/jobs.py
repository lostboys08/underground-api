"""
Background job functions for scheduled tasks.
These functions are called by the cron routes but contain the actual business logic.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import httpx
from config.supabase_client import get_service_client

# Import BlueStakes API functions from utils module to avoid circular imports
from utils.bluestakes import get_bluestakes_auth_token, search_bluestakes_tickets, transform_bluestakes_ticket_to_project_ticket

logger = logging.getLogger(__name__)


async def sync_bluestakes_tickets(company_id: int = None, days_back: int = 28):
    """
    Sync BlueStakes tickets for all companies with credentials or a specific company.
    
    Args:
        company_id: If provided, sync only this company. If None, sync all companies.
        days_back: Number of days to look back for tickets (default 28 days)
    
    Returns:
        Dict with sync statistics
    """
    if company_id:
        logger.info(f"Starting BlueStakes ticket sync for company {company_id}")
    else:
        logger.info("Starting BlueStakes ticket sync for all companies")
    
    sync_stats = {
        "companies_processed": 0,
        "companies_failed": 0,
        "tickets_added": 0,
        "tickets_skipped": 0,
        "tickets_linked": 0,
        "errors": []
    }
    
    try:
        # Step 1: Get companies with BlueStakes credentials
        if company_id:
            companies = await get_company_with_bluestakes_credentials(company_id)
            if not companies:
                logger.warning(f"Company {company_id} not found or has no BlueStakes credentials")
                return sync_stats
        else:
            companies = await get_companies_with_bluestakes_credentials()
            logger.info(f"Found {len(companies)} companies with BlueStakes credentials")
            
            if not companies:
                logger.warning("No companies found with BlueStakes credentials")
                return sync_stats
        
        # Step 2: Calculate date range (last N days)
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        
        # Format dates for BlueStakes API (assuming ISO format)
        search_params = {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "limit": 100  # Reasonable limit per company
        }
        
        logger.info(f"Syncing tickets from {search_params['start']} to {search_params['end']} "
                   f"({days_back} days back)")
        
        # Step 3: Process each company
        for company in companies:
            try:
                company_stats = await sync_company_tickets(company, search_params)
                sync_stats["companies_processed"] += 1
                sync_stats["tickets_added"] += company_stats["tickets_added"]
                sync_stats["tickets_skipped"] += company_stats["tickets_skipped"]
                
                logger.info(f"Company {company['id']} ({company['name']}): "
                           f"Added {company_stats['tickets_added']}, "
                           f"Skipped {company_stats['tickets_skipped']}")
                
            except Exception as e:
                sync_stats["companies_failed"] += 1
                error_msg = f"Failed to sync company {company['id']} ({company['name']}): {str(e)}"
                sync_stats["errors"].append(error_msg)
                logger.error(error_msg)
                # Continue with next company
                continue
        
        # Step 4: Link orphaned tickets to projects based on old_ticket relationships
        try:
            linked_count = await link_orphaned_tickets_to_projects()
            logger.info(f"Linked {linked_count} orphaned tickets to projects")
            sync_stats["tickets_linked"] = linked_count
        except Exception as e:
            logger.error(f"Error linking orphaned tickets to projects: {str(e)}")
            sync_stats["tickets_linked"] = 0

        logger.info(f"BlueStakes ticket sync completed. "
                   f"Companies: {sync_stats['companies_processed']} processed, "
                   f"{sync_stats['companies_failed']} failed. "
                   f"Tickets: {sync_stats['tickets_added']} added, "
                   f"{sync_stats['tickets_skipped']} skipped, "
                   f"{sync_stats.get('tickets_linked', 0)} linked to projects.")
        
        return sync_stats
        
    except Exception as e:
        logger.error(f"Critical error in BlueStakes sync job: {str(e)}")
        sync_stats["errors"].append(f"Critical error: {str(e)}")
        raise


async def get_companies_with_bluestakes_credentials() -> List[Dict[str, Any]]:
    """
    Fetch all companies that have BlueStakes credentials configured.
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("id, name, bluestakes_username, bluestakes_password")
                 .not_.is_("bluestakes_username", "null")
                 .not_.is_("bluestakes_password", "null")
                 .neq("bluestakes_username", "")
                 .neq("bluestakes_password", "")
                 .execute())
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"Error fetching companies with BlueStakes credentials: {str(e)}")
        raise


async def get_company_with_bluestakes_credentials(company_id: int) -> List[Dict[str, Any]]:
    """
    Fetch a specific company with BlueStakes credentials configured.
    Returns as a list to maintain consistency with get_companies_with_bluestakes_credentials.
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("id, name, bluestakes_username, bluestakes_password")
                 .eq("id", company_id)
                 .not_.is_("bluestakes_username", "null")
                 .not_.is_("bluestakes_password", "null")
                 .neq("bluestakes_username", "")
                 .neq("bluestakes_password", "")
                 .execute())
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"Error fetching company {company_id} with BlueStakes credentials: {str(e)}")
        raise


async def sync_company_tickets(company: Dict[str, Any], search_params: Dict[str, Any]) -> Dict[str, int]:
    """
    Sync tickets for a single company.
    """
    company_stats = {"tickets_added": 0, "tickets_skipped": 0}
    
    # Step 1: Authenticate with BlueStakes API
    token = await get_bluestakes_auth_token(
        company["bluestakes_username"], 
        company["bluestakes_password"]
    )
    
    # Step 2: Search for tickets
    bluestakes_response = await search_bluestakes_tickets(token, search_params)
    
    # Debug logging to see what we got from BlueStakes API
    logger.info(f"BlueStakes API response type: {type(bluestakes_response)}")
    logger.info(f"BlueStakes API response: {bluestakes_response}")
    
    # Step 3: Process tickets
    if isinstance(bluestakes_response, list):
        logger.info(f"Processing list response with {len(bluestakes_response)} items")
        for i, response_item in enumerate(bluestakes_response):
            logger.info(f"Response item {i}: type={type(response_item)}, keys={list(response_item.keys()) if isinstance(response_item, dict) else 'N/A'}")
            if isinstance(response_item, dict) and "data" in response_item:
                tickets_data = response_item.get("data", [])
                logger.info(f"Found {len(tickets_data)} tickets in response item {i}")
                
                for ticket_data in tickets_data:
                    if isinstance(ticket_data, dict):
                        ticket_number = ticket_data.get("ticket")
                        
                        if not ticket_number:
                            logger.warning(f"Ticket missing ticket number, skipping: {ticket_data}")
                            continue
                        
                        # Step 4: Check if ticket already exists
                        if await ticket_exists(ticket_number):
                            company_stats["tickets_skipped"] += 1
                            continue
                        
                        # Step 5: Transform and insert ticket
                        try:
                            project_ticket = transform_bluestakes_ticket_to_project_ticket(
                                ticket_data, company["id"]
                            )
                            
                            await insert_project_ticket(project_ticket)
                            company_stats["tickets_added"] += 1
                            
                        except Exception as e:
                            logger.error(f"Error processing ticket {ticket_number}: {str(e)}")
                            continue
    elif isinstance(bluestakes_response, dict):
        logger.info("Processing dict response")
        logger.info(f"Dict keys: {list(bluestakes_response.keys())}")
        
        # Handle direct dict response with tickets data
        if "data" in bluestakes_response:
            tickets_data = bluestakes_response.get("data", [])
            logger.info(f"Found {len(tickets_data)} tickets in direct dict response")
            
            for ticket_data in tickets_data:
                if isinstance(ticket_data, dict):
                    ticket_number = ticket_data.get("ticket")
                    
                    if not ticket_number:
                        logger.warning(f"Ticket missing ticket number, skipping: {ticket_data}")
                        continue
                    
                    # Check if ticket already exists
                    if await ticket_exists(ticket_number):
                        company_stats["tickets_skipped"] += 1
                        continue
                    
                    # Transform and insert ticket
                    try:
                        project_ticket = transform_bluestakes_ticket_to_project_ticket(
                            ticket_data, company["id"]
                        )
                        
                        await insert_project_ticket(project_ticket)
                        company_stats["tickets_added"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing ticket {ticket_number}: {str(e)}")
                        continue
        else:
            logger.warning(f"Dict response does not contain 'data' key. Available keys: {list(bluestakes_response.keys())}")
    else:
        logger.warning(f"Unexpected response type: {type(bluestakes_response)}")
    
    return company_stats


async def ticket_exists(ticket_number: str) -> bool:
    """
    Check if a ticket already exists in the database.
    """
    try:
        result = (get_service_client()
                 .table("project_tickets")
                 .select("ticket_number")
                 .eq("ticket_number", ticket_number)
                 .limit(1)
                 .execute())
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error checking if ticket exists: {str(e)}")
        return False  # Assume it doesn't exist to avoid blocking inserts


async def insert_project_ticket(project_ticket) -> bool:
    """
    Insert a project ticket into the database.
    """
    try:
        insert_data = {
            "project_id": project_ticket.project_id,
            "ticket_number": project_ticket.ticket_number,
            "replace_by_date": project_ticket.replace_by_date.isoformat(),
            "old_ticket": project_ticket.old_ticket,
            "is_continue_update": project_ticket.is_continue_update,
            "legal_date": project_ticket.legal_date.isoformat() if project_ticket.legal_date else None,
            "company_id": project_ticket.company_id
        }
        
        result = (get_service_client()
                 .table("project_tickets")
                 .insert(insert_data)
                 .execute())
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error inserting project ticket: {str(e)}")
        raise


async def link_orphaned_tickets_to_projects() -> int:
    """
    Link tickets with project_id=null to projects based on old_ticket relationships.
    
    Logic:
    1. Find all tickets where project_id is null and old_ticket is not null
    2. For each such ticket, look up the old_ticket in the database
    3. If the old_ticket exists and has a project_id, assign the new ticket to the same project
    
    Returns:
        Number of tickets successfully linked to projects
    """
    try:
        # Step 1: Get all orphaned tickets that have an old_ticket reference
        orphaned_result = (get_service_client()
                          .table("project_tickets")
                          .select("id, ticket_number, old_ticket, company_id")
                          .is_("project_id", "null")
                          .not_.is_("old_ticket", "null")
                          .neq("old_ticket", "")
                          .execute())
        
        if not orphaned_result.data:
            logger.info("No orphaned tickets with old_ticket references found")
            return 0
        
        orphaned_tickets = orphaned_result.data
        logger.info(f"Found {len(orphaned_tickets)} orphaned tickets with old_ticket references")
        
        linked_count = 0
        
        # Step 2: Process each orphaned ticket
        for ticket in orphaned_tickets:
            try:
                ticket_id = ticket["id"]
                old_ticket_number = ticket["old_ticket"]
                company_id = ticket["company_id"]
                
                # Step 3: Look up the old ticket in the database
                old_ticket_result = (get_service_client()
                                   .table("project_tickets")
                                   .select("project_id")
                                   .eq("ticket_number", old_ticket_number)
                                   .eq("company_id", company_id)  # Ensure same company
                                   .not_.is_("project_id", "null")
                                   .limit(1)
                                   .execute())
                
                if old_ticket_result.data:
                    project_id = old_ticket_result.data[0]["project_id"]
                    
                    # Step 4: Update the orphaned ticket with the project_id
                    update_result = (get_service_client()
                                   .table("project_tickets")
                                   .update({"project_id": project_id})
                                   .eq("id", ticket_id)
                                   .execute())
                    
                    if update_result.data:
                        linked_count += 1
                        logger.debug(f"Linked ticket {ticket['ticket_number']} to project {project_id} "
                                   f"based on old_ticket {old_ticket_number}")
                    else:
                        logger.warning(f"Failed to update ticket {ticket['ticket_number']} with project_id {project_id}")
                else:
                    logger.debug(f"No existing project found for old_ticket {old_ticket_number} "
                               f"(ticket: {ticket['ticket_number']})")
                    
            except Exception as e:
                logger.error(f"Error processing orphaned ticket {ticket.get('ticket_number', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Successfully linked {linked_count} orphaned tickets to projects")
        return linked_count
        
    except Exception as e:
        logger.error(f"Error in link_orphaned_tickets_to_projects: {str(e)}")
        raise


async def refresh_todo_table():
    """
    Placeholder function to refresh todo table.
    This will contain logic to update or refresh todo-related data.
    """
    logger.info("Starting todo table refresh job")
    # TODO: Implement todo table refresh logic
    # This would typically:
    # 1. Clean up old/completed todos
    # 2. Update todo priorities
    # 3. Refresh computed fields
    # 4. Maintain data integrity
    logger.info("Todo table refresh job completed")


async def send_ticket_emails():
    """
    Placeholder function to send ticket-related emails.
    This will contain logic to send notifications, updates, or reports via email.
    """
    logger.info("Starting ticket email sending job")
    # TODO: Implement email sending logic
    # This would typically:
    # 1. Identify tickets requiring email notifications
    # 2. Generate appropriate email content
    # 3. Send emails using email service (Resend, etc.)
    # 4. Log email delivery status
    logger.info("Ticket email sending job completed")
