"""
WebSocket Handler for Voice Chat

Manages real-time bidirectional audio streaming for voice conversations.
Optimized for low latency with VAD-based triggering and async processing.
"""

import json
import base64
import logging
import asyncio
import time
from typing import Optional, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import WebSocket, WebSocketDisconnect
from .audio_utils import VADBuffer, AudioProcessor, AudioValidator
from .model_manager import ModelManager

logger = logging.getLogger(__name__)

# Thread pool for CPU-bound STT/TTS operations
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice_")


class VoiceSession:
    """
    Represents a single voice chat session.
    
    Manages audio buffering, transcription, and TTS for one user connection.
    """
    
    def __init__(
        self,
        websocket: WebSocket,
        user_id: str,
        conversation_id: Optional[str] = None
    ):
        """
        Initialize voice session.
        
        Args:
            websocket: WebSocket connection
            user_id: Authenticated user ID
            conversation_id: Optional conversation ID to continue
        """
        self.websocket = websocket
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.session_id = f"{user_id}_{int(time.time())}"
        
        # VAD-based audio buffering (replaces simple buffer)
        self.vad_buffer = VADBuffer(
            silence_threshold_ms=1000,  # 1 second of silence triggers
            max_duration_s=6.0,         # Max 6 seconds before forced trigger
            rms_silence_threshold=0.01
        )
        self.audio_processor = AudioProcessor()
        self.audio_validator = AudioValidator()
        
        # Session state
        self.is_active = True
        self.current_state = "idle"  # idle, listening, processing, speaking
        
        # Processing lock to prevent overlapping requests
        self._processing_lock = asyncio.Lock()
        self._is_processing = False
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'transcriptions': 0,
            'syntheses': 0,
            'errors': 0,
            'start_time': datetime.utcnow().isoformat(),
            'total_latency_ms': []
        }
        
        logger.info(f"Voice session created: {self.session_id}")
    
    async def send_status(self, state: str, message: Optional[str] = None):
        """Send status update to client."""
        self.current_state = state
        
        try:
            await self.websocket.send_json({
                'type': 'status',
                'state': state,
                'message': message,
                'timestamp': time.time()
            })
        except Exception as e:
            logger.error(f"Failed to send status: {e}")
    
    async def send_transcript(self, text: str, language: str = "en"):
        """Send transcription result to client."""
        try:
            await self.websocket.send_json({
                'type': 'transcript',
                'text': text,
                'language': language,
                'timestamp': time.time()
            })
            self.stats['transcriptions'] += 1
        except Exception as e:
            logger.error(f"Failed to send transcript: {e}")
    
    async def send_audio(self, audio_bytes: bytes):
        """Send audio data to client."""
        try:
            audio_base64 = self.audio_processor.bytes_to_base64(audio_bytes)
            
            await self.websocket.send_json({
                'type': 'audio',
                'data': audio_base64,
                'format': 'wav',
                'timestamp': time.time()
            })
            self.stats['syntheses'] += 1
        except Exception as e:
            logger.error(f"Failed to send audio: {e}")
    
    async def send_error(self, error_message: str, error_code: Optional[str] = None):
        """Send error message to client."""
        try:
            await self.websocket.send_json({
                'type': 'error',
                'message': error_message,
                'code': error_code,
                'timestamp': time.time()
            })
            self.stats['errors'] += 1
        except Exception as e:
            logger.error(f"Failed to send error: {e}")
    
    async def send_conversation_update(self, conversation_id: str, title: Optional[str] = None):
        """Send conversation metadata update to client."""
        try:
            await self.websocket.send_json({
                'type': 'conversation_update',
                'conversation_id': conversation_id,
                'title': title,
                'timestamp': time.time()
            })
        except Exception as e:
            logger.error(f"Failed to send conversation update: {e}")
    
    def get_stats(self) -> dict:
        """Get session statistics."""
        avg_latency = 0
        if self.stats['total_latency_ms']:
            avg_latency = sum(self.stats['total_latency_ms']) / len(self.stats['total_latency_ms'])
        
        return {
            **self.stats,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'conversation_id': self.conversation_id,
            'current_state': self.current_state,
            'is_active': self.is_active,
            'buffer_duration': self.vad_buffer.get_duration(),
            'buffer_chunks': self.vad_buffer.get_chunk_count(),
            'avg_latency_ms': avg_latency
        }
    
    def close(self):
        """Close the session and cleanup resources."""
        self.is_active = False
        self.vad_buffer.clear()
        logger.info(f"Voice session closed: {self.session_id}")


