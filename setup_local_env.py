#!/usr/bin/env python3
"""
Simple script to set up local development environment for testing.
Creates a minimal .env file with placeholder values for local development.
"""

import os
from pathlib import Path

def create_local_env():
    """Create a .env file with minimal configuration for local development."""
    
    env_path = Path(".env")
    
    if env_path.exists():
        print("⚠️  .env file already exists. Backing up to .env.backup")
        os.rename(".env", ".env.backup")
    
    env_content = """# Local Development Environment
# Copy this file and update with your actual values

# Supabase Configuration (Required)
SUPABASE_URL=your_supabase_url_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# API Security
API_KEY=local_development_api_key

# Cron Secret (for testing cron endpoints)
CRON_SECRET=local_cron_secret

# Optional: Railway Environment (leave commented for local)
# RAILWAY_ENVIRONMENT=development

# Note: For the backfill script to work, you MUST set the Supabase values above
# Get these from your Supabase project dashboard:
# 1. Go to Settings > API
# 2. Copy the Project URL (SUPABASE_URL)
# 3. Copy the service_role secret key (SUPABASE_SERVICE_ROLE_KEY)
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✅ Created .env file with placeholder values")
    print("\n📝 Next steps:")
    print("1. Edit .env file and add your actual Supabase URL and service role key")
    print("2. Get these values from your Supabase project dashboard:")
    print("   - Go to Settings > API")
    print("   - Copy Project URL and service_role key")
    print("3. Install dependencies: pip install -r requirements.txt")
    print("4. Test the backfill script: python3 backfill_bluestakes_data.py --dry-run")

if __name__ == "__main__":
    create_local_env()
