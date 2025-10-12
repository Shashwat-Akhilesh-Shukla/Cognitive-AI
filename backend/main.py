from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from whisper_module import transcribe_audio_stream
from llm_module import stream_llm_response
from tts_module import tts_stream
import json
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connection established")
    try:
        while True:
            # Receive audio data as JSON with base64
            data = await websocket.receive_json()
            if data.get("type") == "audio":
                import base64
                audio_bytes = base64.b64decode(data["data"])
                logger.info("Received audio data")

                # 1. Speech-to-text using Whisper (get full transcription)
                full_text = ""
                async for partial_text in transcribe_audio_stream(audio_bytes):
                    full_text += partial_text + " "
                full_text = full_text.strip()
                logger.info(f"Transcription: {full_text}")

                # Send transcription
                await websocket.send_json({"type": "transcription", "data": full_text})

                # 2. LLM response from Perplexity Sonar (get full response)
                full_llm_response = ""
                async for llm_chunk in stream_llm_response(full_text):
                    full_llm_response += llm_chunk
                logger.info(f"LLM response: {full_llm_response}")

                # Send LLM response
                await websocket.send_json({"type": "llm_response", "data": full_llm_response})

                # 3. TTS audio stream from Piper
                async for audio_chunk in tts_stream(full_llm_response):
                    # Send audio as base64
                    audio_b64 = base64.b64encode(audio_chunk).decode('utf-8')
                    await websocket.send_json({"type": "audio_response", "data": audio_b64})
                logger.info("TTS streaming completed")

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error: {e}")
        await websocket.send_json({"type": "error", "data": str(e)})
