"""
Audio Processing Utilities

Provides utilities for audio format conversion, resampling, buffering,
and preprocessing for STT/TTS operations.
"""

import io
import base64
import logging
from typing import Optional, List
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Audio processing utilities for format conversion and preprocessing.
    """
    
    @staticmethod
    def base64_to_bytes(base64_str: str) -> bytes:
        """Convert base64 string to bytes."""
        try:
            return base64.b64decode(base64_str)
        except Exception as e:
            logger.error(f"Failed to decode base64 audio: {e}")
            raise ValueError("Invalid base64 audio data")
    
    @staticmethod
    def bytes_to_base64(audio_bytes: bytes) -> str:
        """Convert bytes to base64 string."""
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    @staticmethod
    def convert_to_wav(audio_bytes: bytes, source_format: str = "webm") -> bytes:
        """
        Convert audio bytes from various formats to WAV.
        
        Args:
            audio_bytes: Raw audio data
            source_format: Source audio format (webm, mp3, ogg, etc.)
        
        Returns:
            bytes: WAV audio data
        """
        try:
            from pydub import AudioSegment
            
            # Load audio from bytes
            audio = AudioSegment.from_file(
                io.BytesIO(audio_bytes),
                format=source_format
            )
            
            # Convert to WAV
            wav_io = io.BytesIO()
            audio.export(wav_io, format="wav")
            wav_io.seek(0)
            
            return wav_io.read()
            
        except Exception as e:
            logger.error(f"Failed to convert audio to WAV: {e}")
            raise
    
    @staticmethod
    def resample_audio(audio_bytes: bytes, target_sample_rate: int = 16000) -> bytes:
        """
        Resample audio to target sample rate (Whisper requires 16kHz).
        
        Args:
            audio_bytes: Audio data in any format (WebM, WAV, etc.)
            target_sample_rate: Target sample rate in Hz
        
        Returns:
            bytes: Resampled WAV audio data
        """
        try:
            from pydub import AudioSegment
            
            # Try to load audio - auto-detect format
            # This handles WebM, WAV, MP3, etc.
            try:
                audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
                logger.info(f"Loaded audio: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch, {audio.sample_width*8}bit")
            except Exception as load_error:
                logger.error(f"Failed to load audio for resampling: {load_error}")
                raise ValueError(f"Cannot load audio data: {load_error}")
            
            # Resample if needed
            if audio.frame_rate != target_sample_rate:
                logger.info(f"Resampling from {audio.frame_rate}Hz to {target_sample_rate}Hz")
                audio = audio.set_frame_rate(target_sample_rate)
            else:
                logger.info(f"Audio already at target sample rate: {target_sample_rate}Hz")
            
            # Convert to mono if stereo
            if audio.channels > 1:
                logger.info(f"Converting from {audio.channels} channels to mono")
                audio = audio.set_channels(1)
            
            # Ensure 16-bit sample width (required by Whisper)
            if audio.sample_width != 2:  # 2 bytes = 16 bits
                logger.info(f"Converting from {audio.sample_width*8}bit to 16bit")
                audio = audio.set_sample_width(2)
            
            # Export resampled audio as WAV
            resampled_io = io.BytesIO()
            audio.export(
                resampled_io, 
                format="wav",
                parameters=["-ar", str(target_sample_rate), "-ac", "1", "-sample_fmt", "s16"]
            )
            resampled_io.seek(0)
            wav_bytes = resampled_io.read()
            
            logger.info(f"Resampled audio exported: {len(wav_bytes)} bytes")
            
            # Validate the output
            if len(wav_bytes) < 100:
                raise ValueError(f"Resampled audio too small: {len(wav_bytes)} bytes")
            
            return wav_bytes
            
        except Exception as e:
            logger.error(f"Failed to resample audio: {e}", exc_info=True)
            raise
    
    @staticmethod
    def get_audio_duration(audio_bytes: bytes) -> float:
        """
        Get duration of audio in seconds.
        
        Args:
            audio_bytes: Audio data (any format supported by pydub)
        
        Returns:
            float: Duration in seconds
        """
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            return len(audio) / 1000.0  # Convert ms to seconds
            
        except Exception as e:
            logger.error(f"Failed to get audio duration: {e}")
            return 0.0
    
    @staticmethod
    def save_audio_to_file(audio_bytes: bytes, filepath: str, format: str = "wav"):
        """
        Save audio bytes to file.
        
        Args:
            audio_bytes: Audio data
            filepath: Output file path
            format: Audio format
        """
        try:
            from pydub import AudioSegment
            
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
            audio.export(filepath, format=format)
            logger.info(f"Audio saved to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise


class AudioBuffer:
    """
    Buffer for accumulating audio chunks before processing.
    
    Useful for streaming audio where we want to process chunks
    of a certain duration rather than individual packets.
    """
    
    def __init__(self, chunk_duration: float = 3.0, max_duration: float = 60.0):
        """
        Initialize audio buffer.
        
        Args:
            chunk_duration: Duration in seconds before buffer is considered ready
            max_duration: Maximum buffer duration before forced processing
        """
        self.chunk_duration = chunk_duration
        self.max_duration = max_duration
        self.chunks: List[bytes] = []
        self.total_duration = 0.0
        self.processor = AudioProcessor()
    
    def add(self, audio_data: bytes):
        """
        Add audio chunk to buffer.
        
        Args:
            audio_data: Audio bytes to add
        """
        self.chunks.append(audio_data)
        
        # Use rough byte-based estimation for streaming chunks
        # Don't try to decode incomplete WebM/audio chunks - it will fail
        # Assume ~100 bytes per 10ms at 16kHz mono (rough approximation)
        # This is just for buffering logic, actual duration calculated when combining
        estimated_duration = len(audio_data) / 3200.0
        self.total_duration += estimated_duration
    
    def is_ready(self) -> bool:
        """
        Check if buffer has accumulated enough audio for processing.
        
        Returns:
            bool: True if buffer duration >= chunk_duration
        """
        return self.total_duration >= self.chunk_duration
    
    def is_full(self) -> bool:
        """
        Check if buffer has reached maximum duration.
        
        Returns:
            bool: True if buffer duration >= max_duration
        """
        return self.total_duration >= self.max_duration
    
    def get_audio(self) -> bytes:
        """
        Get combined audio from all chunks.
        
        For streaming audio (like WebM from MediaRecorder), individual chunks
        are NOT valid standalone files. We must concatenate raw bytes first,
        then decode the complete stream.
        
        Returns:
            bytes: Combined audio data in WAV format
        """
        if not self.chunks:
            return b''
        
        try:
            from pydub import AudioSegment
            
            # CRITICAL: For WebM/streaming formats, concatenate raw bytes FIRST
            # Individual chunks are not valid standalone audio files
            combined_bytes = b''.join(self.chunks)
            logger.info(f"[BUFFER] Concatenated {len(self.chunks)} chunks into {len(combined_bytes)} bytes")
            
            # Validate we have enough data
            if len(combined_bytes) < 100:
                logger.warning(f"[BUFFER] Combined audio too small ({len(combined_bytes)} bytes), likely invalid")
                return b''
            
            # Now decode the complete audio stream
            try:
                audio = AudioSegment.from_file(
                    io.BytesIO(combined_bytes),
                    format="webm"  # Explicitly specify WebM format
                )
                logger.info(f"[BUFFER] Successfully decoded WebM audio: {len(audio)}ms, {audio.frame_rate}Hz")
            except Exception as webm_error:
                logger.warning(f"[BUFFER] Failed to decode as WebM: {webm_error}")
                # Fallback: let pydub auto-detect format
                try:
                    audio = AudioSegment.from_file(io.BytesIO(combined_bytes))
                    logger.info(f"[BUFFER] Auto-detected format: {len(audio)}ms, {audio.frame_rate}Hz")
                except Exception as auto_error:
                    logger.error(f"[BUFFER] All decode attempts failed. WebM: {webm_error}, Auto: {auto_error}")
                    raise ValueError(f"Failed to decode audio: {auto_error}")
            
            # Export as WAV
            output_io = io.BytesIO()
            audio.export(output_io, format="wav")
            output_io.seek(0)
            wav_bytes = output_io.read()
            
            logger.info(f"[BUFFER] Exported to WAV: {len(wav_bytes)} bytes")
            return wav_bytes
            
        except Exception as e:
            logger.error(f"[BUFFER] Failed to combine audio chunks: {e}", exc_info=True)
            # Last resort: return empty instead of potentially corrupt data
            return b''
    
    def clear(self):
        """Clear the buffer."""
        self.chunks.clear()
        self.total_duration = 0.0
    
    def get_duration(self) -> float:
        """Get total duration of buffered audio."""
        return self.total_duration
    
    def get_chunk_count(self) -> int:
        """Get number of chunks in buffer."""
        return len(self.chunks)


class VADBuffer:
    """
    Voice Activity Detection buffer for silence-based STT triggering.
    
    Triggers transcription when:
    - Silence is detected for >= silence_threshold_ms, OR
    - Buffer duration reaches max_duration_s
    
    Uses RMS energy for silence detection.
    """
    
    def __init__(
        self,
        silence_threshold_ms: int = 1000,
        max_duration_s: float = 6.0,
        rms_silence_threshold: float = 0.01,
        sample_rate: int = 16000
    ):
        """
        Initialize VAD buffer.
        
        Args:
            silence_threshold_ms: Silence duration before triggering (default: 1000ms)
            max_duration_s: Maximum buffer duration before forced trigger (default: 6s)
            rms_silence_threshold: RMS threshold below which audio is considered silence
            sample_rate: Expected sample rate for duration estimation
        """
        self.silence_threshold_ms = silence_threshold_ms
        self.max_duration_s = max_duration_s
        self.rms_silence_threshold = rms_silence_threshold
        self.sample_rate = sample_rate
        
        self.chunks: List[bytes] = []
        self.total_bytes = 0
        self.silence_start_time: Optional[float] = None
        self.has_speech = False
        
        self._processor = AudioProcessor()
    
    def add_chunk(self, audio_bytes: bytes) -> None:
        """
        Add audio chunk to buffer.
        
        Args:
            audio_bytes: Raw audio data
        """
        import time
        
        self.chunks.append(audio_bytes)
        self.total_bytes += len(audio_bytes)
        
        # Check if this chunk is silence
        is_silence = self._is_silence(audio_bytes)
        
        if is_silence:
            if self.silence_start_time is None:
                self.silence_start_time = time.perf_counter()
        else:
            self.silence_start_time = None
            self.has_speech = True
    
    def _is_silence(self, audio_bytes: bytes) -> bool:
        """
        Check if audio chunk is silence using RMS energy.
        
        Args:
            audio_bytes: Audio data to check
            
        Returns:
            bool: True if audio is below silence threshold
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            
            if len(audio_array) == 0:
                return True
            
            # Normalize to [-1, 1]
            audio_array = audio_array / 32768.0
            
            # Calculate RMS
            rms = np.sqrt(np.mean(audio_array ** 2))
            
            return rms < self.rms_silence_threshold
            
        except Exception:
            # If we can't analyze, assume not silence
            return False
    
    def should_trigger(self) -> bool:
        """
        Check if STT should be triggered.
        
        Returns:
            bool: True if silence threshold reached or max duration exceeded
        """
        import time
        
        # Must have some speech first
        if not self.has_speech:
            return False
        
        # Check silence duration
        if self.silence_start_time is not None:
            silence_duration_ms = (time.perf_counter() - self.silence_start_time) * 1000
            if silence_duration_ms >= self.silence_threshold_ms:
                return True
        
        # Check max duration (rough estimate: ~3200 bytes per second for compressed audio)
        estimated_duration = self.total_bytes / 3200.0
        if estimated_duration >= self.max_duration_s:
            return True
        
        return False
    
    def get_audio_and_reset(self) -> bytes:
        """
        Get combined audio data and reset buffer.
        
        Returns:
            bytes: Combined audio in WAV format
        """
        if not self.chunks:
            return b''
        
        try:
            from pydub import AudioSegment
            import tempfile
            import os
            
            # Concatenate raw bytes first (critical for WebM streaming)
            combined_bytes = b''.join(self.chunks)
            logger.info(f"[VAD] Concatenated {len(self.chunks)} chunks into {len(combined_bytes)} bytes")
            
            # Validate we have enough data
            if len(combined_bytes) < 100:
                logger.warning(f"[VAD] Combined audio too small ({len(combined_bytes)} bytes), likely invalid")
                self.clear()
                return b''
            
            # Strategy 1: Try to decode as WebM from memory
            audio = None
            try:
                audio = AudioSegment.from_file(
                    io.BytesIO(combined_bytes),
                    format="webm"
                )
                logger.info(f"[VAD] Successfully decoded as WebM: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch")
            except Exception as webm_error:
                logger.warning(f"[VAD] WebM decode from memory failed: {str(webm_error)[:200]}")
                
                # Strategy 2: Try auto-detect from memory
                try:
                    audio = AudioSegment.from_file(io.BytesIO(combined_bytes))
                    logger.info(f"[VAD] Auto-detected format: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch")
                except Exception as auto_error:
                    logger.warning(f"[VAD] Auto-detect from memory failed: {str(auto_error)[:200]}")
                    
                    # Strategy 3: Save to temp file and try to read (sometimes fixes format issues)
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp_file:
                            temp_path = temp_file.name
                            temp_file.write(combined_bytes)
                        
                        logger.info(f"[VAD] Trying to decode from temp file: {temp_path}")
                        
                        # Try WebM from file
                        try:
                            audio = AudioSegment.from_file(temp_path, format="webm")
                            logger.info(f"[VAD] Successfully decoded WebM from file: {len(audio)}ms")
                        except Exception as file_webm_error:
                            logger.warning(f"[VAD] WebM from file failed: {str(file_webm_error)[:200]}")
                            # Try auto-detect from file
                            try:
                                audio = AudioSegment.from_file(temp_path)
                                logger.info(f"[VAD] Auto-detected from file: {len(audio)}ms")
                            except Exception as file_auto_error:
                                logger.error(f"[VAD] All decode strategies failed")
                                raise ValueError(f"Failed to decode audio data: {str(file_auto_error)[:200]}")
                    finally:
                        # Clean up temp file
                        if temp_path and os.path.exists(temp_path):
                            try:
                                os.unlink(temp_path)
                            except:
                                pass
            
            # If we still don't have audio, something is very wrong
            if audio is None:
                logger.error(f"[VAD] Audio is None after all decode attempts")
                self.clear()
                raise ValueError("Failed to decode audio: all strategies failed")
            
            # Export as WAV
            output_io = io.BytesIO()
            audio.export(output_io, format="wav")
            output_io.seek(0)
            wav_bytes = output_io.read()
            
            logger.info(f"[VAD] Exported to WAV: {len(wav_bytes)} bytes")
            
        except Exception as e:
            logger.error(f"[VAD] Failed to convert audio: {e}", exc_info=True)
            self.clear()
            raise  # Re-raise instead of returning raw bytes
        
        # Reset buffer
        self.clear()
        
        return wav_bytes
    
    def clear(self) -> None:
        """Reset buffer to empty state."""
        self.chunks.clear()
        self.total_bytes = 0
        self.silence_start_time = None
        self.has_speech = False
    
    def get_duration(self) -> float:
        """Get estimated buffer duration in seconds."""
        return self.total_bytes / 3200.0
    
    def get_chunk_count(self) -> int:
        """Get number of chunks in buffer."""
        return len(self.chunks)


