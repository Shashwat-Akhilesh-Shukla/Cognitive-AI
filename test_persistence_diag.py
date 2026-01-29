
import os
import time
import requests
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
BACKEND_DIR = Path("d:/ai-therapist/backend")
ENV_PATH = BACKEND_DIR / ".env"
DB_PATH = Path("d:/ai-therapist/cognitiveai.db")

def test_persistence():
    print("--- STARTING PERSISTENCE TEST ---")

    # 1. Check if .env exists and has key
    print(f"[1] Checking for .env at {ENV_PATH}...")
    if not ENV_PATH.exists():
        print("FAIL: .env does not exist!")
        return
    
    with open(ENV_PATH, "r") as f:
        content = f.read()
        if "DB_ENCRYPTION_KEY" in content:
            print("SUCCESS: DB_ENCRYPTION_KEY found in .env")
        else:
            print("WARNING: DB_ENCRYPTION_KEY NOT found in .env yet (might be generated on next start)")

    # 2. Simulate Backend Start (this should trigger key generation if missing)
    # We can't easily start/stop the uvicorn process from here safely without killing the main one
    # So we will verify via DB inspection.

    # 3. Read latest message from DB
    print(f"[2] Inspecting DB at {DB_PATH}...")
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        msgs = conn.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1").fetchall()
        
        if not msgs:
            print("INFO: No messages in DB yet.")
        else:
            m = msgs[0]
            print(f"Latest Message ID: {m['message_id']}")
            print(f"Role: {m['role']}")
            print(f"Content (Encrypted?): {m['content'][:30]}...")
            
            # Simple heuristic: if it looks like a fernet token (gAAAA...)
            if m['content'].startswith("gAAAA"):
                print("SUCCESS: Message content appears encrypted.")
            else:
                print("WARNING: Message content might not be encrypted.")
                
        conn.close()
    except Exception as e:
        print(f"FAIL: DB Inspection failed: {e}")

if __name__ == "__main__":
    test_persistence()
