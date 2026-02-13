
import requests

def test_internal_api_routing():
    # base_url = "https://casepeerai.onrender.com"
    base_url = "http://localhost:8000" # Uncomment for local testing if running
    
    # 1. Test GET request (Scenario reported by user)
    print(f"Testing GET {base_url}/internal-api/authenticate/")
    try:
        response = requests.get(f"{base_url}/internal-api/authenticate/")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

    print("-" * 20)

    # 2. Test POST request (Should work if no trailing slash, might fail with slash)
    print(f"Testing POST {base_url}/internal-api/authenticate/")
    try:
        response = requests.post(f"{base_url}/internal-api/authenticate/")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

    print("-" * 20)
    
    # 3. Test POST request without trailing slash
    print(f"Testing POST {base_url}/internal-api/authenticate (no slash)")
    try:
        response = requests.post(f"{base_url}/internal-api/authenticate")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
         print(f"Error: {e}")

    print("-" * 20)

    # 4. Test GET request without trailing slash (Critical check for deployment)
    print(f"Testing GET {base_url}/internal-api/authenticate (no slash)")
    try:
        response = requests.get(f"{base_url}/internal-api/authenticate")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
         print(f"Error: {e}")

    print("-" * 20)

    # 5. Test Search Proxy Endpoint
    search_path = "/api/v1/case/case-search/?search=Kanongataa"
    print(f"Testing GET {base_url}{search_path}")
    try:
        # Note: we need to manually simulate the headers we are sending in caseapi.py to test properly
        # But here we are just testing the endpoint response. 
        # If we get 200 OK but HTML, it means the server IS reachable but redirecting.
        
        response = requests.get(f"{base_url}{search_path}", allow_redirects=False)
        print(f"Status Code: {response.status_code}")
        print(f"Headers: {response.headers}")
        
        if response.status_code in (301, 302):
            print(f"Redirect Location: {response.headers.get('Location')}")
            
        # Print a snippet to see if it's JSON or HTML (Login page)
        print(f"Response Preview: {response.text[:500]}")
    except Exception as e:
         print(f"Error: {e}")

    print("-" * 20)
    
    # 6. Fetch Logs to debug
    # ... (existing log fetch code) ...
    
    print("-" * 20)
    
    # 7. Test Other GET Endpoints
    endpoints_to_test = [
        "/internal-api/cases?limit=1",
        "/internal-api/settings",
        "/internal-api/token_usage"
    ]
    
    for endpoint in endpoints_to_test:
        print(f"Testing GET {base_url}{endpoint}")
        try:
            response = requests.get(f"{base_url}{endpoint}")
            print(f"Status Code: {response.status_code}")
            # print(f"Response Preview: {response.text[:200]}")
            if response.status_code != 200:
                print(f"FAILED: {response.text[:500]}")
            else:
                print("SUCCESS")
        except Exception as e:
             print(f"Error testing {endpoint}: {e}")
        print("-" * 10)

if __name__ == "__main__":
    test_internal_api_routing()
