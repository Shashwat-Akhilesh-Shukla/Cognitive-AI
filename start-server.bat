@echo off
echo Starting CognitiveAI single-server deployment...

REM Start FastAPI server (serves both API and static frontend)
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
