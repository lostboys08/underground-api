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
    logger.info(f"=== UPDATE_SINGLE_TICKET START ===")
    logger.info(f"Ticket: {ticket_number}, Username: {username}")
    logger.info(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
    
    # Check if Playwright is available
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright is not available - cannot proceed with ticket update")
        return TicketUpdateResult(
            success=False,
            message="Ticket update service unavailable: Playwright is not installed",
            details="Please install Playwright: pip install playwright && playwright install"
        )
    
    try:
        logger.info("Starting playwright browser automation...")
        async with async_playwright() as playwright:
            # Launch browser in headless mode for production
            logger.info("Launching Chromium browser...")
            browser = await playwright.chromium.launch(
                headless=True,  # Changed to headless for API usage
                slow_mo=50
            )
            page = await browser.new_page()
            logger.info("Browser launched successfully, created new page")
            
            try:
                # Navigate to BlueStakes
                logger.info("Navigating to BlueStakes ticket entry page...")
                await page.goto("https://newtin.bluestakes.org/newtinweb/UTAH_ticketentry.html", timeout=30000)
                logger.info("Successfully navigated to BlueStakes page")
                
                # Login with better error handling
                logger.info("Attempting to login...")
                try:
                    logger.info("Filling in username field...")
                    await page.get_by_label("Account").fill(username)
                    await page.get_by_label("Account").press("Tab")
                    
                    logger.info("Filling in password field...")
                    await page.get_by_label("Password").fill(password)
                    
                    logger.info("Clicking submit button...")
                    await page.get_by_role("button", name="Submit").click()
                    
                    logger.info("Login form submitted successfully")
                except Exception as e:
                    logger.error(f"Failed to login: {str(e)}")
                    return TicketUpdateResult(
                        success=False,
                        message="Failed to login to BlueStakes",
                        details=f"Login error: {str(e)}"
                    )
                
                # Handle "I Agree" button
                logger.info("Checking for 'I Agree' button...")
                try:
                    await page.get_by_role("button", name="I Agree").click()
                    logger.info("Clicked 'I Agree' button")
                    await page.get_by_label("last").check()
                    logger.info("Checked 'last' checkbox")
                except Exception as e:
                    # If these elements don't exist, continue
                    logger.info(f"'I Agree' elements not found (this is normal): {str(e)}")
                    pass
                
                # Fill in ticket info and search
                logger.info("Starting ticket search process...")
                try:
                    logger.info("Clicking ticket inquiry field...")
                    await page.locator("#txtInquireTicket").click()
                    
                    logger.info(f"Filling ticket number: {ticket_number}")
                    await page.locator("#txtInquireTicket").fill(ticket_number)
                    
                    logger.info("Clicking Inquire button...")
                    await page.get_by_role("button", name="Inquire").click()
                    
                    logger.info(f"Successfully initiated search for ticket: {ticket_number}")
                except Exception as e:
                    logger.error(f"Failed to search for ticket {ticket_number}: {str(e)}")
                    return TicketUpdateResult(
                        success=False,
                        message=f"Failed to search for ticket {ticket_number}",
                        details=f"Search error: {str(e)}"
                    )
                
                # Wait for results and check for newer ticket versions
                logger.info("Waiting for search results...")
                await asyncio.sleep(1)
                
                # Handle ticket version updates
                logger.info("Checking for ticket version updates...")
                version_updates_handled = 0
                while True:
                    updated_ticket_exists = await page.get_by_role("dialog").get_by_role("button", name="Exit").count() > 0
                    if not updated_ticket_exists:
                        logger.info("No more version update dialogs found")
                        break
                    version_updates_handled += 1
                    await page.keyboard.press('Enter')
                    logger.info(f"Ticket has a newer version (update #{version_updates_handled}). Pressing Enter to continue...")
                    await asyncio.sleep(0.5)
                
                logger.info(f"Handled {version_updates_handled} version updates")
                
                # Check if update button exists
                logger.info("Checking if ticket needs update...")
                await asyncio.sleep(1)
                time_to_update = await page.get_by_role("button", name="Update").count() > 0
                logger.info(f"Update button found: {time_to_update}")
                
                if time_to_update:
                    logger.info("Ticket needs update - proceeding with update process...")
                    
                    # Update ticket, respond to prompts
                    logger.info("Clicking Update button...")
                    await page.get_by_role("button", name="Update").click()
                    
                    # Continue digging prompt (Yes and Yes)
                    logger.info("Handling continue digging prompts...")
                    await page.locator("#divUpdateConfirm span").first.click()
                    logger.info("Clicked first continue digging option")
                    await page.locator("#divUpdateConfirm span").nth(2).click()
                    logger.info("Clicked second continue digging option")
                    await page.get_by_role("button", name="OK", exact=True).click()
                    logger.info("Clicked OK for continue digging confirmation")
                    
                    # Reason for continue prompt (Dropdown)
                    logger.info("Selecting reason for continue...")
                    await page.locator("#selUpdateReason").select_option("CONTINUED EXCAVATION - EXTENT OF PROJECT MORE THAN 21 DAYS")
                    logger.info("Selected continued excavation reason")
                    await page.get_by_role("button", name="OK", exact=True).click()
                    logger.info("Clicked OK for reason selection")
                    
                    # Search for facilities button
                    logger.info("Clicking 'Accurate & Complete' button...")
                    await page.get_by_role("button", name="Accurate & Complete").click()
                    
                    # Check if no members found
                    logger.info("Checking for members...")
                    await asyncio.sleep(1)
                    no_members = await page.get_by_role("button", name="Yes").count() > 0
                    logger.info(f"No members dialog found: {no_members}")
                    if no_members:
                        logger.info("Clicking Yes for no members found")
                        await page.get_by_role("button", name="Yes").click()
                        await page.get_by_role("button", name="OK", exact=True).click()
                        logger.info("Confirmed no members found")
                    else:
                        logger.info("Members found, clicking OK")
                        await page.get_by_role("button", name="OK", exact=True).click()
                    
                    # Submit ticket
                    logger.info("Submitting ticket...")
                    await page.get_by_role("button", name="Submit").click()
                    logger.info("Clicked Submit button")
                    await page.get_by_role("button", name="No").click()
                    logger.info("Clicked No for additional options")
                    await page.get_by_role("button", name="OK", exact=True).click()
                    logger.info("Final OK clicked - ticket update completed")
                    
                    logger.info(f"Ticket {ticket_number} updated successfully")
                    
                    result = TicketUpdateResult(
                        success=True,
                        message=f"Ticket {ticket_number} updated successfully",
                        details="Ticket was successfully updated with continued excavation reason"
                    )
                    logger.info(f"Returning success result: {result.message}")
                    return result
                else:
                    logger.info(f"Ticket {ticket_number} is already up to date - no update needed")
                    
                    # Exit ticket search
                    logger.info("Clicking Exit button...")
                    await page.get_by_role("button", name="Exit").click()
                    logger.info("Exited ticket search")
                    
                    result = TicketUpdateResult(
                        success=True,
                        message=f"Ticket {ticket_number} is already up to date",
                        details="No update was needed for this ticket"
                    )
                    logger.info(f"Returning up-to-date result: {result.message}")
                    return result
                    
            finally:
                logger.info("Closing browser...")
                await browser.close()
                logger.info("Browser closed successfully")
                
    except Exception as e:
        error_msg = f"Error updating ticket {ticket_number}: {str(e)}"
        logger.error(f"Exception occurred: {error_msg}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        logger.info(f"=== UPDATE_SINGLE_TICKET END (ERROR) ===")
        return TicketUpdateResult(
            success=False,
            message=error_msg,
            details=f"Exception type: {type(e).__name__}"
        )
        
    logger.info(f"=== UPDATE_SINGLE_TICKET END ===")  # This should not be reached, but just in case
