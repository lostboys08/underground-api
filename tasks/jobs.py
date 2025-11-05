"""
Background job functions for scheduled tasks.

This module has been refactored into focused sub-modules for better maintainability:

- user_management.py: User and project assignment functions
- ticket_sync.py: BlueStakes ticket synchronization functions  
- updatable_tickets.py: Updatable ticket management functions
- email_digest.py: Weekly digest email functions
- ticket_data_sync.py: Ticket data synchronization functions

All functions are re-exported from this module to maintain backward compatibility.
"""

# Import all functions from the new modules to maintain backward compatibility

# User management functions
from .user_management import (
    get_assigned_projects_for_user,
    get_unique_assigned_users
)

# Ticket synchronization functions
from .ticket_sync import (
    sync_bluestakes_tickets,
    sync_company_tickets,
    get_companies_with_bluestakes_credentials,
    get_company_with_bluestakes_credentials,
    ticket_exists,
    insert_project_ticket,
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

# Ticket data synchronization functions
from .ticket_data_sync import (
    should_sync_ticket_data,
    update_project_ticket_bluestakes_data,
    sync_existing_tickets_bluestakes_data
)

# Re-export all functions for backward compatibility
__all__ = [
    # User management
    'get_assigned_projects_for_user',
    'get_unique_assigned_users',
    
    # Ticket synchronization
    'sync_bluestakes_tickets',
    'sync_company_tickets',
    'get_companies_with_bluestakes_credentials',
    'get_company_with_bluestakes_credentials',
    'ticket_exists',
    'insert_project_ticket',
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
    
    # Ticket data synchronization
    'should_sync_ticket_data',
    'update_project_ticket_bluestakes_data',
    'sync_existing_tickets_bluestakes_data'
]