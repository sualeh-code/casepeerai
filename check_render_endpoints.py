import requests
import json

BASE_URL = "https://casepeerai.onrender.com"

endpoints = [
    {"method": "GET", "path": "/internal-api/token_usage"},
    {"method": "POST", "path": "/internal-api/authenticate"},
    {"method": "GET", "path": "/internal-api/cases"},
    {"method": "GET", "path": "/internal-api/negotiations?case_id=0"},
    {"method": "GET", "path": "/internal-api/classifications?case_id=0"},
    {"method": "GET", "path": "/internal-api/settings"},
    {"method": "GET", "path": "/internal-api/logs"},
    {"method": "GET", "path": "/internal-api/integrations/openai/usage"},
    {"method": "GET", "path": "/internal-api/integrations/n8n/executions"},
    {"method": "GET", "path": "/internal-api/cases/0/reminders"},
    {"method": "GET", "path": "/internal-api/cases/0/notes"},
    {"method": "GET", "path": "/internal-api/live/cases/0/negotiations"},
    {"method": "POST", "path": "/internal-api/cases", "data": {
        "id": "TEST-CASE-999", "patient_name": "Test Patient", "status": "Active", "fees_taken": 100.0, "savings": 50.0, "revenue": 10.0
    }},
    {"method": "POST", "path": "/internal-api/negotiations", "data": {
        "case_id": "TEST-CASE-999", "negotiation_type": "Demand", "to": "Insurance", "email_body": "Test Negotiation", "date": "2024-02-11", "actual_bill": 1000.0, "offered_bill": 500.0, "sent_by_us": True, "result": "Pending"
    }},
    {"method": "POST", "path": "/internal-api/classifications", "data": {
        "case_id": "TEST-CASE-999", "ocr_performed": True, "number_of_documents": 5, "confidence": 0.95
    }},
    {"method": "POST", "path": "/internal-api/reminders", "data": {
        "case_id": "TEST-CASE-999", "reminder_number": 1, "reminder_date": "2024-02-12", "reminder_email_body": "Test Reminder"
    }},
    {"method": "POST", "path": "/internal-api/settings", "data": {
        "key": "test_setting", "value": "test_value", "description": "Diagnostic test setting"
    }},
    {"method": "POST", "path": "/internal-api/update-provider-email", "data": {
        "email": "test@example.com", "provider_id": "123456", "case_id": "0"
    }},
]

def check_endpoints():
    print(f"Checking endpoints for: {BASE_URL}")
    print("-" * 60)
    print(f"{'Method':<8} | {'Status':<8} | {'Endpoint'}")
    print("-" * 60)
    
    results = []
    for ep in endpoints:
        url = f"{BASE_URL}{ep['path']}"
        data = ep.get('data', {})
        try:
            if ep['method'] == "GET":
                response = requests.get(url, timeout=15)
            elif ep['method'] == "POST":
                response = requests.post(url, json=data, timeout=15)
            
            status = response.status_code
            print(f"{ep['method']:<8} | {status:<8} | {ep['path']}")
            if status != 200:
                print(f"   Response Body: {response.text[:500]}")
            results.append({"endpoint": ep['path'], "status": status})
        except Exception as e:
            print(f"{ep['method']:<8} | {'ERROR':<8} | {ep['path']} ({str(e)})")
            results.append({"endpoint": ep['path'], "status": "ERROR", "error": str(e)})

    print("-" * 60)
    # Fetch logs if any error occurred
    print("Fetching server logs...")
    try:
        log_resp = requests.get(f"{BASE_URL}/internal-api/logs?limit=20", timeout=10)
        if log_resp.status_code == 200:
            logs = log_resp.json().get("logs", [])
            for line in logs:
                print(f"SERVER LOG: {line.strip()}")
    except:
        print("Failed to fetch server logs.")
    
    return results

if __name__ == "__main__":
    check_endpoints()
