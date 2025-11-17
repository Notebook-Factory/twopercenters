"""
Secure read-only Elasticsearch API endpoints for public data access.

This module provides Flask routes that expose specific, predefined Elasticsearch
queries without allowing arbitrary queries or write operations.

Security features:
- Predefined queries only (no query injection)
- Read-only operations (no index, update, delete)
- Input validation and sanitization
- Rate limiting
- No direct ES cluster exposure
"""

import os
import logging
from typing import Dict, Any, Optional, List
from flask import Blueprint, jsonify, request, Response
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ElasticsearchException
from functools import wraps
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Import existing utility functions
from citations_lib.utils import (
    es_scroll,
    get_es_results,
    get_es_aggregate,
    base64_decode_and_decompress
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Blueprint for API routes
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Initialize rate limiter
# Will be configured with Flask app in register_api_routes()
limiter = None

# Initialize Elasticsearch client
def get_es_client() -> Elasticsearch:
    """Get Elasticsearch client instance."""
    es_url = os.getenv('ELASTICSEARCH_URL') or os.getenv('ES_URL_LOCAL')
    if not es_url:
        raise ValueError("Elasticsearch URL not configured")
    return Elasticsearch([es_url])


# ============================================================================
# SECURITY DECORATORS
# ============================================================================

def validate_json(f):
    """Decorator to validate JSON request body."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            if not request.is_json:
                return jsonify({"error": "Content-Type must be application/json"}), 400
            if not request.json:
                return jsonify({"error": "Request body must be valid JSON"}), 400
        return f(*args, **kwargs)
    return decorated_function


def safe_query(allowed_indices: List[str]):
    """
    Decorator to ensure queries only access allowed indices.

    Args:
        allowed_indices: List of index names that can be queried
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Store allowed indices in request context
            request.allowed_indices = allowed_indices
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def sanitize_string(value: str, max_length: int = 200) -> str:
    """
    Sanitize string input to prevent injection attacks.

    Args:
        value: Input string to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized string
    """
    if not isinstance(value, str):
        raise ValueError("Input must be a string")

    # Truncate to max length
    value = value[:max_length]

    # Remove potentially dangerous characters
    # Allow alphanumeric, spaces, hyphens, underscores, periods, commas
    sanitized = ''.join(c for c in value if c.isalnum() or c in ' -_.,')

    return sanitized.strip()


def validate_year(year: Any) -> int:
    """
    Validate year parameter.

    Args:
        year: Year value to validate

    Returns:
        Validated year as integer

    Raises:
        ValueError: If year is invalid
    """
    try:
        year_int = int(year)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid year: {year}")

    if year_int < 2000 or year_int > 2030:
        raise ValueError(f"Year must be between 2000 and 2030: {year_int}")

    return year_int


def validate_limit(limit: Any, max_limit: int = 1000) -> int:
    """
    Validate limit parameter.

    Args:
        limit: Limit value to validate
        max_limit: Maximum allowed limit

    Returns:
        Validated limit as integer

    Raises:
        ValueError: If limit is invalid
    """
    try:
        limit_int = int(limit)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid limit: {limit}")

    if limit_int < 1:
        raise ValueError("Limit must be positive")

    if limit_int > max_limit:
        raise ValueError(f"Limit cannot exceed {max_limit}")

    return limit_int


# ============================================================================
# API ENDPOINTS
# ============================================================================

@api_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify API and Elasticsearch connectivity.

    GET /api/v1/health

    Returns:
        JSON response with health status
    """
    try:
        client = get_es_client()
        es_health = client.cluster.health()

        return jsonify({
            "status": "healthy",
            "elasticsearch": {
                "connected": True,
                "cluster_name": es_health.get('cluster_name'),
                "status": es_health.get('status')
            }
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": "Cannot connect to Elasticsearch"
        }), 503


@api_bp.route('/indices', methods=['GET'])
@safe_query(['career', 'singleyr', 'career_cntry', 'singleyr_cntry',
             'career_field', 'singleyr_field', 'career_inst', 'singleyr_inst'])
def list_indices():
    """
    List available Elasticsearch indices.

    GET /api/v1/indices

    Returns:
        JSON response with list of available indices
    """
    try:
        return jsonify({
            "indices": request.allowed_indices,
            "description": {
                "career": "Career-wide author data",
                "singleyr": "Single-year author data",
                "career_cntry": "Career-wide country aggregations",
                "singleyr_cntry": "Single-year country aggregations",
                "career_field": "Career-wide field aggregations",
                "singleyr_field": "Single-year field aggregations",
                "career_inst": "Career-wide institution aggregations",
                "singleyr_inst": "Single-year institution aggregations"
            }
        }), 200
    except Exception as e:
        logger.error(f"Error listing indices: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/search/authors', methods=['POST'])
@validate_json
@safe_query(['career', 'singleyr'])
def search_authors():
    """
    Search for authors by name, institution, or field.

    POST /api/v1/search/authors
    Content-Type: application/json

    Request body:
        {
            "query": "author name or institution",
            "index": "career" or "singleyr",
            "year": 2021 (optional, for singleyr index),
            "field": "authfull" or "inst_name" or "sm-field",
            "limit": 100 (optional, max 1000)
        }

    Returns:
        JSON response with search results
    """
    try:
        data = request.json

        # Validate required parameters
        if 'query' not in data:
            return jsonify({"error": "Missing required parameter: query"}), 400

        if 'index' not in data:
            return jsonify({"error": "Missing required parameter: index"}), 400

        if 'field' not in data:
            return jsonify({"error": "Missing required parameter: field"}), 400

        # Validate index
        index = data['index']
        if index not in request.allowed_indices:
            return jsonify({"error": f"Invalid index. Allowed: {request.allowed_indices}"}), 400

        # Sanitize and validate inputs
        query = sanitize_string(data['query'], max_length=200)
        if not query:
            return jsonify({"error": "Query cannot be empty"}), 400

        # Validate field
        allowed_fields = ['authfull', 'inst_name', 'sm-field']
        field = data['field']
        if field not in allowed_fields:
            return jsonify({"error": f"Invalid field. Allowed: {allowed_fields}"}), 400

        # Validate limit
        limit = validate_limit(data.get('limit', 100), max_limit=1000)

        # Validate year if provided
        year = None
        if 'year' in data:
            year = validate_year(data['year'])

        # Execute search using existing utility function
        client = get_es_client()
        results = get_es_results(
            client=client,
            idx=index,
            search_col=field,
            search_term=query,
            and_operator=False,
            exact_match=False
        )

        # Limit results
        if results and len(results) > limit:
            results = results[:limit]

        # Decompress author data if present
        processed_results = []
        for result in results:
            if 'Author_Data' in result:
                try:
                    result['Author_Data'] = base64_decode_and_decompress(result['Author_Data'])
                except Exception as e:
                    logger.warning(f"Failed to decompress author data: {str(e)}")
                    result['Author_Data'] = None
            processed_results.append(result)

        return jsonify({
            "query": query,
            "index": index,
            "field": field,
            "count": len(processed_results),
            "results": processed_results
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except ElasticsearchException as e:
        logger.error(f"Elasticsearch error: {str(e)}")
        return jsonify({"error": "Search failed"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/aggregate/<aggregation_type>', methods=['GET'])
@safe_query(['career_cntry', 'singleyr_cntry', 'career_field',
             'singleyr_field', 'career_inst', 'singleyr_inst'])
def get_aggregation(aggregation_type: str):
    """
    Get aggregated statistics by country, field, or institution.

    GET /api/v1/aggregate/<type>?year=2021&limit=100

    Parameters:
        aggregation_type: "country", "field", or "institution"
        year: Year for singleyr aggregations (optional)
        limit: Maximum number of results (optional, max 1000)

    Returns:
        JSON response with aggregated statistics
    """
    try:
        # Validate aggregation type
        allowed_types = ['country', 'field', 'institution']
        if aggregation_type not in allowed_types:
            return jsonify({
                "error": f"Invalid aggregation type. Allowed: {allowed_types}"
            }), 400

        # Get query parameters
        year_param = request.args.get('year')
        limit = validate_limit(request.args.get('limit', 100), max_limit=1000)

        # Determine index based on aggregation type and year
        if year_param:
            year = validate_year(year_param)
            if aggregation_type == 'country':
                index = 'singleyr_cntry'
            elif aggregation_type == 'field':
                index = 'singleyr_field'
            else:  # institution
                index = 'singleyr_inst'
        else:
            if aggregation_type == 'country':
                index = 'career_cntry'
            elif aggregation_type == 'field':
                index = 'career_field'
            else:  # institution
                index = 'career_inst'

        # Validate index is allowed
        if index not in request.allowed_indices:
            return jsonify({"error": f"Index {index} not allowed"}), 403

        # Execute aggregation query using existing utility function
        client = get_es_client()
        results = get_es_aggregate(
            client=client,
            idx=index,
            agg_type=aggregation_type
        )

        # Limit results
        if results and len(results) > limit:
            results = results[:limit]

        return jsonify({
            "aggregation_type": aggregation_type,
            "index": index,
            "year": year_param,
            "count": len(results) if results else 0,
            "results": results or []
        }), 200

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except ElasticsearchException as e:
        logger.error(f"Elasticsearch error: {str(e)}")
        return jsonify({"error": "Aggregation query failed"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@api_bp.route('/stats/<index_name>', methods=['GET'])
@safe_query(['career', 'singleyr', 'career_cntry', 'singleyr_cntry',
             'career_field', 'singleyr_field', 'career_inst', 'singleyr_inst'])
def get_index_stats(index_name: str):
    """
    Get basic statistics about an index.

    GET /api/v1/stats/<index_name>

    Parameters:
        index_name: Name of the index

    Returns:
        JSON response with index statistics (document count, size, etc.)
    """
    try:
        # Validate index
        if index_name not in request.allowed_indices:
            return jsonify({
                "error": f"Invalid index. Allowed: {request.allowed_indices}"
            }), 400

        # Get index stats
        client = get_es_client()

        # Get document count
        count_result = client.count(index=index_name)
        doc_count = count_result.get('count', 0)

        # Get index stats
        stats = client.indices.stats(index=index_name)
        index_stats = stats['indices'].get(index_name, {})

        total_size_bytes = index_stats.get('total', {}).get('store', {}).get('size_in_bytes', 0)
        total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

        return jsonify({
            "index": index_name,
            "document_count": doc_count,
            "size_mb": total_size_mb,
            "status": "available"
        }), 200

    except ElasticsearchException as e:
        logger.error(f"Elasticsearch error: {str(e)}")
        return jsonify({"error": "Failed to retrieve index statistics"}), 500
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@api_bp.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "error": "Endpoint not found",
        "available_endpoints": [
            "/api/v1/health",
            "/api/v1/indices",
            "/api/v1/search/authors",
            "/api/v1/aggregate/<type>",
            "/api/v1/stats/<index>"
        ]
    }), 404


@api_bp.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors."""
    return jsonify({
        "error": "Method not allowed",
        "message": "Check the API documentation for allowed methods"
    }), 405


@api_bp.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({
        "error": "Internal server error"
    }), 500


def register_api_routes(app):
    """
    Register API routes with Flask app.

    Args:
        app: Flask application instance
    """
    global limiter

    # Initialize rate limiter
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://",  # Use memory storage (upgrade to Redis for production)
        strategy="fixed-window",
        headers_enabled=True
    )

    # Apply rate limiting to specific endpoints
    limiter.limit("100 per hour")(search_authors)
    limiter.limit("200 per hour")(get_aggregation)
    limiter.limit("300 per hour")(get_index_stats)
    limiter.limit("500 per hour")(health_check)

    # Register blueprint
    app.register_blueprint(api_bp)
    logger.info("API routes registered successfully with rate limiting")
