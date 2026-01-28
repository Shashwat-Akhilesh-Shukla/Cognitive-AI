"""
Script to preload voice models (Whisper STT and Coqui TTS)
This will download and cache the models to disk for future use.
"""

import requests
import sys

# Backend URL
BACKEND_URL = "http://localhost:8000"

# You can get a valid token by logging in, or use admin credentials
# For now, we'll call the endpoint without auth since it's a system operation
# If auth is required, you'll need to login first

def preload_models():
    """Trigger model preloading via API endpoint."""
    try:
        print("🔄 Triggering voice model download...")
        print("This may take several minutes as models are large (1-2GB total)")
        print()
        
        # Note: The endpoint requires authentication
        # You may need to update this with a valid token
        response = requests.post(
            f"{BACKEND_URL}/voice/preload",
            headers={
                # Add your token here if needed
                # "Authorization": "Bearer YOUR_TOKEN"
            },
            timeout=600  # 10 minute timeout for large downloads
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Models preloaded successfully!")
            print(f"Model info: {result}")
        elif response.status_code == 401:
            print("❌ Authentication required. Please login first.")
            print("Run this script after logging into the app to get a valid token.")
        else:
            print(f"❌ Failed to preload models: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.Timeout:
        print("⏱️  Request timed out. Models may still be downloading in background.")
        print("Check the backend logs for progress.")
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(preload_models())
