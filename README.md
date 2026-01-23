# CognitiveAI – A Memory-Augmented Personal Intelligence Engine

A high-performance AI agent with short-term memory, long-term vector memory, PDF knowledge ingestion, and autonomous reasoning, built using modern LLMOps architecture.

## Core MVP Features

### 1. Real Time Voice Agent Implementation
Currently the backend is complete. Whisper for STT and Coqui for TTS. Next up Frontend Implementation.

### 2. Short-Term Memory (STM) Manager
Maintains a rolling context window of the last N user interactions using a lightweight buffer memory with relevance scoring.

### 3. Long-Term Memory (LTM) Engine
Stores user facts, preferences, tasks, and past conversation highlights using vector embeddings.

### 4. PDF Knowledge Loader
Uses Unstructured for extraction, auto-chunks, embeds, and stores PDF content into the vector database.

### 5. Cognitive Loop (Reasoning Engine)
Implements a minimal reflection cycle: input → recall → plan → respond → update memory.

### 6. Minimal FastAPI Backend
Clean FastAPI server with endpoints:
- `/chat` - Main chat interface
- `/upload_pdf` - PDF knowledge ingestion
- `/memory_view` - Memory inspection


### 7. Frontend
Next.js interface for clean, fast deployment.

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the backend:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```
5. Run the frontend
   ```bash
   cd frontend
   npm run dev
   ```

## Architecture

```
Frontend (NEXT.JS) ←→ FastAPI Backend ←→ Memory System
                                      ↓
                               Pinecone Vector DB
                                      ↓
                               PDF Knowledge Base
```

## Usage

1. Upload PDFs via `/upload_pdf` to build knowledge base
2. Chat with the AI via `/chat` endpoint
3. View memory contents via `/memory_view`

The system maintains context across conversations and leverages uploaded knowledge for informed responses.

## Docker Deployment

### Local Testing with Docker

1. **Build the Docker image:**
   ```bash
   docker build -t ai-therapist .
   ```

2. **Run with Docker Compose:**
   ```bash
   # Copy environment template
   cp .env.docker.example .env
   
   # Edit .env with your API keys
   # Then run:
   docker-compose up
   ```

3. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - Health Check: http://localhost:8000/health

### Deploying to Render

1. **Push your code to GitHub**

2. **Create a new Web Service on Render:**
   - Connect your GitHub repository
   - Select "Docker" as the environment
   - Render will automatically detect the `Dockerfile`

3. **Configure Environment Variables:**
   Add these in the Render dashboard:
   - `PERPLEXITY_API_KEY`
   - `PINECONE_API_KEY`
   - `PINECONE_ENVIRONMENT`
   - `REDIS_URL`
   - `JWT_SECRET_KEY` (generate a secure random string)
   - `JINA_API_KEY`
   - `STM_TTL` (default: 3600)
   - `FRONTEND_URL` (your Render app URL)

4. **Deploy:**
   - Render will build and deploy automatically
   - Monitor the build logs for any issues
   - Access your app at the provided Render URL

### Database Persistence on Render

⚠️ **Important:** SQLite databases are ephemeral in Docker containers by default.

**Options:**
- **Persistent Disk** (Recommended): Enable Render's persistent disk feature (paid plans)
- **PostgreSQL**: Migrate to Render's free PostgreSQL database
- **Accept Resets**: Database will reset on each deployment (not recommended for production)

### Troubleshooting

- **Build fails**: Check that all dependencies are in `requirements.txt` and `package.json`
- **Services don't start**: Verify environment variables are set correctly
- **Database issues**: Ensure proper database configuration (SQLite path or PostgreSQL connection)
- **API errors**: Check health endpoint at `/health` for service status
