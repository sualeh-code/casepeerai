import requests
import time
import sys

BASE_URL = "http://localhost:8000/api"

def wait_for_server():
    print("Waiting for server to start...")
    for i in range(10):
        try:
            response = requests.get("http://localhost:8000/docs")
            if response.status_code == 200:
                print("Server is up!")
                return True
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(1)
    print("Server failed to start.")
    return False

def test_api():
    if not wait_for_server():
        sys.exit(1)

    print("\n--- Testing API Endpoints ---")

    # 1. Create Case
    case_id = "CASE-TEST-001"
    case_data = {
        "id": case_id,
        "patient_name": "Alice Wonderland",
        "status": "Negotiation",
        "fees_taken": 2500.00,
        "savings": 1200.50
    }
    print(f"\n[POST] Creating Case {case_id}...")
    res = requests.post(f"{BASE_URL}/cases", json=case_data)
    if res.status_code == 200:
        print("✅ Case Created:", res.json())
    else:
        print("❌ Failed:", res.text)

    # 2. Add Negotiation
    neg_data = {
        "case_id": case_id,
        "negotiation_type": "Initial Demand",
        "to": "State Farm",
        "email_body": "We demand policy limits.",
        "date": "2024-12-01",
        "actual_bill": 15000.0,
        "offered_bill": 5000.0,
        "sent_by_us": True,
        "result": "Rejected"
    }
    print(f"\n[POST] Adding Negotiation...")
    res = requests.post(f"{BASE_URL}/negotiations", json=neg_data)
    if res.status_code == 200:
        print("✅ Negotiation Added:", res.json())
    else:
        print("❌ Failed:", res.text)

    # 3. Add Classification
    class_data = {
        "case_id": case_id,
        "ocr_performed": True,
        "number_of_documents": 5,
        "confidence": 0.98
    }
    print(f"\n[POST] Adding Classification...")
    res = requests.post(f"{BASE_URL}/classifications", json=class_data)
    if res.status_code == 200:
        print("✅ Classification Added:", res.json())
    else:
        print("❌ Failed:", res.text)

    # 4. Add Reminder
    rem_data = {
        "case_id": case_id,
        "reminder_number": 1,
        "reminder_date": "2024-12-20",
        "reminder_email_body": "Follow up on demand letter."
    }
    print(f"\n[POST] Adding Reminder...")
    res = requests.post(f"{BASE_URL}/reminders", json=rem_data)
    if res.status_code == 200:
        print("✅ Reminder Added:", res.json())
    else:
        print("❌ Failed:", res.text)

    # 5. Add Token Usage
    token_data = {
        "tokens_used": 1500,
        "cost": 0.045,
        "model_name": "gpt-4-turbo"
    }
    print(f"\n[POST] Adding Token Usage...")
    res = requests.post(f"{BASE_URL}/token_usage", json=token_data)
    if res.status_code == 200:
        print("✅ Token Usage Added:", res.json())
    else:
        print("❌ Failed:", res.text)

    # 6. Verify Data Retrieval
    print(f"\n[GET] Verifying Case Details for {case_id}...")
    res = requests.get(f"{BASE_URL}/cases/{case_id}")
    if res.status_code == 200:
        data = res.json()
        print("✅ Case Retrieved")
        print(f"   Name: {data['patient_name']}")
        print(f"   Status: {data['status']}")
    else:
        print("❌ Failed:", res.text)

    print("\n--- Test Complete ---")

if __name__ == "__main__":
    test_api()
