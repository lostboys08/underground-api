"""
Email service using Next.js API endpoint.
Centralizes all email functionality for both manual and scheduled sending.
"""
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Next.js API configuration
NEXTJS_API_URL = "https://app.underground-iq.com/api/send-email"
API_KEY = os.environ.get("API_KEY")


class Ticket(BaseModel):
    ticket: str           # Ticket number (e.g., "A052820861")
    legal: str            # Legal date in YYYY-MM-DD format
    expires: str          # Expiration date in YYYY-MM-DD format
    place: Optional[str] = None  # Location/place name


class Project(BaseModel):
    id: str
    name: str
    tickets: List[Ticket]


class EmailService:
    """
    Service class for handling all email operations using Next.js API.
    """
    
    @staticmethod
    def _ensure_api_key():
        """Ensure the API key is configured."""
        if not API_KEY:
            raise ValueError("API_KEY environment variable not configured")
    
    @staticmethod
    async def _send_email_via_nextjs(
        to: List[str],
        subject: str,
        template: str,
        template_props: Dict,
        from_email: str = "UndergroundIQ <notifications@underground-iq.com>",
        reply_to: str = "support@uiq.com"
    ) -> Dict:
        """
        Send email via Next.js API endpoint.
        
        Args:
            to: List of recipient email addresses
            subject: Email subject line
            template: Template name
            template_props: Template properties/data
            from_email: From email address
            reply_to: Reply-to email address
            
        Returns:
            Dict with email sending results
        """
        EmailService._ensure_api_key()
        
        payload = {
            "to": to,
            "subject": subject,
            "template": template,
            "templateProps": template_props,
            "from": from_email,
            "replyTo": reply_to
        }
        
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": API_KEY
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    NEXTJS_API_URL,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"Email sent successfully via Next.js API: {result}")
                
                return {
                    "status": "success",
                    "message": "Email sent successfully",
                    "email_id": result.get("id"),
                    "to": to,
                    "subject": subject
                }
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg = f"HTTP {e.response.status_code}: {error_detail.get('error', 'Unknown error')}"
            except:
                pass
            
            logger.error(f"Error sending email via Next.js API: {error_msg}")
            raise ValueError(f"Failed to send email: {error_msg}")
            
        except httpx.TimeoutException:
            logger.error("Timeout sending email via Next.js API")
            raise ValueError("Email sending timed out")
            
        except Exception as e:
            logger.error(f"Unexpected error sending email via Next.js API: {str(e)}")
            raise ValueError(f"Failed to send email: {str(e)}")
    
    @staticmethod
    async def send_test_email() -> Dict:
        """
        Send a test email using the weeklyUpdate template.
        
        Returns:
            Dict with email sending results
        """
        # Sample data for testing
        sample_projects = [
            Project(
                id="1",
                name="Downtown Infrastructure Project",
                tickets=[
                    Ticket(
                        ticket="A052820861",
                        legal="2024-01-10",
                        expires="2024-01-15",
                        place="123 Main St, Downtown"
                    ),
                    Ticket(
                        ticket="B052820862",
                        legal="2024-01-15",
                        expires="2024-01-19",
                        place="456 Oak Ave, Downtown"
                    )
                ]
            ),
            Project(
                id="2",
                name="Residential Area Expansion",
                tickets=[
                    Ticket(
                        ticket="C052820863",
                        legal="2024-01-18",
                        expires="2024-01-23",
                        place="789 Pine Rd, Residential"
                    )
                ]
            )
        ]
        
        template_props = {
            "companyName": "Test Company",
            "projects": [project.dict() for project in sample_projects],
            "reportDate": "January 15 - January 19, 2024",
            "totalTickets": 3,
            "newTickets": 1,
            "expiringTickets": 2
        }
        
        return await EmailService._send_email_via_nextjs(
            to=["test@example.com"],
            subject="Test Weekly Projects & Tickets Digest",
            template="weeklyUpdate",
            template_props=template_props
        )
    
    @staticmethod
    async def send_ticket_notification_email(
        to_emails: List[str],
        ticket_number: str,
        ticket_details: Dict,
        email_type: str = "notification"
    ) -> Dict:
        """
        Send a ticket-related notification email.
        
        Args:
            to_emails: List of recipient email addresses
            ticket_number: The ticket number
            ticket_details: Dictionary containing ticket information
            email_type: Type of email (notification, update, reminder, etc.)
            
        Returns:
            Dict with email sending results
        """
        EmailService._ensure_api_key()
        
        # Generate email content based on type
        if email_type == "notification":
            subject = f"Ticket Notification: {ticket_number}"
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Ticket Notification</h2>
                <p><strong>Ticket Number:</strong> {ticket_number}</p>
                <p><strong>Replace By Date:</strong> {ticket_details.get('replace_by_date', 'N/A')}</p>
                <p><strong>Legal Date:</strong> {ticket_details.get('legal_date', 'N/A')}</p>
                <p><strong>Project ID:</strong> {ticket_details.get('project_id', 'N/A')}</p>
                
                {'<p><strong>Continue Updates:</strong> Yes</p>' if ticket_details.get('is_continue_update') else ''}
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated notification from the Underground API system.
                </p>
            </div>
            """
        else:
            subject = f"Ticket Update: {ticket_number}"
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Ticket Update</h2>
                <p><strong>Ticket Number:</strong> {ticket_number}</p>
                <p>Your ticket has been updated. Please check the system for details.</p>
                
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">
                    This is an automated notification from the Underground API system.
                </p>
            </div>
            """
        
        # This method now uses the Next.js API instead of direct Resend
        params = {
            "from": "UndergroundIQ <notifications@underground-iq.com>",
            "to": to_emails,
            "subject": subject,
            "html": html_content,
        }
        
        try:
            # This method is deprecated and should not be used
            raise ValueError("This method is deprecated")
            logger.info(f"Ticket email sent successfully to {to_emails}: {email}")
            
            return {
                "status": "success",
                "message": f"Ticket email sent successfully",
                "email_id": email.get("id") if isinstance(email, dict) else str(email),
                "to": to_emails,
                "subject": subject,
                "ticket_number": ticket_number
            }
        except Exception as e:
            logger.error(f"Error sending ticket email to {to_emails}: {str(e)}")
            raise
    
    @staticmethod
    async def send_bulk_notification_emails(notifications: List[Dict]) -> Dict:
        """
        Send multiple notification emails in bulk.
        
        Args:
            notifications: List of notification dictionaries, each containing:
                - to: List of email addresses
                - subject: Email subject
                - html: Email HTML content
                
        Returns:
            Dict with bulk sending results
        """
        EmailService._ensure_api_key()
        
        results = {
            "total": len(notifications),
            "sent": 0,
            "failed": 0,
            "errors": []
        }
        
        # This method is deprecated - bulk emails should use the new Next.js API
        raise ValueError(
            "send_bulk_notification_emails is deprecated. "
            "Use individual send_weekly_update() calls or implement bulk support in Next.js API."
        )
        
        logger.info(f"Bulk email operation completed: {results['sent']} sent, {results['failed']} failed")
        return results
    
    @staticmethod
    def get_service_status() -> Dict:
        """
        Get the status of the email service.
        
        Returns:
            Dict with service status information
        """
        return {
            "service": "nextjs-api",
            "api_key_configured": bool(API_KEY),
            "api_key_set": "API_KEY" in os.environ,
            "ready": bool(API_KEY)
        }
    
    @staticmethod
    async def send_invitation_email(
        email: str, 
        name: str, 
        company_name: str, 
        role: str, 
        invite_url: str
    ) -> Dict:
        """
        Send an invitation email using the user_invitation.html template.
        
        Args:
            email: Recipient email address
            name: Recipient's name
            company_name: Name of the company sending the invitation
            role: User's assigned role
            invite_url: The invitation URL with parameters
            
        Returns:
            Dict with email sending results
        """
        EmailService._ensure_api_key()
        
        # Load the invitation template
        template_content = EmailService._load_template("user_invitation.html")
        
        # Template data
        template_data = {
            "recipient_name": name,
            "company_name": company_name,
            "user_role": role,
            "invite_url": invite_url,
            "company_address": "123 Main St, City, State 12345",  # You may want to make this configurable
            "support_url": "https://underground-iq.com/support"
        }
        
        # Render the template
        html_content = EmailService._render_template(template_content, **template_data)
        
        # This method now uses the Next.js API instead of direct Resend
        params = {
            "from": "invites@underground-iq.com",
            "to": [email],
            "subject": f"You're invited to join {company_name} on UndergroundIQ",
            "html": html_content,
        }
        
        try:
            # This method is deprecated and should use the new Next.js API
            raise ValueError(
                "send_invitation_email is deprecated. "
                "Please implement invitation template in Next.js and use _send_email_via_nextjs method."
            )
        except Exception as e:
            logger.error(f"Error sending invitation email to {email} for {company_name}: {str(e)}")
            raise ValueError(f"Failed to send invitation email: {str(e)}")

    @staticmethod
    async def send_weekly_update(
        to: List[str],
        company_name: str,
        projects: List[Project],
        total_tickets: int,
        new_tickets: int,
        expiring_tickets: int,
        report_date: str = None
    ) -> Dict:
        """
        Send a weekly update email using the weeklyUpdate template.
        
        Args:
            to: List of recipient email addresses
            company_name: Company name
            projects: List of Project objects with tickets
            total_tickets: Total number of tickets
            new_tickets: Number of new tickets (within 7 days)
            expiring_tickets: Number of expiring tickets (within 7 days)
            report_date: Report date string (optional)
            
        Returns:
            Dict with email sending results
        """
        if not report_date:
            from datetime import datetime, timedelta
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())  # Monday
            week_end = week_start + timedelta(days=4)  # Friday
            report_date = f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d')}, {week_start.year}"
        
        template_props = {
            "companyName": company_name,
            "projects": [project.dict() for project in projects],
            "reportDate": report_date,
            "totalTickets": total_tickets,
            "newTickets": new_tickets,
            "expiringTickets": expiring_tickets
        }
        
        subject = f"Weekly Projects & Tickets Digest - {report_date}"
        
        return await EmailService._send_email_via_nextjs(
            to=to,
            subject=subject,
            template="weeklyUpdate",
            template_props=template_props
        )

    @staticmethod
    async def send_weekly_digest_email(to_email: str, subject: str, html_content: str) -> Dict:
        """
        Send a weekly digest email using the rendered HTML content.
        
        DEPRECATED: This method is kept for backward compatibility.
        Use send_weekly_update() for new implementations.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_content: Rendered HTML content from template
            
        Returns:
            Dict with email sending results
        """
        logger.warning("send_weekly_digest_email is deprecated. Use send_weekly_update() instead.")
        
        # For backward compatibility, we'll still send the email but log a warning
        # This would require a custom template that accepts raw HTML, which may not be available
        # For now, we'll raise an error to encourage migration to the new method
        raise ValueError(
            "send_weekly_digest_email is deprecated and no longer supported. "
            "Please use send_weekly_update() with the weeklyUpdate template instead."
        )
