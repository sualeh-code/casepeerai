from fastapi.testclient import TestClient
from caseapi import app
import json

def test_api_cases():
    client = TestClient(app)
    print("Testing API endpoint: /api/cases")
    try:
        response = client.get("/api/cases")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response Data (Count: {len(data)}):")
            print(json.dumps(data, indent=2))
        else:
            print(f"Error Response: {response.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_api_cases()
