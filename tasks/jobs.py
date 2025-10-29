"""
Background job functions for scheduled tasks.
These functions are called by the cron routes but contain the actual business logic.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
import httpx
from config.supabase_client import get_service_client
# import resend  # No longer needed - using Next.js API
import os

# Import BlueStakes API functions from utils module to avoid circular imports
from utils.bluestakes import get_bluestakes_auth_token, search_bluestakes_tickets, transform_bluestakes_ticket_to_project_ticket, get_ticket_secondary_functions

logger = logging.getLogger(__name__)


async def get_assigned_projects_for_user(email: str) -> List[Dict[str, Any]]:
    """
    Return all projects a user is assigned to via the project_assignments table.

    Args:
        email: The user's email address used in project_assignments

    Returns:
        List of project objects with at least: id, name, company_id
    """
    try:
        if not email:
            return []

        # Fetch assignments for the email (case-insensitive match against user_email)
        assignments_result = (get_service_client()
                             .table("project_assignments")
                             .select("project_id")
                             .ilike("user_email", email.strip())
                             .execute())

        assignment_rows = assignments_result.data or []
        if not assignment_rows:
            return []

        project_ids = sorted({row.get("project_id") for row in assignment_rows if row.get("project_id") is not None})
        if not project_ids:
            return []

        # Fetch project metadata
        projects_result = (get_service_client()
                          .table("projects")
                          .select("id, name, company_id")
                          .in_("id", project_ids)
                          .execute())

        projects = projects_result.data or []
        # Sort deterministically by name then id
        projects.sort(key=lambda p: (p.get("name") or "", p.get("id") or 0))
        return projects

    except Exception as e:
        logger.error(f"Error fetching assigned projects for {email}: {str(e)}")
        raise


async def get_unique_assigned_users() -> List[Dict[str, Any]]:
    """
    Return all unique users present in project_assignments, de-duplicated by user_email (case-insensitive).

    Selection rules when duplicates exist across projects/roles:
    - Prefer the most recently assigned entry by assigned_at.

    Returns:
        List of objects: { "email": str, "name": str }
    """
    try:
        page_size = 1000
        offset = 0
        email_to_user: Dict[str, Dict[str, Any]] = {}

        while True:
            result = (get_service_client()
                     .table("project_assignments")
                     .select("user_email,user_name,assigned_at")
                     .range(offset, offset + page_size - 1)
                     .execute())

            rows = result.data or []
            if not rows:
                break

            for row in rows:
                raw_email = (row.get("user_email") or "").strip()
                if not raw_email:
                    continue
                email_key = raw_email.lower()
                user_name = row.get("user_name")
                assigned_at = row.get("assigned_at") or ""

                existing = email_to_user.get(email_key)
                if not existing or (assigned_at and existing.get("assigned_at", "") < assigned_at):
                    email_to_user[email_key] = {
                        "email": raw_email,
                        "name": user_name,
                        "assigned_at": assigned_at,
                    }

            if len(rows) < page_size:
                break
            offset += page_size

        users = [{"email": u["email"], "name": u.get("name")} for u in email_to_user.values()]
        users.sort(key=lambda u: (u.get("email") or "").lower())
        return users

    except Exception as e:
        logger.error(f"Error fetching unique assigned users: {str(e)}")
        raise


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
                logger.info(f"Processing company {company['id']}: {company.get('name', 'Unknown')}")
                
                # Get tickets that meet updatable criteria for this company
                updatable_tickets = await get_updatable_ticket_candidates(company["id"])
                logger.info(f"Found {len(updatable_tickets)} updatable ticket candidates for company {company['id']}")
                
                company_stats["tickets_processed"] = len(updatable_tickets)
                
                # Get BlueStakes auth token
                token = await get_bluestakes_auth_token(
                    company["bluestakes_username"], 
                    company["bluestakes_password"]
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
                            logger.info(f"Added updatable ticket {ticket['ticket_number']} to database")
                        else:
                            logger.debug(f"Ticket {ticket['ticket_number']} does not have updates available")
                            
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
                
                logger.info(f"Company {company['id']} sync completed: {company_stats}")
                
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
            logger.warning(f"No companies found with BlueStakes credentials for updateable sync")
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
        
        logger.info(f"Found {len(candidates)} updatable ticket candidates for company {company_id} (filtered {len(existing_numbers)} already in updatable table)")
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
            logger.debug(f"Ticket {ticket_number} already exists in updatable_tickets table")
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


async def send_webhook(webhook_url: str, data: Dict[str, Any]) -> bool:
    """
    Send webhook notification with data to specified URL.
    
    Args:
        webhook_url: The webhook endpoint URL
        data: Dictionary containing the data to send
        
    Returns:
        bool: True if webhook was sent successfully, False otherwise
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                webhook_url,
                json=data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Webhook sent successfully to {webhook_url}")
                return True
            else:
                logger.warning(f"Webhook failed with status {response.status_code}: {response.text}")
                return False
                
    except httpx.TimeoutException:
        logger.error(f"Webhook timeout sending to {webhook_url}")
        return False
    except Exception as e:
        logger.error(f"Error sending webhook to {webhook_url}: {str(e)}")
        return False


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
        "old_tickets_updated": 0,
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
            linking_results = await link_orphaned_tickets_to_projects()
            linked_count = linking_results["linked"]
            old_tickets_updated = linking_results["old_tickets_updated"]
            logger.info(f"Linked {linked_count} orphaned tickets to projects and updated {old_tickets_updated} old tickets")
            sync_stats["tickets_linked"] = linked_count
            sync_stats["old_tickets_updated"] = old_tickets_updated
        except Exception as e:
            logger.error(f"Error linking orphaned tickets to projects: {str(e)}")
            sync_stats["tickets_linked"] = 0
            sync_stats["old_tickets_updated"] = 0

        logger.info(f"BlueStakes ticket sync completed. "
                   f"Companies: {sync_stats['companies_processed']} processed, "
                   f"{sync_stats['companies_failed']} failed. "
                   f"Tickets: {sync_stats['tickets_added']} added, "
                   f"{sync_stats['tickets_skipped']} skipped, "
                   f"{sync_stats.get('tickets_linked', 0)} linked to projects, "
                   f"{sync_stats.get('old_tickets_updated', 0)} old tickets updated.")
        
        # Send webhook notification with results
        # TODO: Uncomment when mitchellhub.org webhook server is back online
        # webhook_url = "https://n8n.mitchellhub.org/webhook/171d82c9-2e36-4b1c-9ca8-211fcf9ebaaf"
        # webhook_data = {
        #     "job_type": "daily_bluestakes_sync",
        #     "timestamp": datetime.utcnow().isoformat(),
        #     "status": "completed",
        #     "results": sync_stats,
        #     "summary": {
        #         "companies_processed": sync_stats['companies_processed'],
        #         "companies_failed": sync_stats['companies_failed'],
        #         "tickets_added": sync_stats['tickets_added'],
        #         "tickets_skipped": sync_stats['tickets_skipped'],
        #         "tickets_linked": sync_stats.get('tickets_linked', 0),
        #         "old_tickets_updated": sync_stats.get('old_tickets_updated', 0),
        #         "total_errors": len(sync_stats.get('errors', []))
        #     }
        # }
        # 
        # # Send webhook (don't fail the job if webhook fails)
        # try:
        #     webhook_success = await send_webhook(webhook_url, webhook_data)
        #     if webhook_success:
        #         logger.info("Webhook notification sent successfully")
        #     else:
        #         logger.warning("Failed to send webhook notification")
        # except Exception as e:
        #     logger.error(f"Error sending webhook notification: {str(e)}")
        
        logger.info("Webhook notifications temporarily disabled - mitchellhub.org server down")
        
        return sync_stats
        
    except Exception as e:
        logger.error(f"Critical error in BlueStakes sync job: {str(e)}")
        sync_stats["errors"].append(f"Critical error: {str(e)}")
        
        # Send webhook notification for failed job
        # TODO: Uncomment when mitchellhub.org webhook server is back online
        # webhook_url = "https://n8n.mitchellhub.org/webhook/171d82c9-2e36-4b1c-9ca8-211fcf9ebaaf"
        # webhook_data = {
        #     "job_type": "daily_bluestakes_sync",
        #     "timestamp": datetime.utcnow().isoformat(),
        #     "status": "failed",
        #     "error": str(e),
        #     "results": sync_stats,
        #     "summary": {
        #         "companies_processed": sync_stats['companies_processed'],
        #         "companies_failed": sync_stats['companies_failed'],
        #         "tickets_added": sync_stats['tickets_added'],
        #         "tickets_skipped": sync_stats['tickets_skipped'],
        #         "tickets_linked": sync_stats.get('tickets_linked', 0),
        #         "old_tickets_updated": sync_stats.get('old_tickets_updated', 0),
        #         "total_errors": len(sync_stats.get('errors', []))
        #     }
        # }
        # 
        # # Send webhook (don't fail further if webhook fails)
        # try:
        #     await send_webhook(webhook_url, webhook_data)
        #     logger.info("Error webhook notification sent")
        # except Exception as webhook_error:
        #     logger.error(f"Failed to send error webhook: {str(webhook_error)}")
        
        logger.info("Error webhook notifications temporarily disabled - mitchellhub.org server down")
        
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


