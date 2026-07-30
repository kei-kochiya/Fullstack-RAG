@echo off
echo Starting RAG Infrastructure (Docker)...
cd infra
docker compose up -d
cd ..

echo Starting FastAPI Backend...
start cmd /k "cd backend && .venv\Scripts\activate && python main.py"

echo Starting Next.js Frontend...
start cmd /k "cd frontend && npm run dev"

echo All systems started! The frontend and backend are running in separate windows.
pause
