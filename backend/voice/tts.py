"""
Text-to-Speech (TTS) using Coqui TTS

Implements local TTS synthesis with caching and optimization.
"""
import os
import io
import logging
import time
from typing import Optional, AsyncIterator
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


class CoquiTTS:
    """
    Coqui TTS-based text-to-speech engine.
    
    Features:
    - Local synthesis (no API costs)
    - Model caching
    - Multiple voice options
    - Streaming support
    """
    
    def __init__(
        self,
        model_name: str = "tts_models/en/ljspeech/tacotron2-DDC",
        cache_dir: str = "backend/models"
    ):
        """
        Initialize Coqui TTS model.
        
        Args:
            model_name: Coqui TTS model identifier
            cache_dir: Directory for model caching
        """
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.tts = None
        
        # Create cache directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize model
        self._load_model()
    
    def _load_model(self):
        """Load the TTS model with caching."""
        try:
            from TTS.api import TTS
            
            logger.info(f"Loading Coqui TTS model: {self.model_name}")
            logger.info(f"Cache directory: {self.cache_dir}")
            
            # Set cache directory via environment variable
            os.environ['TTS_HOME'] = str(self.cache_dir)
            
            # Initialize TTS
            self.tts = TTS(
                model_name=self.model_name,
                progress_bar=False,
                gpu=False  # Use CPU for compatibility
            )
            
            logger.info("✓ Coqui TTS model loaded successfully")
            
        except ImportError:
            logger.error("TTS library not installed. Install with: pip install TTS")
            raise
        except Exception as e:
            logger.error(f"Failed to load TTS model: {e}")
            raise
    
    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: Optional[str] = None
    ) -> bytes:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to synthesize
            speaker: Speaker name (for multi-speaker models)
            language: Language code (for multi-lingual models)
        
        Returns:
            bytes: WAV audio data
        """
        if not self.tts:
            raise RuntimeError("TTS model not loaded")
        
        start_time = time.time()
        
        try:
            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                # Synthesize to file
                kwargs = {}
                if speaker:
                    kwargs['speaker'] = speaker
                if language:
                    kwargs['language'] = language
                
                self.tts.tts_to_file(
                    text=text,
                    file_path=temp_path,
                    **kwargs
                )
                
                # Read audio data
                with open(temp_path, 'rb') as f:
                    audio_bytes = f.read()
                
                processing_time = time.time() - start_time
                logger.info(f"TTS synthesis complete: {len(text)} chars in {processing_time:.2f}s")
                
                return audio_bytes
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise
    
    def synthesize_sync(
        self,
        text: str,
        speaker: Optional[str] = None,
        language: Optional[str] = None
    ) -> bytes:
        """
        Synchronous version of synthesize.
        
        Args:
            text: Text to synthesize
            speaker: Speaker name
            language: Language code
        
        Returns:
            bytes: WAV audio data
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.synthesize(text, speaker, language))
    
    async def synthesize_stream(
        self,
        text: str,
        chunk_size: int = 1024
    ) -> AsyncIterator[bytes]:
        """
        Synthesize speech with streaming output.
        
        Note: Coqui TTS doesn't natively support streaming,
        so we synthesize the full audio and chunk it.
        
        Args:
            text: Text to synthesize
            chunk_size: Size of audio chunks in bytes
        
        Yields:
            bytes: Audio chunks
        """
        # Synthesize full audio
        audio_bytes = await self.synthesize(text)
        
        # Yield in chunks
        for i in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[i:i + chunk_size]
            yield chunk
    
    def get_available_speakers(self) -> list:
        """
        Get list of available speakers (for multi-speaker models).
        
        Returns:
            list: Speaker names
        """
        if not self.tts:
            return []
        
        try:
            if hasattr(self.tts, 'speakers') and self.tts.speakers:
                return self.tts.speakers
        except Exception:
            pass
        
        return []
    
    def get_available_languages(self) -> list:
        """
        Get list of available languages (for multi-lingual models).
        
        Returns:
            list: Language codes
        """
        if not self.tts:
            return []
        
        try:
            if hasattr(self.tts, 'languages') and self.tts.languages:
                return self.tts.languages
        except Exception:
            pass
        
        return []
    
    def get_model_info(self) -> dict:
        """
        Get model information.
        
        Returns:
            dict: Model metadata
        """
        return {
            'model_name': self.model_name,
            'cache_dir': str(self.cache_dir),
            'loaded': self.tts is not None,
            'speakers': self.get_available_speakers(),
            'languages': self.get_available_languages()
        }
    
    @staticmethod
    def list_available_models() -> list:
        """
        List all available Coqui TTS models.
        
        Returns:
            list: Model names
        """
        try:
            from TTS.api import TTS
            return TTS.list_models()
        except Exception as e:
            logger.error(f"Failed to list TTS models: {e}")
            return []
