"""
Script to fix ticket numbers with trailing whitespace in the database.

This script finds all ticket numbers in the project_tickets table that have
leading or trailing whitespace and updates them to remove the whitespace.

Run this script once to clean up existing data after the code fix has been deployed.
"""
import sys
import os

# Add parent directory to path to import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.supabase_client import get_service_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fix_ticket_numbers_whitespace():
    """Find and fix ticket numbers with leading/trailing whitespace."""

    try:
        supabase = get_service_client()

        # Fetch all tickets
        logger.info("Fetching all tickets from database...")
        result = supabase.table("project_tickets").select("id, ticket_number").execute()

        if not result.data:
            logger.info("No tickets found in database")
            return

        logger.info(f"Found {len(result.data)} tickets. Checking for whitespace issues...")

        tickets_to_fix = []
        for ticket in result.data:
            ticket_number = ticket["ticket_number"]
            stripped = ticket_number.strip()

            if ticket_number != stripped:
                tickets_to_fix.append({
                    "id": ticket["id"],
                    "old": ticket_number,
                    "new": stripped
                })

        if not tickets_to_fix:
            logger.info("No tickets with whitespace issues found. Database is clean!")
            return

        logger.warning(f"Found {len(tickets_to_fix)} tickets with whitespace issues:")
        for ticket in tickets_to_fix:
            logger.warning(f"  ID {ticket['id']}: '{ticket['old']}' -> '{ticket['new']}'")

        # Ask for confirmation
        response = input(f"\nDo you want to fix these {len(tickets_to_fix)} tickets? (yes/no): ")
        if response.lower() != 'yes':
            logger.info("Operation cancelled by user")
            return

        # Update tickets
        logger.info("Updating tickets...")
        fixed_count = 0
        failed_count = 0

        for ticket in tickets_to_fix:
            try:
                supabase.table("project_tickets").update({
                    "ticket_number": ticket["new"]
                }).eq("id", ticket["id"]).execute()

                logger.info(f"Fixed ticket ID {ticket['id']}: '{ticket['old']}' -> '{ticket['new']}'")
                fixed_count += 1
            except Exception as e:
                logger.error(f"Failed to fix ticket ID {ticket['id']}: {str(e)}")
                failed_count += 1

        logger.info(f"\n=== Summary ===")
        logger.info(f"Fixed: {fixed_count}")
        logger.info(f"Failed: {failed_count}")
        logger.info(f"Total: {len(tickets_to_fix)}")

    except Exception as e:
        logger.error(f"Error during whitespace fix: {str(e)}")
        raise


if __name__ == "__main__":
    logger.info("Starting ticket number whitespace fix...")
    fix_ticket_numbers_whitespace()
    logger.info("Done!")
