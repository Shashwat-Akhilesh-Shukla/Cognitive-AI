"""
WebSocket Handler for Voice Chat

Manages real-time bidirectional audio streaming for voice conversations.
"""

import json
import base64
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import time

from fastapi import WebSocket, WebSocketDisconnect
from .audio_utils import AudioBuffer, AudioProcessor, AudioValidator
from .model_manager import ModelManager

logger = logging.getLogger(__name__)


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
        
        # Audio processing
        self.audio_buffer = AudioBuffer(
            chunk_duration=float(os.getenv("AUDIO_CHUNK_DURATION", "3.0")),  # Not used for auto-processing anymore
            max_duration=float(os.getenv("MAX_AUDIO_DURATION", "300.0"))  # 5 minutes max
        )
        self.audio_processor = AudioProcessor()
        self.audio_validator = AudioValidator()
        
        # Session state
        self.is_active = True
        self.current_state = "idle"  # idle, listening, processing, speaking
        
        # Statistics
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'transcriptions': 0,
            'syntheses': 0,
            'errors': 0,
            'start_time': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Voice session created: {self.session_id}")
    
    async def send_status(self, state: str, message: Optional[str] = None):
        """
        Send status update to client.
        
        Args:
            state: Current state (idle, listening, processing, speaking)
            message: Optional status message
        """
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
        """
        Send transcription result to client.
        
        Args:
            text: Transcribed text
            language: Detected language
        """
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
        """
        Send audio data to client.
        
        Args:
            audio_bytes: Audio data (WAV format)
        """
        try:
            # Convert to base64 for JSON transmission
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
        """
        Send error message to client.
        
        Args:
            error_message: Error description
            error_code: Optional error code
        """
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
        """
        Send conversation metadata update to client.
        
        Args:
            conversation_id: Conversation ID
            title: Optional conversation title
        """
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
        return {
            **self.stats,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'conversation_id': self.conversation_id,
            'current_state': self.current_state,
            'is_active': self.is_active,
            'buffer_duration': self.audio_buffer.get_duration(),
            'buffer_chunks': self.audio_buffer.get_chunk_count()
        }
    
    def close(self):
        """Close the session and cleanup resources."""
        self.is_active = False
        self.audio_buffer.clear()
        logger.info(f"Voice session closed: {self.session_id}")


