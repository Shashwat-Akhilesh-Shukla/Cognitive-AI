"""
FastAPI Backend for CognitiveAI with Multi-User Support

Provides REST API endpoints for authentication, chat, PDF upload, and memory inspection.
All data is strictly isolated per user.
"""

import os
import json
import tempfile
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Header, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr
import uvicorn
import logging
from dotenv import load_dotenv
import time

# Robust .env loading
env_path = Path(__file__).parent / ".env"
if not env_path.exists():
    print(f"Creating missing .env file at: {env_path}")
    env_path.touch()

print(f"Loading env from: {env_path}")
load_dotenv(env_path)

from backend.memory.stm import STMManager
from backend.memory.ltm import LTMManager
from backend.pdf_loader import PDFLoader
from backend.reasoning import CognitiveReasoningEngine
from backend.database import get_database, Database, User
from backend.auth import AuthService
from backend.conversations import ConversationManager
from backend.voice.websocket_handler import VoiceWebSocketHandler
from backend.voice.model_manager import ModelManager
from backend.response_cleaner import clean_response


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="CognitiveAI API",
    description="Memory-Augmented Personal Intelligence Engine (Multi-User)",
    version="2.0.0"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://0.0.0.0:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for frontend
static_path = Path(__file__).parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")




stm_manager: Optional[STMManager] = None
ltm_manager: Optional[LTMManager] = None
pdf_loader: Optional[PDFLoader] = None
reasoning_engine: Optional[CognitiveReasoningEngine] = None
db: Optional[Database] = None
conversation_manager: Optional[ConversationManager] = None
voice_handler: Optional[VoiceWebSocketHandler] = None









class SignupRequest(BaseModel):
    """Request model for user signup."""
    username: str
    password: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    """Request model for user login."""
    username: str
    password: str


class AuthResponse(BaseModel):
    """Response model for auth endpoints."""
    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    client_discard_token: Optional[bool] = None


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    conversation_id: Optional[str] = None
    doc_id: Optional[str] = None
    emotion: Optional[str] = "neutral"


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    conversation_id: str
    reasoning: Dict[str, Any]
    metadata: Dict[str, Any]


class MemoryStats(BaseModel):
    """Response model for memory statistics."""
    stm_count: int
    ltm_stats: Dict[str, Any]
    pdf_documents: List[Dict[str, Any]]
    reasoning_stats: Dict[str, Any]






def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """
    Extract and verify user_id from JWT token in Authorization header.
    Raises HTTPException if token is invalid or missing.
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    try:
        
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise ValueError("Invalid authorization header format")

        token = parts[1]
        payload = AuthService.verify_token(token)

        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Token missing user_id")

        return user_id

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")






def validate_environment():
    """Validate required environment variables at startup."""
    required_vars = ["JWT_SECRET_KEY", "REDIS_URL", "PERPLEXITY_API_KEY"]
    missing = []
    for var in required_vars:
        val = os.getenv(var)
        if not val:
            missing.append(var)
        elif var == "JWT_SECRET_KEY" and val == "your-secret-key-change-in-production":
            raise RuntimeError(f"Environment variable {var} is set to default placeholder; must change in production")

    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    logger.info("✓ Environment validation passed")


def initialize_memory_systems():
    """Initialize global memory systems and reasoning engine."""
    global stm_manager, ltm_manager, pdf_loader, reasoning_engine, db, conversation_manager, voice_handler

    try:
        jwt_secret = os.getenv("JWT_SECRET_KEY")
        if not jwt_secret or jwt_secret == "your-secret-key-change-in-production":
            raise RuntimeError("JWT_SECRET_KEY is required and must be set to a secure value")

        
        db = get_database()

        
        
        redis_url = os.getenv("REDIS_URL")
        stm_ttl = int(os.getenv("STM_TTL", "1800"))
        if not redis_url:
            raise RuntimeError("REDIS_URL is required. STM must use Redis only.")

        stm_manager = STMManager(redis_url=redis_url, ttl_seconds=stm_ttl, max_size=50)

        
        pinecone_api_key = os.getenv("PINECONE_API_KEY")
        if not pinecone_api_key:
            logger.warning("PINECONE_API_KEY not set — LTM disabled.")
            ltm_manager = None
        else:
            try:
                ltm_manager = LTMManager(
                    api_key=pinecone_api_key,
                    cloud=os.getenv("PINECONE_CLOUD", "aws"),
                    region=os.getenv("PINECONE_REGION", "us-east-1"),
                    index_name="cognitiveai-ltm"
                )
            except Exception as e:
                logger.warning(f"Failed to initialize LTM: {e}")
                ltm_manager = None

        
        pdf_loader = PDFLoader(ltm_manager)

        
        perplexity_api_key = os.getenv("PERPLEXITY_API_KEY")
        if not perplexity_api_key:
            logger.warning("PERPLEXITY_API_KEY not set. Chat will not work.")

        reasoning_engine = CognitiveReasoningEngine(
            stm_manager=stm_manager,
            ltm_manager=ltm_manager,
            pdf_loader=pdf_loader,
            perplexity_api_key=perplexity_api_key or ""
        )

        # Initialize conversation manager
        conversation_manager = ConversationManager(db)

        # Initialize voice WebSocket handler
        voice_handler = VoiceWebSocketHandler(
            reasoning_engine=reasoning_engine,
            conversation_manager=conversation_manager,
            database=db,
            stm_manager=stm_manager,
            ltm_manager=ltm_manager,
            pdf_loader=pdf_loader
        )

        logger.info("Memory systems initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize memory systems: {e}")
        logger.warning("Continuing without full initialization.")


@app.on_event("startup")
async def startup_event():
    """Initialize systems on startup with env validation."""
    try:
        validate_environment()
        initialize_memory_systems()
        
        # Initialize voice models at startup (MANDATORY for low latency)
        # Models are loaded BEFORE server accepts requests
        if ModelManager.is_voice_enabled():
            try:
                logger.info("Initializing voice models at startup...")
                init_result = ModelManager.initialize_at_startup()
                logger.info(f"Voice models ready: {init_result}")
            except Exception as e:
                logger.error(f"Voice model initialization failed: {e}")
                # Don't fail startup - voice will be unavailable but app runs
                logger.warning("Voice functionality will be unavailable")
        
        logger.info("✓ Startup complete: All systems initialized and validated")
    except RuntimeError as e:
        logger.critical(f"✗ Startup failed: {e}")
        raise
    except Exception as e:
        logger.critical(f"✗ Unexpected startup error: {e}")
        raise






@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the static frontend HTML."""
    static_path = Path(__file__).parent.parent / "static" / "index.html"
    if static_path.exists():
        return static_path.read_text()
    return {"message": "CognitiveAI API (Multi-User)", "status": "running"}


