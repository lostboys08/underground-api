# Bluestakes Ticket Sync Implementation

## Overview

This implementation caches comprehensive Bluestakes ticket data in the `project_tickets` table to eliminate individual API calls during frontend display, improving dashboard performance from 5-10+ seconds to sub-second loads.

## Database Schema

The `project_tickets` table has been extended with 30+ new columns to store Bluestakes data:

### Location & Maps
- `place` - City name
- `street` - Street name
- `location_description` - Location description from Bluestakes API "location" field
- `formatted_address` - Pre-calculated formatted address string for display (e.g., "123-456 Main St at Oak Ave")
- `work_area` - **GeoJSON polygon data (JSONB)** for map display

### Date Fields
- `expires` - Expiration date
- `original_date` - Original creation date

### Work Details
- `done_for` - Work recipient
- `type` - Ticket type

### Address Details
- `st_from_address` - Address range start
- `st_to_address` - Address range end
- `cross1` - First cross street
- `cross2` - Second cross street
- `county` - County name
- `state` - State
- `zip` - Zip code

### Contact Information
- `name` - Primary contact name (from API "contact" field)
- `phone` - Primary phone (from API "contact_phone" field)
- `email` - Contact email

### Removed Fields (December 2024)
The following fields have been removed as they are redundant or not used:
- `latitude` - Removed (coordinate data available in work_area GeoJSON)
- `longitude` - Removed (coordinate data available in work_area GeoJSON)
- `priority` - Removed (not used by application)
- `category` - Removed (not used by application)

### Ticket Management
- `revision` - Revision number

### Metadata
- `bluestakes_data_updated_at` - Last sync timestamp
- `bluestakes_data` - Full raw API response backup (JSONB)

## API Endpoints

### Automated Sync (Cron Jobs)

#### Daily Bluestakes Data Sync
- **Endpoint**: `POST /cron/sync-bluestakes-data`
- **Schedule**: Daily at 2:00 AM (configured in `railway.json`)
- **Purpose**: Updates existing tickets with fresh Bluestakes data
- **Parameters**:
  - `company_id` (optional) - Sync specific company
  - `max_age_hours` (default: 24) - Only sync tickets older than X hours
  - `batch_size` (default: 50) - Batch processing size

### Manual Sync Endpoints

#### Individual Ticket Sync
- **Endpoint**: `POST /tickets/{ticket_number}/sync-bluestakes`
- **Purpose**: Manually sync a specific ticket with fresh Bluestakes data
- **Returns**: Job queued confirmation

#### Bulk Ticket Sync
- **Endpoint**: `POST /tickets/sync-all-bluestakes`
- **Purpose**: Manually sync all tickets (or company-specific) with fresh data
- **Parameters**:
  - `company_id` (optional) - Sync specific company
  - `max_age_hours` (default: 24) - Only sync tickets older than X hours
  - `batch_size` (default: 50) - Batch processing size

## Backfill Script

### Usage

#### Local Development (requires environment setup)
```bash
# Set up local environment first
python3 setup_local_env.py
# Edit .env file with your Supabase credentials

# Then run backfill script
python3 backfill_bluestakes_data.py --dry-run
python3 backfill_bluestakes_data.py --company-id 1
python3 backfill_bluestakes_data.py --force
```

#### Production Testing (via API - recommended)
```bash
# Test via API endpoints (no local setup needed)
python3 test_backfill_endpoint.py --url https://your-app.railway.app --cron-secret YOUR_CRON_SECRET --dry-run

# Actually trigger backfill
python3 test_backfill_endpoint.py --url https://your-app.railway.app --cron-secret YOUR_CRON_SECRET --no-dry-run

# Test specific company
python3 test_backfill_endpoint.py --url https://your-app.railway.app --cron-secret YOUR_CRON_SECRET --company-id 1 --no-dry-run
```

### Features
- Statistics reporting (tickets needing backfill)
- Company credential verification
- Batch processing with configurable size
- Force mode for updating all tickets
- Dry run mode for testing
- Comprehensive error handling and logging

## Technical Implementation

### Data Flow
1. **New Tickets**: When syncing new tickets, full Bluestakes data is fetched and stored
2. **Existing Tickets**: Periodic sync updates tickets with fresh data based on age
3. **API Rate Limiting**: 100ms delays between API calls to respect Bluestakes limits
4. **Error Handling**: Failed tickets are logged but don't stop the batch process

### Key Functions

#### `transform_bluestakes_ticket_to_project_ticket()`
- Maps all Bluestakes API fields to database columns
- Handles GeoJSON validation for `work_area`
- Cleans string values (converts empty strings to NULL)
- Sets sync timestamp and stores raw API response

#### `sync_existing_tickets_bluestakes_data()`
- Batch processes existing tickets
- Checks sync age before updating
- Respects API rate limits
- Comprehensive error recovery

#### `update_project_ticket_bluestakes_data()`
- Updates individual tickets with fresh data
- Authenticates with company-specific credentials
- Handles missing or invalid tickets gracefully

## Performance Impact

### Before Implementation
- **Dashboard Load Time**: 5-10+ seconds
- **API Calls per Page**: 20-50 individual Bluestakes API calls
- **User Experience**: Slow map rendering, frequent timeouts
- **API Usage**: High, risk of rate limiting

### After Implementation
- **Dashboard Load Time**: Sub-second
- **API Calls per Page**: 0 (uses cached data)
- **User Experience**: Instant map rendering with polygons
- **API Usage**: Reduced to daily sync operations

## Monitoring and Maintenance

### Logs
- All sync operations are logged with timestamps
- Failed tickets are logged with error details
- API rate limiting and retry attempts are tracked

### Health Checks
- Use `/cron/status` to verify cron job configuration
- Monitor `bluestakes_data_updated_at` timestamps for sync health
- Check error logs for API authentication issues

### Troubleshooting

#### Common Issues
1. **Missing Company Credentials**: Ensure Bluestakes username/password are set in companies table
2. **API Rate Limits**: Increase delays between API calls if needed
3. **Invalid GeoJSON**: Check `work_area` data validation in logs
4. **Stale Data**: Verify cron jobs are running and sync timestamps are recent

#### Manual Recovery
```bash
# Force sync all tickets for a company
curl -X POST "http://localhost:8000/tickets/sync-all-bluestakes?company_id=1&max_age_hours=0"

# Check specific ticket sync status
curl -X POST "http://localhost:8000/tickets/TICKET123/sync-bluestakes"
```

## Future Enhancements

1. **Real-time Sync**: WebSocket notifications when ticket data changes
2. **Selective Field Updates**: Only update changed fields to reduce API calls
3. **Caching Layers**: Redis cache for frequently accessed ticket data
4. **Analytics**: Track sync performance and API usage metrics
