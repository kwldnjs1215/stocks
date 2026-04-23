@echo off
echo Starting Stock Dashboard...

start "FastAPI Backend" cmd /k "python api.py"

timeout /t 2 /nobreak >nul

start "React Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 3 /nobreak >nul

start http://localhost:5176
