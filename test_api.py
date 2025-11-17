#!/usr/bin/env python
"""
Test script for Elasticsearch read-only API endpoints.

Usage:
    python test_api.py [base_url]

Examples:
    python test_api.py http://localhost:8050
    python test_api.py https://your-domain.com
"""

import sys
import requests
import json
from typing import Dict, Any


def print_test_result(name: str, success: bool, details: str = ""):
    """Print formatted test result."""
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"{status} - {name}")
    if details:
        print(f"  {details}")
    print()


def test_health_check(base_url: str) -> bool:
    """Test the health check endpoint."""
    try:
        response = requests.get(f"{base_url}/api/v1/health", timeout=10)
        success = response.status_code == 200
        details = f"Status: {response.status_code}"

        if success:
            data = response.json()
            es_status = data.get('elasticsearch', {}).get('status', 'unknown')
            details += f", ES Status: {es_status}"

        print_test_result("Health Check", success, details)
        return success
    except Exception as e:
        print_test_result("Health Check", False, f"Error: {str(e)}")
        return False


def test_list_indices(base_url: str) -> bool:
    """Test the list indices endpoint."""
    try:
        response = requests.get(f"{base_url}/api/v1/indices", timeout=10)
        success = response.status_code == 200
        details = f"Status: {response.status_code}"

        if success:
            data = response.json()
            indices = data.get('indices', [])
            details += f", Found {len(indices)} indices"

        print_test_result("List Indices", success, details)
        return success
    except Exception as e:
        print_test_result("List Indices", False, f"Error: {str(e)}")
        return False


def test_search_authors(base_url: str) -> bool:
    """Test the search authors endpoint."""
    try:
        payload = {
            "query": "test",
            "index": "career",
            "field": "authfull",
            "limit": 5
        }

        response = requests.post(
            f"{base_url}/api/v1/search/authors",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        success = response.status_code in [200, 404]  # 404 if no results
        details = f"Status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            count = data.get('count', 0)
            details += f", Found {count} results"

        print_test_result("Search Authors", success, details)
        return success
    except Exception as e:
        print_test_result("Search Authors", False, f"Error: {str(e)}")
        return False


def test_get_aggregation(base_url: str) -> bool:
    """Test the aggregation endpoint."""
    try:
        response = requests.get(
            f"{base_url}/api/v1/aggregate/country?limit=5",
            timeout=30
        )

        success = response.status_code == 200
        details = f"Status: {response.status_code}"

        if success:
            data = response.json()
            count = data.get('count', 0)
            details += f", Found {count} aggregations"

        print_test_result("Get Aggregation (Country)", success, details)
        return success
    except Exception as e:
        print_test_result("Get Aggregation (Country)", False, f"Error: {str(e)}")
        return False


def test_index_stats(base_url: str) -> bool:
    """Test the index statistics endpoint."""
    try:
        response = requests.get(f"{base_url}/api/v1/stats/career", timeout=10)
        success = response.status_code == 200
        details = f"Status: {response.status_code}"

        if success:
            data = response.json()
            doc_count = data.get('document_count', 0)
            size_mb = data.get('size_mb', 0)
            details += f", Docs: {doc_count:,}, Size: {size_mb:.2f} MB"

        print_test_result("Index Statistics", success, details)
        return success
    except Exception as e:
        print_test_result("Index Statistics", False, f"Error: {str(e)}")
        return False


def test_rate_limiting(base_url: str) -> bool:
    """Test that rate limiting headers are present."""
    try:
        response = requests.get(f"{base_url}/api/v1/health", timeout=10)
        has_limit = 'X-RateLimit-Limit' in response.headers
        has_remaining = 'X-RateLimit-Remaining' in response.headers

        success = has_limit and has_remaining
        details = f"Headers present: X-RateLimit-Limit={has_limit}, X-RateLimit-Remaining={has_remaining}"

        if success:
            limit = response.headers.get('X-RateLimit-Limit', 'N/A')
            remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
            details += f" (Limit: {limit}, Remaining: {remaining})"

        print_test_result("Rate Limiting Headers", success, details)
        return success
    except Exception as e:
        print_test_result("Rate Limiting Headers", False, f"Error: {str(e)}")
        return False


def test_invalid_requests(base_url: str) -> bool:
    """Test that invalid requests are properly rejected."""
    tests_passed = 0
    total_tests = 3

    # Test 1: Missing required parameter
    try:
        payload = {"index": "career", "field": "authfull"}  # Missing 'query'
        response = requests.post(
            f"{base_url}/api/v1/search/authors",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 400:
            tests_passed += 1
            print("  ✓ Rejects missing required parameter")
        else:
            print(f"  ✗ Should reject missing parameter (got {response.status_code})")
    except Exception as e:
        print(f"  ✗ Error testing missing parameter: {str(e)}")

    # Test 2: Invalid index
    try:
        payload = {
            "query": "test",
            "index": "invalid_index",
            "field": "authfull"
        }
        response = requests.post(
            f"{base_url}/api/v1/search/authors",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 400:
            tests_passed += 1
            print("  ✓ Rejects invalid index")
        else:
            print(f"  ✗ Should reject invalid index (got {response.status_code})")
    except Exception as e:
        print(f"  ✗ Error testing invalid index: {str(e)}")

    # Test 3: Invalid year
    try:
        payload = {
            "query": "test",
            "index": "singleyr",
            "field": "authfull",
            "year": 1800  # Too old
        }
        response = requests.post(
            f"{base_url}/api/v1/search/authors",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 400:
            tests_passed += 1
            print("  ✓ Rejects invalid year")
        else:
            print(f"  ✗ Should reject invalid year (got {response.status_code})")
    except Exception as e:
        print(f"  ✗ Error testing invalid year: {str(e)}")

    success = tests_passed == total_tests
    print_test_result("Input Validation", success, f"Passed {tests_passed}/{total_tests} validation tests")
    return success


def run_all_tests(base_url: str):
    """Run all API tests."""
    print("=" * 70)
    print(f"Testing Elasticsearch API at: {base_url}")
    print("=" * 70)
    print()

    results = []
    results.append(("Health Check", test_health_check(base_url)))
    results.append(("List Indices", test_list_indices(base_url)))
    results.append(("Search Authors", test_search_authors(base_url)))
    results.append(("Get Aggregation", test_get_aggregation(base_url)))
    results.append(("Index Statistics", test_index_stats(base_url)))
    results.append(("Rate Limiting", test_rate_limiting(base_url)))
    results.append(("Input Validation", test_invalid_requests(base_url)))

    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status} - {name}")

    print()
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 70)

    return passed == total


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        base_url = sys.argv[1].rstrip('/')
    else:
        base_url = "http://localhost:8050"

    print()
    all_passed = run_all_tests(base_url)
    print()

    if all_passed:
        print("✓ All tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Check the output above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
