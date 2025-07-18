# Supabase Integration Setup Guide

This guide walks you through setting up Supabase with your existing FastAPI application and project management schema.

## 📋 Prerequisites

- Python 3.8+
- Existing Supabase project with your schema already set up
- Environment variables configured

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

# Encryption key for stored passwords (set this in production!)
ENCRYPTION_KEY=your-secure-encryption-key-here
```

**Where to find these values:**
1. Go to your Supabase Dashboard
2. Navigate to **Settings** → **API**
3. Copy the values:
   - **URL** → `SUPABASE_URL`
   - **anon/public key** → `SUPABASE_ANON_KEY`  
   - **service_role key** → `SUPABASE_SERVICE_ROLE_KEY`
   - **JWT Secret** → `SUPABASE_JWT_SECRET`

### 3. Schema Overview

Your existing Supabase schema includes:

```sql
-- Main entities
companies          # Business entities with Bluestakes credentials
profiles           # User profiles linked to auth.users
projects           # Projects belonging to companies  
project_tickets    # Tickets within projects

-- Junction tables
company_projects   # Many-to-many: companies ↔ projects
user_projects     # User assignments to projects
```

## 🏗️ Architecture Overview

### Database Schema

**Companies Table:**
- Store company information and encrypted Bluestakes credentials
- Used for PDF generation with stored credentials

**Profiles Table:**
- Linked to Supabase Auth users via `user_id` (UUID)
- Contains user roles and company assignments

**Projects & Tickets:**
- Hierarchical project management system
- Tickets are assigned to users and tracked within projects

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
│   ├── profiles.py           # User profile management
│   ├── companies.py          # Company & credentials management
│   └── pdf_generator.py      # Enhanced PDF with stored credentials
├── utils/
│   └── auth.py               # JWT verification utilities
└── main.py                   # FastAPI app with all routers
```

## 🔌 API Endpoints

### User Profile Management (`/profiles`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/profiles/` | Create user profile | ❌ |
| GET | `/profiles/{id}` | Get profile by ID | ❌ |
| GET | `/profiles/` | List profiles (filtered) | ❌ |
| PUT | `/profiles/{id}` | Update profile | ❌ |
| DELETE | `/profiles/{id}` | Delete profile | ❌ |
| GET | `/profiles/me/profile` | Get my profile | ✅ JWT |
| PUT | `/profiles/me/profile` | Update my profile | ✅ JWT |
| GET | `/profiles/by-user/{user_id}` | Get profile by user_id | ❌ |

### Company Management (`/companies`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/companies/` | Create company | ❌ |
| GET | `/companies/{id}` | Get company | ❌ |
| GET | `/companies/` | List companies | ❌ |
| PUT | `/companies/{id}` | Update company | ❌ |
| DELETE | `/companies/{id}` | Delete company | ❌ |
| GET | `/companies/{id}/bluestakes-credentials` | Get stored credentials | ✅ JWT |

### Enhanced PDF Generation (`/pdf`)

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/pdf/generate` | Generate ticket PDF | ❌ |

**PDF Generation Options:**
- **Option 1:** Use stored company credentials: `?ticket=123&company_id=1`
- **Option 2:** Provide credentials directly: `?ticket=123&username=user&password=pass`

## 🔐 Security Features

### Password Encryption

Bluestakes passwords are encrypted using Fernet symmetric encryption:

```python
from cryptography.fernet import Fernet

# Passwords are automatically encrypted when stored
company = CompanyCreate(
    name="My Company",
    bluestakes_username="myuser", 
    bluestakes_password="mypass"  # This gets encrypted
)
```

### Access Control

- **Company credentials** are only accessible to:
  - Users belonging to that company
  - Users with admin role
- **JWT authentication** required for sensitive operations
- **Row Level Security** policies enforce data isolation

## 📊 Usage Examples

### Create a Company with Bluestakes Credentials

```bash
curl -X POST "http://localhost:8000/companies/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Construction Co",
    "bluestakes_username": "company_user",
    "bluestakes_password": "secure_password",
    "address": "123 Main St",
    "city": "Anytown",
    "state": "CA",
    "zip": "12345"
  }'
```

### Generate PDF using Stored Credentials

```bash
# Using company stored credentials (recommended)
curl "http://localhost:8000/pdf/generate?ticket=12345&company_id=1"

# Using provided credentials
curl "http://localhost:8000/pdf/generate?ticket=12345&username=user&password=pass"
```

### Get Current User Profile

```bash
curl -X GET "http://localhost:8000/profiles/me/profile" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### List Profiles by Company

```bash
curl "http://localhost:8000/profiles/?company_id=1&limit=20"
```

## 🛡️ Production Security

### Environment Variables

**Required for Production:**
```env
ENCRYPTION_KEY=your-very-secure-32-character-key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

### Best Practices

1. **Set a strong encryption key** (32+ characters)
2. **Use HTTPS** in production
3. **Implement proper RLS policies** in Supabase
4. **Monitor access** to credential endpoints
5. **Rotate encryption keys** periodically
6. **Use environment-specific configurations**

## 🔧 Advanced Features

### Bulk Operations

The API supports:
- Filtering profiles by company and role
- Pagination on all list endpoints
- Efficient joins with company data

### Integration Patterns

**PDF Generation Workflow:**
1. User selects a company (with stored credentials)
2. API automatically retrieves and decrypts credentials
3. Generates PDF with Bluestakes data
4. No need to enter credentials manually

**Multi-tenant Architecture:**
- Companies are isolated data containers
- Users belong to companies
- Projects are scoped to companies
- Tickets are scoped to projects

## 🆘 Troubleshooting

### Encryption Issues

```python
# Test encryption/decryption
from routes.companies import encrypt_password, decrypt_password

encrypted = encrypt_password("test_password")
decrypted = decrypt_password(encrypted)
print(f"Encryption working: {decrypted == 'test_password'}")
```

### Database Connection

```python
from config.supabase_client import supabase_service

# Test connection
result = supabase_service.table("companies").select("count").execute()
print(f"Companies count: {len(result.data)}")
```

### Authentication Issues

- Verify JWT secret matches your Supabase project
- Check user profile exists and has company assignment
- Ensure proper Authorization header format: `Bearer <token>`

## 📚 Additional Resources

- [Supabase RLS Documentation](https://supabase.com/docs/guides/auth/row-level-security)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Cryptography Library](https://cryptography.io/en/latest/)
- [Python-JOSE JWT](https://python-jose.readthedocs.io/) 