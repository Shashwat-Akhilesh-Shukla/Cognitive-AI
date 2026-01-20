# Multi-stage Dockerfile for AI Therapist
# Combines Next.js frontend and FastAPI backend into a single container

# ============================================
# Stage 1: Build Frontend (Next.js)
# ============================================
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy frontend package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy frontend source
COPY frontend/ ./

# Build Next.js application
RUN npm run build

# ============================================
# Stage 2: Production Image
# ============================================
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy backend requirements
COPY backend/requirements.txt ./backend/

# Install Python dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source code
COPY backend/ ./backend/

# Copy entire built frontend from builder stage
# This includes .next, node_modules, and all source files
COPY --from=frontend-builder /app/frontend ./frontend

# Copy startup script
COPY start.sh ./
RUN chmod +x start.sh

# Create directory for SQLite database (if using persistent volume)
RUN mkdir -p /app/data

# Expose ports
# Port 3000: Frontend (Next.js)
# Port 8000: Backend (FastAPI)
EXPOSE 3000 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV NODE_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run startup script
CMD ["./start.sh"]
