#!/usr/bin/env python3
"""
Quick test to verify voice pipeline is working
"""
import sys
import os
sys.path.insert(0, 'd:\\ai-therapist')

# Set environment
os.environ['VOICE_ENABLED'] = 'true'
os.environ['WHISPER_DEVICE'] = 'cpu'
os.environ['WHISPER_COMPUTE_TYPE'] = 'int8'

print("=" * 60)
print("VOICE PIPELINE DIAGNOSTIC TEST")
print("=" * 60)

# Test 1: Check imports
print("\n[TEST 1] Checking imports...")
try:
    from backend.voice.model_manager import ModelManager
    from backend.voice.websocket_handler import VoiceWebSocketHandler
    from backend.voice.audio_utils import AudioBuffer, AudioProcessor, AudioValidator
    print("✓ All imports successful")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Check voice enabled
print("\n[TEST 2] Checking voice enabled...")
if ModelManager.is_voice_enabled():
    print("✓ Voice is enabled")
else:
    print("✗ Voice is disabled")
    sys.exit(1)

# Test 3: Try to load STT model
print("\n[TEST 3] Loading STT model...")
print("   (This may take 1-2 minutes on first run)")
try:
    stt_model = ModelManager.get_stt_model()
    if stt_model:
        print(f"✓ STT model loaded successfully")
        print(f"   Model: {stt_model.model_name}")
        print(f"   Device: {stt_model.device}")
        print(f"   Compute type: {stt_model.compute_type}")
    else:
        print("✗ STT model is None")
        sys.exit(1)
except Exception as e:
    print(f"✗ Failed to load STT model: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Check TTS model
print("\n[TEST 4] Checking TTS model...")
try:
    tts_model = ModelManager.get_tts_model()
    if tts_model:
        print(f"✓ TTS model available")
    else:
        print("⚠ TTS model not available (optional)")
except Exception as e:
    print(f"⚠ TTS loading issue: {e}")

# Test 5: Test audio utilities
print("\n[TEST 5] Testing audio utilities...")
try:
    buffer = AudioBuffer()
    processor = AudioProcessor()
    validator = AudioValidator()
    print("✓ Audio utilities initialized")
except Exception as e:
    print(f"✗ Audio utilities failed: {e}")
    sys.exit(1)

# Test 6: Check model info
print("\n[TEST 6] Getting model info...")
try:
    info = ModelManager.get_model_info()
    print(f"✓ Model info retrieved:")
    for key, value in info.items():
        if key != 'cache_dir':
            print(f"   {key}: {value}")
except Exception as e:
    print(f"⚠ Could not get model info: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC SUMMARY")
print("=" * 60)
print("✓ All critical components working")
print("\nVoice pipeline should be functional!")
print("\nNext steps:")
print("1. Check browser console for [Voice] logs")
print("2. Verify audio chunks are being sent")
print("3. Check backend terminal for transcript logs")
print("4. If no transcript, check this output above")
print("=" * 60)
