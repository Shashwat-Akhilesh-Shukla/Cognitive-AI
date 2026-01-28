"""
Direct model preloader - downloads and caches voice models to disk
Run this once to download models, they'll be cached permanently.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.voice.model_manager import ModelManager

def main():
    print("=" * 60)
    print("Voice Model Preloader")
    print("=" * 60)
    print()
    print("This will download and cache:")
    print("  • Whisper STT model (~1.5GB)")
    print("  • Coqui TTS model (~100MB)")
    print()
    print("Models will be cached to: backend/models/")
    print("This is a one-time download - models persist on disk.")
    print()
    print("⏳ Starting download... (this may take 5-10 minutes)")
    print()
    
    try:
        # Trigger model preload
        ModelManager.preload_models()
        
        print()
        print("=" * 60)
        print("✅ SUCCESS! All models downloaded and cached.")
        print("=" * 60)
        print()
        
        # Show model info
        info = ModelManager.get_model_info()
        print("Model Information:")
        print(f"  Cache Directory: {info['cache_dir']}")
        print(f"  STT Model: {info['config']['whisper_model']}")
        print(f"  TTS Model: {info['config']['coqui_model']}")
        print(f"  STT Loaded: {info['stt_loaded']}")
        print(f"  TTS Loaded: {info['tts_loaded']}")
        print()
        print("🎉 Voice mode is ready to use!")
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 60)
        print("❌ ERROR: Failed to download models")
        print("=" * 60)
        print(f"Error: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Check your internet connection")
        print("  2. Ensure you have enough disk space (~2GB)")
        print("  3. Check if faster-whisper and TTS are installed:")
        print("     pip install faster-whisper TTS")
        return 1

if __name__ == "__main__":
    sys.exit(main())