async def link_orphaned_tickets_to_projects() -> Dict[str, int]:
    """
    Link tickets with project_id=null to projects based on old_ticket relationships.
    
    Logic:
    1. Find all tickets where project_id is null and old_ticket is not null
    2. For each such ticket, look up the old_ticket in the database
    3. If the old_ticket exists and has a project_id, assign the new ticket to the same project
    4. Update the old ticket to set is_continue_update to FALSE
    
    Returns:
        Dict with counts of tickets linked and old tickets updated
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
            return {"linked": 0, "old_tickets_updated": 0}
        
        orphaned_tickets = orphaned_result.data
        logger.info(f"Found {len(orphaned_tickets)} orphaned tickets with old_ticket references")
        
        linked_count = 0
        old_tickets_updated_count = 0
        
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
                        
                        # Update the old ticket to set is_continue_update to FALSE
                        try:
                            if await update_old_ticket_continue_status(old_ticket_number, company_id):
                                old_tickets_updated_count += 1
                        except Exception as e:
                            logger.error(f"Error updating old ticket {old_ticket_number} continue status: {str(e)}")
                    else:
                        logger.warning(f"Failed to update ticket {ticket['ticket_number']} with project_id {project_id}")
                else:
                    logger.debug(f"No existing project found for old_ticket {old_ticket_number} "
                               f"(ticket: {ticket['ticket_number']})")
                    
            except Exception as e:
                logger.error(f"Error processing orphaned ticket {ticket.get('ticket_number', 'unknown')}: {str(e)}")
                continue
        
        logger.info(f"Successfully linked {linked_count} orphaned tickets to projects and updated {old_tickets_updated_count} old tickets")
        return {"linked": linked_count, "old_tickets_updated": old_tickets_updated_count}
        
    except Exception as e:
        logger.error(f"Error in link_orphaned_tickets_to_projects: {str(e)}")
        raise


async def update_old_ticket_continue_status(old_ticket_number: str, company_id: int) -> bool:
    """
    Update the is_continue_update status to FALSE for an old ticket when a new ticket is linked to a project.
    
    Args:
        old_ticket_number: The ticket number of the old ticket to update
        company_id: The company ID to ensure we're updating the right ticket
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        # Update the old ticket to set is_continue_update to FALSE
        update_result = (get_service_client()
                        .table("project_tickets")
                        .update({"is_continue_update": False})
                        .eq("ticket_number", old_ticket_number)
                        .eq("company_id", company_id)
                        .execute())
        
        if update_result.data:
            logger.debug(f"Updated old ticket {old_ticket_number} is_continue_update to FALSE")
            return True
        else:
            logger.warning(f"No old ticket found to update: {old_ticket_number} for company {company_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating old ticket {old_ticket_number} continue status: {str(e)}")
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
    Send ticket-related emails for scheduled cron job.
    This function identifies tickets requiring notifications and sends appropriate emails.
    """
    logger.info("Starting ticket email sending job")
    
    try:
        from services.email_service import EmailService
        
        # 1. Identify tickets requiring email notifications
        # For now, we'll send a test email to demonstrate the functionality
        # In a real implementation, you would:
        # - Query the database for tickets with specific criteria
        # - Find users assigned to those tickets
        # - Generate appropriate email content for each ticket
        
        # Example: Send a test ticket notification
        test_result = await EmailService.send_test_email()
        logger.info(f"Test email sent from cron job: {test_result}")
        
        # TODO: Implement actual ticket email logic
        # Example implementation would look like:
        # tickets = await get_tickets_requiring_notifications()
        # for ticket in tickets:
        #     users = await get_assigned_users_for_ticket(ticket['id'])
        #     for user in users:
        #         await EmailService.send_ticket_notification_email(
        #             to_emails=[user['email']],
        #             ticket_number=ticket['ticket_number'],
        #             ticket_details=ticket,
        #             email_type="notification"
        #         )
        
        logger.info("Ticket email sending job completed successfully")
        return {
            "status": "completed",
            "message": "Ticket email job processed",
            "emails_sent": 1,  # In real implementation, count actual emails sent
            "test_result": test_result
        }
        
    except Exception as e:
        logger.error(f"Error in ticket email sending job: {str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "message": "Ticket email job failed"
        }


async def send_notification_emails():
    """
    Send general notification emails for scheduled cron job.
    This function handles non-ticket-specific notifications.
    """
    logger.info("Starting notification email sending job")
    
    try:
        from services.email_service import EmailService
        
        # TODO: Implement actual notification email logic
        # This would typically:
        # 1. Query database for pending notifications
        # 2. Generate email content based on notification type  
        # 3. Send emails using email service
        # 4. Update notification status in database
        # 5. Log email delivery status
        
        # For now, demonstrate functionality with a test email
        test_result = await EmailService.send_test_email()
        logger.info(f"Test notification email sent from cron job: {test_result}")
        
        timestamp = datetime.utcnow().isoformat()
        logger.info(f"Notification email job completed at {timestamp}")
        
        return {
            "status": "completed",
            "timestamp": timestamp,
            "message": "Notification email job processed",
            "emails_sent": 1,  # In real implementation, count actual emails sent
            "test_result": test_result
        }
        
    except Exception as e:
        logger.error(f"Error in notification email sending job: {str(e)}")
        return {
            "status": "failed",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "message": "Notification email job failed"
        }


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
        
        # Get all unique assigned users
        users = await get_unique_assigned_users()
        logger.info(f"Found {len(users)} assigned users for weekly digest")
        
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
                    logger.debug(f"No projects found for user {user_email}")
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
                    logger.debug(f"No active tickets found for user {user_email}")
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
                logger.info(f"Weekly digest sent to {user_email}: {result}")
                
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


async def save_bluestakes_ticket_data(ticket_number: str, bluestakes_data: Dict[str, Any]) -> None:
    """
    Save the full bluestakes ticket response to the database.
    
    Args:
        ticket_number: The ticket number
        bluestakes_data: The full response from bluestakes API
    """
    try:
        # Check if ticket data already exists
        existing = (get_service_client()
                   .table("bluestakes_tickets")
                   .select("ticket_number")
                   .eq("ticket_number", ticket_number)
                   .limit(1)
                   .execute())
        
        if existing.data:
            # Update existing record
            (get_service_client()
             .table("bluestakes_tickets")
             .update({
                 "ticket_data": bluestakes_data,
                 "updated_at": datetime.utcnow().isoformat()
             })
             .eq("ticket_number", ticket_number)
             .execute())
        else:
            # Insert new record
            (get_service_client()
             .table("bluestakes_tickets")
             .insert({
                 "ticket_number": ticket_number,
                 "ticket_data": bluestakes_data,
                 "created_at": datetime.utcnow().isoformat(),
                 "updated_at": datetime.utcnow().isoformat()
             })
             .execute())
        
        logger.info(f"Saved bluestakes data for ticket {ticket_number}")
        
    except Exception as e:
        logger.error(f"Error saving bluestakes data for ticket {ticket_number}: {str(e)}")


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
        
        # Fetch from bluestakes API
        token = await get_bluestakes_auth_token(
            company_creds.data[0]["bluestakes_username"],
            company_creds.data[0]["bluestakes_password"]
        )
        
        # Get the specific ticket directly
        from utils.bluestakes import get_ticket_details
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
            return {"name": "UndergroundIQ", "address": "123 Main St, City, State 12345"}
        
        company_id = project_result.data[0]["company_id"]
        
        # Get company details
        company_result = (get_service_client()
                         .table("companies")
                         .select("name, address")
                         .eq("id", company_id)
                         .execute())
        
        if company_result.data:
            return company_result.data[0]
        else:
            return {"name": "UndergroundIQ", "address": "123 Main St, City, State 12345"}
            
    except Exception as e:
        logger.error(f"Error getting company info for digest (project {project_id}): {str(e)}")
        return {"name": "UndergroundIQ", "address": "123 Main St, City, State 12345"}


async def render_weekly_digest_template(template_data: Dict[str, Any], projects_data: List[Dict[str, Any]]) -> str:
    """
    Render the weekly digest template with project data.
    
    Args:
        template_data: Base template variables
        projects_data: List of project data with tickets
        
    Returns:
        Rendered HTML content
    """
    try:
        from services.email_service import EmailService
        
        # Load the template
        template_content = EmailService._load_template("weekly_projects_digest.html")
        
        # Start with base template data
        rendered = EmailService._render_template(template_content, **template_data)
        
        # Handle project blocks - find the project block section
        project_block_start = "<!-- PROJECT_BLOCK_START -->"
        project_block_end = "<!-- PROJECT_BLOCK_END -->"
        
        start_idx = rendered.find(project_block_start)
        end_idx = rendered.find(project_block_end)
        
        if start_idx == -1 or end_idx == -1:
            logger.warning("Could not find project block markers in template")
            return rendered
        
        # Extract the project block template
        project_block_template = rendered[start_idx:end_idx + len(project_block_end)]
        
        # Generate project blocks
        project_blocks = []
        for project in projects_data:
            # Render project block with project data (removed project_id)
            project_block = EmailService._render_template(
                project_block_template,
                project_name=project["project_name"],
                project_ticket_count=str(project["ticket_count"])
            )
            
            # Handle ticket items within this project block
            ticket_item_start = "<!-- TICKET_ITEM_START -->"
            ticket_item_end = "<!-- TICKET_ITEM_END -->"
            
            ticket_start_idx = project_block.find(ticket_item_start)
            ticket_end_idx = project_block.find(ticket_item_end)
            
            if ticket_start_idx != -1 and ticket_end_idx != -1:
                # Extract ticket item template
                ticket_item_template = project_block[ticket_start_idx:ticket_end_idx + len(ticket_item_end)]
                
                # Generate ticket items
                ticket_items = []
                for ticket in project["tickets"]:
                    # Add location to ticket data for template rendering
                    ticket_data = ticket.copy()
                    ticket_data["location"] = ticket.get("location", "Location not available")
                    ticket_item = EmailService._render_template(ticket_item_template, **ticket_data)
                    ticket_items.append(ticket_item)
                
                # Replace ticket section with generated items
                ticket_section = "".join(ticket_items)
                project_block = (project_block[:ticket_start_idx] + 
                               ticket_section + 
                               project_block[ticket_end_idx + len(ticket_item_end):])
            
            project_blocks.append(project_block)
        
        # Replace the original project block with all generated blocks
        all_project_blocks = "".join(project_blocks)
        final_rendered = (rendered[:start_idx] + 
                         all_project_blocks + 
                         rendered[end_idx + len(project_block_end):])
        
        return final_rendered
        
    except Exception as e:
        logger.error(f"Error rendering weekly digest template: {str(e)}")
        raise


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
    
    today = datetime.now()
    seven_days_ago = today - timedelta(days=7)
    seven_days_from_now = today + timedelta(days=7)
    
    for project_data in projects_data:
        tickets = []
        for ticket_data in project_data["tickets"]:
            try:
                # Use the raw datetime objects we added
                legal_date_raw = ticket_data.get("legal_date_raw")
                replace_by_date_raw = ticket_data.get("replace_by_date_raw")
                
                # Convert to YYYY-MM-DD format for the API
                legal_date = legal_date_raw.strftime("%Y-%m-%d") if legal_date_raw else today.strftime("%Y-%m-%d")
                expires_date = replace_by_date_raw.strftime("%Y-%m-%d") if replace_by_date_raw else today.strftime("%Y-%m-%d")
                
                # Count new tickets (legal date within 7 days)
                if legal_date_raw and legal_date_raw >= seven_days_ago:
                    new_tickets_count += 1
                
                # Count expiring tickets (expires within 7 days)
                if replace_by_date_raw and replace_by_date_raw <= seven_days_from_now:
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
