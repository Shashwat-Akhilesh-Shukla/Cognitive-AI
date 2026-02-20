"""
Database layer for CognitiveAI with User model.
Handles user persistence and authentication.
Uses PostgreSQL via psycopg2.
"""
from backend.security import (
    encrypt_message, decrypt_message,
    generate_user_key, encrypt_user_key, decrypt_user_key, get_user_cipher
)
import psycopg2
import psycopg2.extras
from psycopg2 import IntegrityError as PgIntegrityError
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging
import json
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ai_therapist:ai_project@localhost:5432/ai_therapist")


def get_connection() -> psycopg2.extensions.connection:
    """Create a psycopg2 connection to PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    return conn


class User:
    """User data model."""
    def __init__(self, user_id: str, username: str, password_hash: str, email: Optional[str] = None, created_at: Optional[str] = None, encryption_key_encrypted: Optional[str] = None):
        self.user_id = user_id
        self.username = username
        self.password_hash = password_hash
        self.email = email
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.encryption_key_encrypted = encryption_key_encrypted

    def to_dict(self) -> Dict[str, Any]:
        """Return user data as dict (without password hash or internal keys)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at
        }


class Database:
    """PostgreSQL database manager for users."""

    def __init__(self):
        self.init_db()

    def init_db(self):
        """Initialize database schema."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        email TEXT,
                        created_at TEXT NOT NULL,
                        encryption_key_encrypted TEXT
                    )
                """)

                # Migration check: ensure encryption_key_encrypted exists (for existing DBs)
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'encryption_key_encrypted'
                """)
                if not cur.fetchone():
                    logger.info("Migrating users table: adding encryption_key_encrypted column")
                    try:
                        cur.execute("ALTER TABLE users ADD COLUMN encryption_key_encrypted TEXT")
                    except Exception as e:
                        logger.error(f"Migration failed: {e}")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS pdf_documents (
                        document_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        filename TEXT,
                        title TEXT,
                        file_size INTEGER,
                        upload_timestamp DOUBLE PRECISION,
                        metadata TEXT
                    )
                """)

                # Drop old chats table (replaced by conversations + messages)
                cur.execute("DROP TABLE IF EXISTS chats")

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        conversation_id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        title TEXT,
                        created_at DOUBLE PRECISION NOT NULL,
                        updated_at DOUBLE PRECISION NOT NULL
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        message_id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp DOUBLE PRECISION NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id)
                    )
                """)

            conn.commit()
            logger.info(f"PostgreSQL database initialized. URL: {DATABASE_URL.split('@')[-1]}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Database init failed: {e}")
            raise
        finally:
            conn.close()

    def create_user(self, user_id: str, username: str, password_hash: str, email: Optional[str] = None) -> User:
        """Create a new user in the database with a personal encryption key."""

        # Generate and encrypt a new user-bound key
        raw_key = generate_user_key()
        enc_key = encrypt_user_key(raw_key)

        user = User(user_id, username, password_hash, email, encryption_key_encrypted=enc_key)

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (user_id, username, password_hash, email, created_at, encryption_key_encrypted) VALUES (%s, %s, %s, %s, %s, %s)",
                    (user.user_id, user.username, user.password_hash, user.email, user.created_at, user.encryption_key_encrypted)
                )
            conn.commit()
            logger.info(f"User created: {username} (Secure Key Generated)")
            return user
        except PgIntegrityError as e:
            conn.rollback()
            logger.error(f"Failed to create user {username}: {e}")
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create user {username}: {e}")
            raise
        finally:
            conn.close()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Retrieve user by username."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, username, password_hash, email, created_at, encryption_key_encrypted FROM users WHERE username = %s",
                    (username,)
                )
                row = cur.fetchone()
            if row:
                return User(row[0], row[1], row[2], row[3], row[4], row[5])
            return None
        finally:
            conn.close()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by user_id."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, username, password_hash, email, created_at, encryption_key_encrypted FROM users WHERE user_id = %s",
                    (user_id,)
                )
                row = cur.fetchone()
            if row:
                return User(row[0], row[1], row[2], row[3], row[4], row[5])
            return None
        finally:
            conn.close()

    def username_exists(self, username: str) -> bool:
        """Check if username already exists."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM users WHERE username = %s",
                    (username,)
                )
                return cur.fetchone() is not None
        finally:
            conn.close()

    def delete_user(self, user_id: str) -> bool:
        """Delete a user (for cleanup/testing)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
                deleted = cur.rowcount
            conn.commit()
            return deleted > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False
        finally:
            conn.close()

    def create_pdf_metadata(self, document_id: str, user_id: str, filename: str, title: str, file_size: int, upload_timestamp: float, metadata: Optional[Dict[str, Any]] = None):
        """Create or update PDF metadata entry (upsert)."""
        meta_json = json.dumps(metadata or {})
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pdf_documents (document_id, user_id, filename, title, file_size, upload_timestamp, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_id) DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        filename = EXCLUDED.filename,
                        title = EXCLUDED.title,
                        file_size = EXCLUDED.file_size,
                        upload_timestamp = EXCLUDED.upload_timestamp,
                        metadata = EXCLUDED.metadata
                    """,
                    (document_id, user_id, filename, title, file_size, upload_timestamp, meta_json)
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to upsert pdf metadata {document_id}: {e}")
            raise
        finally:
            conn.close()

    def get_pdf_documents_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        """Retrieve PDF metadata entries for a given user."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT document_id, filename, title, file_size, upload_timestamp, metadata FROM pdf_documents WHERE user_id = %s",
                    (user_id,)
                )
                rows = cur.fetchall()
            results: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    meta = json.loads(r[5]) if r[5] else {}
                except Exception:
                    meta = {}
                results.append({
                    "document_id": r[0],
                    "filename": r[1],
                    "title": r[2],
                    "file_size": r[3],
                    "upload_timestamp": r[4],
                    "metadata": meta
                })
            return results
        finally:
            conn.close()

    def delete_pdf_metadata(self, document_id: str, user_id: Optional[str] = None) -> bool:
        """Delete PDF metadata entry (scoped to user if provided)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                if user_id:
                    cur.execute("DELETE FROM pdf_documents WHERE document_id = %s AND user_id = %s", (document_id, user_id))
                else:
                    cur.execute("DELETE FROM pdf_documents WHERE document_id = %s", (document_id,))
                deleted = cur.rowcount
            conn.commit()
            return deleted > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete pdf metadata {document_id}: {e}")
            return False
        finally:
            conn.close()

    # Conversation management methods
    def create_conversation(self, user_id: str, title: Optional[str] = None, created_at: Optional[float] = None, updated_at: Optional[float] = None) -> str:
        """Create a new conversation. Returns conversation_id."""
        import uuid
        import time
        conversation_id = str(uuid.uuid4())
        now = time.time()
        created = created_at or now
        updated = updated_at or now

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversations (conversation_id, user_id, title, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)",
                    (conversation_id, user_id, title, created, updated)
                )
            conn.commit()
            logger.debug(f"Conversation created for user {user_id}: {conversation_id}")
            return conversation_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create conversation for user {user_id}: {e}")
            raise
        finally:
            conn.close()

    def get_conversation(self, conversation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a conversation by ID (scoped to user)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT conversation_id, user_id, title, created_at, updated_at FROM conversations WHERE conversation_id = %s AND user_id = %s",
                    (conversation_id, user_id)
                )
                row = cur.fetchone()
            if row:
                return {
                    "conversation_id": row[0],
                    "user_id": row[1],
                    "title": row[2],
                    "created_at": row[3],
                    "updated_at": row[4]
                }
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve conversation {conversation_id}: {e}")
            return None
        finally:
            conn.close()

    def list_conversations(self, user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """List all conversations for a user, ordered by updated_at (most recent first)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT conversation_id, title, created_at, updated_at FROM conversations WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                    (user_id, limit, offset)
                )
                rows = cur.fetchall()
            results: List[Dict[str, Any]] = []
            for r in rows:
                results.append({
                    "conversation_id": r[0],
                    "title": r[1],
                    "created_at": r[2],
                    "updated_at": r[3]
                })
            return results
        except Exception as e:
            logger.error(f"Failed to list conversations for user {user_id}: {e}")
            return []
        finally:
            conn.close()

    def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update conversation title."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE conversations SET title = %s WHERE conversation_id = %s",
                    (title, conversation_id)
                )
                updated = cur.rowcount
            conn.commit()
            return updated > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update conversation title {conversation_id}: {e}")
            return False
        finally:
            conn.close()

    def update_conversation_timestamp(self, conversation_id: str, updated_at: Optional[float] = None) -> bool:
        """Update conversation updated_at timestamp."""
        import time
        timestamp = updated_at or time.time()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE conversations SET updated_at = %s WHERE conversation_id = %s",
                    (timestamp, conversation_id)
                )
                updated = cur.rowcount
            conn.commit()
            return updated > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update conversation timestamp {conversation_id}: {e}")
            return False
        finally:
            conn.close()

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        """Delete a conversation and all its messages (scoped to user)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Delete messages first
                cur.execute("DELETE FROM messages WHERE conversation_id = %s AND user_id = %s", (conversation_id, user_id))
                # Delete conversation
                cur.execute("DELETE FROM conversations WHERE conversation_id = %s AND user_id = %s", (conversation_id, user_id))
                deleted = cur.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Deleted conversation {conversation_id} for user {user_id}")
            return deleted > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete conversation {conversation_id}: {e}")
            return False
        finally:
            conn.close()

    # Message management methods

    def _get_user_cipher_suite(self, user_id: str):
        """Helper to retrieve the correct cipher suite for a user."""
        try:
            user = self.get_user_by_id(user_id)
            if user and user.encryption_key_encrypted:
                raw_key = decrypt_user_key(user.encryption_key_encrypted)
                if raw_key:
                    return get_user_cipher(raw_key)
            return None
        except Exception as e:
            logger.error(f"Failed to get cipher for user {user_id}: {e}")
            return None

    def add_message(self, conversation_id: str, user_id: str, role: str, content: str, timestamp: float, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store a message in a conversation. Returns message_id."""
        import uuid
        message_id = str(uuid.uuid4())

        # Get cipher for this user
        cipher = self._get_user_cipher_suite(user_id)

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO messages (message_id, conversation_id, user_id, role, content, timestamp, metadata) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (message_id, conversation_id, user_id, role, encrypt_message(content, cipher), timestamp, json.dumps(metadata))
                )
            conn.commit()
            logger.debug(f"Message stored in conversation {conversation_id}: {message_id}")
            return message_id
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to store message in conversation {conversation_id}: {e}")
            raise
        finally:
            conn.close()

    def get_messages_for_conversation(self, conversation_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Retrieve messages for a conversation, ordered by timestamp."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT user_id FROM conversations WHERE conversation_id = %s", (conversation_id,))
                conv_row = cur.fetchone()

            user_id = conv_row[0] if conv_row else None
            cipher = None
            if user_id:
                cipher = self._get_user_cipher_suite(user_id)

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT message_id, role, content, timestamp, metadata FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC LIMIT %s OFFSET %s",
                    (conversation_id, limit, offset)
                )
                rows = cur.fetchall()

            results: List[Dict[str, Any]] = []
            for r in rows:
                try:
                    meta = json.loads(r[4]) if r[4] else {}
                except Exception:
                    meta = {}
                results.append({
                    "message_id": r[0],
                    "role": r[1],
                    "content": decrypt_message(r[2], cipher),
                    "timestamp": r[3],
                    "metadata": meta
                })
            return results
        except Exception as e:
            logger.error(f"Failed to retrieve messages for conversation {conversation_id}: {e}")
            return []
        finally:
            conn.close()

    def delete_messages_for_user(self, user_id: str) -> bool:
        """Delete all messages for a user (scoped deletion)."""
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
                deleted = cur.rowcount
            conn.commit()
            if deleted > 0:
                logger.info(f"Deleted {deleted} messages for user {user_id}")
            return deleted > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete messages for user {user_id}: {e}")
            return False
        finally:
            conn.close()


db: Optional[Database] = None


def get_database() -> Database:
    """Get or initialize the global database instance."""
    global db
    if db is None:
        db = Database()
    return db
