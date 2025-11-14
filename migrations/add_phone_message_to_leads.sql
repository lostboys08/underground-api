-- Migration: Add phone and message fields to crm.leads table
-- Date: 2025-11-14
-- Description: Adds phone and message fields to support contact form submissions

ALTER TABLE crm.leads
ADD COLUMN IF NOT EXISTS phone text NULL,
ADD COLUMN IF NOT EXISTS message text NULL;

COMMENT ON COLUMN crm.leads.phone IS 'Contact phone number from form submission';
COMMENT ON COLUMN crm.leads.message IS 'Message or inquiry from contact form';
