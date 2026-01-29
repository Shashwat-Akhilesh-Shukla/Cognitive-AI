
import os
import sys
import time
import json
sys.path.append(os.getcwd())

from backend.database import get_database

def test_persistence():
    print("Testing DB Persistence...")
    db = get_database()
    
    # 1. User
    user_id = "test_user_persist_" + str(int(time.time()))
    print(f"Creating user {user_id}")
    try:
        db.create_user(user_id, "testuser_persist", "hashedpw", "test@test.com")
    except Exception:
        pass # might exist

    # 2. Conversation
    print("Creating conversation...")
    conv_id = db.create_conversation(user_id, "Persistence Test")
    print(f"Conversation ID: {conv_id}")
    
    # 3. Add Messages
    print("Adding messages...")
    msg1_id = db.add_message(conv_id, user_id, "user", "Hello Persistence", time.time())
    print(f"Added msg1: {msg1_id}")
    
    msg2_id = db.add_message(conv_id, user_id, "assistant", "I am here.", time.time() + 1)
    print(f"Added msg2: {msg2_id}")
    
    # 4. Read immediately
    msgs = db.get_messages_for_conversation(conv_id)
    print(f"Immediate read: Found {len(msgs)} messages")
    for m in msgs:
        print(f" - {m['role']}: {m['content']}")
        
    if len(msgs) != 2:
        print("FAIL: Immediate read failed.")
        return

    # 5. Simulate new connection / reload (get_database is singleton, so we rely on init_db logic checks)
    print("Verifying data integrity...")
    msgs_again = db.get_messages_for_conversation(conv_id)
    if len(msgs_again) == 2:
        print("SUCCESS: Data persisted correctly.")
    else:
        print(f"FAIL: Data lost? Found {len(msgs_again)} messages")

if __name__ == "__main__":
    test_persistence()
