# MCP for Retriever - API Reference

## Overview

This document provides a comprehensive API reference for the MCP for Retriever system, including authentication endpoints, MCP tools, and data models.

## Authentication API (Gateway - Port 8000)

### Base URL
```
http://localhost:8000
```

### Endpoints

#### POST /auth/token
Authenticate user and receive JWT tokens.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "string"
}
```

**Status Codes:**
- `200 OK` - Authentication successful
- `401 Unauthorized` - Invalid credentials
- `422 Unprocessable Entity` - Validation error

#### POST /auth/refresh
Refresh access token using refresh token.

**Request Headers:**
```
Authorization: Bearer <refresh_token>
```

**Response:**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### GET /auth/me
Get current user information.

**Request Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "id": 1,
  "username": "string",
  "email": "user@example.com",
  "permissions": [
    {
      "tool_name": "search_web",
      "scopes": ["web:search"]
    }
  ]
}
```

## MCP Tools API (MCP Server - Port 8001)

### Authentication
All MCP tools require a valid JWT token in the Authorization header:
```
Authorization: Bearer <access_token>
```

### Available Tools

#### search_web
Search the web using Tavily API.

**Parameters:**
```typescript
{
  "query": string,      // Search query
  "limit": number       // Maximum results (default: 10, max: 100)
}
```

**Required Scopes:** `web:search`

**Response:**
```typescript
[
  {
    "title": string,
    "url": string,
    "content": string,
    "score": number,
    "published_date": string | null
  }
]
```

**Example:**
```json
{
  "query": "FastMCP documentation",
  "limit": 5
}
```

#### search_vectors
Search vector database for similar content.

**Parameters:**
```typescript
{
  "query": string,           // Search query
  "collection": string,      // Collection name
  "top_k": number,          // Number of results (default: 10)
  "filter": object | null   // Optional metadata filter
}
```

**Required Scopes:** `vector:search`

**Response:**
```typescript
[
  {
    "id": string,
    "score": number,
    "payload": {
      "content": string,
      "metadata": object
    }
  }
]
```

#### search_database
Search relational database.

**Parameters:**
```typescript
{
  "query": string,              // Search query
  "table": string,              // Table name
  "columns": string[],          // Columns to search
  "limit": number,              // Result limit (default: 10)
  "filters": object | null      // Additional SQL filters
}
```

**Required Scopes:** `db:read`

**Response:**
```typescript
[
  {
    "id": number,
    "data": object,
    "relevance_score": number
  }
]
```

#### search_all
Search across all available data sources.

**Parameters:**
```typescript
{
  "query": string,         // Search query
  "sources": string[],     // Sources to search ["web", "vector", "database"]
  "limit_per_source": number  // Results per source (default: 5)
}
```

**Required Scopes:** Depends on selected sources
- `web` requires `web:search`
- `vector` requires `vector:search`
- `database` requires `db:read`

**Response:**
```typescript
{
  "web": [...],      // Web search results
  "vector": [...],   // Vector search results
  "database": [...]  // Database search results
}
```

### Vector Database Operations

#### create_vector
Store a vector in the database.

**Parameters:**
```typescript
{
  "collection": string,     // Collection name
  "id": string,            // Vector ID
  "vector": number[],      // Embedding vector
  "payload": object        // Associated metadata
}
```

**Required Scopes:** `vector:write`

**Response:**
```typescript
{
  "id": string,
  "status": "created" | "updated"
}
```

#### delete_vector
Delete a vector from the database.

**Parameters:**
```typescript
{
  "collection": string,    // Collection name
  "id": string            // Vector ID
}
```

**Required Scopes:** `vector:write`

**Response:**
```typescript
{
  "id": string,
  "status": "deleted"
}
```

### Database Operations

#### execute_query
Execute a read-only SQL query.

**Parameters:**
```typescript
{
  "query": string,         // SQL query (SELECT only)
  "params": object | null  // Query parameters
}
```

**Required Scopes:** `db:read`

**Response:**
```typescript
{
  "columns": string[],
  "rows": any[][],
  "row_count": number
}
```

## Resources

### data://services/health
Get health status of all services.

