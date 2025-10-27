#!/usr/bin/env python3
"""
Test script for the bulk weekly digest email functionality.
This script tests the send_weekly_project_digest function.
"""
import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tasks.jobs import send_weekly_project_digest


async def test_bulk_weekly_digest():
    """Test the bulk weekly digest functionality."""
    print("🚀 Testing bulk weekly digest email process...")
    print("This will:")
    print("  1. Get all assigned users from the database")
    print("  2. For each user, gather their projects and tickets")
    print("  3. Send individual weekly update emails via Next.js API")
    print("  4. Calculate new/expiring ticket counts automatically")
    print()
    
    try:
        result = await send_weekly_project_digest()
        
        print("✅ Bulk weekly digest process completed!")
        print(f"📊 Results:")
        print(f"   Status: {result.get('status', 'unknown')}")
        print(f"   Message: {result.get('message', 'No message')}")
        print(f"   Emails sent: {result.get('emails_sent', 0)}")
        
        if result.get('errors'):
            print(f"   Errors: {len(result['errors'])}")
            for i, error in enumerate(result['errors'][:3], 1):  # Show first 3 errors
                print(f"     {i}. {error}")
            if len(result['errors']) > 3:
                print(f"     ... and {len(result['errors']) - 3} more errors")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in bulk weekly digest process: {e}")
        print(f"Error type: {type(e).__name__}")
        return False


async def main():
    """Run the bulk email test."""
    print("📧 Bulk Weekly Digest Email Test")
    print("=" * 50)
    
    # Check if API_KEY is set
    if not os.environ.get("API_KEY"):
        print("❌ API_KEY environment variable not set!")
        print("Please set the API_KEY environment variable and try again.")
        return
    
    print(f"✅ API Key configured")
    print(f"🌐 Next.js API endpoint: https://app.underground-iq.com/api/send-email")
    print(f"📅 Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Run the test
    success = await test_bulk_weekly_digest()
    
    print()
    print("=" * 50)
    if success:
        print("🎉 Bulk email test completed successfully!")
        print("The weekly digest process is working with the new Next.js API.")
    else:
        print("⚠️  Bulk email test encountered issues.")
        print("Please check the error messages above and your configuration.")
    
    print()
    print("💡 Tips:")
    print("  - Make sure your database has users with assigned projects")
    print("  - Verify the Next.js API is running and accessible")
    print("  - Check that the 'weeklyUpdate' template exists in Next.js")
    print("  - Ensure the API_KEY matches between FastAPI and Next.js")


if __name__ == "__main__":
    asyncio.run(main())