class VoiceWebSocketHandler:
    """
    Handles WebSocket connections for voice chat.
    
    Orchestrates STT, LLM processing, and TTS for real-time conversations.
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
        """
        Initialize WebSocket handler.
        
        Args:
            reasoning_engine: Cognitive reasoning engine
            conversation_manager: Conversation manager
            database: Database instance
            stm_manager: Short-term memory manager
            ltm_manager: Long-term memory manager
            pdf_loader: PDF loader instance
        """
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
        """
        Handle a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            user_id: Authenticated user ID
            conversation_id: Optional conversation ID
        """
        # Accept connection
        await websocket.accept()
        
        # Create session
        session = VoiceSession(websocket, user_id, conversation_id)
        self.active_sessions[session.session_id] = session
        
        # Send initial status
        await session.send_status("idle", "Voice session connected")
        
        try:
            # Main message loop
            while session.is_active:
                try:
                    # Receive message from client
                    message = await websocket.receive_json()
                    session.stats['messages_received'] += 1
                    
                    # Handle different message types
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
            # Cleanup
            session.close()
            if session.session_id in self.active_sessions:
                del self.active_sessions[session.session_id]
            
            logger.info(f"Session stats: {session.get_stats()}")
    
    async def _handle_audio(self, session: VoiceSession, message: dict):
        """
        Handle incoming audio data.
        
        Args:
            session: Voice session
            message: Audio message
        """
        try:
            # Update status
            await session.send_status("listening", "Receiving audio")
            
            # Extract audio data
            audio_data_b64 = message.get('data')
            if not audio_data_b64:
                logger.warning("No audio data provided in message")
                await session.send_error("No audio data provided")
                return
            
            # Decode audio
            audio_bytes = session.audio_processor.base64_to_bytes(audio_data_b64)
            logger.debug(f"Received audio chunk: {len(audio_bytes)} bytes from {session.user_id}")
            
            # Add to buffer (don't process automatically)
            session.audio_buffer.add(audio_bytes)
            buffer_duration = session.audio_buffer.get_duration()
            buffer_chunks = session.audio_buffer.get_chunk_count()
            logger.debug(f"Buffer: {buffer_chunks} chunks, {buffer_duration:.2f}s duration")
            
            # Check if buffer is ready for processing
            if session.audio_buffer.is_ready() or session.audio_buffer.is_full():
                logger.info(f"Buffer ready for processing (ready={session.audio_buffer.is_ready()}, full={session.audio_buffer.is_full()})")
                await self._process_audio_buffer(session)
        
        except Exception as e:
            logger.error(f"Error handling audio: {e}", exc_info=True)
            await session.send_error(f"Audio processing error: {str(e)}")
    
    async def _process_audio_buffer(self, session: VoiceSession):
        """
        Process buffered audio through STT → LLM → TTS pipeline.
        
        Args:
            session: Voice session
        """
        try:
            # Update status
            await session.send_status("processing", "Transcribing audio")
            
            # Get combined audio from buffer
            audio_bytes = session.audio_buffer.get_audio()
            logger.info(f"Processing {len(audio_bytes)} bytes of audio from {session.user_id}")
            
            # Validate audio
            if not session.audio_validator.is_valid_audio(audio_bytes, min_duration=0.5):
                logger.warning(f"Invalid or too short audio ({len(audio_bytes)} bytes), skipping")
                session.audio_buffer.clear()
                await session.send_status("idle", "Audio too short, please speak longer")
                return
            
            # Convert to WAV and resample to 16kHz (Whisper requirement)
            try:
                logger.info("Resampling audio to 16kHz")
                audio_bytes = session.audio_processor.resample_audio(audio_bytes, target_sample_rate=16000)
                logger.info(f"Resampled audio: {len(audio_bytes)} bytes")
            except Exception as e:
                logger.warning(f"Audio conversion failed, using original: {e}")
            
            # Step 1: Speech-to-Text
            logger.info("Loading STT model...")
            stt_model = ModelManager.get_stt_model()
            if not stt_model:
                logger.error("STT model is None - voice functionality unavailable")
                await session.send_error("STT model not available")
                return
            
            logger.info("Transcribing audio...")
            transcript_result = await stt_model.transcribe(audio_bytes)
            transcript_text = transcript_result.get('text', '').strip()
            
            if not transcript_text:
                logger.warning("Empty transcription result")
                session.audio_buffer.clear()
                await session.send_status("idle", "No speech detected")
                return
            
            logger.info(f"✓ Transcribed: {transcript_text}")
            
            # Send transcript to client
            await session.send_transcript(
                transcript_text,
                transcript_result.get('language', 'en')
            )
            
            # Clear buffer after successful transcription
            session.audio_buffer.clear()
            
            # Step 2: Process through LLM
            logger.info("Processing through LLM...")
            await session.send_status("processing", "Generating response")
            
            response_text = await self._process_with_llm(
                session,
                transcript_text
            )
            
            if not response_text:
                logger.error("LLM returned empty response")
                await session.send_error("Failed to generate response")
                return
            
            logger.info(f"✓ LLM Response: {response_text}")
            
            # Send response to client
            try:
                await session.websocket.send_json({
                    'type': 'response',
                    'text': response_text
                })
            except Exception as e:
                logger.warning(f"Failed to send response: {e}")
            
            # Step 3: Text-to-Speech (optional)
            logger.info("Synthesizing response audio...")
            await session.send_status("speaking", "Synthesizing speech")
            
            tts_model = ModelManager.get_tts_model()
            if not tts_model:
                logger.warning("TTS model not available, skipping audio synthesis")
                await session.send_status("idle", "Ready for next message")
                return
            
            audio_response = await tts_model.synthesize(response_text)
            
            # Send audio to client
            logger.info(f"Sending audio response ({len(audio_response)} bytes)...")
            await session.send_audio(audio_response)
            
            # Back to idle
            await session.send_status("idle", "Ready for next message")
        
        except Exception as e:
            logger.error(f"Error processing audio buffer: {e}", exc_info=True)
            await session.send_error(f"Processing error: {str(e)}")
            session.audio_buffer.clear()
            await session.send_status("idle", "Ready")
    
    async def _process_with_llm(
        self,
        session: VoiceSession,
        user_message: str
    ) -> Optional[str]:
        """
        Process user message through the reasoning engine.
        
        Args:
            session: Voice session
            user_message: Transcribed user message
        
        Returns:
            str: AI response text
        """
        try:
            # Retrieve memories (same as text chat)
            stm_list = []
            if self.stm_manager:
                try:
                    raw_stm = self.stm_manager.get_relevant_memories(
                        session.user_id,
                        user_message,
                        limit=5
                    )
                    for m in raw_stm:
                        try:
                            stm_list.append({
                                'content': getattr(m, 'content', str(m)),
                                'timestamp': getattr(m, 'timestamp', time.time()),
                                'importance': getattr(m, 'importance', 1.0)
                            })
                        except Exception:
                            stm_list.append({'content': str(m)})
                except Exception:
                    pass
            
            ltm_list = []
            if self.ltm_manager:
                try:
                    ltm_list = self.ltm_manager.search_memories(
                        user_message,
                        limit=5,
                        user_id=session.user_id
                    )
                except Exception:
                    pass
            
            pdf_snippets = []
            if self.pdf_loader:
                try:
                    chunks = self.pdf_loader.search_pdf_knowledge(
                        query=user_message,
                        limit=3,
                        user_id=session.user_id
                    )
                    for c in chunks:
                        content = c.get('content', '')[:300]
                        pdf_snippets.append(content)
                except Exception:
                    pass
            
            # Process through reasoning engine
            result = await self.reasoning_engine.process_message(
                user_message=user_message,
                user_id=session.user_id,
                stm_memories=stm_list,
                ltm_memories=ltm_list,
                pdf_snippets=pdf_snippets
            )
            
            # Update memories
            try:
                actions = result.get('memory_actions', []) if isinstance(result, dict) else []
                for action in actions:
                    if not isinstance(action, dict):
                        continue
                    
                    if action.get('type') == 'stm' and self.stm_manager:
                        try:
                            self.stm_manager.add_memory(
                                session.user_id,
                                action.get('content', ''),
                                importance=action.get('importance', 0.8)
                            )
                        except Exception:
                            pass
                    
                    elif action.get('type') == 'ltm' and self.ltm_manager:
                        try:
                            self.ltm_manager.add_memory(
                                action.get('content', ''),
                                memory_type=action.get('memory_type', 'note'),
                                metadata={'user_id': session.user_id},
                                importance=action.get('importance', 0.7),
                                user_id=session.user_id
                            )
                        except Exception:
                            pass
            except Exception:
                pass
            
            # Manage conversation
            if not session.conversation_id:
                # Create new conversation
                session.conversation_id = self.conversation_manager.create_conversation(
                    session.user_id
                )
                
                # Generate title from first message
                title = self.conversation_manager.generate_title_from_message(user_message)
                self.conversation_manager.update_conversation_title(
                    session.conversation_id,
                    title
                )
                
                # Notify client
                await session.send_conversation_update(session.conversation_id, title)
            else:
                # Update existing conversation timestamp
                self.conversation_manager.update_conversation_timestamp(
                    session.conversation_id
                )
            
            # Store messages in database
            if self.database:
                timestamp = time.time()
                
                # Store user message
                self.database.add_message(
                    session.conversation_id,
                    session.user_id,
                    "user",
                    user_message,
                    timestamp,
                    metadata={'mode': 'voice'}
                )
                
                # Store assistant response
                self.database.add_message(
                    session.conversation_id,
                    session.user_id,
                    "assistant",
                    result.get('response', ''),
                    timestamp + 0.001,
                    metadata={'mode': 'voice', 'reasoning': result.get('reasoning', {})}
                )
            
            return result.get('response', '')
        
        except Exception as e:
            logger.error(f"LLM processing error: {e}")
            return None
    
    async def _handle_stop(self, session: VoiceSession):
        """
        Handle stop command from client.
        
        Args:
            session: Voice session
        """
        logger.info(f"Stop signal received from {session.user_id}")
        
        # Check buffer status
        chunk_count = session.audio_buffer.get_chunk_count()
        buffer_duration = session.audio_buffer.get_duration()
        logger.info(f"Buffer status: {chunk_count} chunks, {buffer_duration:.2f}s duration")
        
        # Process any remaining audio in buffer
        if chunk_count > 0:
            logger.info(f"Processing buffered audio on stop signal ({buffer_duration:.2f}s)")
            await self._process_audio_buffer(session)
        else:
            logger.info("Buffer empty, no audio to process")
            await session.send_status("idle", "Ready")
    
    def get_active_sessions(self) -> list:
        """Get list of active session IDs."""
        return list(self.active_sessions.keys())
    
    def get_session_count(self) -> int:
        """Get number of active sessions."""
        return len(self.active_sessions)


# Import os for environment variables
import os
