"""
Email service using Resend API.
Centralizes all email functionality for both manual and scheduled sending.
"""
import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
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
    def _load_template(template_name: str) -> str:
        """
        Load an HTML template from the templates directory.
        
        Args:
            template_name: Name of the template file (e.g., 'weekly_projects_digest.html')
            
        Returns:
            Template content as string
        """
        template_path = Path(__file__).parent.parent / "templates" / "email" / template_name
        
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")
        
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @staticmethod
    def _render_template(template_content: str, **kwargs) -> str:
        """
        Render a template by replacing placeholder variables.
        
        Args:
            template_content: The template content as string
            **kwargs: Variables to replace in the template
            
        Returns:
            Rendered template content
        """
        rendered = template_content
        
        # Replace all template variables
        for key, value in kwargs.items():
            placeholder = f"{{{{{key}}}}}"
            rendered = rendered.replace(placeholder, str(value))
        
        return rendered
    
    @staticmethod
    async def send_test_email() -> Dict:
        """
        Send a test email using the weekly_projects_digest.html template.
        
        Returns:
            Dict with email sending results
        """
        EmailService._ensure_api_key()
        
        # Load the weekly projects digest template
        template_content = EmailService._load_template("weekly_projects_digest.html")
        
        # Sample data for testing the template
        sample_data = {
            "company_name": "UndergroundIQ",
            "company_address": "123 Main St, City, State 12345",
            "support_url": "https://underground-iq.com/support",
            "unsubscribe_url": "https://underground-iq.com/unsubscribe",
            "preferences_url": "https://underground-iq.com/preferences",
            "recipient_name": "Test User",
            "week_start": "2024-01-15",
            "week_end": "2024-01-21",
            "preheader_text": "Your weekly projects and tickets summary",
            "total_projects": "2",
            "total_tickets": "5",
            "project_id": "PROJ-001",
            "project_name": "Sample Project Alpha",
            "project_image_url": "https://via.placeholder.com/568x200/0f172a/ffffff?text=Project+Map",
            "project_ticket_count": "3",
            "ticket_number": "TKT-001",
            "replace_by_date": "2024-02-15",
            "legal_date": "2024-02-20",
            "ticket_meta": "High Priority"
        }
        
        # Render the template with sample data
        html_content = EmailService._render_template(template_content, **sample_data)
        
        params: resend.Emails.SendParams = {
            "from": "UndergoundIQ@underground-iq.com",
            "to": ["kaim@kennyseng.com"],
            "subject": "Weekly Projects & Tickets Digest - Test",
            "html": html_content,
        }
        
        try:
            email: resend.Email = resend.Emails.send(params)
            logger.info(f"Test email sent successfully: {email}")
            
            return {
                "status": "success",
                "message": "Test email sent successfully using weekly_projects_digest.html template",
                "email_id": email.get("id") if isinstance(email, dict) else str(email),
                "to": params["to"],
                "subject": params["subject"],
                "template_used": "weekly_projects_digest.html"
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
