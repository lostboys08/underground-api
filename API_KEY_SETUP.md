# API Key Authentication Setup

Your Underground API is now secured with API key authentication! 🔐

## Quick Setup

### 1. Generate a Secure API Key

```bash
# Generate a random 32-character API key (recommended)
openssl rand -hex 32

# Example output: a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

### 2. Set Environment Variables

**For Local Development:**
Create or update your `.env` file:
```env
API_KEY=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

**For Railway Deployment:**
1. Go to your Railway project dashboard
2. Navigate to Variables tab
3. Add: `API_KEY` = `your-generated-key-here`

### 3. Update Your Next.js App

**Environment Variable in Next.js:**
```env
# In your Next.js .env.local file
NEXT_PUBLIC_API_KEY=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
# Or use a server-side env var if you prefer:
API_KEY=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
```

**Using in API Calls:**
```typescript
// Client-side example
const apiKey = process.env.NEXT_PUBLIC_API_KEY;

const response = await fetch('/api/companies', {
  headers: {
    'X-API-Key': apiKey,
    'Content-Type': 'application/json'
  }
});

// Server-side example (API routes)
const response = await fetch('https://your-api-domain.com/companies', {
  headers: {
    'X-API-Key': process.env.API_KEY,
    'Content-Type': 'application/json'
  }
});
```

## What's Protected

✅ **Protected Endpoints** (require API key):
- `/companies/*` - All company endpoints
- `/profiles/*` - All profile endpoints  
- `/pdf/*` - All PDF generation endpoints
- `/debug/*` - All debug endpoints

🌍 **Public Endpoints** (no API key needed):
- `/` - API home/info
- `/health` - Health check
- `/docs` - API documentation
- `/openapi.json` - OpenAPI spec
- `/redoc` - Alternative docs

## Testing

```bash
# Test without API key (should return 401)
curl http://localhost:8000/companies

# Response: {"error": "Missing API key. Include X-API-Key header.", "status_code": 401}

# Test with API key (should work)
curl -H "X-API-Key: your-api-key-here" http://localhost:8000/companies

# Test public endpoint (should work without key)
curl http://localhost:8000/health
```

## Security Best Practices

🔒 **DO:**
- Generate long, random API keys (32+ characters)
- Store API keys in environment variables only
- Use HTTPS in production
- Rotate API keys regularly
- Monitor API usage for suspicious activity

⚠️ **DON'T:**
- Commit API keys to version control
- Share API keys in plain text
- Use simple/predictable API keys
- Hardcode API keys in your application code
- Log API keys in application logs

## Complete Environment Setup

Here's your complete `.env` file template:

```env
# API Security
API_KEY=your-secure-api-key-here

# Supabase Configuration  
SUPABASE_URL=your-supabase-project-url
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Encryption
ENCRYPTION_KEY=your-encryption-key-for-passwords
```

Your API is now secure! 🎉 