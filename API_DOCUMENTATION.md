# Elasticsearch Read-Only API Documentation

## Overview

This API provides secure, read-only access to the 2%ers citation analytics Elasticsearch data. The API is served under the same domain as the Plotly Dash dashboard and exposes specific, predefined queries without allowing arbitrary queries or write operations.

**Base URL**: `https://your-domain.com/api/v1`

## Security Features

✅ **Read-only operations** - No index, update, or delete operations allowed
✅ **Predefined queries only** - No arbitrary Elasticsearch queries accepted
✅ **Input validation** - All parameters are sanitized and validated
✅ **Rate limiting** - Prevents abuse with per-IP limits
✅ **No direct cluster exposure** - Elasticsearch is only accessible through controlled endpoints
✅ **Error handling** - Detailed error messages without exposing internal details

## Rate Limits

The API implements the following rate limits per IP address:

- **Default**: 200 requests/day, 50 requests/hour
- **Health check**: 500 requests/hour
- **Index stats**: 300 requests/hour
- **Aggregations**: 200 requests/hour
- **Search**: 100 requests/hour

Rate limit information is included in response headers:
- `X-RateLimit-Limit` - Request limit per time window
- `X-RateLimit-Remaining` - Remaining requests in current window
- `X-RateLimit-Reset` - Time when the rate limit resets

## Authentication

Currently, the API does not require authentication. All endpoints are publicly accessible within the rate limits. For production deployments requiring authentication, consider adding API key or OAuth2 authentication.

## Available Indices

The following Elasticsearch indices are available:

| Index | Description |
|-------|-------------|
| `career` | Career-wide author citation data |
| `singleyr` | Single-year author citation data |
| `career_cntry` | Career-wide country aggregations |
| `singleyr_cntry` | Single-year country aggregations |
| `career_field` | Career-wide field aggregations |
| `singleyr_field` | Single-year field aggregations |
| `career_inst` | Career-wide institution aggregations |
| `singleyr_inst` | Single-year institution aggregations |

---

## Endpoints

### 1. Health Check

Check API and Elasticsearch connectivity status.

**Endpoint**: `GET /api/v1/health`

**Rate Limit**: 500 requests/hour

**Response**:
```json
{
  "status": "healthy",
  "elasticsearch": {
    "connected": true,
    "cluster_name": "citedb",
    "status": "green"
  }
}
```

**Example**:
```bash
curl https://your-domain.com/api/v1/health
```

---

### 2. List Indices

Get a list of available Elasticsearch indices.

**Endpoint**: `GET /api/v1/indices`

**Rate Limit**: 50 requests/hour (default)

**Response**:
```json
{
  "indices": [
    "career",
    "singleyr",
    "career_cntry",
    "singleyr_cntry",
    "career_field",
    "singleyr_field",
    "career_inst",
    "singleyr_inst"
  ],
  "description": {
    "career": "Career-wide author data",
    "singleyr": "Single-year author data",
    ...
  }
}
```

**Example**:
```bash
curl https://your-domain.com/api/v1/indices
```

---

### 3. Search Authors

Search for authors by name, institution, or field.

**Endpoint**: `POST /api/v1/search/authors`

**Rate Limit**: 100 requests/hour

**Content-Type**: `application/json`

**Request Body**:
```json
{
  "query": "search term",
  "index": "career",
  "field": "authfull",
  "year": 2021,
  "limit": 100
}
```

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search term (max 200 chars, sanitized) |
| `index` | string | Yes | Index to search (`career` or `singleyr`) |
| `field` | string | Yes | Field to search (`authfull`, `inst_name`, or `sm-field`) |
| `year` | integer | No | Year filter for singleyr index (2000-2030) |
| `limit` | integer | No | Max results to return (default: 100, max: 1000) |

**Response**:
```json
{
  "query": "Einstein",
  "index": "career",
  "field": "authfull",
  "count": 15,
  "results": [
    {
      "authid": "12345",
      "authfull": "Albert Einstein",
      "inst_name": "Princeton University",
      "sm-field": "Physics",
      "Author_Data": {
        "h_index": 95,
        "citations": 125000,
        ...
      }
    },
    ...
  ]
}
```

**Example**:
```bash
curl -X POST https://your-domain.com/api/v1/search/authors \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Einstein",
    "index": "career",
    "field": "authfull",
    "limit": 10
  }'
```

**Error Responses**:

- `400 Bad Request` - Invalid parameters or missing required fields
- `500 Internal Server Error` - Elasticsearch query failed

---

### 4. Get Aggregations

Retrieve aggregated statistics by country, field, or institution.

**Endpoint**: `GET /api/v1/aggregate/<type>`

**Rate Limit**: 200 requests/hour

**Path Parameters**:

