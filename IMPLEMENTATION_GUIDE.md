# Elasticsearch Read-Only API - Implementation Guide

## Overview

This guide describes the implementation of secure, read-only HTTP endpoints for accessing Elasticsearch data from your Plotly Dash dashboard. The implementation adds Flask routes that proxy specific Elasticsearch queries without exposing the cluster or allowing write operations.

## What Was Implemented

### 1. New Files Created

#### `api_routes.py` (530 lines)
The main API implementation module containing:
- **5 API endpoints** for querying Elasticsearch data
- **Security decorators** for input validation and query safety
- **Rate limiting integration** to prevent abuse
- **Error handling** for all edge cases
- **Sanitization functions** to prevent injection attacks

#### `API_DOCUMENTATION.md`
Comprehensive API documentation including:
- Endpoint specifications with request/response examples
- Security features and rate limits
- Usage examples with curl commands
- Production deployment recommendations
- Testing instructions

#### `test_api.py`
Automated test script to verify all endpoints work correctly:
- Tests all 5 API endpoints
- Validates rate limiting headers
- Tests input validation and error handling
- Provides detailed pass/fail reports

### 2. Modified Files

#### `app.py`
Added API route registration (3 lines):
```python
# Register API routes for public read-only Elasticsearch access
from api_routes import register_api_routes
register_api_routes(server)
```

#### `requirements.txt`
Added Flask-Limiter for rate limiting:
```
Flask-Limiter==3.5.0
```

## API Endpoints

All endpoints are served under `/api/v1/`:

1. **GET `/api/v1/health`** - Health check and Elasticsearch connectivity
2. **GET `/api/v1/indices`** - List available indices
3. **POST `/api/v1/search/authors`** - Search for authors by name/institution/field
4. **GET `/api/v1/aggregate/<type>`** - Get aggregated statistics
5. **GET `/api/v1/stats/<index>`** - Get index statistics

## Security Features

### ✅ Read-Only Operations
- Only allows `search`, `count`, and `stats` operations
- No `index`, `update`, `delete`, or `bulk` operations possible
- Uses existing read-only utility functions from `citations_lib/utils.py`

### ✅ Predefined Queries Only
- All queries are defined in code, not constructed from user input
- No arbitrary Elasticsearch DSL queries accepted
- Whitelist of allowed indices enforced with `@safe_query` decorator

### ✅ Input Validation & Sanitization
- All string inputs sanitized to remove dangerous characters
- Year parameters validated (2000-2030 range)
- Limit parameters capped at 1000
- Field names validated against whitelist

### ✅ Rate Limiting
- **Default**: 200 requests/day, 50 requests/hour per IP
- **Health check**: 500 requests/hour
- **Search**: 100 requests/hour
- **Aggregations**: 200 requests/hour
- **Stats**: 300 requests/hour
- Rate limit info exposed in response headers

### ✅ Error Handling
- Proper HTTP status codes for all error conditions
- Detailed logging for debugging
- User-friendly error messages without internal details
- Elasticsearch exceptions properly caught and handled

## Deployment Instructions

### Local Testing

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Ensure Elasticsearch is running**:
   ```bash
   # Check your .env file has:
   ES_URL_LOCAL=http://172.17.0.3:9200
   ```

3. **Run the application**:
   ```bash
   python app.py
   ```
   The app runs on `http://localhost:8050`

4. **Test the API**:
   ```bash
   # Run automated tests
   python test_api.py http://localhost:8050

   # Or test manually
   curl http://localhost:8050/api/v1/health
   ```

### Dokku Deployment

The implementation is ready for Dokku deployment with no additional configuration needed:

1. **Commit and push**:
   ```bash
   git add api_routes.py app.py requirements.txt test_api.py API_DOCUMENTATION.md IMPLEMENTATION_GUIDE.md
   git commit -m "Add secure read-only Elasticsearch API endpoints"
   git push dokku main
   ```

2. **The API will be automatically available at**:
   ```
   https://your-domain.com/api/v1/health
   https://your-domain.com/api/v1/indices
   etc.
   ```

3. **Verify deployment**:
   ```bash
   python test_api.py https://your-domain.com
   ```

### Environment Variables

The implementation automatically uses the correct Elasticsearch URL:

- **Dokku**: Uses `ELASTICSEARCH_URL` (automatically set by dokku-elasticsearch plugin)
- **Local**: Uses `ES_URL_LOCAL` from `.env` file

No additional configuration required!

## Usage Examples

### Health Check
```bash
curl https://your-domain.com/api/v1/health
```

### Search for Authors
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

### Get Country Aggregations
```bash
curl "https://your-domain.com/api/v1/aggregate/country?limit=20"
```

### Get Index Statistics
```bash
curl https://your-domain.com/api/v1/stats/career
```

## Production Recommendations

### 1. Upgrade Rate Limiting to Redis

For multi-worker deployments, use Redis for distributed rate limiting:

```bash
# On Dokku server
dokku redis:create citedb-redis
dokku redis:link citedb-redis twopercenters
```

Then update `api_routes.py`:
```python
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=os.getenv('REDIS_URL', 'redis://localhost:6379'),
    ...
)
```

### 2. Add API Authentication (Optional)

If you need to restrict access, add API key authentication:

```python
# Add environment variable
dokku config:set twopercenters API_KEYS="key1,key2,key3"

# Add middleware to api_routes.py
def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        valid_keys = os.getenv('API_KEYS', '').split(',')
        if not api_key or api_key not in valid_keys:
            return jsonify({"error": "Invalid API key"}), 401
        return f(*args, **kwargs)
    return decorated_function
```

