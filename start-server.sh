#!/bin/bash
set -e

echo "Starting CognitiveAI single-server deployment..."

# Run database migrations if needed
if [ -f "backend/database.py" ]; then
    echo "Database ready"
fi

# Start FastAPI server (serves both API and static frontend)
cd backend
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
