#!/usr/bin/env python3
"""
Backfill script for populating existing project_tickets with comprehensive Bluestakes data.

DEPRECATED: This script uses the deprecated sync_existing_tickets_bluestakes_data function
which has been consolidated into sync_bluestakes_tickets for better efficiency.

The consolidated sync_bluestakes_tickets now handles both new tickets and updates in a single pass,
eliminating the need for separate backfill operations for tickets within the 28-day window.

For tickets older than 28 days, this script still works via backward compatibility wrappers.

Usage:
    python backfill_bluestakes_data.py [--company-id COMPANY_ID] [--batch-size BATCH_SIZE] [--force]

Arguments:
    --company-id: Optional company ID to backfill (backfills all companies if not provided)
    --batch-size: Number of tickets to process in each batch (default: 50)
    --force: Force backfill even for tickets that already have bluestakes_data_updated_at
    --dry-run: Show what would be updated without making changes
"""

import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Add the project root to Python path (script is now in root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tasks.jobs import sync_existing_tickets_bluestakes_data
from config.supabase_client import get_service_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def get_backfill_stats(company_id: int = None) -> Dict[str, Any]:
    """
    Get statistics about tickets that need backfilling.
    
    Args:
        company_id: Optional company ID to filter by
        
    Returns:
        Dict with backfill statistics
    """
    try:
        # Query for all tickets
        query = get_service_client().table("project_tickets").select("ticket_number, company_id, bluestakes_data_updated_at")
        
        if company_id:
            query = query.eq("company_id", company_id)
        
        result = query.execute()
        
        if not result.data:
            return {
                "total_tickets": 0,
                "tickets_with_data": 0,
                "tickets_needing_backfill": 0,
                "companies": []
            }
        
        total_tickets = len(result.data)
        tickets_with_data = 0
        companies = set()
        
        for ticket in result.data:
            companies.add(ticket["company_id"])
            if ticket.get("bluestakes_data_updated_at"):
                tickets_with_data += 1
        
        tickets_needing_backfill = total_tickets - tickets_with_data
        
        return {
            "total_tickets": total_tickets,
            "tickets_with_data": tickets_with_data,
            "tickets_needing_backfill": tickets_needing_backfill,
            "companies": sorted(list(companies))
        }
        
    except Exception as e:
        logger.error(f"Error getting backfill stats: {str(e)}")
        return {
            "total_tickets": 0,
            "tickets_with_data": 0,
            "tickets_needing_backfill": 0,
            "companies": [],
            "error": str(e)
        }


async def verify_company_credentials(company_id: int) -> bool:
    """
    Verify that a company has Bluestakes credentials configured.
    
    Args:
        company_id: The company ID to check
        
    Returns:
        True if credentials are configured, False otherwise
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("id, name, bluestakes_username, bluestakes_password")
                 .eq("id", company_id)
                 .not_.is_("bluestakes_username", "null")
                 .not_.is_("bluestakes_password", "null")
                 .execute())
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error verifying credentials for company {company_id}: {str(e)}")
        return False


async def main():
    """Main backfill function."""
    parser = argparse.ArgumentParser(description="Backfill existing project_tickets with Bluestakes data")
    parser.add_argument("--company-id", type=int, help="Company ID to backfill (backfills all if not provided)")
    parser.add_argument("--batch-size", type=int, default=50, help="Number of tickets to process in each batch")
    parser.add_argument("--force", action="store_true", help="Force backfill even for tickets with existing data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without making changes")
    
    args = parser.parse_args()
    
    logger.info("Starting Bluestakes data backfill process")
    logger.info(f"Parameters: company_id={args.company_id}, batch_size={args.batch_size}, force={args.force}, dry_run={args.dry_run}")
    
    try:
        # Get initial statistics
        logger.info("Gathering backfill statistics...")
        stats = await get_backfill_stats(args.company_id)
        
        if "error" in stats:
            logger.error(f"Failed to get backfill stats: {stats['error']}")
            return 1
        
        logger.info(f"Backfill Statistics:")
        logger.info(f"  Total tickets: {stats['total_tickets']}")
        logger.info(f"  Tickets with Bluestakes data: {stats['tickets_with_data']}")
        logger.info(f"  Tickets needing backfill: {stats['tickets_needing_backfill']}")
        logger.info(f"  Companies involved: {stats['companies']}")
        
        if stats['tickets_needing_backfill'] == 0 and not args.force:
            logger.info("No tickets need backfilling. Use --force to update all tickets.")
            return 0
        
        # Verify company credentials
        if args.company_id:
            companies_to_check = [args.company_id]
        else:
            companies_to_check = stats['companies']
        
        logger.info("Verifying company credentials...")
        valid_companies = []
        for company_id in companies_to_check:
            if await verify_company_credentials(company_id):
                valid_companies.append(company_id)
                logger.info(f"  Company {company_id}: ✓ Has Bluestakes credentials")
            else:
                logger.warning(f"  Company {company_id}: ✗ Missing Bluestakes credentials")
        
        if not valid_companies:
            logger.error("No companies have valid Bluestakes credentials configured")
            return 1
        
        # Confirm before proceeding (unless dry run)
        if not args.dry_run:
            if args.force:
                logger.warning("FORCE mode enabled - will update ALL tickets regardless of existing data")
            
            response = input(f"\nProceed with backfill for {len(valid_companies)} companies? (y/N): ")
            if response.lower() != 'y':
                logger.info("Backfill cancelled by user")
                return 0
        
        # Perform backfill
        if args.dry_run:
            logger.info("DRY RUN - No changes will be made")
            logger.info(f"Would backfill tickets for companies: {valid_companies}")
        else:
            logger.info("Starting backfill process...")
            
            # Set max_age_hours to 0 if force is enabled (sync all tickets)
            max_age_hours = 0 if args.force else 999999  # Very large number to sync all tickets
            
            if args.company_id:
                # Backfill specific company
                result = await sync_existing_tickets_bluestakes_data(
                    company_id=args.company_id,
                    batch_size=args.batch_size,
                    max_age_hours=max_age_hours
                )
            else:
                # Backfill all companies
                result = await sync_existing_tickets_bluestakes_data(
                    company_id=None,
                    batch_size=args.batch_size,
                    max_age_hours=max_age_hours
                )
            
            logger.info("Backfill completed!")
            logger.info(f"Results:")
            logger.info(f"  Tickets processed: {result['tickets_processed']}")
            logger.info(f"  Tickets updated: {result['tickets_updated']}")
            logger.info(f"  Tickets skipped: {result['tickets_skipped']}")
            logger.info(f"  Tickets failed: {result['tickets_failed']}")
            
            if result['errors']:
                logger.warning(f"  Errors encountered: {len(result['errors'])}")
                for error in result['errors'][:5]:  # Show first 5 errors
                    logger.warning(f"    {error}")
                if len(result['errors']) > 5:
                    logger.warning(f"    ... and {len(result['errors']) - 5} more errors")
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Backfill failed with error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
