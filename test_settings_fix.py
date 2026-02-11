import requests
import sys

# Since the server might not be running, we'll try to check locally if it is
# Otherwise, this serves as a template for the user to run.
BASE_URL = "http://localhost:8000"

def test_settings_endpoints():
    print(f"Testing settings endpoints on {BASE_URL}...")
    
    endpoints = [
        "/internal-api/settings",
        "/internal-api/settings/"
    ]
    
    for ep in endpoints:
        url = f"{BASE_URL}{ep}"
        try:
            print(f"Checking {url}...", end=" ")
            # Using GET for settings
            response = requests.get(url, timeout=5)
            print(f"Status: {response.status_code}")
            if response.status_code == 404:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"Failed to connect: {e}")

if __name__ == "__main__":
    test_settings_endpoints()