class VoiceWebSocketHandler:
    """
    Handles WebSocket connections for voice chat.
    
    Orchestrates STT, LLM processing, and TTS for real-time conversations.
    Features:
    - VAD-based auto-triggering for low latency
    - Non-blocking async processing
    - Detailed timing logs
    """
    
    def __init__(
        self,
        reasoning_engine,
        conversation_manager,
        database,
        stm_manager=None,
        ltm_manager=None,
        pdf_loader=None
    ):
        """Initialize WebSocket handler."""
        self.reasoning_engine = reasoning_engine
        self.conversation_manager = conversation_manager
        self.database = database
        self.stm_manager = stm_manager
        self.ltm_manager = ltm_manager
        self.pdf_loader = pdf_loader
        
        # Active sessions
        self.active_sessions: Dict[str, VoiceSession] = {}
        
        logger.info("Voice WebSocket handler initialized")
    
    async def handle_connection(
        self,
        websocket: WebSocket,
        user_id: str,
        conversation_id: Optional[str] = None
    ):
        """Handle a new WebSocket connection."""
        await websocket.accept()
        
        session = VoiceSession(websocket, user_id, conversation_id)
        self.active_sessions[session.session_id] = session
        
        await session.send_status("idle", "Voice session connected")
        
        try:
            while session.is_active:
                try:
                    message = await websocket.receive_json()
                    session.stats['messages_received'] += 1
                    
                    msg_type = message.get('type')
                    
                    if msg_type == 'audio':
                        await self._handle_audio(session, message)
                    
                    elif msg_type == 'stop':
                        await self._handle_stop(session)
                    
                    elif msg_type == 'ping':
                        await websocket.send_json({'type': 'pong', 'timestamp': time.time()})
                    
                    else:
                        logger.warning(f"Unknown message type: {msg_type}")
                
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: {session.session_id}")
                    break
                
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await session.send_error(f"Error processing message: {str(e)}")
        
        finally:
            session.close()
            if session.session_id in self.active_sessions:
                del self.active_sessions[session.session_id]
            
            logger.info(f"Session stats: {session.get_stats()}")
    
    async def _handle_audio(self, session: VoiceSession, message: dict):
        """
        Handle incoming audio data.
        
        Supports two modes:
        1. Complete recording (complete=True): Process immediately
        2. Streaming chunks (legacy): Buffer and trigger with VAD
        """
        try:
            # Extract audio data
            audio_data_b64 = message.get('data')
            is_complete = message.get('complete', False)
            
            if not audio_data_b64:
                logger.warning("No audio data provided in message")
                return
            
            # Decode audio
            audio_bytes = session.audio_processor.base64_to_bytes(audio_data_b64)
            
            if is_complete:
                # This is a complete recording, process immediately
                logger.info(f"[VOICE] Received complete recording: {len(audio_bytes)} bytes")
                await session.send_status("processing", "Processing audio")
                # Process in background to keep WebSocket responsive
                asyncio.create_task(self._process_complete_audio(session, audio_bytes))
            else:
                # Legacy streaming mode: add to VAD buffer
                session.vad_buffer.add_chunk(audio_bytes)
                
                # Update status to listening
                if session.current_state != "listening":
                    await session.send_status("listening", "Receiving audio")
                
                # Check if VAD triggers processing
                if session.vad_buffer.should_trigger():
                    logger.info(f"[VAD] Silence detected, triggering STT for {session.user_id}")
                    # Process in background to keep WebSocket responsive
                    asyncio.create_task(self._process_audio_buffer(session))
        
        except Exception as e:
            logger.error(f"Error handling audio: {e}", exc_info=True)
            await session.send_error(f"Audio processing error: {str(e)}")
    
    async def _process_audio_buffer(self, session: VoiceSession):
        """
        Process buffered audio through STT → LLM → TTS pipeline.
        
        Uses thread pool for CPU-bound operations to avoid blocking.
        """
        # Prevent overlapping processing
        if session._is_processing:
            logger.warning("Already processing, skipping")
            return
        
        async with session._processing_lock:
            session._is_processing = True
            t_start = time.perf_counter()
            
            try:
                await session.send_status("processing", "Transcribing audio")
                
                # Get audio from VAD buffer
                audio_bytes = session.vad_buffer.get_audio_and_reset()
                
                if not audio_bytes or len(audio_bytes) < 1000:
                    logger.warning("Audio too short, skipping")
                    await session.send_status("idle", "Audio too short")
                    return
                
                logger.info(f"[VOICE_TIMING] Processing {len(audio_bytes)} bytes")
                
                # ===== STT (run in thread pool) =====
                t_stt_start = time.perf_counter()
                logger.info(f"[VOICE_TIMING] Audio→STT start: {(t_stt_start - t_start)*1000:.0f}ms")
                
                stt_model = ModelManager.get_stt_model()
                if not stt_model:
                    await session.send_error("STT model not available")
                    return
                
                # Resample to 16kHz for Whisper
                try:
                    logger.info(f"Resampling audio from buffer to 16kHz WAV: {len(audio_bytes)} bytes")
                    audio_bytes = session.audio_processor.resample_audio(audio_bytes, target_sample_rate=16000)
                    logger.info(f"Audio resampled successfully: {len(audio_bytes)} bytes")
                    
                except Exception as e:
                    logger.error(f"Audio resampling failed: {e}", exc_info=True)
                    await session.send_error(f"Audio processing failed: {str(e)}. Please try again.")
                    await session.send_status("idle", "Ready")
                    return
                
                # Run STT in thread pool (CPU-bound)
                loop = asyncio.get_event_loop()
                try:
                    transcript_result = await loop.run_in_executor(
                        _executor,
                        stt_model.transcribe_sync,
                        audio_bytes
                    )
                except Exception as stt_error:
                    logger.error(f"STT transcription failed: {stt_error}", exc_info=True)
                    await session.send_error(f"Speech recognition failed: {str(stt_error)}")
                    await session.send_status("idle", "Ready")
                    return
                
                transcript_text = transcript_result.get('text', '').strip()
                t_stt_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] STT duration: {(t_stt_end - t_stt_start)*1000:.0f}ms")
                
                if not transcript_text:
                    logger.warning("Empty transcription")
                    await session.send_status("idle", "No speech detected")
                    return
                
                logger.info(f"✓ Transcribed: {transcript_text}")
                await session.send_transcript(transcript_text, transcript_result.get('language', 'en'))
                
                # ===== LLM (async) =====
                t_llm_start = time.perf_counter()
                await session.send_status("processing", "Generating response")
                
                response_text = await self._process_with_llm(session, transcript_text)
                
                t_llm_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] LLM duration: {(t_llm_end - t_llm_start)*1000:.0f}ms")
                
                if not response_text:
                    await session.send_error("Failed to generate response")
                    return
                
                logger.info(f"✓ LLM Response: {response_text[:100]}...")
                
                # Send text response
                try:
                    await session.websocket.send_json({
                        'type': 'response',
                        'text': response_text
                    })
                except Exception as e:
                    logger.warning(f"Failed to send response: {e}")
                
                # ===== TTS (run in thread pool) =====
                t_tts_start = time.perf_counter()
                await session.send_status("speaking", "Synthesizing speech")
                
                tts_model = ModelManager.get_tts_model()
                if not tts_model:
                    logger.warning("TTS model not available")
                    await session.send_status("idle", "Ready")
                    return
                
                # Sanitize text for TTS
                from .text_preprocessor import sanitize_for_tts
                clean_text = sanitize_for_tts(response_text)
                
                # Run TTS in thread pool (CPU-bound)
                audio_response = await loop.run_in_executor(
                    _executor,
                    tts_model.synthesize_sync,
                    clean_text
                )
                
                t_tts_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] TTS duration: {(t_tts_end - t_tts_start)*1000:.0f}ms")
                
                # Send audio
                await session.send_audio(audio_response)
                
                # Total timing
                total_ms = (t_tts_end - t_start) * 1000
                logger.info(f"[VOICE_TIMING] ===== Total round-trip: {total_ms:.0f}ms =====")
                session.stats['total_latency_ms'].append(total_ms)
                
                await session.send_status("idle", "Ready for next message")
            
            except Exception as e:
                logger.error(f"Error processing audio buffer: {e}", exc_info=True)
                await session.send_error(f"Processing error: {str(e)}")
                session.vad_buffer.clear()
                await session.send_status("idle", "Ready")
            
            finally:
                session._is_processing = False
    
    async def _process_complete_audio(self, session: VoiceSession, audio_bytes: bytes):
        """
        Process a complete audio recording through STT → LLM → TTS pipeline.
        
        This method handles complete recordings sent from the frontend,
        avoiding the WebM chunk concatenation issues.
        """
        # Prevent overlapping processing
        if session._is_processing:
            logger.warning("Already processing, skipping")
            return
        
        async with session._processing_lock:
            session._is_processing = True
            t_start = time.perf_counter()
            
            try:
                await session.send_status("processing", "Transcribing audio")
                
                # Validate audio size
                if not audio_bytes or len(audio_bytes) < 1000:
                    logger.warning("Audio too short, skipping")
                    await session.send_status("idle", "Audio too short")
                    return
                
                logger.info(f"[VOICE_TIMING] Processing complete recording: {len(audio_bytes)} bytes")
                
                # ===== STT (run in thread pool) =====
                t_stt_start = time.perf_counter()
                logger.info(f"[VOICE_TIMING] Audio→STT start: {(t_stt_start - t_start)*1000:.0f}ms")
                
                stt_model = ModelManager.get_stt_model()
                if not stt_model:
                    await session.send_error("STT model not available")
                    return
                
                # Validate and resample to 16kHz for Whisper
                try:
                    # Resample to 16kHz first
                    logger.info(f"Resampling audio from WebM to 16kHz WAV: {len(audio_bytes)} bytes")
                    audio_bytes = session.audio_processor.resample_audio(audio_bytes, target_sample_rate=16000)
                    logger.info(f"Audio resampled successfully: {len(audio_bytes)} bytes")
                    
                    # Now validate the resampled WAV data
                    if not session.audio_validator.validate_format(audio_bytes):
                        logger.error("Invalid WAV format after resampling")
                        await session.send_error("Audio resampling failed. Please try again.")
                        await session.send_status("idle", "Ready")
                        return
                    
                    logger.info("Resampled WAV validated successfully")
                    
                except Exception as e:
                    logger.error(f"Audio resampling failed: {e}", exc_info=True)
                    await session.send_error(f"Audio processing failed: {str(e)}. Please try again.")
                    await session.send_status("idle", "Ready")
                    return
                
                # Run STT in thread pool (CPU-bound)
                loop = asyncio.get_event_loop()
                try:
                    transcript_result = await loop.run_in_executor(
                        _executor,
                        stt_model.transcribe_sync,
                        audio_bytes
                    )
                except Exception as stt_error:
                    logger.error(f"STT transcription failed: {stt_error}", exc_info=True)
                    await session.send_error(f"Speech recognition failed: {str(stt_error)}")
                    await session.send_status("idle", "Ready")
                    return
                
                transcript_text = transcript_result.get('text', '').strip()
                t_stt_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] STT duration: {(t_stt_end - t_stt_start)*1000:.0f}ms")
                
                if not transcript_text:
                    logger.warning("Empty transcription")
                    await session.send_status("idle", "No speech detected")
                    return
                
                logger.info(f"✓ Transcribed: {transcript_text}")
                await session.send_transcript(transcript_text, transcript_result.get('language', 'en'))
                
                # ===== LLM (async) =====
                t_llm_start = time.perf_counter()
                await session.send_status("processing", "Generating response")
                
                response_text = await self._process_with_llm(session, transcript_text)
                
                t_llm_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] LLM duration: {(t_llm_end - t_llm_start)*1000:.0f}ms")
                
                if not response_text:
                    await session.send_error("Failed to generate response")
                    return
                
                logger.info(f"✓ LLM Response: {response_text[:100]}...")
                
                # Send text response
                try:
                    await session.websocket.send_json({
                        'type': 'response',
                        'text': response_text
                    })
                except Exception as e:
                    logger.warning(f"Failed to send response: {e}")
                
                # ===== TTS (run in thread pool) =====
                t_tts_start = time.perf_counter()
                await session.send_status("speaking", "Synthesizing speech")
                
                tts_model = ModelManager.get_tts_model()
                if not tts_model:
                    logger.warning("TTS model not available")
                    await session.send_status("idle", "Ready")
                    return
                
                # Sanitize text for TTS
                from .text_preprocessor import sanitize_for_tts
                clean_text = sanitize_for_tts(response_text)
                
                # Run TTS in thread pool (CPU-bound)
                audio_response = await loop.run_in_executor(
                    _executor,
                    tts_model.synthesize_sync,
                    clean_text
                )
                
                t_tts_end = time.perf_counter()
                logger.info(f"[VOICE_TIMING] TTS duration: {(t_tts_end - t_tts_start)*1000:.0f}ms")
                
                # Send audio
                await session.send_audio(audio_response)
                
                # Total timing
                total_ms = (t_tts_end - t_start) * 1000
                logger.info(f"[VOICE_TIMING] ===== Total round-trip: {total_ms:.0f}ms =====")
                session.stats['total_latency_ms'].append(total_ms)
                
                await session.send_status("idle", "Ready for next message")
            
            except Exception as e:
                logger.error(f"Error processing complete audio: {e}", exc_info=True)
                await session.send_error(f"Processing error: {str(e)}")
                await session.send_status("idle", "Ready")
            
            finally:
                session._is_processing = False
    
    async def _process_with_llm(
        self,
        session: VoiceSession,
        user_message: str
    ) -> Optional[str]:
        """
        Process user message through the reasoning engine.
        
        Uses voice mode for shorter, cleaner responses.
        """
        try:
            # Voice mode: Skip heavy memory retrieval for speed
            # Only get minimal context
            stm_list = []
            ltm_list = []
            pdf_snippets = []
            
            # Process through reasoning engine with voice mode
            result = await self.reasoning_engine.process_message(
                user_message=user_message,
                user_id=session.user_id,
                stm_memories=stm_list,
                ltm_memories=ltm_list,
                pdf_snippets=pdf_snippets,
                voice_mode=True  # Enable voice mode for shorter responses
            )
            
            # Manage conversation
            if not session.conversation_id:
                session.conversation_id = self.conversation_manager.create_conversation(
                    session.user_id
                )
                title = self.conversation_manager.generate_title_from_message(user_message)
                self.conversation_manager.update_conversation_title(
                    session.conversation_id,
                    title
                )
                await session.send_conversation_update(session.conversation_id, title)
            else:
                self.conversation_manager.update_conversation_timestamp(
                    session.conversation_id
                )
            
            # Store messages
            if self.database:
                timestamp = time.time()
                self.database.add_message(
                    session.conversation_id,
                    session.user_id,
                    "user",
                    user_message,
                    timestamp,
                    metadata={'mode': 'voice'}
                )
                self.database.add_message(
                    session.conversation_id,
                    session.user_id,
                    "assistant",
                    result.get('response', ''),
                    timestamp + 0.001,
                    metadata={'mode': 'voice'}
                )
            
            return result.get('response', '')
        
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return None
    
    async def _handle_stop(self, session: VoiceSession):
        """Handle explicit stop signal from client."""
        logger.info(f"Stop signal received from {session.user_id}")
        
        chunk_count = session.vad_buffer.get_chunk_count()
        
        if chunk_count > 0:
            logger.info(f"Processing buffered audio on stop signal ({chunk_count} chunks)")
            await self._process_audio_buffer(session)
        else:
            await session.send_status("idle", "Ready")
    
    def get_active_sessions(self) -> list:
        """Get list of active session IDs."""
        return list(self.active_sessions.keys())
    
    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.active_sessions)
