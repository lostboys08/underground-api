# BlueStakes Credentials API Documentation

## Overview

The credentials API provides endpoints for testing and storing BlueStakes credentials with built-in validation and frontend-friendly responses.

## Endpoints

### 1. Test Credentials (Validation Only)

**Endpoint:** `POST /tickets/test-credentials`

**Purpose:** Test BlueStakes credentials without storing them. Useful for frontend validation.

**Parameters:**
- `username` (query, required): BlueStakes username
- `password` (query, required): BlueStakes password

**Example Request:**
```bash
curl -X POST "http://localhost:8000/tickets/test-credentials?username=myuser&password=mypass" \
  -H "X-API-Key: your-api-key"
```

**Response Format:**
```typescript
interface CredentialsTestResponse {
  success: boolean;
  message: string;
  data: {
    company_id: number;        // Always 0 for test-only
    username: string;
    credentials_tested: boolean;
    credentials_valid: boolean;
    credentials_stored: boolean; // Always false for test-only
    test_error: string | null;
    storage_error: string | null;
    company_name?: string;
  };
  error: string | null;
}
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "BlueStakes credentials are valid",
  "data": {
    "company_id": 0,
    "username": "myuser",
    "credentials_tested": true,
    "credentials_valid": true,
    "credentials_stored": false,
    "test_error": null,
    "storage_error": null
  },
  "error": null
}
```

**Invalid Credentials (401):**
```json
{
  "success": false,
  "message": "BlueStakes credentials are invalid - please check username and password",
  "data": {
    "company_id": 0,
    "username": "myuser",
    "credentials_tested": true,
    "credentials_valid": false,
    "credentials_stored": false,
    "test_error": "Authentication failed with status 401",
    "storage_error": null
  },
  "error": "INVALID_CREDENTIALS"
}
```

### 2. Store Credentials (Test + Store)

**Endpoint:** `POST /tickets/store-credentials/{company_id}`

**Purpose:** Test credentials and store them if valid. Encrypts passwords before storage.

**Parameters:**
- `company_id` (path, required): Company ID to store credentials for
- `username` (query, required): BlueStakes username
- `password` (query, required): BlueStakes password

**Example Request:**
```bash
curl -X POST "http://localhost:8000/tickets/store-credentials/1?username=myuser&password=mypass" \
  -H "X-API-Key: your-api-key"
```

**Success Response (200):**
```json
{
  "success": true,
  "message": "BlueStakes credentials successfully tested and stored for Company Name",
  "data": {
    "company_id": 1,
    "username": "myuser",
    "credentials_tested": true,
    "credentials_valid": true,
    "credentials_stored": true,
    "test_error": null,
    "storage_error": null,
    "company_name": "Company Name"
  },
  "error": null
}
```

## Error Codes

The API uses structured error codes that your frontend can handle programmatically:

| Error Code | HTTP Status | Description | Frontend Action |
|------------|-------------|-------------|-----------------|
| `USERNAME_PASSWORD_REQUIRED` | 400 | Missing username or password | Show validation error |
| `COMPANY_NOT_FOUND` | 404 | Company ID doesn't exist | Show "Company not found" |
| `INVALID_CREDENTIALS` | 401 | BlueStakes rejected credentials | Show "Invalid credentials" |
| `AUTHENTICATION_ERROR` | 503 | BlueStakes API unavailable | Show "Service unavailable" |
| `ENCRYPTION_ERROR` | 500 | Server encryption issue | Show "Server error" |
| `STORAGE_ERROR` | 500 | Database storage failed | Show "Storage error" |
| `UNEXPECTED_ERROR` | 500 | Unexpected server error | Show generic error |

## Frontend Integration Examples

### React/TypeScript Example

