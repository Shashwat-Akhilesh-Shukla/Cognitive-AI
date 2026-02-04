"""
Model Manager for Voice Agent

Handles startup-only loading and lifecycle management of STT and TTS models.
Implements singleton pattern with fail-fast initialization.

CRITICAL: Models MUST be loaded at application startup via initialize_at_startup().
Lazy loading is disabled to prevent first-request latency spikes.
"""

import os
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Import GPU detector for automatic device configuration
try:
    from backend.gpu_detector import detect_gpu, log_gpu_status
    GPU_DETECTOR_AVAILABLE = True
except ImportError:
    logger.warning("GPU detector not available, defaulting to CPU")
    GPU_DETECTOR_AVAILABLE = False


class ModelNotInitializedError(Exception):
    """Raised when attempting to access models before startup initialization."""
    pass


class ModelManager:
    """
    Centralized manager for STT and TTS models.
    
    IMPORTANT: Call initialize_at_startup() during application startup.
    Models are NOT lazily loaded - they must be pre-initialized.
    
    Features:
    - Startup-only loading (fail-fast)
    - Singleton pattern: one instance per model type
    - Automatic caching to disk
    - Environment-based configuration
    """
    
    _instance = None
    _stt_model = None
    _tts_model = None
    _initialized = False
    _initialization_time_ms = 0
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def get_cache_dir(cls) -> Path:
        """Get the model cache directory from environment or use default."""
        cache_dir = os.getenv("MODEL_CACHE_DIR", "backend/models")
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        return cache_path
    
    @classmethod
    def is_voice_enabled(cls) -> bool:
        """Check if voice functionality is enabled."""
        return os.getenv("VOICE_ENABLED", "true").lower() == "true"
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if models have been initialized at startup."""
        return cls._initialized
    
    @classmethod
    def _ensure_initialized(cls):
        """Raise error if models not initialized. Call this before returning models."""
        if not cls._initialized:
            raise ModelNotInitializedError(
                "Voice models not initialized. Call ModelManager.initialize_at_startup() "
                "during application startup before handling voice requests."
            )
    
    @classmethod
    def initialize_at_startup(cls) -> dict:
        """
        Initialize all voice models at application startup.
        
        MUST be called during FastAPI startup event.
        Fails fast if any model fails to load.
        
        Returns:
            dict: Initialization timing and status
            
        Raises:
            Exception: If any model fails to load (fail-fast)
        """
        if cls._initialized:
            logger.warning("Models already initialized, skipping re-initialization")
            return {"status": "already_initialized", "time_ms": cls._initialization_time_ms}
        
        if not cls.is_voice_enabled():
            logger.info("Voice functionality disabled (VOICE_ENABLED=false), skipping model init")
            cls._initialized = True
            return {"status": "disabled", "time_ms": 0}
        
        start_time = time.perf_counter()
        
        # Detect and log GPU status
        if GPU_DETECTOR_AVAILABLE:
            logger.info("==" * 25)
            gpu_info = log_gpu_status()
            logger.info("==" * 25)
        
        try:
            # Load STT model
            logger.info("=" * 50)
            logger.info("[STARTUP] Loading STT model...")
            stt_start = time.perf_counter()
            cls._load_stt_model()
            stt_time = (time.perf_counter() - stt_start) * 1000
            logger.info(f"[STARTUP] STT model loaded in {stt_time:.0f}ms")
            
            # Load TTS model
            logger.info("[STARTUP] Loading TTS model...")
            tts_start = time.perf_counter()
            cls._load_tts_model()
            tts_time = (time.perf_counter() - tts_start) * 1000
            logger.info(f"[STARTUP] TTS model loaded in {tts_time:.0f}ms")
            
            total_time = (time.perf_counter() - start_time) * 1000
            cls._initialization_time_ms = total_time
            cls._initialized = True
            
            logger.info("=" * 50)
            logger.info(f"[STARTUP] ✓ All voice models initialized in {total_time:.0f}ms")
            logger.info("=" * 50)
            
            return {
                "status": "success",
                "stt_time_ms": stt_time,
                "tts_time_ms": tts_time,
                "total_time_ms": total_time
            }
            
        except Exception as e:
            logger.error("=" * 50)
            logger.error(f"[STARTUP] ✗ FATAL: Voice model initialization failed: {e}")
            logger.error("[STARTUP] Voice functionality will be unavailable")
            logger.error("=" * 50)
            # Re-raise to fail fast - startup should abort
            raise
    
    @classmethod
    def _load_stt_model(cls):
        """Internal: Load STT model. Called only during startup."""
        from .stt import WhisperSTT
        
        # Get GPU-aware configuration
        if GPU_DETECTOR_AVAILABLE:
            from backend.gpu_detector import get_whisper_config
            gpu_config = get_whisper_config()
            device = os.getenv("WHISPER_DEVICE", gpu_config['device'])
            compute_type = os.getenv("WHISPER_COMPUTE_TYPE", gpu_config['compute_type'])
        else:
            # Fallback to environment or defaults
            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        
        model_name = os.getenv("WHISPER_MODEL", "openai/whisper-medium")
        
        logger.info(f"  Model: {model_name}")
        logger.info(f"  Device: {device}, Compute: {compute_type}")
        
        cls._stt_model = WhisperSTT(
            model_name=model_name,
            cache_dir=str(cls.get_cache_dir()),
            device=device,
            compute_type=compute_type
        )
    
    @classmethod
    def _load_tts_model(cls):
        """Internal: Load TTS model. Called only during startup."""
        from .tts import CoquiTTS
        
        model_name = os.getenv("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
        
        logger.info(f"  Model: {model_name}")
        
        cls._tts_model = CoquiTTS(
            model_name=model_name,
            cache_dir=str(cls.get_cache_dir())
        )
    
    @classmethod
    def get_stt_model(cls):
        """
        Get the pre-loaded STT model.
        
        Returns:
            WhisperSTT: Initialized Whisper model instance
            
        Raises:
            ModelNotInitializedError: If called before initialize_at_startup()
        """
        if not cls.is_voice_enabled():
            return None
        
        cls._ensure_initialized()
        return cls._stt_model
    
    @classmethod
    def get_tts_model(cls):
        """
        Get the pre-loaded TTS model.
        
        Returns:
            CoquiTTS: Initialized Coqui TTS model instance
            
        Raises:
            ModelNotInitializedError: If called before initialize_at_startup()
        """
        if not cls.is_voice_enabled():
            return None
        
        cls._ensure_initialized()
        return cls._tts_model
    
    @classmethod
    def preload_models(cls):
        """
        DEPRECATED: Use initialize_at_startup() instead.
        
        Kept for backwards compatibility.
        """
        logger.warning("preload_models() is deprecated. Use initialize_at_startup() instead.")
        return cls.initialize_at_startup()
    
    @classmethod
    def unload_models(cls):
        """
        Unload models to free memory.
        
        Useful for cleanup or when voice functionality is no longer needed.
        """
        if cls._stt_model is not None:
            del cls._stt_model
            cls._stt_model = None
            logger.info("STT model unloaded")
        
        if cls._tts_model is not None:
            del cls._tts_model
            cls._tts_model = None
            logger.info("TTS model unloaded")
        
        cls._initialized = False
        cls._initialization_time_ms = 0
    
    @classmethod
    def get_model_info(cls) -> dict:
        """
        Get information about loaded models.
        
        Returns:
            dict: Model status and configuration
        """
        return {
            "voice_enabled": cls.is_voice_enabled(),
            "initialized": cls._initialized,
            "initialization_time_ms": cls._initialization_time_ms,
            "stt_loaded": cls._stt_model is not None,
            "tts_loaded": cls._tts_model is not None,
            "cache_dir": str(cls.get_cache_dir()),
            "config": {
                "whisper_model": os.getenv("WHISPER_MODEL", "openai/whisper-medium"),
                "whisper_device": os.getenv("WHISPER_DEVICE", "cpu"),
                "whisper_compute_type": os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
                "coqui_model": os.getenv("COQUI_MODEL", "tts_models/en/ljspeech/tacotron2-DDC"),
            }
        }
