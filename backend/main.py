from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from whisper_module import transcribe_audio_stream
from llm_module import stream_llm_response
from tts_module import tts_stream

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            audio_bytes = await websocket.receive_bytes()
            # 1. Speech-to-text using Whisper (returns text_iter)
            text_iter = transcribe_audio_stream(audio_bytes)
            async for partial_text in text_iter:
                await websocket.send_text(partial_text)
                # 2. LLM response from Perplexity Sonar (streamed)
                llm_iter = stream_llm_response(partial_text)
                async for llm_chunk in llm_iter:
                    await websocket.send_text(llm_chunk)
                    # 3. TTS audio stream from Coqui
                    tts_audio_stream = tts_stream(llm_chunk)
                    async for audio_chunk in tts_audio_stream:
                        await websocket.send_bytes(audio_chunk)
    except WebSocketDisconnect:
        print("Client disconnected")