class AudioValidator:
    """
    Validates audio data for processing.
    """
    
    @staticmethod
    def is_valid_audio(audio_bytes: bytes, min_duration: float = 0.1) -> bool:
        """
        Check if audio data is valid for processing.
        
        Args:
            audio_bytes: Audio data to validate
            min_duration: Minimum required duration in seconds
        
        Returns:
            bool: True if audio is valid
        """
        if not audio_bytes or len(audio_bytes) == 0:
            return False
        
        # Simple validation: check if we have enough bytes
        # Assume ~3200 bytes per second (rough estimate for compressed audio)
        # This avoids trying to decode incomplete/streaming chunks
        min_bytes = int(min_duration * 3200)
        return len(audio_bytes) >= min_bytes
    
    @staticmethod
    def validate_format(audio_bytes: bytes, allowed_formats: List[str] = None) -> bool:
        """
        Validate audio format.
        
        Args:
            audio_bytes: Audio data
            allowed_formats: List of allowed formats (e.g., ['wav', 'mp3', 'webm'])
        
        Returns:
            bool: True if format is valid
        """
        if allowed_formats is None:
            allowed_formats = ['wav', 'mp3', 'webm', 'ogg']
        
        try:
            from pydub import AudioSegment
            
            # Try to load audio - if successful, format is valid
            AudioSegment.from_file(io.BytesIO(audio_bytes))
            return True
        except Exception:
            return False
