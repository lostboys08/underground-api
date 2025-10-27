#!/usr/bin/env python3
"""
Test script for the new Next.js email integration.
This script tests the weekly update email functionality.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.email_service import EmailService, Project, Ticket


async def test_weekly_update_email():
    """Test the send_weekly_update method."""
    print("Testing weekly update email...")
    
    # Create sample data
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
    
    try:
        result = await EmailService.send_weekly_update(
            to=["test@example.com"],
            company_name="Test Company",
            projects=sample_projects,
            total_tickets=3,
            new_tickets=1,
            expiring_tickets=2
        )
        
        print("✅ Weekly update email sent successfully!")
        print(f"Result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending weekly update email: {e}")
        return False


async def test_send_test_email():
    """Test the send_test_email method."""
    print("Testing send_test_email method...")
    
    try:
        result = await EmailService.send_test_email()
        print("✅ Test email sent successfully!")
        print(f"Result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending test email: {e}")
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting email integration tests...\n")
    
    # Check if API_KEY is set
    if not os.environ.get("API_KEY"):
        print("❌ API_KEY environment variable not set!")
        print("Please set the API_KEY environment variable and try again.")
        return
    
    print(f"Using Next.js API endpoint: https://app.underground-iq.com/api/send-email")
    print(f"API Key configured: {'✅' if os.environ.get('API_KEY') else '❌'}\n")
    
    # Run tests
    tests = [
        ("Weekly Update Email", test_weekly_update_email),
        ("Test Email Method", test_send_test_email),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Running: {test_name}")
        success = await test_func()
        results.append((test_name, success))
        print()
    
    # Summary
    print("📊 Test Results:")
    print("-" * 40)
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("🎉 All tests passed! Email integration is working correctly.")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")


if __name__ == "__main__":
    asyncio.run(main())
