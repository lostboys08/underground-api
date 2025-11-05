#!/usr/bin/env python3
"""
Migration script to encrypt existing plain-text BlueStakes passwords.

This script:
1. Finds all companies with plain-text passwords
2. Encrypts them using the Fernet encryption
3. Updates the database with encrypted passwords
4. Provides rollback capability if needed

Usage:
    python migrate_encrypt_passwords.py --dry-run    # Preview changes
    python migrate_encrypt_passwords.py              # Apply changes
    python migrate_encrypt_passwords.py --rollback   # Rollback (if backup exists)
"""

import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.supabase_client import get_service_client
from utils.encryption import encrypt_password, is_encrypted_password, EncryptionError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_companies_with_passwords() -> List[Dict[str, Any]]:
    """
    Get all companies that have BlueStakes passwords (encrypted or plain-text).
    
    Returns:
        List of company records with credentials
    """
    try:
        result = (get_service_client()
                 .table("companies")
                 .select("id, name, bluestakes_username, bluestakes_password")
                 .not_.is_("bluestakes_password", "null")
                 .neq("bluestakes_password", "")
                 .execute())
        
        return result.data if result.data else []
        
    except Exception as e:
        logger.error(f"Error fetching companies: {str(e)}")
        raise


async def backup_passwords() -> str:
    """
    Create a backup of current passwords before migration.
    
    Returns:
        Backup filename
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"password_backup_{timestamp}.txt"
    
    try:
        companies = await get_companies_with_passwords()
        
        with open(backup_filename, 'w') as f:
            f.write(f"# Password backup created at {datetime.now().isoformat()}\n")
            f.write("# Format: company_id:username:password\n")
            f.write("# DO NOT COMMIT THIS FILE TO VERSION CONTROL\n\n")
            
            for company in companies:
                f.write(f"{company['id']}:{company['bluestakes_username']}:{company['bluestakes_password']}\n")
        
        logger.info(f"Password backup created: {backup_filename}")
        return backup_filename
        
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        raise


async def analyze_passwords() -> Dict[str, int]:
    """
    Analyze current password state.
    
    Returns:
        Dictionary with counts of encrypted vs plain-text passwords
    """
    companies = await get_companies_with_passwords()
    
    stats = {
        "total": len(companies),
        "encrypted": 0,
        "plain_text": 0,
        "empty": 0
    }
    
    for company in companies:
        password = company.get("bluestakes_password", "")
        
        if not password:
            stats["empty"] += 1
        elif is_encrypted_password(password):
            stats["encrypted"] += 1
        else:
            stats["plain_text"] += 1
    
    return stats


async def encrypt_company_passwords(dry_run: bool = False) -> Dict[str, Any]:
    """
    Encrypt all plain-text passwords.
    
    Args:
        dry_run: If True, only analyze what would be done
        
    Returns:
        Dictionary with migration results
    """
    companies = await get_companies_with_passwords()
    
    results = {
        "total_processed": 0,
        "encrypted": 0,
        "already_encrypted": 0,
        "errors": 0,
        "error_details": []
    }
    
    for company in companies:
        results["total_processed"] += 1
        company_id = company["id"]
        password = company.get("bluestakes_password", "")
        
        if not password:
            logger.warning(f"Company {company_id} has empty password, skipping")
            continue
        
        # Check if already encrypted
        if is_encrypted_password(password):
            logger.info(f"Company {company_id} password already encrypted, skipping")
            results["already_encrypted"] += 1
            continue
        
        # Encrypt the password
        try:
            encrypted_password = encrypt_password(password)
            logger.info(f"Company {company_id} password encrypted successfully")
            
            if not dry_run:
                # Update database
                update_result = (get_service_client()
                               .table("companies")
                               .update({"bluestakes_password": encrypted_password})
                               .eq("id", company_id)
                               .execute())
                
                if not update_result.data:
                    raise Exception(f"Failed to update company {company_id} in database")
                
                logger.info(f"Company {company_id} password updated in database")
            else:
                logger.info(f"DRY RUN: Would encrypt password for company {company_id}")
            
            results["encrypted"] += 1
            
        except EncryptionError as e:
            error_msg = f"Encryption failed for company {company_id}: {str(e)}"
            logger.error(error_msg)
            results["errors"] += 1
            results["error_details"].append(error_msg)
            
        except Exception as e:
            error_msg = f"Database update failed for company {company_id}: {str(e)}"
            logger.error(error_msg)
            results["errors"] += 1
            results["error_details"].append(error_msg)
    
    return results


async def rollback_from_backup(backup_file: str) -> Dict[str, Any]:
    """
    Rollback passwords from backup file.
    
    Args:
        backup_file: Path to backup file
        
    Returns:
        Dictionary with rollback results
    """
    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"Backup file not found: {backup_file}")
    
    results = {
        "total_processed": 0,
        "restored": 0,
        "errors": 0,
        "error_details": []
    }
    
    try:
        with open(backup_file, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            
            # Skip comments and empty lines
            if line.startswith('#') or not line:
                continue
            
            try:
                company_id, username, password = line.split(':', 2)
                company_id = int(company_id)
                
                results["total_processed"] += 1
                
                # Update database
                update_result = (get_service_client()
                               .table("companies")
                               .update({
                                   "bluestakes_username": username,
                                   "bluestakes_password": password
                               })
                               .eq("id", company_id)
                               .execute())
                
                if not update_result.data:
                    raise Exception(f"Failed to update company {company_id} in database")
                
                logger.info(f"Company {company_id} password restored from backup")
                results["restored"] += 1
                
            except ValueError as e:
                error_msg = f"Invalid backup line format: {line}"
                logger.error(error_msg)
                results["errors"] += 1
                results["error_details"].append(error_msg)
                
            except Exception as e:
                error_msg = f"Failed to restore company from line '{line}': {str(e)}"
                logger.error(error_msg)
                results["errors"] += 1
                results["error_details"].append(error_msg)
    
    except Exception as e:
        logger.error(f"Error reading backup file: {str(e)}")
        raise
    
    return results


async def main():
    """Main migration function."""
    parser = argparse.ArgumentParser(description="Migrate BlueStakes passwords to encrypted format")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them")
    parser.add_argument("--rollback", type=str, help="Rollback using specified backup file")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze current password state")
    
    args = parser.parse_args()
    
    try:
        # Check encryption key availability
        from utils.encryption import get_encryption_key
        try:
            get_encryption_key()
            logger.info("✓ Encryption key is properly configured")
        except EncryptionError as e:
            logger.error(f"❌ Encryption key error: {str(e)}")
            return 1
        
        if args.rollback:
            logger.info(f"Starting rollback from backup: {args.rollback}")
            results = await rollback_from_backup(args.rollback)
            
            logger.info("=== ROLLBACK RESULTS ===")
            logger.info(f"Total processed: {results['total_processed']}")
            logger.info(f"Successfully restored: {results['restored']}")
            logger.info(f"Errors: {results['errors']}")
            
            if results['error_details']:
                logger.error("Error details:")
                for error in results['error_details']:
                    logger.error(f"  - {error}")
            
            return 0 if results['errors'] == 0 else 1
        
        # Analyze current state
        logger.info("Analyzing current password state...")
        stats = await analyze_passwords()
        
        logger.info("=== CURRENT PASSWORD STATE ===")
        logger.info(f"Total companies with passwords: {stats['total']}")
        logger.info(f"Already encrypted: {stats['encrypted']}")
        logger.info(f"Plain text (need encryption): {stats['plain_text']}")
        logger.info(f"Empty passwords: {stats['empty']}")
        
        if args.analyze_only:
            return 0
        
        if stats['plain_text'] == 0:
            logger.info("✓ All passwords are already encrypted. No migration needed.")
            return 0
        
        # Create backup before migration (unless dry run)
        backup_file = None
        if not args.dry_run:
            backup_file = await backup_passwords()
        
        # Perform migration
        mode = "DRY RUN" if args.dry_run else "LIVE MIGRATION"
        logger.info(f"Starting password encryption migration ({mode})...")
        
        results = await encrypt_company_passwords(dry_run=args.dry_run)
        
        logger.info(f"=== {mode} RESULTS ===")
        logger.info(f"Total processed: {results['total_processed']}")
        logger.info(f"Successfully encrypted: {results['encrypted']}")
        logger.info(f"Already encrypted: {results['already_encrypted']}")
        logger.info(f"Errors: {results['errors']}")
        
        if results['error_details']:
            logger.error("Error details:")
            for error in results['error_details']:
                logger.error(f"  - {error}")
        
        if not args.dry_run and backup_file:
            logger.info(f"Backup created: {backup_file}")
            logger.info(f"To rollback: python {__file__} --rollback {backup_file}")
        
        if args.dry_run and results['encrypted'] > 0:
            logger.info(f"To apply changes: python {__file__}")
        
        return 0 if results['errors'] == 0 else 1
        
    except KeyboardInterrupt:
        logger.info("Migration cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