@app.get("/health")
async def health_check():
    """Comprehensive health check endpoint with service-level diagnostics."""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }

    # Database health check (PostgreSQL/SQLite)
    db_health = {"available": db is not None, "status": "unknown"}
    if db:
        try:
            from backend.db_config import check_database_connection, get_pool_status
            if check_database_connection():
                db_health["status"] = "ok"
                # Add connection pool stats if available
                pool_stats = get_pool_status()
                if pool_stats:
                    db_health["pool"] = pool_stats
            else:
                db_health["status"] = "connection_failed"
                health_status["status"] = "degraded"
        except Exception as e:
            db_health["status"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    health_status["services"]["database"] = db_health

    # Redis health check
    redis_health = {"available": stm_manager is not None, "status": "unknown"}
    if stm_manager:
        try:
            from backend.redis_client import get_redis
            r = get_redis()
            r.ping()
            redis_health["status"] = "ok"
        except Exception as e:
            redis_health["status"] = f"error: {str(e)}"
            health_status["status"] = "degraded"
    health_status["services"]["redis"] = redis_health

    # Cache health check (Redis caching layer)
    cache_health = {"available": True, "status": "unknown"}
    try:
        from backend.cache import get_cache
        cache = get_cache()
        cache_stats = cache.health_check()
        cache_health.update(cache_stats)
    except Exception as e:
        cache_health["status"] = f"error: {str(e)}"
    health_status["services"]["cache"] = cache_health

    # Pinecone health check
    pinecone_health = {"available": ltm_manager is not None, "status": "unknown"}
    if ltm_manager:
        try:
            # Basic availability check
            pinecone_health["status"] = "ok"
        except Exception as e:
            pinecone_health["status"] = f"error: {str(e)}"
            
    health_status["services"]["pinecone"] = pinecone_health

    # Perplexity health check — use a real minimal POST (HEAD returns 405)
    api_key = (reasoning_engine.perplexity_api_key if reasoning_engine else None) or os.getenv("PERPLEXITY_API_KEY", "")
    perplexity_health = {"available": bool(api_key), "status": "unknown"}
    if perplexity_health["available"]:
        try:
            import httpx
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 1
                    }
                )
                if resp.status_code == 200:
                    perplexity_health["status"] = "ok"
                elif resp.status_code == 401:
                    perplexity_health["status"] = "unauthorized — check API key"
                    health_status["status"] = "degraded"
                elif resp.status_code == 429:
                    perplexity_health["status"] = "ok (rate_limited)"
                elif resp.status_code >= 500:
                    perplexity_health["status"] = f"server_error ({resp.status_code})"
                    health_status["status"] = "degraded"
                else:
                    perplexity_health["status"] = f"unexpected ({resp.status_code})"
        except Exception as e:
            perplexity_health["status"] = f"unreachable: {str(e)}"
            health_status["status"] = "degraded"
    else:
        perplexity_health["status"] = "not_configured"
    health_status["services"]["perplexity"] = perplexity_health

    # Systems overview
    health_status["systems"] = {
        "database": db is not None,
        "stm": stm_manager is not None,
        "ltm": ltm_manager is not None,
        "pdf_loader": pdf_loader is not None,
        "reasoning_engine": reasoning_engine is not None
    }

    return health_status


