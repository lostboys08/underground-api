import asyncio
import time
from datetime import datetime
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright is not installed. Ticket update functionality will be disabled.")
    PLAYWRIGHT_AVAILABLE = False
    
    # Create a dummy async_playwright for graceful handling
    class DummyPlaywright:
        def __init__(self):
            pass
        def __aenter__(self):
            raise ImportError("Playwright is not available")
        def __aexit__(self, *args):
            pass
    
    async_playwright = DummyPlaywright

class TicketUpdateResult:
    def __init__(self, success: bool, message: str, details: Optional[str] = None):
        self.success = success
        self.message = message
        self.details = details
        self.updated_at = datetime.now()

async def update_single_ticket(username: str, password: str, ticket_number: str) -> TicketUpdateResult:
    """
    Update a single BlueStakes ticket using Playwright automation.
    
    Args:
        username: BlueStakes username
        password: BlueStakes password  
        ticket_number: Ticket number to update
        
    Returns:
        TicketUpdateResult object with success status and details
    """
    # Check if Playwright is available
    if not PLAYWRIGHT_AVAILABLE:
        return TicketUpdateResult(
            success=False,
            message="Ticket update service unavailable: Playwright is not installed",
            details="Please install Playwright: pip install playwright && playwright install"
        )
    
    try:
        async with async_playwright() as playwright:
            # Launch browser in headless mode for production
            browser = await playwright.chromium.launch(
                headless=True,  # Changed to headless for API usage
                slow_mo=50
            )
            page = await browser.new_page()
            
            try:
                # Navigate to BlueStakes
                await page.goto("https://newtin.bluestakes.org/newtinweb/UTAH_ticketentry.html", timeout=30000)
                
                # Login with better error handling
                try:
                    await page.get_by_label("Account").fill(username)
                    await page.get_by_label("Account").press("Tab")
                    await page.get_by_label("Password").fill(password)
                    await page.get_by_role("button", name="Submit").click()
                except Exception as e:
                    logger.error(f"Failed to login: {str(e)}")
                    return TicketUpdateResult(
                        success=False,
                        message="Failed to login to BlueStakes",
                        details=f"Login error: {str(e)}"
                    )
                
                # Handle "I Agree" button
                try:
                    await page.get_by_role("button", name="I Agree").click()
                    await page.get_by_label("last").check()
                except Exception:
                    # If these elements don't exist, continue
                    pass
                
                # Fill in ticket info and search
                try:
                    await page.locator("#txtInquireTicket").click()
                    await page.locator("#txtInquireTicket").fill(ticket_number)
                    await page.get_by_role("button", name="Inquire").click()
                    logger.info(f"Searching for ticket: {ticket_number}")
                except Exception as e:
                    logger.error(f"Failed to search for ticket {ticket_number}: {str(e)}")
                    return TicketUpdateResult(
                        success=False,
                        message=f"Failed to search for ticket {ticket_number}",
                        details=f"Search error: {str(e)}"
                    )
                
                # Wait for results and check for newer ticket versions
                await asyncio.sleep(1)
                
                # Handle ticket version updates
                while True:
                    updated_ticket_exists = await page.get_by_role("dialog").get_by_role("button", name="Exit").count() > 0
                    if not updated_ticket_exists:
                        break
                    await page.keyboard.press('Enter')
                    logger.info("Ticket has a newer version. Checking for updates...")
                    await asyncio.sleep(0.5)
                
                # Check if update button exists
                await asyncio.sleep(1)
                time_to_update = await page.get_by_role("button", name="Update").count() > 0
                
                if time_to_update:
                    logger.info("Updating ticket...")
                    
                    # Update ticket, respond to prompts
                    await page.get_by_role("button", name="Update").click()
                    
                    # Continue digging prompt (Yes and Yes)
                    await page.locator("#divUpdateConfirm span").first.click()
                    await page.locator("#divUpdateConfirm span").nth(2).click()
                    await page.get_by_role("button", name="OK", exact=True).click()
                    
                    # Reason for continue prompt (Dropdown)
                    await page.locator("#selUpdateReason").select_option("CONTINUED EXCAVATION - EXTENT OF PROJECT MORE THAN 21 DAYS")
                    await page.get_by_role("button", name="OK", exact=True).click()
                    
                    # Search for facilities button
                    await page.get_by_role("button", name="Accurate & Complete").click()
                    
                    # Check if no members found
                    await asyncio.sleep(1)
                    no_members = await page.get_by_role("button", name="Yes").count() > 0
                    if no_members:
                        await page.get_by_role("button", name="Yes").click()
                        await page.get_by_role("button", name="OK", exact=True).click()
                    else:
                        await page.get_by_role("button", name="OK", exact=True).click()
                    
                    # Submit ticket
                    await page.get_by_role("button", name="Submit").click()
                    await page.get_by_role("button", name="No").click()
                    await page.get_by_role("button", name="OK", exact=True).click()
                    
                    logger.info(f"Ticket {ticket_number} updated successfully")
                    
                    return TicketUpdateResult(
                        success=True,
                        message=f"Ticket {ticket_number} updated successfully",
                        details="Ticket was successfully updated with continued excavation reason"
                    )
                else:
                    logger.info(f"Ticket {ticket_number} is already up to date")
                    
                    # Exit ticket search
                    await page.get_by_role("button", name="Exit").click()
                    
                    return TicketUpdateResult(
                        success=True,
                        message=f"Ticket {ticket_number} is already up to date",
                        details="No update was needed for this ticket"
                    )
                    
            finally:
                await browser.close()
                
    except Exception as e:
        error_msg = f"Error updating ticket {ticket_number}: {str(e)}"
        logger.error(error_msg)
        return TicketUpdateResult(
            success=False,
            message=error_msg,
            details=f"Exception type: {type(e).__name__}"
        )
