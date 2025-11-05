#!/usr/bin/env python3
"""
Simple script to test the backfill functionality via API endpoints.
This can be run from anywhere and doesn't require local environment setup.
"""

import requests
import json
import sys
import argparse
from typing import Optional

def test_backfill_via_api(base_url: str, cron_secret: str, company_id: Optional[int] = None, dry_run: bool = True):
    """
    Test the backfill functionality by calling the API endpoints.
    
    Args:
        base_url: The base URL of your API (e.g., https://your-app.railway.app)
        cron_secret: The CRON_SECRET value from your environment
        company_id: Optional company ID to test with
        dry_run: If True, just shows what would happen
    """
    
    headers = {
        "X-CRON-SECRET": cron_secret,
        "Content-Type": "application/json"
    }
    
    # Test cron status first
    print("🔍 Testing cron status...")
    try:
        response = requests.get(f"{base_url}/cron/status", headers=headers)
        if response.status_code == 200:
            print("✅ Cron service is accessible")
            status_data = response.json()
            print(f"   Available endpoints: {len(status_data.get('available_jobs', []))}")
        else:
            print(f"❌ Cron status failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Failed to connect to API: {str(e)}")
        return False
    
    if dry_run:
        print("\n🧪 DRY RUN - This would trigger the backfill process")
        print(f"   Endpoint: POST {base_url}/cron/sync-bluestakes-data")
        if company_id:
            print(f"   Company ID: {company_id}")
        else:
            print("   Company ID: All companies")
        print("   To actually run: use --no-dry-run flag")
        return True
    
    # Actually trigger the backfill
    print("\n🚀 Triggering backfill process...")
    
    params = {}
    if company_id:
        params["company_id"] = company_id
    
    try:
        response = requests.post(
            f"{base_url}/cron/sync-bluestakes-data",
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Backfill job queued successfully!")
            print(f"   Status: {result.get('status')}")
            print(f"   Message: {result.get('message')}")
            print(f"   Parameters: {json.dumps(result.get('parameters', {}), indent=2)}")
            print("\n📊 Check your application logs to monitor progress")
            return True
        else:
            print(f"❌ Backfill failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Failed to trigger backfill: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Test backfill functionality via API")
    parser.add_argument("--url", required=True, help="Base URL of your API (e.g., https://your-app.railway.app)")
    parser.add_argument("--cron-secret", required=True, help="CRON_SECRET value from your environment")
    parser.add_argument("--company-id", type=int, help="Optional company ID to test with")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually trigger the backfill (default is dry run)")
    
    args = parser.parse_args()
    
    # Clean up URL
    base_url = args.url.rstrip('/')
    
    print(f"🔧 Testing backfill functionality")
    print(f"   API URL: {base_url}")
    print(f"   Company ID: {args.company_id or 'All companies'}")
    print(f"   Mode: {'LIVE' if args.no_dry_run else 'DRY RUN'}")
    print()
    
    success = test_backfill_via_api(
        base_url=base_url,
        cron_secret=args.cron_secret,
        company_id=args.company_id,
        dry_run=not args.no_dry_run
    )
    
    if success:
        print("\n🎉 Test completed successfully!")
        if not args.no_dry_run:
            print("💡 Use --no-dry-run to actually trigger the backfill")
    else:
        print("\n💥 Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
