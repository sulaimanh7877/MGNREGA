"""
Example usage and testing for the MGNREGA Analytics API.
"""

import requests
import json
from datetime import datetime

# API base URL
BASE_URL = "http://localhost:8000"

def print_response(title: str, response: dict):
    """Pretty print API response."""
    print(f"\n{'='*60}")
    print(f"🔹 {title}")
    print(f"{'='*60}")
    print(json.dumps(response, indent=2, default=str)[:500] + "...")

def main():
    # Test 1: Health check
    print("\n🚀 Testing MGNREGA Analytics API\n")
    
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print_response("Health Check", resp.json())
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure the server is running: python run_server.py")
        return
    
    # Test 2: Get cross-district metrics
    try:
        resp = requests.get(f"{BASE_URL}/metrics/cross-district/2023-24/April")
        if resp.status_code == 200:
            print_response("Cross-District Metrics", resp.json())
        else:
            print(f"⚠️ No data for 2023-24/April. Try different dates or fetch data first.")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 3: Get analytics metadata
    try:
        resp = requests.get(f"{BASE_URL}/analytics-metadata")
        print_response("Analytics Metadata", resp.json())
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Test 4: Get cache stats
    try:
        resp = requests.get(f"{BASE_URL}/cache-stats")
        print_response("Cache Statistics", resp.json())
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ API Testing Complete!")
    print("="*60)
    print("\n📚 API Documentation available at: http://localhost:8000/docs")

if __name__ == "__main__":
    main()
