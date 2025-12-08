"""
BlueStakes ticket synchronization functions.
These functions handle the synchronization of tickets from the BlueStakes API
to the local database, including authentication, data transformation, and linking.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List
from config.supabase_client import get_service_client
from utils.bluestakes import (
    get_bluestakes_auth_token,
    search_bluestakes_tickets,
    transform_bluestakes_ticket_to_project_ticket
)
from utils.encryption import safe_decrypt_password, EncryptionError
from tasks.response_sync import sync_bluestakes_responses
from tasks.updatable_tickets import sync_updateable_tickets

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
        "old_tickets_updated": 0,
        "updateable_tickets_checked": 0,
        "updateable_tickets_found": 0,
        "responses_synced": 0,
        "responses_failed": 0,
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
        
        # Step 3: Process each company
        for company in companies:
            try:
                company_stats = await sync_company_tickets(company, search_params)
                sync_stats["companies_processed"] += 1
                sync_stats["tickets_added"] += company_stats["tickets_added"]
                sync_stats["tickets_skipped"] += company_stats["tickets_skipped"]
                
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

        # Step 5: Sync updateable tickets
        logger.info("Starting updateable tickets sync...")
        try:
            updateable_stats = await sync_updateable_tickets(company_id)
            sync_stats["updateable_tickets_checked"] = updateable_stats.get("tickets_checked", 0)
            sync_stats["updateable_tickets_found"] = updateable_stats.get("updateable_tickets_found", 0)
            logger.info(f"Updateable tickets sync completed: {updateable_stats.get('tickets_checked', 0)} checked, "
                       f"{updateable_stats.get('updateable_tickets_found', 0)} updateable found")
        except Exception as e:
            logger.error(f"Error syncing updateable tickets: {str(e)}")
            sync_stats["updateable_tickets_checked"] = 0
            sync_stats["updateable_tickets_found"] = 0
            sync_stats["errors"].append(f"Updateable tickets sync error: {str(e)}")

        # Step 6: Sync responses for all active tickets
        logger.info("Starting BlueStakes responses sync for active tickets...")
        try:
            response_stats = await sync_bluestakes_responses(company_id)
            sync_stats["responses_synced"] = response_stats.get("total_tickets_updated", 0)
            sync_stats["responses_failed"] = response_stats.get("total_tickets_failed", 0)
            logger.info(f"Responses sync completed: {response_stats.get('total_tickets_updated', 0)} updated, "
                       f"{response_stats.get('total_tickets_failed', 0)} failed")
        except Exception as e:
            logger.error(f"Error syncing responses: {str(e)}")
            sync_stats["responses_synced"] = 0
            sync_stats["responses_failed"] = 0
            sync_stats["errors"].append(f"Responses sync error: {str(e)}")

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
        #         "updateable_tickets_checked": sync_stats.get('updateable_tickets_checked', 0),
        #         "updateable_tickets_found": sync_stats.get('updateable_tickets_found', 0),
        #         "responses_synced": sync_stats.get('responses_synced', 0),
        #         "responses_failed": sync_stats.get('responses_failed', 0),
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
                 .schema("public")
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
                 .schema("public")
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
    Sync tickets for a single company with pagination support.
    Continues fetching until fewer than `limit` tickets are returned.
    """
    company_stats = {"tickets_added": 0, "tickets_skipped": 0}

    try:
        # Decrypt the password before using it
        decrypted_password = safe_decrypt_password(company["bluestakes_password"])
    except EncryptionError as e:
        logger.error(f"Failed to decrypt password for company {company['id']}: {str(e)}")
        raise Exception(f"Password decryption failed for company {company['id']}: {str(e)}")

    # Step 1: Authenticate with BlueStakes API (with caching)
    token = await get_bluestakes_auth_token(
        company["bluestakes_username"],
        decrypted_password,
        company["id"]  # Pass company_id for token caching
    )

    # Step 2: Paginate through all tickets
    limit = search_params.get("limit", 100)
    offset = 0

    while True:
        # Build paginated search params
        paginated_params = {**search_params, "offset": offset}

        logger.info(f"Fetching tickets for company {company['id']} with offset {offset}, limit {limit}")

        # Search for tickets (with retry support)
        bluestakes_response = await search_bluestakes_tickets(
            token,
            paginated_params,
            company["id"],
            company["bluestakes_username"],
            decrypted_password
        )

        # Extract tickets from response
        tickets_data = _extract_tickets_from_response(bluestakes_response)

        if not tickets_data:
            logger.info(f"No more tickets found for company {company['id']} at offset {offset}")
            break

        tickets_fetched = len(tickets_data)
        logger.info(f"Fetched {tickets_fetched} tickets for company {company['id']} at offset {offset}")

        # Process this batch of tickets
        batch_stats = await _process_ticket_batch(tickets_data, token, company["id"])
        company_stats["tickets_added"] += batch_stats["tickets_added"]
        company_stats["tickets_skipped"] += batch_stats["tickets_skipped"]

        # If we got fewer tickets than the limit, we've reached the end
        if tickets_fetched < limit:
            logger.info(f"Reached end of tickets for company {company['id']} (got {tickets_fetched} < {limit})")
            break

        # Move to next page
        offset += limit

        # Small delay between pages to be respectful to the API
        await asyncio.sleep(0.5)

    logger.info(f"Finished syncing company {company['id']}: {company_stats['tickets_added']} added, {company_stats['tickets_skipped']} skipped")
    return company_stats