**Response:**
```typescript
{
  "overall": "healthy" | "degraded" | "unhealthy",
  "services": {
    "web_search": {
      "healthy": boolean,
      "service_name": string,
      "details": object | null,
      "error": string | null
    },
    "vector_db": {...},
    "database": {...}
  }
}
```

### data://user/permissions
Get current user's permissions.

**Response:**
```typescript
{
  "user_id": string,
  "scopes": string[],
  "tools": {
    "tool_name": {
      "allowed": boolean,
      "scopes": string[]
    }
  }
}
```

## Data Models

### QueryResult
```typescript
interface QueryResult {
  id: string | number;
  content: string;
  metadata?: Record<string, any>;
  score?: number;
  source: "web" | "vector" | "database";
}
```

### RetrieverHealth
```typescript
interface RetrieverHealth {
  healthy: boolean;
  service_name: string;
  details?: Record<string, any>;
  error?: string;
}
```

### ToolPermission
```typescript
interface ToolPermission {
  tool_name: string;
  allowed: boolean;
  scopes: string[];
}
```

## Error Responses

All endpoints follow a consistent error response format:

```typescript
{
  "error": {
    "code": string,           // Error code (e.g., "AUTH_FAILED")
    "message": string,        // Human-readable message
    "details": object | null  // Additional error details
  }
}
```

### Common Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| `AUTH_REQUIRED` | No authentication token provided | 401 |
| `AUTH_INVALID` | Invalid or expired token | 401 |
| `PERMISSION_DENIED` | Insufficient permissions | 403 |
| `NOT_FOUND` | Resource not found | 404 |
| `VALIDATION_ERROR` | Invalid request parameters | 422 |
| `RATE_LIMITED` | Too many requests | 429 |
| `SERVICE_ERROR` | Internal service error | 500 |
| `SERVICE_UNAVAILABLE` | Service temporarily unavailable | 503 |

## Rate Limiting

API requests are rate-limited per user:

- **Authentication endpoints**: 10 requests per minute
- **Search operations**: 100 requests per minute
- **Write operations**: 50 requests per minute

Rate limit information is included in response headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## Pagination

For endpoints that return lists, pagination is supported:

**Query Parameters:**
- `offset`: Starting position (default: 0)
- `limit`: Number of results (default: 10, max: 100)

**Response Headers:**
```
X-Total-Count: 1234
X-Page-Count: 13
```

## WebSocket Support

Real-time updates are available via WebSocket:

**Endpoint:** `ws://localhost:8001/ws`

**Authentication:** Send token in first message:
```json
{
  "type": "auth",
  "token": "Bearer <access_token>"
}
```

**Subscribe to updates:**
```json
{
  "type": "subscribe",
  "channels": ["search_results", "health_status"]
}
```

## SDK Examples

### Python Client
```python
from mcp_retriever_client import MCPRetrieverClient

# Initialize client
client = MCPRetrieverClient(
    gateway_url="http://localhost:8000",
    username="user",
    password="pass"
)

# Search web
results = await client.search_web(
    query="FastMCP tutorial",
    limit=10
)

# Search across all sources
all_results = await client.search_all(
    query="Python async",
    sources=["web", "vector", "database"]
)
```

### JavaScript/TypeScript Client
```typescript
import { MCPRetrieverClient } from 'mcp-retriever-client';

// Initialize client
const client = new MCPRetrieverClient({
  gatewayUrl: 'http://localhost:8000',
  username: 'user',
  password: 'pass'
});

// Search vectors
const results = await client.searchVectors({
  query: 'machine learning',
  collection: 'documents',
  topK: 20
});
```

## Health Check Endpoints

### GET /health
Basic health check for gateway.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### GET /health/detailed
Detailed health check including dependencies.

**Response:**
```json
{
  "status": "ok",
  "services": {
    "database": "connected",
    "mcp_server": "connected",
    "cache": "connected"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

## Versioning

API versioning is handled through headers:

```
Accept: application/vnd.mcp-retriever.v1+json
```

Current version: `v1`

## OpenAPI Specification

OpenAPI 3.0 specification is available at:
- Gateway: `http://localhost:8000/openapi.json`
- MCP Server: `http://localhost:8001/openapi.json`