```typescript
interface CredentialsFormData {
  username: string;
  password: string;
}

interface CredentialsResponse {
  success: boolean;
  message: string;
  data: {
    company_id: number;
    username: string;
    credentials_tested: boolean;
    credentials_valid: boolean;
    credentials_stored: boolean;
    test_error: string | null;
    storage_error: string | null;
    company_name?: string;
  };
  error: string | null;
}

// Test credentials without storing
async function testCredentials(credentials: CredentialsFormData): Promise<CredentialsResponse> {
  const params = new URLSearchParams({
    username: credentials.username,
    password: credentials.password
  });
  
  const response = await fetch(`/api/tickets/test-credentials?${params}`, {
    method: 'POST',
    headers: {
      'X-API-Key': process.env.NEXT_PUBLIC_API_KEY!
    }
  });
  
  return await response.json();
}

// Store credentials (test + store)
async function storeCredentials(
  companyId: number, 
  credentials: CredentialsFormData
): Promise<CredentialsResponse> {
  const params = new URLSearchParams({
    username: credentials.username,
    password: credentials.password
  });
  
  const response = await fetch(`/api/tickets/store-credentials/${companyId}?${params}`, {
    method: 'POST',
    headers: {
      'X-API-Key': process.env.NEXT_PUBLIC_API_KEY!
    }
  });
  
  return await response.json();
}

// Usage in component
function CredentialsForm({ companyId }: { companyId: number }) {
  const [credentials, setCredentials] = useState<CredentialsFormData>({
    username: '',
    password: ''
  });
  const [isValidating, setIsValidating] = useState(false);
  const [validationResult, setValidationResult] = useState<CredentialsResponse | null>(null);

  const handleTest = async () => {
    setIsValidating(true);
    try {
      const result = await testCredentials(credentials);
      setValidationResult(result);
      
      if (result.success) {
        // Show success message
        console.log('Credentials are valid!');
      } else {
        // Handle specific error types
        switch (result.error) {
          case 'INVALID_CREDENTIALS':
            console.error('Invalid username or password');
            break;
          case 'AUTHENTICATION_ERROR':
            console.error('BlueStakes service unavailable');
            break;
          default:
            console.error('Validation failed:', result.message);
        }
      }
    } catch (error) {
      console.error('Network error:', error);
    } finally {
      setIsValidating(false);
    }
  };

  const handleStore = async () => {
    // First test, then store if valid
    const testResult = await testCredentials(credentials);
    
    if (testResult.success) {
      const storeResult = await storeCredentials(companyId, credentials);
      
      if (storeResult.success) {
        console.log('Credentials stored successfully!');
      } else {
        console.error('Storage failed:', storeResult.message);
      }
    }
  };

  return (
    <form>
      <input
        type="text"
        placeholder="Username"
        value={credentials.username}
        onChange={(e) => setCredentials(prev => ({ ...prev, username: e.target.value }))}
      />
      <input
        type="password"
        placeholder="Password"
        value={credentials.password}
        onChange={(e) => setCredentials(prev => ({ ...prev, password: e.target.value }))}
      />
      
      <button type="button" onClick={handleTest} disabled={isValidating}>
        {isValidating ? 'Testing...' : 'Test Credentials'}
      </button>
      
      <button 
        type="button" 
        onClick={handleStore} 
        disabled={!validationResult?.success}
      >
        Store Credentials
      </button>
      
      {validationResult && (
        <div className={validationResult.success ? 'success' : 'error'}>
          {validationResult.message}
        </div>
      )}
    </form>
  );
}
```

## Security Features

1. **Credential Validation:** All credentials are tested against BlueStakes API before storage
2. **Password Encryption:** Passwords are encrypted using Fernet encryption before database storage
3. **Error Handling:** Comprehensive error handling with user-friendly messages
4. **API Key Protection:** All endpoints require valid API key authentication
5. **Structured Responses:** Consistent response format for easy frontend handling

## Best Practices

1. **Test First:** Use `/test-credentials` for real-time validation during form input
2. **Handle Errors:** Check `error` field and handle specific error codes appropriately
3. **Show Progress:** Use loading states during API calls (credentials testing can take 2-3 seconds)
4. **Secure Storage:** Never log or store passwords in frontend code
5. **User Feedback:** Provide clear feedback for each step of the validation process

## Rate Limiting Considerations

- BlueStakes API has rate limits
- Avoid rapid successive calls to test endpoints
- Consider debouncing validation calls in forms
- Cache validation results temporarily to avoid redundant calls
