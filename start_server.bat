@echo off
echo [INFO] 포트 8000 프로세스 정리 중...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    taskkill /PID %%P /F >nul 2>&1
)
timeout /t 1 /nobreak >nul
echo [INFO] FastAPI 서버 시작 중...
cd /d C:\Users\user\workspaces\shorts
uv run python main_api.py
