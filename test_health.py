
import requests
import sys

BASE_URL = "http://localhost:8000"

def check_health():
    print(f"Checking health of {BASE_URL}...")
    try:
        # Check root or docs
        resp = requests.get(f"{BASE_URL}/docs", timeout=5)
        print(f"Docs endpoint: {resp.status_code}")
        
        # Check specific endpoint?
        # Maybe conversations list if we had a token
    except Exception as e:
        print(f"Backend unreachable: {e}")
        return

if __name__ == "__main__":
    check_health()
