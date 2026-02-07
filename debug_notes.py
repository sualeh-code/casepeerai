import requests
import json

url = "http://localhost:8000/internal-api/cases/1850882/notes"
try:
    print(f"Fetching from {url}...")
    res = requests.get(url)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        if "results" in data and len(data["results"]) > 0:
            first_note = data["results"][0]
            print("\nFirst Note Full Structure:")
            print(json.dumps(first_note, indent=2))
            
            print("\nKeys found in results[0]:")
            print(list(first_note.keys()))
        else:
            print("\nNo notes found or 'results' key missing.")
            print(f"Full response: {json.dumps(data, indent=2)}")
    else:
        print(f"Error response: {res.text[:500]}")
except Exception as e:
    print(f"Request failed: {e}")
