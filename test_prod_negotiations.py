import requests
import json

base_url = "https://casepeerai.onrender.com/internal-api"

# 1. Create a test case first
test_case_id = "PROD-TEST-NEG-1"
case_payload = {
    "id": test_case_id,
    "patient_name": "Prod Test Patient",
    "status": "Negotiation",
    "fees_taken": 0.0,
    "savings": 0.0,
    "revenue": 0.0,
    "emails_received": 0,
    "emails_sent": 0
}

print(f"Creating test case {test_case_id} on PRODUCTION...")
try:
    res = requests.post(f"{base_url}/cases", json=case_payload, timeout=10)
    print(f"Status: {res.status_code}")
except Exception as e:
    print(f"Failed to connect to production: {e}")
    exit(1)

# 2. Test negotiations endpoint
neg_payload = {
    "case_id": test_case_id,
    "negotiation_type": "Initial Demand",
    "to": "Insurance Company", # The problematic field
    "email_body": "Production test body",
    "date": "2024-02-07",
    "actual_bill": 2000.0,
    "offered_bill": 1000.0,
    "sent_by_us": True,
    "result": "Pending"
}

print(f"\nTesting production negotiations POST endpoint...")
try:
    res = requests.post(f"{base_url}/negotiations", json=neg_payload, timeout=10)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        print(f"Success! Response: {json.dumps(res.json(), indent=2)}")
    else:
        print(f"Error: {res.status_code} - {res.text}")
except Exception as e:
    print(f"Request failed: {e}")
