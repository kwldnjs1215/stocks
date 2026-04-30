@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_PORT=8001"
set "FRONTEND_PORT=5176"

echo.
echo  ====================================================
echo   Stocks Dashboard
echo  ====================================================
echo   Backend local   http://localhost:%BACKEND_PORT%
echo   Backend network http://192.168.0.3:%BACKEND_PORT%
echo   Frontend local  http://localhost:%FRONTEND_PORT%
echo   Frontend net    http://192.168.0.3:%FRONTEND_PORT%
echo  ====================================================
echo.

echo  Stopping old services on 8001 / 5176 / 5177 / 5178...
for %%P in (8001 5176 5177 5178) do (
    for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%A >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul

echo  Starting backend...
start "stocks backend" cmd /k "cd /d "%ROOT%" && .venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port %BACKEND_PORT%"

timeout /t 2 /nobreak >nul

echo  Starting frontend...
start "stocks frontend" cmd /k "cd /d "%ROOT%frontend" && set BACKEND_PORT=%BACKEND_PORT%&& set FRONTEND_PORT=%FRONTEND_PORT%&& npm.cmd run dev -- --host 0.0.0.0 --port %FRONTEND_PORT% --strictPort"

timeout /t 3 /nobreak >nul
echo.
echo  Ready:
echo   http://localhost:%FRONTEND_PORT%
echo.
start http://localhost:%FRONTEND_PORT%
