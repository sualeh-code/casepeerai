import requests
import sys

BASE_URL = "http://localhost:8000"

def test_live_negotiations(case_id):
    print(f"Testing live negotiations for case {case_id}...")
    try:
        response = requests.get(f"{BASE_URL}/dashboard/api/live/cases/{case_id}/negotiations")
        if response.status_code == 200:
            data = response.json()
            print("[OK] Success!")
            print(f"Source: {data.get('source')}")
            print(f"Count: {data.get('count')}")
            if data.get('negotiations'):
                print("First negotiation sample:")
                print(data['negotiations'][0])
            else:
                print("No negotiations found (this might be normal if the case has none).")
        else:
            print(f"[FAIL] Failed with status {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"[ERROR] Error: {e}")

if __name__ == "__main__":
    # Use a known case ID if possible, otherwise default to one seen in logs
    case_id = "1850882" 
    if len(sys.argv) > 1:
        case_id = sys.argv[1]
    test_live_negotiations(case_id)
