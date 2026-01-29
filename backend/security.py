import os
import logging
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)

# Global variable to cache the master cipher suite
_master_cipher_suite = None

def get_master_cipher():
    """
    Retrieve or initialize the Master Encryption Key.
    This key is used to:
    1. Encrypt/Decrypt legacy data (where user has no specific key).
    2. Encrypt/Decrypt the per-user keys stored in the database.
    """
    global _master_cipher_suite
    if _master_cipher_suite:
        return _master_cipher_suite

    # Try to load from environment
    key = os.getenv("DB_ENCRYPTION_KEY")
    
    if not key:
        logger.warning("No DB_ENCRYPTION_KEY found. Generating and SAVING a new one.")
        key_bytes = Fernet.generate_key()
        key_str = key_bytes.decode('utf-8')
        
        # Save to .env file for persistence
        try:
            from pathlib import Path
            env_path = Path(__file__).parent / ".env"
            
            # Read existing content to avoid partial writes
            existing_content = ""
            if env_path.exists():
                existing_content = env_path.read_text(encoding='utf-8')
            
            # Append only if not already there (race condition check)
            if "DB_ENCRYPTION_KEY=" not in existing_content:
                with open(env_path, "a", encoding='utf-8') as f:
                    f.write(f"\nDB_ENCRYPTION_KEY='{key_str}'\n")
                logger.info(f"Saved new DB_ENCRYPTION_KEY to {env_path}")
            else:
                # Reload env to pick up what another process might have written
                from dotenv import load_dotenv
                load_dotenv(env_path)
                key = os.getenv("DB_ENCRYPTION_KEY")
                if key:
                    key_bytes = key.encode('utf-8')
        except Exception as e:
            logger.critical(f"Failed to save key to .env: {e}")
            # We continue with the generated key, but warn loudly
            
        key = key_bytes
    else:
        # Handle if key is string or bytes
        if isinstance(key, str):
            key = key.encode('utf-8')
            
        masked_key = key.decode('utf-8')[:4] + "..." + key.decode('utf-8')[-4:]
        logger.info(f"Loaded persistent DB encryption key ({masked_key})")
    
    try:
        _master_cipher_suite = Fernet(key)
    except Exception as e:
        logger.critical(f"Invalid Master Key format! {e}")
        # Fallback to temp key to keep app running (though data will be unreadable)
        _master_cipher_suite = Fernet(Fernet.generate_key())

    return _master_cipher_suite

# --- User-Bound Key Management ---

def generate_user_key() -> str:
    """Generate a new random encryption key for a user. Returns base64 encoded string."""
    return Fernet.generate_key().decode('utf-8')

def encrypt_user_key(user_key: str) -> str:
    """
    Encrypt the user's raw key using the Master Key.
    This allows storing the user's key safely in the DB.
    """
    master = get_master_cipher()
    return master.encrypt(user_key.encode('utf-8')).decode('utf-8')

def decrypt_user_key(encrypted_user_key: str) -> Optional[str]:
    """
    Decrypt the user's encrypted key using the Master Key.
    Returns the raw user key string.
    """
    if not encrypted_user_key:
        return None
    try:
        master = get_master_cipher()
        return master.decrypt(encrypted_user_key.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decrypt user key: {e}")
        return None

def get_user_cipher(user_key: str) -> Fernet:
    """Create a Fernet cipher suite from a user's raw key."""
    return Fernet(user_key.encode('utf-8'))

# --- Generic Content Encryption ---

def encrypt_content(content: str, cipher: Fernet) -> str:
    """Encrypt string content using a specific cipher."""
    if not content:
        return ""
    try:
        return cipher.encrypt(content.encode('utf-8')).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise

def decrypt_content(token: str, cipher: Fernet) -> str:
    """Decrypt token using a specific cipher."""
    if not token:
        return ""
    try:
        return cipher.decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception:
        # Graceful failure for UI
        return "[Message could not be decrypted]"

# --- Backward Compatibility / Helper wrapper ---

def encrypt_message(message: str, specific_cipher: Optional[Fernet] = None) -> str:
    """
    Encrypts a message.
    If specific_cipher is provided (user-bound), uses that.
    Otherwise falls back to Master Key (legacy behavior).
    """
    cipher = specific_cipher or get_master_cipher()
    return encrypt_content(message, cipher)

def decrypt_message(encrypted_token: str, specific_cipher: Optional[Fernet] = None) -> str:
    """
    Decrypts a message.
    If specific_cipher is provided, tries that first.
    If that fails (or not provided), could optionally fallback to Master Key 
    (useful during migration, but risky if keys overlap).
    For now, we stick to the provided cipher or Master.
    """
    cipher = specific_cipher or get_master_cipher()
    return decrypt_content(encrypted_token, cipher)