@app.get("/test-perplexity")
async def test_perplexity():
    """
    Test the Perplexity API connection by making a real minimal call.
    Returns detailed success/error info without requiring authentication.
    """
    import httpx

    api_key = (reasoning_engine.perplexity_api_key if reasoning_engine else None) or os.getenv("PERPLEXITY_API_KEY", "")

    if not api_key:
        raise HTTPException(status_code=503, detail="PERPLEXITY_API_KEY not configured")

    # Log the first/last 6 chars so we can verify the key loaded correctly
    key_preview = f"{api_key[:10]}...{api_key[-6:]}" if len(api_key) > 16 else "<too short>"
    logger.info(f"Testing Perplexity with key preview: {key_preview}")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [{"role": "user", "content": "Reply with just the word: OK"}],
                    "max_tokens": 5
                }
            )

        if resp.status_code == 200:
            data = resp.json()
            answer = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return {
                "success": True,
                "status_code": 200,
                "model": data.get("model"),
                "response": answer,
                "key_preview": key_preview,
                "message": "Perplexity API is working correctly"
            }
        elif resp.status_code == 401:
            return {
                "success": False,
                "status_code": 401,
                "key_preview": key_preview,
                "error": "Unauthorized — API key is invalid or expired",
                "perplexity_message": resp.text
            }
        elif resp.status_code == 429:
            return {
                "success": True,
                "status_code": 429,
                "key_preview": key_preview,
                "message": "API key is valid but rate limited"
            }
        else:
            return {
                "success": False,
                "status_code": resp.status_code,
                "key_preview": key_preview,
                "error": resp.text
            }
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Perplexity API request timed out")
    except Exception as e:
        logger.error(f"Perplexity test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Perplexity API test failed: {str(e)}")





@app.post("/auth/signup", response_model=AuthResponse)
async def signup(request: SignupRequest):
    """
    Create a new user account.

    Validates username/password, stores hashed password in DB, returns JWT token.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        
        is_valid_username, username_error = AuthService.validate_username(request.username)
        if not is_valid_username:
            raise HTTPException(status_code=400, detail=username_error)

        is_valid_password, password_error = AuthService.validate_password(request.password)
        if not is_valid_password:
            raise HTTPException(status_code=400, detail=password_error)

        
        if db.username_exists(request.username):
            raise HTTPException(status_code=409, detail="Username already exists")

        
        password_hash = AuthService.hash_password(request.password)

        
        user_id = AuthService.generate_user_id()
        user = db.create_user(
            user_id=user_id,
            username=request.username,
            password_hash=password_hash,
            email=request.email
        )

        

        
        token = AuthService.generate_token(user_id, request.username)

        logger.info(f"New user created: {request.username} (ID: {user_id})")

        return AuthResponse(
            success=True,
            message="User created successfully",
            token=token,
            user=user.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Signup failed")


@app.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    Authenticate a user and return a JWT token.

    Verifies username and password, returns token on success.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        
        user = db.get_user_by_username(request.username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        
        if not AuthService.verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid username or password")

        

        
        token = AuthService.generate_token(user.user_id, user.username)

        logger.info(f"User logged in: {request.username}")

        return AuthResponse(
            success=True,
            message="Login successful",
            token=token,
            user=user.to_dict()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/auth/logout", response_model=AuthResponse)
async def logout(user_id: str = Depends(get_current_user)):
    """
    Logout endpoint.

    Clears user's TEMPORARY session data (STM, PDF text) while PRESERVING
    persistent data (chat history via localStorage, LTM knowledge).
    
    Frontend should discard token after receiving this.
    """
    try:
        # Only clear TEMPORARY session data, not persistent memories
        
        # 1. Clear short-term memory (conversation session data)
        if stm_manager:
            stm_manager.clear_memories(user_id)
            logger.info(f"Cleared STM for user {user_id}")

        # 2. Clear conversation context (if tracking in reasoning engine)
        if reasoning_engine:
            try:
                reasoning_engine.clear_short_term_memory_for_user(user_id)
                reasoning_engine.reset_conversation_context_for_user(user_id)
            except Exception:
                # Engine is stateless, these are no-ops
                pass

        # 3. Clear temporary PDF extraction text from Redis
        # Note: PDF metadata in database is PRESERVED
        try:
            from backend.redis_client import get_redis
            r = get_redis()
            
            # Delete temporary PDF extracted text
            pattern = f"pdf:{user_id}:*"
            deleted_count = 0
            for key in r.scan_iter(match=pattern):
                try:
                    r.delete(key)
                    deleted_count += 1
                except Exception:
                    pass
            if deleted_count > 0:
                logger.info(f"Cleared {deleted_count} temporary PDF extractions for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not clear Redis PDF data: {e}")

        # DO NOT delete LTM memories - these are persistent and should be preserved
        # LTM (long-term memories and learned facts) survives logout
        logger.info(f"User logged out: {user_id} (LTM preserved for persistence)")

        return AuthResponse(
            success=True,
            message="Logout successful. Client must discard the access token; no refresh tokens are used. Your chat history and learned knowledge are preserved.",
            client_discard_token=True
        )

    except Exception as e:
        logger.error(f"Logout error for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


@app.get("/auth/me")
async def get_current_user_info(user_id: str = Depends(get_current_user)):
    """Get current user's information."""
    if not db:
        raise HTTPException(status_code=503, detail="Database not initialized")

    try:
        user = db.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user info")