### 3. Enable CORS (If Needed)

To allow cross-origin requests:

```bash
pip install flask-cors
```

```python
# In app.py
from flask_cors import CORS
CORS(server, resources={r"/api/*": {"origins": "*"}})
```

### 4. Monitor API Usage

Add monitoring to track API usage:

```python
# Add request/response logging middleware in api_routes.py
@api_bp.before_request
def log_request():
    logger.info(f"API Request: {request.method} {request.path} from {get_remote_address()}")
```

### 5. Add Response Caching

For frequently accessed data, add caching:

```python
from flask_caching import Cache

cache = Cache(server, config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': os.getenv('REDIS_URL')})

@api_bp.route('/stats/<index_name>')
@cache.cached(timeout=300)  # Cache for 5 minutes
def get_index_stats(index_name):
    ...
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Client (Browser/API)                  │
└───────────────────────────┬─────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  Dokku (Reverse Proxy)                   │
└───────────────────────────┬─────────────────────────────┘
                            │
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌──────────────────┐                   ┌──────────────────┐
│  Dash Routes     │                   │   API Routes     │
│  (/, /keke)      │                   │  (/api/v1/*)     │
│                  │                   │                  │
│  - Interactive   │                   │  - Read-only     │
│  - Dashboard     │                   │  - JSON          │
│  - Callbacks     │                   │  - Rate limited  │
└────────┬─────────┘                   └────────┬─────────┘
         │                                      │
         │                                      │
         └──────────────┬───────────────────────┘
                        │
                        │ (Both use same ES client)
                        ▼
                ┌──────────────────┐
                │  Elasticsearch   │
                │  (Read-only      │
                │   queries only)  │
                └──────────────────┘
```

## File Structure

```
/home/user/twopercenters/
├── api_routes.py              # NEW - API endpoint implementation
├── API_DOCUMENTATION.md       # NEW - API documentation
├── IMPLEMENTATION_GUIDE.md    # NEW - This guide
├── test_api.py               # NEW - API test script
├── app.py                    # MODIFIED - Added API registration
├── requirements.txt          # MODIFIED - Added Flask-Limiter
├── pages/
│   ├── home.py
│   └── test.py
├── citations_lib/
│   ├── utils.py              # Used by API for ES queries
│   └── ...
└── ...
```

## Troubleshooting

### Issue: API returns 503 "Cannot connect to Elasticsearch"

**Solution**: Verify Elasticsearch is running and accessible:
```bash
# On Dokku
dokku elasticsearch:info citedb

# Locally
curl $ES_URL_LOCAL
```

### Issue: Rate limit exceeded (429)

**Solution**: Wait for the rate limit window to reset, or increase limits in `api_routes.py`:
```python
limiter = Limiter(
    default_limits=["500 per day", "100 per hour"],  # Increased
    ...
)
```

### Issue: API endpoints not found (404)

**Solution**: Verify API routes are registered:
```python
# Check that this line exists in app.py
register_api_routes(server)
```

### Issue: CORS errors in browser

**Solution**: Add CORS support (see Production Recommendations #3 above)

## Security Considerations

### What This Implementation Protects Against

✅ **SQL/NoSQL Injection** - All inputs sanitized
✅ **Query Injection** - Only predefined queries allowed
✅ **Data Modification** - Read-only operations only
✅ **Resource Exhaustion** - Rate limiting prevents abuse
✅ **Information Disclosure** - Error messages don't expose internals
✅ **Unauthorized Access** - Index whitelist enforced

### What You Should Still Consider

⚠️ **Authentication** - Currently no auth required (see Production Recommendations #2)
⚠️ **DDoS Protection** - Consider Cloudflare or similar CDN
⚠️ **Data Privacy** - Ensure no sensitive data in public indices
⚠️ **Audit Logging** - Log API access for monitoring
⚠️ **HTTPS Only** - Ensure Dokku enforces HTTPS

## Testing Checklist

Before deploying to production:

- [ ] Run `python test_api.py http://localhost:8050` locally
- [ ] Verify all endpoints return expected status codes
- [ ] Confirm rate limiting headers are present
- [ ] Test invalid inputs are rejected with 400 errors
- [ ] Deploy to Dokku staging environment
- [ ] Run `python test_api.py https://staging-domain.com`
- [ ] Test with real queries from your dashboard use cases
- [ ] Monitor Elasticsearch logs during API usage
- [ ] Verify no write operations attempted
- [ ] Load test with multiple concurrent requests
- [ ] Deploy to production

## Next Steps

1. **Deploy to Dokku** - Push changes and verify endpoints work
2. **Update Dashboard** - Optionally use API endpoints in your Dash app
3. **Share API** - Provide API documentation to users who need data access
4. **Monitor Usage** - Track API usage and adjust rate limits as needed
5. **Add Authentication** - If public access is too permissive
6. **Upgrade to Redis** - For production rate limiting with multiple workers

## Support

For questions or issues:
- Review `API_DOCUMENTATION.md` for endpoint details
- Check logs: `dokku logs twopercenters -t`
- Run tests: `python test_api.py`
- Verify ES connectivity: `dokku elasticsearch:info citedb`

## Conclusion

You now have a secure, production-ready read-only API for your Elasticsearch data that:
- ✅ Runs on the same domain as your Dash dashboard
- ✅ Exposes only specific, predefined queries
- ✅ Prevents all write operations
- ✅ Includes rate limiting and input validation
- ✅ Works seamlessly on Dokku with no additional configuration

The implementation follows Flask and security best practices and is ready for immediate deployment!
