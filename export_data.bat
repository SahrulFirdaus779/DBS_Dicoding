@echo off
title ZakatSight - Export Data dari MongoDB

cd /d "%~dp0services\web_dashboard"

echo.
echo Exporting data from MongoDB to ..\..\data\raw\mongodb_export
echo Tip: set MONGO_URI / MONGO_DB via environment variables if needed.
echo.

.\env\Scripts\python.exe export_from_mongodb.py

echo.
echo Export selesai.
pause
