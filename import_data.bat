@echo off
title ZakatSight - Import Data ke MongoDB

cd /d "%~dp0services\web_dashboard"

echo.
echo [1/2] Mengimport data penerimaan donasi...
.\env\Scripts\python.exe import_to_mongodb.py

echo.
echo [2/2] Mengimport data mustahiq (penerima manfaat)...
.\env\Scripts\python.exe import_mustahiq_to_mongodb.py

echo.
echo  Import selesai! Silakan jalankan start.bat
pause
