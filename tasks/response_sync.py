"""
Ticket response synchronization functions.
These functions handle syncing responses data from BlueStakes API to project_tickets.
"""
import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Dict, Any, Optional, List
from config.supabase_client import get_service_client
from utils.bluestakes import get_bluestakes_auth_token, get_ticket_responses
from utils.encryption import safe_decrypt_password, EncryptionError

logger = logging.getLogger(__name__)


async def sync_ticket_responses(ticket_number: str, company_id: int) -> bool:
    """
    Sync responses data for a single ticket from BlueStakes API.

    Args:
        ticket_number: The ticket number to sync responses for
        company_id: The company ID for authentication

    Returns:
        True if sync was successful, False otherwise
    """
    try:
        # Get company Bluestakes credentials
        company_creds = (get_service_client()
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

        # Get ticket responses
        response_data = await get_ticket_responses(
            token,
            ticket_number,
            company_id,
            company_creds.data[0]["bluestakes_username"],
            decrypted_password
        )

        if not response_data:
            logger.warning(f"Could not fetch responses for ticket {ticket_number}")
            return False

        # Extract the responses array from the response
        responses_array = response_data.get("responses", [])

        # Update the ticket's responses column (overwrites existing data)
        update_data = {
            "responses": responses_array
        }

        result = (get_service_client()
                 .table("project_tickets")
                 .update(update_data)
                 .eq("ticket_number", ticket_number)
                 .execute())

        return bool(result.data)

    except Exception as e:
        logger.error(f"Error syncing responses for ticket {ticket_number}: {str(e)}")
        return False


async def sync_bluestakes_responses(company_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Sync responses for all active tickets (expires > today).

    Args:
        company_id: If provided, sync only tickets for this company

    Returns:
        Dict with sync statistics by company
    """
    stats = {
        "total_tickets_processed": 0,
        "total_tickets_updated": 0,
        "total_tickets_failed": 0,
        "companies": {},
        "errors": []
    }

    try:
        # Get today's date for comparison
        today = date.today()

        # Build query for active tickets (expires > today)
        query = (get_service_client()
                .table("project_tickets")
                .select("ticket_number, company_id")
                .gt("expires", today.isoformat()))

        if company_id:
            query = query.eq("company_id", company_id)

        result = query.execute()

        if not result.data:
            logger.info("No active tickets found to sync responses")
            return stats

        # Group tickets by company for efficient credential reuse
        tickets_by_company: Dict[int, List[str]] = {}
        for ticket in result.data:
            ticket_company_id = ticket["company_id"]
            if ticket_company_id not in tickets_by_company:
                tickets_by_company[ticket_company_id] = []
            tickets_by_company[ticket_company_id].append(ticket["ticket_number"])

        logger.info(f"Found {len(result.data)} active tickets across {len(tickets_by_company)} companies")

        # Process tickets grouped by company
        for ticket_company_id, ticket_numbers in tickets_by_company.items():
            company_stats = {
                "tickets_processed": 0,
                "tickets_updated": 0,
                "tickets_failed": 0,
                "errors": []
            }

            logger.info(f"Processing {len(ticket_numbers)} tickets for company {ticket_company_id}")

            for ticket_number in ticket_numbers:
                try:
                    stats["total_tickets_processed"] += 1
                    company_stats["tickets_processed"] += 1

                    # Sync the ticket responses
                    if await sync_ticket_responses(ticket_number, ticket_company_id):
                        stats["total_tickets_updated"] += 1
                        company_stats["tickets_updated"] += 1
                        logger.info(f"Synced responses for ticket {ticket_number}")
                    else:
                        stats["total_tickets_failed"] += 1
                        company_stats["tickets_failed"] += 1
                        logger.warning(f"Failed to sync responses for ticket {ticket_number}")

                    # Add 100ms delay between tickets for rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    stats["total_tickets_failed"] += 1
                    company_stats["tickets_failed"] += 1
                    error_msg = f"Error processing ticket {ticket_number}: {str(e)}"
                    company_stats["errors"].append(error_msg)
                    stats["errors"].append(error_msg)
                    logger.error(error_msg)
                    continue

            # Store company stats
            stats["companies"][ticket_company_id] = company_stats
            logger.info(f"Company {ticket_company_id}: {company_stats['tickets_updated']} updated, {company_stats['tickets_failed']} failed")

        logger.info(f"Response sync completed: {stats['total_tickets_updated']} updated, {stats['total_tickets_failed']} failed")
        return stats

    except Exception as e:
        error_msg = f"Error in sync_bluestakes_responses: {str(e)}"
        stats["errors"].append(error_msg)
        logger.error(error_msg)
        return stats