| Parameter | Type | Values | Description |
|-----------|------|--------|-------------|
| `type` | string | `country`, `field`, `institution` | Aggregation type |

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `year` | integer | No | Year for single-year aggregations (2000-2030) |
| `limit` | integer | No | Max results (default: 100, max: 1000) |

**Response**:
```json
{
  "aggregation_type": "country",
  "index": "career_cntry",
  "year": null,
  "count": 50,
  "results": [
    {
      "country": "United States",
      "author_count": 15234,
      "avg_h_index": 45.2,
      "total_citations": 12500000,
      ...
    },
    ...
  ]
}
```

**Examples**:

Get career-wide country aggregations:
```bash
curl https://your-domain.com/api/v1/aggregate/country
```

Get single-year field aggregations:
```bash
curl https://your-domain.com/api/v1/aggregate/field?year=2021&limit=50
```

Get institution aggregations with limit:
```bash
curl "https://your-domain.com/api/v1/aggregate/institution?limit=20"
```

**Error Responses**:

- `400 Bad Request` - Invalid aggregation type or parameters
- `403 Forbidden` - Requested index not allowed
- `500 Internal Server Error` - Aggregation query failed

---

### 5. Index Statistics

Get basic statistics about an Elasticsearch index.

**Endpoint**: `GET /api/v1/stats/<index_name>`

**Rate Limit**: 300 requests/hour

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `index_name` | string | Name of the index (from available indices) |

**Response**:
```json
{
  "index": "career",
  "document_count": 156789,
  "size_mb": 1234.56,
  "status": "available"
}
```

**Example**:
```bash
curl https://your-domain.com/api/v1/stats/career
```

**Error Responses**:

- `400 Bad Request` - Invalid index name
- `500 Internal Server Error` - Failed to retrieve statistics

---

## Error Handling

All error responses follow this format:

```json
{
  "error": "Error message description"
}
```

Common HTTP status codes:

- `400` - Bad Request (invalid parameters)
- `403` - Forbidden (unauthorized access to resource)
- `404` - Not Found (endpoint doesn't exist)
- `405` - Method Not Allowed (wrong HTTP method)
- `429` - Too Many Requests (rate limit exceeded)
- `500` - Internal Server Error (server-side error)
- `503` - Service Unavailable (Elasticsearch unavailable)

---

## Best Practices

1. **Cache responses** - Results don't change frequently, implement client-side caching
2. **Respect rate limits** - Monitor `X-RateLimit-*` headers and back off if needed
3. **Use specific queries** - Request only the data you need with appropriate `limit` parameters
4. **Handle errors gracefully** - Implement retry logic with exponential backoff for 5xx errors
5. **Sanitize inputs** - Even though the API validates inputs, sanitize on the client side too

---

## Production Deployment Recommendations

### Rate Limiting with Redis

For production deployments with multiple workers, use Redis for rate limiting:

```python
# In api_routes.py register_api_routes():
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv('REDIS_URL', 'redis://localhost:6379'),
    strategy="fixed-window",
    headers_enabled=True
)
```

### API Authentication

For authenticated access, add API key middleware:

```python
# Add to api_routes.py
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key not in VALID_API_KEYS:
            return jsonify({"error": "Invalid or missing API key"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Apply to endpoints:
@api_bp.route('/search/authors', methods=['POST'])
@require_api_key
@validate_json
def search_authors():
    ...
```

### CORS Configuration

If the API needs to be accessed from other domains:

```python
# In app.py
from flask_cors import CORS

# After creating the Flask server
CORS(server, resources={r"/api/*": {"origins": ["https://trusted-domain.com"]}})
```

### HTTPS Only

Ensure your Dokku deployment forces HTTPS:

```bash
dokku letsencrypt:enable twopercenters
dokku config:set twopercenters FORCE_HTTPS=true
```

### Monitoring and Logging

Add application monitoring:

```python
# Add to api_routes.py
import time
from flask import g

@api_bp.before_request
def before_request():
    g.start_time = time.time()

@api_bp.after_request
def after_request(response):
    if hasattr(g, 'start_time'):
        elapsed = time.time() - g.start_time
        logger.info(f"{request.method} {request.path} - {response.status_code} - {elapsed:.3f}s")
    return response
```

---

## Testing the API

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export ES_URL_LOCAL=http://localhost:9200
```

3. Run the app:
```bash
python app.py
```

4. Test endpoints:
```bash
# Health check
curl http://localhost:8050/api/v1/health

# List indices
curl http://localhost:8050/api/v1/indices

# Search authors
curl -X POST http://localhost:8050/api/v1/search/authors \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "index": "career", "field": "authfull"}'
```

### Dokku Deployment

After deploying to Dokku:

```bash
# The API will be available at:
https://your-domain.com/api/v1/health
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-repo/issues
- Email: your-email@example.com

---

## License

This API is part of the 2%ers citation analytics project. See LICENSE file for details.
