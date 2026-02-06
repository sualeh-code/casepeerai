import requests
import json

try:
    print("Fetching /internal-api/cases...")
    res = requests.get("http://localhost:8000/internal-api/cases")
    print(f"Status: {res.status_code}")
    print(f"Content-Type: {res.headers.get('content-type')}")
    
    try:
        data = res.json()
        print(f"Type: {type(data)}")
        if isinstance(data, list):
             print(f"Length: {len(data)}")
             if len(data) > 0:
                 print(f"First item: {data[0]}")
        else:
             print(f"Content: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"JSON Decode Error: {e}")
        print(f"Text: {res.text[:500]}")

    print("\nFetching /internal-api/cases/CASE-TEST-001/notes...")
    res = requests.get("http://localhost:8000/internal-api/cases/CASE-TEST-001/notes")
    print(f"Status: {res.status_code}")
    
    try:
        data = res.json()
        print(f"Full Response: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"JSON Error: {e}")
        print(f"Text: {res.text[:500]}")

except Exception as e:
    print(f"Request failed: {e}")
