@echo off
setlocal enabledelayedexpansion

:: ── 프로필 결정 (기본: company) ──────────────────────────────────
set "PROFILE=%~1"
if "!PROFILE!"=="" set "PROFILE=company"

set "ROOT=%~dp0"
set "ENV_FILE=!ROOT!.env.!PROFILE!"

if not exist "!ENV_FILE!" (
    echo.
    echo  [오류] !ENV_FILE! 파일이 없습니다.
    echo  .env.example 을 복사해서 .env.!PROFILE! 로 만들어 주세요.
    echo.
    pause & exit /b 1
)

:: ── .env.{profile} 파싱 ─────────────────────────────────────────
for /f "usebackq tokens=1,* delims==" %%K in ("!ENV_FILE!") do (
    set "_k=%%K"
    set "_k=!_k: =!"
    if not "!_k!"=="" (
        if not "!_k:~0,1!"=="#" (
            set "%%K=%%L"
        )
    )
)

:: ── 기본값 ──────────────────────────────────────────────────────
if "!BACKEND_PORT!"=="" set "BACKEND_PORT=8001"
if "!FRONTEND_PORT!"=="" set "FRONTEND_PORT=5176"

:: ── 안내 출력 ────────────────────────────────────────────────────
echo.
echo  ====================================================
echo   Stocks Dashboard  [!PROFILE!]
echo  ====================================================
echo   백엔드   http://localhost:!BACKEND_PORT!
echo   프론트   http://localhost:!FRONTEND_PORT!
echo  ====================================================
echo.

:: ── 기존 프로세스 종료 ───────────────────────────────────────────
echo  기존 서비스 종료 중...
for %%P in (!BACKEND_PORT! !FRONTEND_PORT!) do (
    for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr ":%%P " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%A >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul

:: ── 백엔드 시작 (env vars 상속됨) ───────────────────────────────
echo  백엔드 시작...
start "stocks 백엔드 [!PROFILE!]" cmd /k "cd /d "!ROOT!" && set STOCKS_PROFILE=!PROFILE! && .venv\Scripts\uvicorn api:app --host 0.0.0.0 --port !BACKEND_PORT! --reload"
timeout /t 2 /nobreak >nul

:: ── 프론트엔드 시작 ──────────────────────────────────────────────
echo  프론트엔드 시작...
start "stocks 프론트 [!PROFILE!]" cmd /k "cd /d "!ROOT!frontend" && set BACKEND_PORT=!BACKEND_PORT! && npm run dev -- --host 0.0.0.0 --port !FRONTEND_PORT! --strictPort"
timeout /t 3 /nobreak >nul

start http://localhost:!FRONTEND_PORT!
echo  완료!
