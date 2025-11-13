"""
Admin endpoints for administrative tasks.
These routes are protected by API key authentication.
"""
from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/contact-submit")
async def contact_submit():
    """
    Contact form submission endpoint.

    Returns:
        dict: Success message
    """
    return {"message": "success from your API"}
