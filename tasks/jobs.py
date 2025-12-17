"""
Background job functions for scheduled tasks.

This module has been refactored into focused sub-modules for better maintainability:

- user_management.py: User and project assignment functions
- ticket_sync.py: BlueStakes ticket synchronization (consolidated insert + update)
- updatable_tickets.py: Updatable ticket management functions
- email_digest.py: Weekly digest email functions

All functions are re-exported from this module to maintain backward compatibility.
Note: ticket_data_sync.py has been consolidated into ticket_sync.py
"""

# Import all functions from the new modules to maintain backward compatibility

# User management functions
from .user_management import (
    get_assigned_projects_for_user,
    get_unique_assigned_users
)

# Ticket synchronization functions (consolidated insert + update)
from .ticket_sync import (
    sync_bluestakes_tickets,
    sync_company_tickets,
    get_companies_with_bluestakes_credentials,
    get_company_with_bluestakes_credentials,
    ticket_exists,
    insert_project_ticket,
    update_project_ticket,
    get_existing_ticket_sync_status,
    link_orphaned_tickets_to_projects,
    update_old_ticket_continue_status
)

# Updatable tickets functions
from .updatable_tickets import (
    sync_updateable_tickets,
    get_companies_for_updateable_sync,
    get_updatable_ticket_candidates,
    insert_updatable_ticket
)

# Email digest functions
from .email_digest import (
    send_weekly_project_digest,
    get_project_tickets_for_digest,
    get_company_info_for_digest,
    prepare_user_digest_data,
    format_location_from_bluestakes,
    get_ticket_location_from_bluestakes
)

# Backward compatibility wrappers for deprecated ticket_data_sync functions
# These now use the consolidated ticket_sync module
async def should_sync_ticket_data(ticket_number: str, max_age_hours: int = 24) -> bool:
    """
    DEPRECATED: Use get_existing_ticket_sync_status instead.
    Check if a ticket's Bluestakes data should be synced based on age.
    """
    status = await get_existing_ticket_sync_status(ticket_number, max_age_hours)
    return status["needs_sync"]


async def update_project_ticket_bluestakes_data(ticket_number: str, company_id: int) -> bool:
    """
    DEPRECATED: Consolidated into sync_bluestakes_tickets.
    This function is kept for backward compatibility only.

    To update a single ticket, use sync_bluestakes_tickets with appropriate date range.
    """
    from config.supabase_client import get_service_client
    from utils.bluestakes import get_ticket_details
    from utils.bluestakes_token_manager import get_token_for_company
    from utils.bluestakes import transform_bluestakes_ticket_to_project_ticket
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Get token and fetch ticket details
        token = await get_token_for_company(company_id)
        ticket_data = await get_ticket_details(token, ticket_number)

        if not ticket_data or ticket_data.get("error"):
            logger.warning(f"Could not fetch ticket details for {ticket_number}")
            return False

        # Transform and update
        project_ticket = transform_bluestakes_ticket_to_project_ticket(ticket_data, company_id)
        return await update_project_ticket(project_ticket)

    except Exception as e:
        logger.error(f"Error updating ticket {ticket_number}: {str(e)}")
        return False


async def sync_existing_tickets_bluestakes_data(company_id: int = None, batch_size: int = 50, max_age_hours: int = 24):
    """
    DEPRECATED: This function is now consolidated into sync_bluestakes_tickets.

    The consolidated sync_bluestakes_tickets handles both new tickets and updates
    in a single pass, eliminating the need for separate data sync.

    For backward compatibility, this now calls sync_bluestakes_tickets.
    """
    import logging
    logger = logging.getLogger(__name__)

    logger.warning("sync_existing_tickets_bluestakes_data is deprecated. "
                  "Use sync_bluestakes_tickets instead for consolidated sync.")

    # Call the consolidated sync function
    return await sync_bluestakes_tickets(company_id=company_id)

# Re-export all functions for backward compatibility
__all__ = [
    # User management
    'get_assigned_projects_for_user',
    'get_unique_assigned_users',

    # Ticket synchronization (consolidated)
    'sync_bluestakes_tickets',
    'sync_company_tickets',
    'get_companies_with_bluestakes_credentials',
    'get_company_with_bluestakes_credentials',
    'ticket_exists',
    'insert_project_ticket',
    'update_project_ticket',
    'get_existing_ticket_sync_status',
    'link_orphaned_tickets_to_projects',
    'update_old_ticket_continue_status',

    # Updatable tickets
    'sync_updateable_tickets',
    'get_companies_for_updateable_sync',
    'get_updatable_ticket_candidates',
    'insert_updatable_ticket',

    # Email digest
    'send_weekly_project_digest',
    'get_project_tickets_for_digest',
    'get_company_info_for_digest',
    'prepare_user_digest_data',
    'format_location_from_bluestakes',
    'get_ticket_location_from_bluestakes',

    # Backward compatibility wrappers (deprecated)
    'should_sync_ticket_data',
    'update_project_ticket_bluestakes_data',
    'sync_existing_tickets_bluestakes_data'
]