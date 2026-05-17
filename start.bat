@echo off
title ZakatSight - Starting All Services

echo.
echo  ================================================
echo   ZakatSight Enterprise Platform - Startup
echo  ================================================
echo.

echo [1/2] Menjalankan Flask Backend API (Port 5000)...
cd /d "%~dp0services\web_dashboard"
start "ZakatSight - Flask API (Port 5000)" cmd /k ".\env\Scripts\python.exe app.py"
timeout /t 3 /nobreak >nul

echo [2/2] Menjalankan Next.js Frontend (Port 3000)...
cd /d "%~dp0services\frontend"
start "ZakatSight - Next.js Frontend (Port 3000)" cmd /k "npm run dev"

echo.
echo  ================================================
echo   Semua server berjalan! Buka browser:
echo.
echo   Internal Dashboard : http://localhost:3000
echo   Public Dashboard   : http://localhost:3000/transparansi
echo   Flask API          : http://localhost:5000/api/v1/public/stats
echo  ================================================
echo.
pause
