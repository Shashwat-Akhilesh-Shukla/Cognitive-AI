# TODO: Fix and Build Production-Grade Voice Chat Application

## 1. Fix Backend Logic
- [x] Fix backend/main.py: Change processing logic to transcribe full audio, then full LLM response, then stream TTS. Send JSON messages with types.

## 2. Fix TTS Module Bug
- [x] Fix backend/tts_module.py: Correct stream.write call in play_tts function.

## 3. Update Frontend Message Handling
- [x] Update frontend/src/components/VoiceChat.tsx: Adjust to receive JSON messages and handle audio properly.

## 4. Install Dependencies and Run App
- [x] Install backend requirements (pip install -r requirements.txt).
- [x] Ensure .env file with PERPLEXITY_API_KEY.
- [x] Download Piper TTS model if needed.
- [x] Run backend: uvicorn main:app --host 0.0.0.0 --port 8000
- [x] Install frontend dependencies: npm install
- [x] Run frontend: npm run dev

## 5. Test Application
- [ ] Test voice chat functionality for bugs.
- [ ] Debug and fix any remaining issues.

## 6. Enhance for Production
- [x] Add proper error handling and logging.
- [ ] Improve async processing and concurrency.
- [ ] Add environment configuration and security.
- [ ] Optimize performance and add monitoring.
