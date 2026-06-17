# Authentication

> **⚠️ Important Notice for Frontend Developers**
>
> This backend currently has **NO authentication or authorization implemented**. All API endpoints are publicly accessible with no tokens, sessions, or API keys required from the client side.
>
> This document describes: (a) the current state, (b) what authentication is present (LLM provider API keys are backend-only secrets), and (c) recommendations for adding authentication if needed.

---

## Table of Contents

1. [Current Authentication State](#1-current-authentication-state)
2. [LLM Provider API Key Handling (Backend-Only)](#2-llm-provider-api-key-handling-backend-only)
3. [CORS Configuration](#3-cors-configuration)
4. [Frontend Requirements (Current)](#4-frontend-requirements-current)
5. [Recommended Authentication Implementation](#5-recommended-authentication-implementation)

---

## 1. Current Authentication State

| Aspect | Status |
|--------|--------|
| User login / registration | ❌ Not implemented |
| JWT / session tokens | ❌ Not implemented |
| API key authentication | ❌ Not implemented for clients |
| OAuth2 / SSO | ❌ Not implemented |
| Role-based access control | ❌ Not implemented |
| Rate limiting | ❌ Not implemented |
| Request signing | ❌ Not implemented |

**All 7 REST endpoints are fully open with no authentication required.**

The backend relies on network-level security (it defaults to `127.0.0.1`, i.e., localhost-only). In its current form, it is intended for local development and trusted environments only.

---

## 2. LLM Provider API Key Handling (Backend-Only)

While there is no client authentication, the backend itself authenticates with external LLM provider APIs. These are **backend secrets** — they are never exposed to the frontend.

### How LLM API Keys Work

```
.env file (server-side only)
  │
  ▼ python-dotenv loads at startup
app/config.py → Settings object
  │
  ▼ app/llm/factory.py → get_llm_provider()
  │   Reads: settings.LLM_PROVIDER
  │   Validates: API key is set and not placeholder
  │   Raises ValueError if key is missing
  │
  ▼ LLM Provider SDK (AsyncGroq / AsyncCerebras / AsyncAnthropic)
      Sends API key as HTTP Bearer token to external LLM API
```

### Validation Logic (from `factory.py`)

The factory validates that the API key is:
1. Non-empty string
2. Not equal to the placeholder value (e.g., `"your_groq_api_key_here"`)

If validation fails, the provider initialization raises `ValueError` and the LLM will be `None`. In this case, `process_query()` returns:
```json
{
  "response": "LLM provider is not configured. Check your .env settings.",
  "tool_calls": []
}
```

### LLM Provider API Authentication Details

| Provider | Auth Mechanism | Key Variable | External Endpoint |
|----------|----------------|--------------|-------------------|
| Groq | HTTP Bearer Token | `GROQ_API_KEY` | `https://api.groq.com` |
| Cerebras | HTTP Bearer Token | `CEREBRAS_API_KEY` | `https://api.cerebras.ai` |
| Anthropic | `x-api-key` header | `ANTHROPIC_API_KEY` | `https://api.anthropic.com` |

**These keys are never returned in any API response and must never be included in frontend code.**

---

## 3. CORS Configuration

CORS is configured **fully open** in `app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This means:
- **Any origin** can make cross-origin requests (no `Origin` header restriction)
- **All HTTP methods** (GET, POST, PUT, DELETE, OPTIONS) are permitted
- **All request headers** are allowed
- **Credentials** (cookies, auth headers) are allowed (though none are currently used)

**Frontend implication:** No proxy setup is needed. Direct `fetch()` or `axios` calls from `http://localhost:3000` (or any port) to `http://localhost:8000` work out of the box.

---

## 4. Frontend Requirements (Current)

Since there is no authentication, the frontend needs **zero auth-related implementation** to call this backend:

```javascript
// Example: Direct API call from React — no token needed
const response = await fetch('http://127.0.0.1:8000/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ message: 'Find papers on transformers' })
});
const data = await response.json();
```

No headers such as `Authorization`, `X-API-Key`, or cookies are required.

---

## 5. Recommended Authentication Implementation

> **This section is informational only — none of the following exists in the codebase.**
>
> If the system needs to be secured (e.g., deployed publicly), here is the recommended approach.

### 5.1 Recommended: JWT Bearer Token Authentication

**Login Flow (to be implemented):**

```
1. User submits username + password to POST /auth/login
2. Backend validates credentials against a user store (database)
3. Backend generates a signed JWT:
   - Payload: { "sub": user_id, "roles": [...], "exp": timestamp }
   - Signed with: HS256 or RS256 secret
4. Frontend stores JWT in memory (preferred) or localStorage
5. Frontend includes JWT in subsequent requests:
   Authorization: Bearer <token>
6. Backend middleware validates JWT on every protected endpoint
```

**Token Validation (to be implemented):**

```python
# Pseudocode — not in current codebase
from fastapi.security import HTTPBearer
from jose import jwt

security = HTTPBearer()

async def verify_token(credentials = Depends(security)):
    token = credentials.credentials
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return payload["sub"]  # user_id
```

### 5.2 Authorization Roles (Recommended Design)

| Role | Permissions |
|------|------------|
| `viewer` | `GET /api/tools`, `GET /api/prompts`, `GET /api/resources`, `GET /api/resources/read` |
| `researcher` | All viewer permissions + `POST /api/chat`, `POST /api/prompts/execute` |
| `admin` | All permissions + LLM provider reconfiguration |

### 5.3 Frontend Requirements After Auth is Added

If authentication is implemented, the frontend would need:

1. **Login page** — collects username/password, calls `POST /auth/login`
2. **Token storage** — stores JWT in `localStorage` or `sessionStorage` (or memory for security)
3. **Axios interceptor / fetch wrapper** — automatically appends `Authorization: Bearer <token>` to every request
4. **Token refresh** — handles 401 responses by refreshing the token or redirecting to login
5. **Protected routes** — wraps routes that require authentication with a guard component
6. **Logout** — clears stored token and redirects to login page

**Example Axios interceptor (for future use):**

```javascript
axios.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

axios.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      // Token expired — redirect to login
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### 5.4 State Management for Auth (Recommended)

```
AuthContext (React Context or Zustand store)
├── user: { id, email, roles } | null
├── token: string | null
├── isAuthenticated: boolean
├── login(credentials) → Promise<void>
├── logout() → void
└── isLoading: boolean
```