@app.get("/conversations")
async def list_conversations(
    user_id: str = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0
):
    """
    List all conversations for the current user.
    
    Returns conversations ordered by most recent first (updated_at DESC).
    Each conversation includes title, timestamps, and conversation_id.
    """
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="Conversation manager not initialized")
    
    try:
        conversations = conversation_manager.list_conversations(user_id, limit=limit, offset=offset)
        logger.info(f"Retrieved {len(conversations)} conversations for user {user_id}")
        return {
            "success": True,
            "conversations": conversations,
            "count": len(conversations)
        }
    except Exception as e:
        logger.error(f"Failed to list conversations for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list conversations")


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0
):
    """
    Get all messages for a specific conversation.
    
    Returns messages ordered by timestamp (oldest first).
    Verifies that the conversation belongs to the requesting user.
    """
    if not conversation_manager or not db:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    try:
        # Verify conversation belongs to user
        conversation = conversation_manager.get_conversation(conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Get messages for this conversation
        messages = db.get_messages_for_conversation(conversation_id, limit=limit, offset=offset)
        logger.info(f"Retrieved {len(messages)} messages for conversation {conversation_id}")
        
        return {
            "success": True,
            "conversation": conversation,
            "messages": messages,
            "count": len(messages)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve messages for conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation messages")


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a conversation and all its messages.
    
    Verifies that the conversation belongs to the requesting user.
    """
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="Conversation manager not initialized")
    
    try:
        success = conversation_manager.delete_conversation(conversation_id, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        return {
            "success": True,
            "message": "Conversation deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete conversation")


@app.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    title: str,
    user_id: str = Depends(get_current_user)
):
    """
    Update conversation title.
    
    Verifies that the conversation belongs to the requesting user.
    """
    if not conversation_manager:
        raise HTTPException(status_code=503, detail="Conversation manager not initialized")
    
    try:
        # Verify conversation belongs to user
        conversation = conversation_manager.get_conversation(conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Update title
        success = conversation_manager.update_conversation_title(conversation_id, title)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update title")
        
        return {
            "success": True,
            "message": "Conversation title updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update conversation {conversation_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation")





@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Main chat endpoint (user-scoped).

    Processes user messages through the cognitive reasoning engine.
    All data is isolated to the authenticated user.
    """
    if not reasoning_engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not initialized")

    try:
        
        stm_list = []
        try:
            if stm_manager:
                raw_stm = stm_manager.get_relevant_memories(user_id, request.message, limit=5)
                for m in raw_stm:
                    try:
                        stm_list.append({
                            "id": getattr(m, "id", None),
                            "content": getattr(m, "content", str(m)),
                            "timestamp": getattr(m, "timestamp", time.time()),
                            "importance": getattr(m, "importance", 1.0),
                            "metadata": getattr(m, "metadata", {})
                        })
                    except Exception:
                        stm_list.append({"content": str(m)})
        except Exception:
            stm_list = []

        ltm_list = []
        try:
            if ltm_manager:
                ltm_list = ltm_manager.search_memories(request.message, limit=5, user_id=user_id)
        except Exception:
            ltm_list = []

        pdf_snippets = []
        try:
            if pdf_loader:
                if request.doc_id:
                    chunks = pdf_loader.search_pdf_knowledge(query=request.message, document_id=request.doc_id, limit=3, user_id=user_id)
                else:
                    chunks = pdf_loader.search_pdf_knowledge(query=request.message, limit=3, user_id=user_id)
                for c in chunks:
                    content = c.get("content", "")[:300]
                    pdf_snippets.append(content)
        except Exception:
            pdf_snippets = []

        
        result = await reasoning_engine.process_message(
            user_message=request.message,
            user_id=user_id,
            stm_memories=stm_list,
            ltm_memories=ltm_list,
            pdf_snippets=pdf_snippets,
            current_emotion=request.emotion
        )

        
        try:
            actions = result.get("memory_actions", []) if isinstance(result, dict) else []
            for action in actions:
                if not isinstance(action, dict):
                    continue
                if action.get("type") == "stm" and stm_manager:
                    try:
                        stm_manager.add_memory(user_id, action.get("content", ""), importance=action.get("importance", 0.8))
                    except Exception:
                        pass
                elif action.get("type") == "ltm" and ltm_manager:
                    try:
                        ltm_manager.add_memory(
                            action.get("content", ""),
                            memory_type=action.get("memory_type", "note"),
                            metadata=action.get("metadata", {"user_id": user_id}),
                            importance=action.get("importance", 0.7),
                            user_id=user_id
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        # Conversation management: create new or continue existing
        import time
        try:
            if not request.conversation_id:
                # Create new conversation
                if not conversation_manager:
                    raise HTTPException(status_code=503, detail="Conversation manager not initialized")
                
                conversation_id = conversation_manager.create_conversation(user_id)
                logger.info(f"Created new conversation {conversation_id} for user {user_id}")
                
                # Generate title from first message
                title = conversation_manager.generate_title_from_message(request.message)
                conversation_manager.update_conversation_title(conversation_id, title)
                logger.info(f"Set conversation title: {title}")
            else:
                # Continue existing conversation
                conversation_id = request.conversation_id
                
                # Verify conversation belongs to user
                conversation = conversation_manager.get_conversation(conversation_id, user_id)
                if not conversation:
                    raise HTTPException(status_code=404, detail="Conversation not found")
                
                # Update conversation timestamp
                conversation_manager.update_conversation_timestamp(conversation_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Conversation management error: {e}")
            raise HTTPException(status_code=500, detail="Failed to manage conversation")

        # Clean the response before storing and returning
        cleaned_response = clean_response(result.get("response", ""))
        
        # Store user message and assistant response in SQL for chat history
        try:
            if db:
                timestamp = time.time()
                # Store user message
                db.add_message(conversation_id, user_id, "user", request.message, timestamp, metadata={"doc_id": request.doc_id})
                # Store cleaned assistant response
                db.add_message(conversation_id, user_id, "assistant", cleaned_response, timestamp + 0.001, metadata={"reasoning": result.get("reasoning", {})})
                logger.debug(f"Stored messages in conversation {conversation_id}")
        except Exception as e:
            logger.warning(f"Failed to store messages in SQL for user {user_id}: {e}")

        return ChatResponse(
            response=cleaned_response,
            conversation_id=conversation_id,
            reasoning=result.get("reasoning", {}),
            metadata={**result.get("metadata", {}), "user_id": user_id}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")




@app.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Streaming chat endpoint (user-scoped).
    
    Streams response chunks as Server-Sent Events (SSE) for progressive rendering.
    All data is isolated to the authenticated user.
    """
    if not reasoning_engine:
        raise HTTPException(status_code=503, detail="Reasoning engine not initialized")

    async def generate_stream():
        """Generate SSE stream with response chunks and metadata."""
        full_response = ""
        conversation_id = None
        
        try:
            # Retrieve memories (same as regular chat)
            stm_list = []
            try:
                if stm_manager:
                    raw_stm = stm_manager.get_relevant_memories(user_id, request.message, limit=5)
                    for m in raw_stm:
                        try:
                            stm_list.append({
                                "id": getattr(m, "id", None),
                                "content": getattr(m, "content", str(m)),
                                "timestamp": getattr(m, "timestamp", time.time()),
                                "importance": getattr(m, "importance", 1.0),
                                "metadata": getattr(m, "metadata", {})
                            })
                        except Exception:
                            stm_list.append({"content": str(m)})
            except Exception:
                stm_list = []

            ltm_list = []
            try:
                if ltm_manager:
                    ltm_list = ltm_manager.search_memories(request.message, limit=5, user_id=user_id)
            except Exception:
                ltm_list = []

            pdf_snippets = []
            try:
                if pdf_loader:
                    if request.doc_id:
                        chunks = pdf_loader.search_pdf_knowledge(query=request.message, document_id=request.doc_id, limit=3, user_id=user_id)
                    else:
                        chunks = pdf_loader.search_pdf_knowledge(query=request.message, limit=3, user_id=user_id)
                    for c in chunks:
                        content = c.get("content", "")[:300]
                        pdf_snippets.append(content)
            except Exception:
                pdf_snippets = []

            # Process input and plan response
            processed_input = reasoning_engine._process_input(request.message, user_id, request.emotion)
            recalled_info = {
                "stm_memories": stm_list,
                "ltm_memories": ltm_list,
                "pdf_knowledge": pdf_snippets,
                "user_profile": {}
            }
            response_plan = reasoning_engine._plan_response(processed_input, recalled_info)

            # Stream response chunks
            response_generator = await reasoning_engine._generate_response(
                response_plan, processed_input, recalled_info, stream=True
            )
            
            async for chunk in response_generator:
                # Stream raw chunks without cleaning to preserve spacing
                # Cleaning will happen on the full response before database storage
                full_response += chunk
                # Send raw chunk as SSE
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Determine memory actions
            memory_actions = reasoning_engine._determine_memory_actions(
                request.message, full_response, recalled_info, response_plan, user_id
            )

            # Execute memory actions
            try:
                for action in memory_actions:
                    if not isinstance(action, dict):
                        continue
                    if action.get("type") == "stm" and stm_manager:
                        try:
                            stm_manager.add_memory(user_id, action.get("content", ""), importance=action.get("importance", 0.8))
                        except Exception:
                            pass
                    elif action.get("type") == "ltm" and ltm_manager:
                        try:
                            ltm_manager.add_memory(
                                action.get("content", ""),
                                memory_type=action.get("memory_type", "note"),
                                metadata=action.get("metadata", {"user_id": user_id}),
                                importance=action.get("importance", 0.7),
                                user_id=user_id
                            )
                        except Exception:
                            pass
            except Exception:
                pass

            # Conversation management
            try:
                if not request.conversation_id:
                    if not conversation_manager:
                        raise HTTPException(status_code=503, detail="Conversation manager not initialized")
                    
                    conversation_id = conversation_manager.create_conversation(user_id)
                    logger.info(f"Created new conversation {conversation_id} for user {user_id}")
                    
                    title = conversation_manager.generate_title_from_message(request.message)
                    conversation_manager.update_conversation_title(conversation_id, title)
                else:
                    conversation_id = request.conversation_id
                    conversation = conversation_manager.get_conversation(conversation_id, user_id)
                    if not conversation:
                        raise HTTPException(status_code=404, detail="Conversation not found")
                    conversation_manager.update_conversation_timestamp(conversation_id)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Conversation management error: {e}")

            # Clean the FULL response before storing in database
            cleaned_full_response = clean_response(full_response)

            # Store messages in database with cleaned response
            try:
                if db:
                    timestamp = time.time()
                    db.add_message(conversation_id, user_id, "user", request.message, timestamp, metadata={"doc_id": request.doc_id})
                    db.add_message(conversation_id, user_id, "assistant", cleaned_full_response, timestamp + 0.001, metadata={"reasoning": response_plan})
            except Exception as e:
                logger.error(f"CRITICAL: Failed to store messages in SQL for user {user_id}: {e}", exc_info=True)
                # We attempt to yield an error event so frontend knows persistence failed (optional)
                # yield f"data: {json.dumps({'type': 'error', 'message': 'Message persistence failed'})}\n\n"

            # Send final metadata event
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"

        except Exception as e:
            logger.error(f"Streaming chat error for user {user_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate_stream(), media_type="text/event-stream")



@app.post("/upload_pdf")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    """
    Upload and process a PDF file (user-scoped).

    PDF content is extracted, validated, and stored server-side for semantic search.
    Frontend receives only a doc_id reference and can use it in subsequent chat messages.
    """
    if not pdf_loader:
        raise HTTPException(status_code=503, detail="PDF loader not initialized")

    
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        
        content = await file.read()
        max_upload_size = 5 * 1024 * 1024
        if len(content) > max_upload_size:
            raise HTTPException(status_code=400, detail=f"Uploaded PDF exceeds maximum allowed size of 5 MB (got {len(content) / (1024*1024):.1f} MB)")
        
        if len(content) < 100:
            raise HTTPException(status_code=400, detail="Uploaded file is too small or empty")

        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        
        import uuid as _uuid
        doc_id = str(_uuid.uuid4())
        
        logger.info(f"PDF upload initiated: {file.filename} (user {user_id}, doc_id {doc_id}, size {len(content) / 1024:.1f} KB)")

        
        background_tasks.add_task(
            process_pdf_background,
            temp_file_path,
            file.filename,
            doc_id,
            user_id
        )

        return {
            "message": f"PDF '{file.filename}' received and is being processed. Use doc_id in chat to reference it.",
            "filename": file.filename,
            "status": "processing",
            "doc_id": doc_id,
            "size_kb": len(content) / 1024
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF upload error for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF upload failed: {str(e)}")


def process_pdf_background(
    file_path: str,
    filename: str,
    doc_id: str,
    user_id: str
):
    """Process PDF in background, store extracted text and chunks for LLM usage."""
    try:
        logger.info(f"Starting PDF processing for {filename} (user {user_id}, doc_id {doc_id})")
        
        # Extract and validate text
        extracted = pdf_loader.extract_text(file_path)
        
        max_bytes = 200 * 1024
        extracted_bytes = len(extracted.encode("utf-8"))
        if extracted_bytes > max_bytes:
            logger.error(f"Extracted text for {filename} (user {user_id}) is {extracted_bytes / 1024:.1f} KB, exceeds limit of 200 KB")
            Path(file_path).unlink(missing_ok=True)
            return
        
        logger.info(f"Extracted {extracted_bytes / 1024:.1f} KB from {filename}")

        # Store extracted text in Redis for quick retrieval
        try:
            from backend.redis_client import get_redis
            import os
            r = get_redis()
            key = f"pdf:{user_id}:{doc_id}"
            r.set(key, extracted)
            r.expire(key, int(os.getenv("STM_TTL", "1800")))
            logger.info(f"Stored extracted PDF text in Redis: {key}")
        except Exception as redis_error:
            logger.warning(f"Could not store extracted PDF text in Redis: {redis_error}")

        logger.info(f"Loading PDF into LTM for {filename} (user {user_id})")

        # Load into LTM for semantic search and chunking
        if pdf_loader:
            try:
                pdf_loader.load_pdf(
                    file_path,
                    metadata={"user_id": user_id, "filename": filename},
                    doc_id=doc_id,
                    user_id=user_id
                )
                logger.info(f"Successfully loaded PDF {filename} into LTM for user {user_id}")
            except ValueError as val_error:
                logger.error(f"PDF validation failed for {filename}: {val_error}")
                # Clean up Redis if LTM load fails
                try:
                    from backend.redis_client import get_redis
                    r = get_redis()
                    r.delete(f"pdf:{user_id}:{doc_id}")
                except Exception:
                    pass
                return
            except Exception as load_error:
                logger.error(f"Failed to load PDF {filename} into LTM: {load_error}")
                # Clean up Redis if LTM load fails
                try:
                    from backend.redis_client import get_redis
                    r = get_redis()
                    r.delete(f"pdf:{user_id}:{doc_id}")
                except Exception:
                    pass
                return
            finally:
                # Always clean up temp file
                try:
                    Path(file_path).unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to delete temp file {file_path}: {cleanup_error}")
        else:
            logger.error("PDF loader not initialized")
            Path(file_path).unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Background PDF processing failed for {filename} (user {user_id}): {e}", exc_info=True)
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass






@app.get("/memory/stm")
async def get_stm_memories(
    limit: int = 10,
    user_id: str = Depends(get_current_user)
):
    """Get user's recent short-term memories."""
    if not stm_manager:
        raise HTTPException(status_code=503, detail="STM manager not initialized")

    try:
        memories = stm_manager.get_all_memories(user_id)
        recent_memories = memories[-limit:]

        return {
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "importance": m.importance,
                    "metadata": m.metadata
                }
                for m in recent_memories
            ],
            "total_count": len(memories)
        }

    except Exception as e:
        logger.error(f"Error getting STM memories for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="STM retrieval failed")


@app.post("/memory/clear_stm")
async def clear_stm(user_id: str = Depends(get_current_user)):
    """Clear user's short-term memory."""
    if not stm_manager:
        raise HTTPException(status_code=503, detail="STM manager not initialized")

    try:
        stm_manager.clear_memories(user_id)
        return {"message": f"STM cleared for user {user_id}"}

    except Exception as e:
        logger.error(f"Error clearing STM for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="STM clear failed")


@app.get("/memory/ltm/search")
async def search_ltm_memories(
    query: str,
    limit: int = 10,
    user_id: str = Depends(get_current_user)
):
    """Search user's long-term memories."""
    if not ltm_manager:
        raise HTTPException(status_code=503, detail="LTM manager not initialized")

    try:
        
        results = ltm_manager.search_memories(
            query,
            limit=limit,
            user_id=user_id
        )

        return {
            "query": query,
            "results": results,
            "count": len(results)
        }

    except Exception as e:
        logger.error(f"Error searching LTM for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="LTM search failed")


@app.get("/pdf/documents")
async def get_pdf_documents(user_id: str = Depends(get_current_user)):
    """Get user's uploaded PDF documents."""
    if not pdf_loader:
        raise HTTPException(status_code=503, detail="PDF loader not initialized")

    try:
        documents = pdf_loader.get_pdf_documents(user_id)
        return {"documents": documents, "count": len(documents)}

    except Exception as e:
        logger.error(f"Error getting PDF documents for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="PDF documents retrieval failed")


@app.delete("/pdf/{document_id}")
async def delete_pdf_document(
    document_id: str,
    user_id: str = Depends(get_current_user)
):
    """Delete user's PDF document."""
    if not pdf_loader:
        raise HTTPException(status_code=503, detail="PDF loader not initialized")

    try:
        pdf_loader.delete_pdf(document_id, user_id)
        
        try:
            from backend.redis_client import get_redis
            r = get_redis()
            r.delete(f"pdf:{user_id}:{document_id}")
        except Exception:
            pass

        return {"message": f"PDF document {document_id} deleted"}

    except Exception as e:
        logger.error(f"Error deleting PDF {document_id} for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="PDF deletion failed")






@app.get("/system/stats")
async def system_stats(user_id: str = Depends(get_current_user)):
    """Get system statistics (user-scoped)."""
    try:
        
        pdf_count = 0
        try:
            from backend.redis_client import get_redis
            r = get_redis()
            pattern = f"pdf:{user_id}:*"
            for _ in r.scan_iter(match=pattern):
                pdf_count += 1
        except Exception:
            pdf_count = 0

        stats = {
            "health": await health_check(),
            "user_id": user_id,
            "stm_count": len(stm_manager.get_all_memories(user_id)) if stm_manager else 0,
            "pdf_count": pdf_count
        }
        return stats

    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        raise HTTPException(status_code=500, detail="System stats failed")


# ============================================================================
# VOICE AGENT ENDPOINTS
# ============================================================================

@app.websocket("/ws/voice")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT authentication token")
):
    """
    WebSocket endpoint for real-time voice chat.
    
    Protocol:
    - Client → Server: {"type": "audio", "data": "<base64_audio>"}
    - Server → Client: {"type": "status", "state": "listening|processing|speaking", "message": "..."}
    - Server → Client: {"type": "transcript", "text": "...", "language": "en"}
    - Server → Client: {"type": "audio", "data": "<base64_audio>", "format": "wav"}
    - Server → Client: {"type": "error", "message": "...", "code": "..."}
    - Server → Client: {"type": "conversation_update", "conversation_id": "...", "title": "..."}
    
    Query Parameters:
    - token: JWT authentication token
    """
    if not voice_handler:
        await websocket.close(code=1011, reason="Voice functionality not available")
        return
    
    # Verify token
    try:
        payload = AuthService.verify_token(token)
        if not payload:
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
        
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=1008, reason="Token missing user_id")
            return
    
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # Handle the voice session
    try:
        await voice_handler.handle_connection(
            websocket=websocket,
            user_id=user_id,
            conversation_id=None  # Will be created or continued within the session
        )
    except Exception as e:
        logger.error(f"Voice session error: {e}")
        try:
            await websocket.close(code=1011, reason=f"Session error: {str(e)}")
        except Exception:
            pass


@app.get("/voice/info")
async def get_voice_info(user_id: str = Depends(get_current_user)):
    """
    Get voice functionality information and status.
    
    Returns model info, capabilities, and current session stats.
    """
    try:
        model_info = ModelManager.get_model_info()
        
        # Get active session info
        session_info = {
            'active_sessions': voice_handler.get_session_count() if voice_handler else 0,
            'session_ids': voice_handler.get_active_sessions() if voice_handler else []
        }
        
        return {
            'voice_enabled': model_info.get('voice_enabled', False),
            'models': model_info,
            'sessions': session_info,
            'capabilities': {
                'stt': model_info.get('stt_loaded', False),
                'tts': model_info.get('tts_loaded', False),
                'streaming': True,
                'languages': ['en']  # Can be expanded based on model capabilities
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting voice info: {e}")
        raise HTTPException(status_code=500, detail="Failed to get voice info")


@app.post("/voice/preload")
async def preload_voice_models(user_id: str = Depends(get_current_user)):
    """
    Preload voice models (STT and TTS).
    
    This endpoint can be called to warm up the models before first use.
    Useful for reducing latency on first voice interaction.
    """
    try:
        logger.info(f"Preloading voice models for user {user_id}")
        ModelManager.preload_models()
        
        return {
            'success': True,
            'message': 'Voice models preloaded successfully',
            'model_info': ModelManager.get_model_info()
        }
    
    except Exception as e:
        logger.error(f"Failed to preload voice models: {e}")
        raise HTTPException(status_code=500, detail=f"Model preload failed: {str(e)}")


@app.websocket("/ws/voice")
async def voice_websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    conversation_id: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for real-time voice chat.
    
    Handles bidirectional audio streaming for voice conversations.
    Requires authentication via token query parameter.
    """
    if not voice_handler:
        await websocket.close(code=1011, reason="Voice handler not initialized")
        return
    
    try:
        # Verify token
        payload = AuthService.verify_token(token)
        if not payload:
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
        
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=1008, reason="Token missing user_id")
            return
        
        logger.info(f"Voice WebSocket connection from user {user_id}")
        
        # Handle connection
        await voice_handler.handle_connection(
            websocket=websocket,
            user_id=user_id,
            conversation_id=conversation_id
        )
    
    except Exception as e:
        logger.error(f"Voice WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except:
            pass




if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