def _extract_tickets_from_response(bluestakes_response) -> List[Dict[str, Any]]:
    """
    Extract ticket data from various response formats.
    """
    tickets_data = []

    if isinstance(bluestakes_response, list):
        for response_item in bluestakes_response:
            if isinstance(response_item, dict) and "data" in response_item:
                tickets_data.extend(response_item.get("data", []))
    elif isinstance(bluestakes_response, dict):
        if "data" in bluestakes_response:
            tickets_data = bluestakes_response.get("data", [])
        else:
            logger.warning(f"Dict response does not contain 'data' key. Available keys: {list(bluestakes_response.keys())}")
    else:
        logger.warning(f"Unexpected response type: {type(bluestakes_response)}")

    return tickets_data


async def _process_ticket_batch(tickets_data: List[Dict[str, Any]], token: str, company_id: int) -> Dict[str, int]:
    """
    Process a batch of tickets - check existence, fetch details, and insert.
    """
    from utils.bluestakes import get_ticket_details

    batch_stats = {"tickets_added": 0, "tickets_skipped": 0}

    for ticket_data in tickets_data:
        if not isinstance(ticket_data, dict):
            continue

        ticket_number = ticket_data.get("ticket")

        if not ticket_number:
            logger.warning(f"Ticket missing ticket number, skipping: {ticket_data}")
            continue

        # Check if ticket already exists
        if await ticket_exists(ticket_number):
            batch_stats["tickets_skipped"] += 1
            continue

        # Fetch full ticket details and transform
        try:
            full_ticket_data = await get_ticket_details(token, ticket_number)

            # Use full ticket data if available, otherwise fall back to basic data
            if full_ticket_data and not full_ticket_data.get("error"):
                project_ticket = transform_bluestakes_ticket_to_project_ticket(
                    full_ticket_data, company_id
                )
            else:
                project_ticket = transform_bluestakes_ticket_to_project_ticket(
                    ticket_data, company_id
                )

            await insert_project_ticket(project_ticket)
            batch_stats["tickets_added"] += 1

            # Add small delay to respect API rate limits
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Error processing ticket {ticket_number}: {str(e)}")
            continue

    return batch_stats


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
    Insert a project ticket into the database with all Bluestakes data fields.
    """
    try:
        insert_data = {
            "project_id": project_ticket.project_id,
            "ticket_number": project_ticket.ticket_number,
            "replace_by_date": project_ticket.replace_by_date.isoformat(),
            "old_ticket": project_ticket.old_ticket,
            "is_continue_update": project_ticket.is_continue_update,
            "legal_date": project_ticket.legal_date.isoformat() if project_ticket.legal_date else None,
            "company_id": project_ticket.company_id,
            
            # Location & Maps
            "place": project_ticket.place,
            "street": project_ticket.street,
            "location_description": project_ticket.location_description,
            "formatted_address": project_ticket.formatted_address,
            "work_area": project_ticket.work_area,

            # Date Fields (convert to date strings for PostgreSQL DATE fields)
            "expires": project_ticket.expires.date().isoformat() if project_ticket.expires else None,
            "original_date": project_ticket.original_date.date().isoformat() if project_ticket.original_date else None,

            # Work Details
            "done_for": project_ticket.done_for,
            "type": project_ticket.type,
            
            # Address Details
            "st_from_address": project_ticket.st_from_address,
            "st_to_address": project_ticket.st_to_address,
            "cross1": project_ticket.cross1,
            "cross2": project_ticket.cross2,
            "county": project_ticket.county,
            "state": project_ticket.state,
            "zip": project_ticket.zip,
            
            # Contact Information
            "name": project_ticket.name,
            "phone": project_ticket.phone,
            "email": project_ticket.email,
            
            # Ticket Management
            "revision": project_ticket.revision,
            
            # Metadata
            "bluestakes_data_updated_at": project_ticket.bluestakes_data_updated_at.isoformat() if project_ticket.bluestakes_data_updated_at else None,
            "bluestakes_data": project_ticket.bluestakes_data
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
            return {"linked": 0, "old_tickets_updated": 0}
        
        orphaned_tickets = orphaned_result.data
        
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
                        
                        # Update the old ticket to set is_continue_update to FALSE
                        try:
                            if await update_old_ticket_continue_status(old_ticket_number, company_id):
                                old_tickets_updated_count += 1
                        except Exception as e:
                            logger.error(f"Error updating old ticket {old_ticket_number} continue status: {str(e)}")
                    else:
                        logger.warning(f"Failed to update ticket {ticket['ticket_number']} with project_id {project_id}")
                    
            except Exception as e:
                logger.error(f"Error processing orphaned ticket {ticket.get('ticket_number', 'unknown')}: {str(e)}")
                continue
        
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
            return True
        else:
            logger.warning(f"No old ticket found to update: {old_ticket_number} for company {company_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error updating old ticket {old_ticket_number} continue status: {str(e)}")
        raise
