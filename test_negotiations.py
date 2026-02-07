import requests
import json

base_url = "http://localhost:8000/internal-api"

# 1. Create a test case first (to avoid 404 Case not found)
test_case_id = "TEST-NEG-FIX"
case_payload = {
    "id": test_case_id,
    "patient_name": "Test Patient",
    "status": "Negotiation",
    "fees_taken": 0.0,
    "savings": 0.0,
    "revenue": 0.0,
    "emails_received": 0,
    "emails_sent": 0
}

print(f"Creating test case {test_case_id}...")
res = requests.post(f"{base_url}/cases", json=case_payload)
print(f"Status: {res.status_code}")

# 2. Test negotiations endpoint (the one that was failing)
neg_payload = {
    "case_id": test_case_id,
    "negotiation_type": "Initial Demand",
    "to": "Insurance Company", # This was causing the 500
    "email_body": "Test demand body",
    "date": "2024-02-07",
    "actual_bill": 1000.0,
    "offered_bill": 500.0,
    "sent_by_us": True,
    "result": "Pending"
}

print(f"\nTesting negotiations POST endpoint...")
res = requests.post(f"{base_url}/negotiations", json=neg_payload)
print(f"Status: {res.status_code}")
try:
    print(f"Response: {json.dumps(res.json(), indent=2)}")
except:
    print(f"Raw Response: {res.text}")

# 3. Verify via GET
print(f"\nVerifying via GET /negotiations?case_id={test_case_id}...")
res = requests.get(f"{base_url}/negotiations?case_id={test_case_id}")
print(f"Status: {res.status_code}")
try:
    data = res.json()
    print(f"Count: {len(data)}")
    if len(data) > 0:
        print("Success! Negotiation record found.")
except Exception as e:
    print(f"Error parsing GET response: {e}")
