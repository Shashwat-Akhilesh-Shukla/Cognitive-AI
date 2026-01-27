import os
from cryptography.fernet import Fernet

# This creates a cipher suite using a key from your Environment Variables
def get_cipher_suite():
    # In a real app, this comes from os.getenv("ENCRYPTION_KEY")
    # For now, if no key exists, we generate a temporary one for testing
    
    # ERROR FIX: Added quotes around "DB_ENCRYPTION_KEY"
    key = os.getenv("DB_ENCRYPTION_KEY")
    
    # ERROR FIX: Added colon (:) at the end
    if not key:
        # ERROR FIX: Added quotes around the print message
        print("WARNING: No DB_ENCRYPTION_KEY found. Generating a temp one.")
        key = Fernet.generate_key()
    return Fernet(key)

# ERROR FIX: Fixed structure to (message: str) -> str:
def encrypt_message(message: str) -> str:
    """Encrypts a raw string into a Fernet token"""
    # ERROR FIX: Added colon
    if not message:
        return ""
    
    cipher = get_cipher_suite()
    # Fernet requires bytes, so we encode the string
    encrypted_bytes = cipher.encrypt(message.encode('utf-8'))
    # Database stores strings, so we decode back to utf-8 string
    return encrypted_bytes.decode('utf-8')

# ERROR FIX: Fixed structure to (token: str) -> str:
def decrypt_message(encrypted_token: str) -> str:
    """Decrypts a Fernet token back into a raw string"""
    # ERROR FIX: Added colon
    if not encrypted_token:
        return ""
        
    # ERROR FIX: Added colon
    try:
        cipher = get_cipher_suite()
        decrypted_bytes = cipher.decrypt(encrypted_token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    # ERROR FIX: Added colon
    except Exception as e:
        # If decryption fails (e.g., data wasn't encrypted yet), return original
        return encrypted_token