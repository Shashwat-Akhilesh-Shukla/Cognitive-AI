import numpy as np
import asyncio
from piper.voice import PiperVoice

MODEL_PATH = "./models/en_US-amy.onnx"
voice = PiperVoice.load(MODEL_PATH)

async def tts_stream(text: str):
    """Stream TTS audio chunks as they're generated"""
    for audio_bytes in voice.synthesize(text):
        # Convert bytes to numpy array if needed for your use case
        # int_data = np.frombuffer(audio_bytes, dtype=np.int16)
        await asyncio.sleep(0.001)
        yield audio_bytes

async def play_tts(text):
    import sounddevice as sd
    stream = sd.OutputStream(
        samplerate=voice.config.sample_rate,
        channels=1,
        dtype='int16'
    )
    stream.start()

    try:
        async for audio_chunk in tts_stream(text):
            int_data = np.frombuffer(audio_chunk, dtype=np.int16)
            stream.write(int_data)
    finally:
        stream.stop()
        stream.close()
