"""
Ticket data synchronization functions.
These functions handle updating existing tickets with fresh BlueStakes data,
including checking sync requirements and batch processing.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from config.supabase_client import get_service_client
from utils.bluestakes import get_bluestakes_auth_token, get_ticket_details, transform_bluestakes_ticket_to_project_ticket
from utils.encryption import safe_decrypt_password, EncryptionError

logger = logging.getLogger(__name__)


async def should_sync_ticket_data(ticket_number: str, max_age_hours: int = 24) -> bool:
    """
    Check if a ticket's Bluestakes data should be synced based on age.
    
    Args:
        ticket_number: The ticket number to check
        max_age_hours: Maximum age in hours before sync is needed
        
    Returns:
        True if sync is needed, False otherwise
    """
    try:
        result = (get_service_client()
                 .table("project_tickets")
                 .select("bluestakes_data_updated_at")
                 .eq("ticket_number", ticket_number)
                 .limit(1)
                 .execute())
        
        if not result.data:
            return True  # Ticket not found, sync needed
        
        updated_at = result.data[0].get("bluestakes_data_updated_at")
        if not updated_at:
            return True  # Never synced, sync needed
        
        # Parse the timestamp and check age
        # Handle the timestamp string - it might be timezone-naive or timezone-aware
        if isinstance(updated_at, str):
            # If it's a string, parse it
            if updated_at.endswith('Z'):
                updated_datetime = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            elif '+' in updated_at or updated_at.endswith('00:00'):
                updated_datetime = datetime.fromisoformat(updated_at)
            else:
                # Assume it's UTC if no timezone info
                updated_datetime = datetime.fromisoformat(updated_at).replace(tzinfo=timezone.utc)
        else:
            # If it's already a datetime object, ensure it has timezone info
            updated_datetime = updated_at
            if updated_datetime.tzinfo is None:
                updated_datetime = updated_datetime.replace(tzinfo=timezone.utc)
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        
        return updated_datetime < cutoff_time
        
    except Exception as e:
        logger.error(f"Error checking sync status for ticket {ticket_number}: {str(e)}")
        return True  # On error, assume sync is needed


async def update_project_ticket_bluestakes_data(ticket_number: str, company_id: int) -> bool:
    """
    Update an existing project ticket with fresh Bluestakes data.
    
    Args:
        ticket_number: The ticket number to update
        company_id: The company ID for authentication
        
    Returns:
        True if update was successful, False otherwise
    """
    try:
        # Get company Bluestakes credentials
        company_creds = (get_service_client()
                        .schema("public")
                        .table("companies")
                        .select("bluestakes_username, bluestakes_password")
                        .eq("id", company_id)
                        .not_.is_("bluestakes_username", "null")
                        .not_.is_("bluestakes_password", "null")
                        .execute())
        
        if not company_creds.data:
            logger.warning(f"No Bluestakes credentials found for company {company_id}")
            return False
        
        try:
            # Decrypt the password before using it
            decrypted_password = safe_decrypt_password(company_creds.data[0]["bluestakes_password"])
        except EncryptionError as e:
            logger.error(f"Failed to decrypt password for company {company_id}: {str(e)}")
            return False
        
        # Authenticate with Bluestakes API (with caching)
        token = await get_bluestakes_auth_token(
            company_creds.data[0]["bluestakes_username"],
            decrypted_password,
            company_id  # Pass company_id for token caching
        )
        
        # Get full ticket details
        ticket_data = await get_ticket_details(token, ticket_number)
        
        if not ticket_data or ticket_data.get("error"):
            logger.warning(f"Could not fetch ticket details for {ticket_number}")
            return False
        
        # Transform the data
        project_ticket = transform_bluestakes_ticket_to_project_ticket(ticket_data, company_id)
        
        # Prepare update data (excluding fields that shouldn't be updated)
        update_data = {
            # Location & Maps
            "place": project_ticket.place,
            "street": project_ticket.street,
            "location_description": project_ticket.location_description,
            "formatted_address": project_ticket.formatted_address,
            "work_area": project_ticket.work_area,

            # Date Fields
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
        
        # Update the ticket
        result = (get_service_client()
                 .table("project_tickets")
                 .update(update_data)
                 .eq("ticket_number", ticket_number)
                 .execute())
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error updating ticket {ticket_number} with Bluestakes data: {str(e)}")
        return False


async def sync_existing_tickets_bluestakes_data(company_id: int = None, batch_size: int = 50, max_age_hours: int = 24) -> Dict[str, int]:
    """
    Sync existing tickets with fresh Bluestakes data.
    
    Args:
        company_id: If provided, sync only tickets for this company
        batch_size: Number of tickets to process in each batch
        max_age_hours: Only sync tickets older than this many hours
        
    Returns:
        Dict with sync statistics
    """
    stats = {
        "tickets_processed": 0,
        "tickets_updated": 0,
        "tickets_skipped": 0,
        "tickets_failed": 0,
        "errors": []
    }
    
    try:
        # Get tickets in batches
        offset = 0
        while True:
            # Build query fresh each iteration to avoid accumulating parameters
            query = get_service_client().table("project_tickets").select("ticket_number, company_id")

            if company_id:
                query = query.eq("company_id", company_id)

            result = query.range(offset, offset + batch_size - 1).execute()
            
            if not result.data:
                break
            
            for ticket in result.data:
                ticket_number = ticket["ticket_number"]
                ticket_company_id = ticket["company_id"]
                
                try:
                    stats["tickets_processed"] += 1
                    
                    # Check if sync is needed
                    if not await should_sync_ticket_data(ticket_number, max_age_hours):
                        stats["tickets_skipped"] += 1
                        continue
                    
                    # Update the ticket
                    if await update_project_ticket_bluestakes_data(ticket_number, ticket_company_id):
                        stats["tickets_updated"] += 1
                        logger.info(f"Updated ticket {ticket_number} with fresh Bluestakes data")
                    else:
                        stats["tickets_failed"] += 1
                        logger.warning(f"Failed to update ticket {ticket_number}")
                    
                    # Add delay to respect API rate limits
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    stats["tickets_failed"] += 1
                    error_msg = f"Error processing ticket {ticket_number}: {str(e)}"
                    stats["errors"].append(error_msg)
                    logger.error(error_msg)
                    continue
            
            # Move to next batch
            offset += batch_size
            
            # If we got fewer results than batch_size, we're done
            if len(result.data) < batch_size:
                break
        
        logger.info(f"Sync completed: {stats['tickets_updated']} updated, {stats['tickets_skipped']} skipped, {stats['tickets_failed']} failed")
        return stats
        
    except Exception as e:
        error_msg = f"Error in sync_existing_tickets_bluestakes_data: {str(e)}"
        stats["errors"].append(error_msg)
        logger.error(error_msg)
        return stats
