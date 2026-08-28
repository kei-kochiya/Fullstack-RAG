@echo off
echo [1/3] Starting Infrastructure Containers...
cd infra
docker compose up -d
cd ..

echo [2/3] Starting FastAPI Backend on http://localhost:8000...
start "RAG Backend" cmd /k "cd backend && uv run python main.py"

echo [3/3] Starting Next.js Frontend on http://localhost:3000...
start "RAG Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo =======================================================
echo Fullstack RAG System started!
echo Frontend: http://localhost:3000
echo Backend API Docs: http://localhost:8000/docs
echo MinIO Console: http://localhost:9001
echo Qdrant Dashboard: http://localhost:6333/dashboard
echo =======================================================
pause
