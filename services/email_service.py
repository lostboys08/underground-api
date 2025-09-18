"""
Email service using Resend API.
Centralizes all email functionality for both manual and scheduled sending.
"""
import os
import logging
from typing import Dict, List, Optional
import resend

logger = logging.getLogger(__name__)

# Initialize Resend API key from environment variable
resend.api_key = os.environ.get("RESEND_API_KEY")


class EmailService:
    """
    Service class for handling all email operations using Resend.
    """
    
    @staticmethod
    def _ensure_api_key():
        """Ensure the Resend API key is configured."""
        if not resend.api_key:
            raise ValueError("RESEND_API_KEY environment variable not configured")
    
    @staticmethod
    async def send_test_email() -> Dict:
        """
        Send a basic test email for testing purposes.
        
        Returns:
            Dict with email sending results
        """
        EmailService._ensure_api_key()
        
        params: resend.Emails.SendParams = {
            "from": "UndergoundIQ@underground-iq.com",
            "to": ["delivered@resend.dev", "kaim@kennyseng.com"],
            "subject": "Hello World",
            "html": "<strong>it works!</strong>",
        }
        
        try:
            email: resend.Email = resend.Emails.send(params)
            logger.info(f"Test email sent successfully: {email}")
            
            return {
                "status": "success",
                "message": "Test email sent successfully",
                "email_id": email.get("id") if isinstance(email, dict) else str(email),
                "to": params["to"],
                "subject": params["subject"]
            }
        except Exception as e:
            logger.error(f"Error sending test email: {str(e)}")
            raise
    
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
                
                {'<p><strong>Continue Update:</strong> Yes</p>' if ticket_details.get('is_continue_update') else ''}
                
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
        
        params: resend.Emails.SendParams = {
            "from": "Underground API <noreply@resend.dev>",  # You'll want to update this domain
            "to": to_emails,
            "subject": subject,
            "html": html_content,
        }
        
        try:
            email: resend.Email = resend.Emails.send(params)
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
        
        for notification in notifications:
            try:
                params: resend.Emails.SendParams = {
                    "from": "Underground API <noreply@resend.dev>",
                    "to": notification["to"],
                    "subject": notification["subject"],
                    "html": notification["html"],
                }
                
                email: resend.Email = resend.Emails.send(params)
                results["sent"] += 1
                logger.info(f"Bulk email sent to {notification['to']}: {email}")
                
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Failed to send email to {notification.get('to', 'unknown')}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)
        
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
            "service": "resend",
            "api_key_configured": bool(resend.api_key),
            "api_key_set": "RESEND_API_KEY" in os.environ,
            "ready": bool(resend.api_key)
        }
