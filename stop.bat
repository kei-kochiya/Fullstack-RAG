@echo off
echo Stopping RAG Infrastructure (Docker)...
cd infra
docker compose down
cd ..
echo.
echo Infrastructure stopped!
echo Note: Please close the Frontend and Backend command windows manually.
pause
