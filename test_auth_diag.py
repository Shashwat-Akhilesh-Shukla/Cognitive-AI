
import os
import sys

# Add the project root to the python path
sys.path.append(os.getcwd())

from backend.auth import AuthService
from backend.database import get_database

def test_auth():
    print("Testing Auth...")
    
    # 1. Database Init
    db = get_database()
    print("Database initialized.")
    
    # 2. Signup Mock
    username = "testuser_auth_diag"
    password = "password123"
    
    # Check if user exists (cleanup)
    user = db.get_user_by_username(username)
    if user:
        print(f"User {username} exists, deleting...")
        db.delete_user(user.user_id)
        
    print(f"Creating user {username}...")
    
    is_valid_user, msg = AuthService.validate_username(username)
    if not is_valid_user:
        print(f"Username invalid: {msg}")
        return
        
    is_valid_pass, msg = AuthService.validate_password(password)
    if not is_valid_pass:
        print(f"Password invalid: {msg}")
        return
        
    password_hash = AuthService.hash_password(password)
    user_id = AuthService.generate_user_id()
    
    try:
        db.create_user(user_id, username, password_hash)
        print("User created successfully in DB.")
    except Exception as e:
        print(f"Failed to create user: {e}")
        return

    # 3. Login Mock
    print("Attempting login verification...")
    user_fetched = db.get_user_by_username(username)
    if not user_fetched:
        print("User could not be fetched after creation.")
        return
        
    if AuthService.verify_password(password, user_fetched.password_hash):
        print("Password verification successful.")
    else:
        print("Password verification FAILED.")
        
    # 4. Token Gen
    token = AuthService.generate_token(user_id, username)
    print(f"Token generated: {token[:20]}...")
    
    payload = AuthService.verify_token(token)
    if payload and payload['user_id'] == user_id:
        print("Token verification successful.")
    else:
        print("Token verification FAILED.")
        
    print("Auth Diagnostic Complete.")

if __name__ == "__main__":
    test_auth()
