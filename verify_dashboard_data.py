
import requests
import sys

# Base URL for the API
BASE_URL = "http://localhost:8000"

def verify_dashboard_data():
    print(f"Verifying dashboard data from {BASE_URL}...")
    
    # 1. Verify Cases Endpoint
    print("\n1. Testing /internal-api/cases...")
    try:
        response = requests.get(f"{BASE_URL}/internal-api/cases?limit=5")
        if response.status_code == 200:
            cases = response.json()
            print(f"   [OK] Fetched {len(cases)} cases")
            if len(cases) > 0:
                print(f"   Sample Case: {cases[0].get('patient_name')} (ID: {cases[0].get('id')})")
                
                # Check for negotiations in the first case
                case_id = cases[0].get('id')
                negotiations = cases[0].get('negotiations', [])
                print(f"   Nested Negotiations: {len(negotiations)}")
        else:
            print(f"   [FAIL] Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"   [ERROR] Connection failed: {e}")

    # 2. Verify N8n Stats Endpoint
    print("\n2. Testing /internal-api/integrations/n8n/executions...")
    try:
        response = requests.get(f"{BASE_URL}/internal-api/integrations/n8n/executions")
        if response.status_code == 200:
            stats = response.json()
            print(f"   [OK] Fetched n8n stats")
            print(f"   Success: {stats.get('success')}, Error: {stats.get('error')}")
        else:
            print(f"   [FAIL] Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    except Exception as e:
        print(f"   [ERROR] Connection failed: {e}")

if __name__ == "__main__":
    verify_dashboard_data()
