#!/usr/bin/env python3
"""
Test script for database schema changes and field mapping updates.

Tests:
1. Address formatting with various scenarios
2. Field mappings (name, phone, location_description)
3. Verification that removed fields don't exist in model
"""
import logging
from utils.bluestakes import (
    transform_bluestakes_ticket_to_project_ticket,
    format_address_from_bluestakes_data
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_format_address():
    """Test address formatting with various scenarios"""
    logger.info("Testing address formatting...")

    # Test 1: Full address with range and cross streets
    ticket_data = {
        "street": "Main St",
        "st_from_address": "123",
        "st_to_address": "456",
        "cross1": "Oak Ave",
        "cross2": "Elm St"
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "123-456 Main St between Oak Ave and Elm St"
    assert result == expected, f"Test 1 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 1 passed: {result}")

    # Test 2: Same from/to address with one cross street
    ticket_data = {
        "street": "Main St",
        "st_from_address": "123",
        "st_to_address": "123",
        "cross1": "Oak Ave",
        "cross2": None
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "123 Main St at Oak Ave"
    assert result == expected, f"Test 2 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 2 passed: {result}")

    # Test 3: Street only (no addresses or cross streets)
    ticket_data = {
        "street": "Main St",
        "st_from_address": None,
        "st_to_address": None,
        "cross1": None,
        "cross2": None
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "Main St"
    assert result == expected, f"Test 3 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 3 passed: {result}")

    # Test 4: No street (edge case)
    ticket_data = {
        "street": None,
        "st_from_address": "123",
        "st_to_address": "456"
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "Address not available"
    assert result == expected, f"Test 4 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 4 passed: {result}")

    # Test 5: Zero addresses should be ignored
    ticket_data = {
        "street": "Main St",
        "st_from_address": "0",
        "st_to_address": "0",
        "cross1": "Oak Ave",
        "cross2": None
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "Main St at Oak Ave"
    assert result == expected, f"Test 5 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 5 passed: {result}")

    # Test 6: Two cross streets with address range
    ticket_data = {
        "street": "Broadway",
        "st_from_address": "100",
        "st_to_address": "200",
        "cross1": "1st Ave",
        "cross2": "2nd Ave"
    }
    result = format_address_from_bluestakes_data(ticket_data)
    expected = "100-200 Broadway between 1st Ave and 2nd Ave"
    assert result == expected, f"Test 6 failed: Expected '{expected}', got '{result}'"
    logger.info(f"✅ Test 6 passed: {result}")

    logger.info("✅ All address formatting tests passed!\n")


def test_field_mapping():
    """Test that new field mappings are correct"""
    logger.info("Testing field mappings...")

    # Mock Bluestakes API response with new field names
    ticket_data = {
        "ticket": "TEST123",
        "replace_by_date": "2024-12-31T00:00:00Z",
        "contact": "John Doe",              # Should map to "name"
        "contact_phone": "555-1234",        # Should map to "phone"
        "location": "Near city hall",       # Should map to "location_description"
        "street": "Main St",
        "st_from_address": "100",
        "st_to_address": "200",
        "cross1": "1st Ave",
        "cross2": "2nd Ave",
        "place": "Springfield",
        "email": "john@example.com"
    }

    result = transform_bluestakes_ticket_to_project_ticket(ticket_data, company_id=1)

    # Verify new mappings
    assert result.name == "John Doe", f"name should be 'John Doe', got '{result.name}'"
    logger.info(f"✅ name field correctly mapped from 'contact': {result.name}")

    assert result.phone == "555-1234", f"phone should be '555-1234', got '{result.phone}'"
    logger.info(f"✅ phone field correctly mapped from 'contact_phone': {result.phone}")

    assert result.location_description == "Near city hall", \
        f"location_description should be 'Near city hall', got '{result.location_description}'"
    logger.info(f"✅ location_description field correctly mapped from 'location': {result.location_description}")

    assert result.formatted_address == "100-200 Main St between 1st Ave and 2nd Ave", \
        f"formatted_address incorrect: '{result.formatted_address}'"
    logger.info(f"✅ formatted_address correctly generated: {result.formatted_address}")

    # Verify place and street are still populated
    assert result.place == "Springfield", f"place should be 'Springfield', got '{result.place}'"
    logger.info(f"✅ place field still works: {result.place}")

    assert result.street == "Main St", f"street should be 'Main St', got '{result.street}'"
    logger.info(f"✅ street field still works: {result.street}")

    logger.info("✅ All field mapping tests passed!\n")


def test_removed_fields():
    """Test that removed fields don't exist in the model"""
    logger.info("Testing removed fields...")

    ticket_data = {
        "ticket": "TEST456",
        "replace_by_date": "2024-12-31T00:00:00Z",
        "contact": "Jane Smith",
        "contact_phone": "555-5678",
        "location": "Downtown",
        "street": "Oak St",
        # Include old field names that should be ignored
        "latitude": "40.7128",
        "longitude": "-74.0060",
        "priority": "High",
        "category": "Emergency"
    }

    result = transform_bluestakes_ticket_to_project_ticket(ticket_data, company_id=1)

    # Verify removed fields don't exist (will raise AttributeError if they do)
    removed_fields = ["latitude", "longitude", "priority", "category"]
    for field in removed_fields:
        try:
            value = getattr(result, field)
            assert False, f"{field} field should not exist, but has value: {value}"
        except AttributeError:
            logger.info(f"✅ {field} field correctly removed from model")

    logger.info("✅ All removed field tests passed!\n")


def test_edge_cases():
    """Test edge cases and None values"""
    logger.info("Testing edge cases...")

    # Test with missing optional fields
    ticket_data = {
        "ticket": "TEST789",
        "replace_by_date": "2024-12-31T00:00:00Z",
        # Missing contact, contact_phone, location
        "street": "Elm St"
    }

    result = transform_bluestakes_ticket_to_project_ticket(ticket_data, company_id=1)

    assert result.name is None, f"name should be None when 'contact' is missing, got '{result.name}'"
    logger.info(f"✅ name correctly None when 'contact' missing")

    assert result.phone is None, f"phone should be None when 'contact_phone' is missing, got '{result.phone}'"
    logger.info(f"✅ phone correctly None when 'contact_phone' missing")

    assert result.location_description is None, \
        f"location_description should be None when 'location' is missing, got '{result.location_description}'"
    logger.info(f"✅ location_description correctly None when 'location' missing")

    assert result.formatted_address == "Elm St", \
        f"formatted_address should still work with minimal data, got '{result.formatted_address}'"
    logger.info(f"✅ formatted_address works with minimal data: {result.formatted_address}")

    logger.info("✅ All edge case tests passed!\n")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting schema change tests...")
    logger.info("=" * 60 + "\n")

    try:
        test_format_address()
        test_field_mapping()
        test_removed_fields()
        test_edge_cases()

        logger.info("=" * 60)
        logger.info("✅ ALL TESTS PASSED!")
        logger.info("=" * 60)
    except AssertionError as e:
        logger.error(f"❌ TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"❌ ERROR: {e}")
        exit(1)
