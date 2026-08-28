@echo off
echo Stopping Infrastructure Containers...
cd infra
docker compose down
cd ..

echo Infrastructure stopped.
echo Note: Close the backend and frontend command windows to stop local dev servers.
pause
