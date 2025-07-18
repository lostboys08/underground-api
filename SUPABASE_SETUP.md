# Supabase Integration Setup Guide

This guide walks you through setting up Supabase with your FastAPI application.

## 📋 Prerequisites

- Python 3.8+
- A Supabase account (https://supabase.com)
- A Supabase project created

## 🚀 Quick Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in your project root:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key-here
SUPABASE_ANON_KEY=your-anon-key-here
SUPABASE_JWT_SECRET=your-jwt-secret-here
```

**Where to find these values:**
1. Go to your Supabase Dashboard
2. Navigate to **Settings** → **API**
3. Copy the values:
   - **URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_ANON_KEY`  
   - **service_role key** → `SUPABASE_SERVICE_ROLE_KEY`
   - **JWT Secret** → `SUPABASE_JWT_SECRET`

### 3. Database Setup

Run the SQL schema in your Supabase SQL Editor:

```bash
# Copy and paste the contents of sql/users_table.sql
# into Supabase Dashboard → SQL Editor
```

Or use the Supabase CLI:
```bash
supabase db reset
```

## 🏗️ Architecture Overview

### Client Types

1. **Service Role Client** (`supabase_service`)
   - Full database access
   - Bypasses RLS policies
   - Use for admin operations

2. **Anonymous Client** (`supabase_anon`)
   - Respects RLS policies
   - Public access only
   - Use for public endpoints

3. **Authenticated Client** (`get_user_client(jwt)`)
   - User-specific access
   - Respects RLS policies
   - Use for user-specific operations

### File Structure

```
project/
├── config/
│   └── supabase_client.py    # Supabase configuration
├── routes/
│   ├── users.py              # User CRUD operations
│   └── pdf_generator.py      # Existing PDF routes
├── utils/
│   └── auth.py               # JWT verification utilities
├── sql/
│   └── users_table.sql       # Database schema
└── main.py                   # FastAPI app with routers
```

## 🔌 API Endpoints

### User Management

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/users/` | Create user | ❌ |
| GET | `/users/{id}` | Get user by ID | ❌ |
| GET | `/users/` | List users (paginated) | ❌ |
| PUT | `/users/{id}` | Update user | ❌ |
| DELETE | `/users/{id}` | Delete user | ❌ |
| GET | `/users/profile/me` | Get current user profile | ✅ |
| PUT | `/users/profile/me` | Update current user profile | ✅ |

### Usage Examples

#### Create a User
```bash
curl -X POST "http://localhost:8000/users/" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "john@example.com",
    "name": "John Doe",
    "age": 30,
    "metadata": {"preferences": {"theme": "dark"}}
  }'
```

#### Get User Profile (Authenticated)
```bash
curl -X GET "http://localhost:8000/users/profile/me" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## 🔐 Authentication

### JWT Token Format

Supabase JWTs contain:
- `sub`: User ID
- `email`: User email
- `exp`: Expiration timestamp
- `aud`: Audience (should be "authenticated")
- `user_metadata`: Custom user data

### Using Auth Dependencies

```python
from utils.auth import get_current_user_id, verify_jwt_token

@router.get("/protected")
async def protected_route(user_id: str = Depends(get_current_user_id)):
    return {"message": f"Hello user {user_id}"}

@router.get("/optional-auth")
async def optional_auth_route(user_id: Optional[str] = Depends(get_current_user_optional)):
    if user_id:
        return {"message": f"Hello authenticated user {user_id}"}
    return {"message": "Hello anonymous user"}
```

## 🛡️ Row Level Security (RLS)

The users table has these RLS policies:

1. **Users can view own profile**: Users can only see their own data
2. **Users can update own profile**: Users can only update their own data
3. **Service role full access**: Admin operations bypass RLS
4. **Allow public user creation**: Anyone can create a user (optional)

### Testing RLS

When using JWT authentication, operations automatically respect RLS:

```python
# This will only return/update the authenticated user's data
user_client = get_user_client(jwt_token)
result = user_client.table("users").select("*").execute()
```

## 🚨 Error Handling

### Common Errors

1. **Missing Environment Variables**
   ```
   ValueError: Missing required environment variables
   ```
   **Solution**: Check your `.env` file

2. **Invalid JWT Token**
   ```
   401 Unauthorized: Invalid token
   ```
   **Solution**: Verify token format and expiration

3. **RLS Policy Violations**
   ```
   403 Forbidden: Row-level security policy violation
   ```
   **Solution**: Check RLS policies and user permissions

## 🧪 Testing

### Test with Service Role (Admin)

```python
from config.supabase_client import supabase_service

# This bypasses RLS - use for admin operations
result = supabase_service.table("users").select("*").execute()
```

### Test with User Authentication

```python
from config.supabase_client import get_user_client

# This respects RLS - use for user operations
user_client = get_user_client("user_jwt_token")
result = user_client.table("users").select("*").execute()
```

## 📊 Production Considerations

### Security Best Practices

1. **Never expose service role key** in client-side code
2. **Use anon key for public operations** only
3. **Implement proper RLS policies** for data protection
4. **Validate JWT tokens** on protected routes
5. **Use HTTPS** in production

### Performance Tips

1. **Use connection pooling** for high-traffic apps
2. **Implement caching** for frequently accessed data
3. **Add database indexes** for common queries
4. **Monitor Supabase usage** and optimize queries

### Environment-specific Configuration

```python
# config/supabase_client.py
import os

class SupabaseConfig:
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        if self.environment == "production":
            # Production-specific settings
            self.timeout = 30
            self.retry_attempts = 3
        else:
            # Development settings
            self.timeout = 10
            self.retry_attempts = 1
```

## 🆘 Troubleshooting

### Connection Issues
- Verify Supabase URL and keys
- Check network connectivity
- Ensure Supabase project is active

### Authentication Issues
- Verify JWT secret matches Supabase project
- Check token expiration
- Ensure proper Authorization header format

### RLS Issues
- Review RLS policies in Supabase Dashboard
- Test with service role to bypass RLS temporarily
- Check user authentication status

## 📚 Additional Resources

- [Supabase Documentation](https://supabase.com/docs)
- [supabase-py GitHub](https://github.com/supabase/supabase-py)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [Row Level Security Guide](https://supabase.com/docs/guides/auth/row-level-security) 