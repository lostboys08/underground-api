"""
User management functions for project assignments and user queries.
These functions handle user-project relationships and user data retrieval.
"""
import logging
from typing import Dict, Any, List
from config.supabase_client import get_service_client

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
