---
title: FastAPI
description: A FastAPI server
tags:
  - fastapi
  - hypercorn
  - python
---

# FastAPI Example

This example starts up a [FastAPI](https://fastapi.tiangolo.com/) server.

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/-NvLj4?referralCode=CRJ8FE)
## ✨ Features

- FastAPI
- [Hypercorn](https://hypercorn.readthedocs.io/)
- Python 3

## 💁‍♀️ How to use

- Clone locally and install packages with pip using `pip install -r requirements.txt`
- Run locally using `hypercorn main:app --reload`

## 📝 Notes

- To learn about how to use FastAPI with most of its features, you can visit the [FastAPI Documentation](https://fastapi.tiangolo.com/tutorial/)
- To learn about Hypercorn and how to configure it, read their [Documentation](https://hypercorn.readthedocs.io/)

## API Authentication

This API now requires API key authentication for all endpoints except:
- `/` (root/home)
- `/health` (health check)
- `/docs` (API documentation)
- `/openapi.json` and `/redoc` (documentation assets)

### Setting up API Key Authentication

1. **Set the API Key Environment Variable**:
   ```bash
   # For local development (.env file)
   API_KEY=your-secret-api-key-here
   
   # For Railway deployment
   # Set API_KEY in your Railway environment variables
   ```

2. **Generate a Secure API Key**:
   ```bash
   # Generate a random 32-character API key (recommended)
   openssl rand -hex 32
   
   # Or use any secure random string generator
   ```

3. **Using the API Key in Your Next.js App**:
   ```typescript
   // In your Next.js app, include the header in all API requests
   const response = await fetch('your-api-url/companies', {
     headers: {
       'X-API-Key': process.env.NEXT_PUBLIC_API_KEY, // Store in env vars
       'Content-Type': 'application/json'
     }
   });
   ```

4. **Environment Variables Required**:
   ```env
   # API Security
   API_KEY=your-secure-api-key-here
   
   # Existing Supabase configuration
   SUPABASE_URL=your-supabase-url
   SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
   SUPABASE_ANON_KEY=your-anon-key
   SUPABASE_JWT_SECRET=your-jwt-secret
   
   # Encryption
   ENCRYPTION_KEY=your-encryption-key
   ```

### Testing API Key Authentication

```bash
# Without API key (should return 401)
curl http://localhost:8000/companies

# With API key (should work)
curl -H "X-API-Key: your-api-key" http://localhost:8000/companies

# Public endpoints work without API key
curl http://localhost:8000/health
```

### Security Notes

- **Never commit API keys to version control**
- **Use environment variables for all sensitive configuration**
- **Generate strong, random API keys (32+ characters)**
- **Rotate API keys regularly in production**
- **Use HTTPS in production to protect API keys in transit**
