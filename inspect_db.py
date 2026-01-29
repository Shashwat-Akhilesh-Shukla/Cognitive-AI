
import sqlite3
import os
import sys
from pathlib import Path

DB_PATH = Path("cognitiveai.db").absolute()

def inspect():
    print(f"Inspecting DB at: {DB_PATH}")
    if not DB_PATH.exists():
        print("ERROR: DB file does not exist!")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    print("\n--- TABLES ---")
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for t in tables:
        print(f" - {t['name']}")
        
    print("\n--- USERS ---")
    users = conn.execute("SELECT user_id, username FROM users").fetchall()
    for u in users:
        print(f" - {u['username']} ({u['user_id']})")
        
    print("\n--- CONVERSATIONS ---")
    convs = conn.execute("SELECT conversation_id, user_id, title FROM conversations").fetchall()
    for c in convs:
        print(f" - {c['conversation_id']} | User: {c['user_id']} | Title: {c['title']}")
        
    print("\n--- MESSAGES (Raw Encrypted) ---")
    msgs = conn.execute("SELECT message_id, conversation_id, role, content FROM messages").fetchall()
    print(f"Total Messages: {len(msgs)}")
    for m in msgs:
        content_preview = m['content'][:20] + "..." if m['content'] else "EMPTY"
        print(f" - [{m['role']}] {content_preview} (Conv: {m['conversation_id']})")
        
    conn.close()

if __name__ == "__main__":
    inspect()
