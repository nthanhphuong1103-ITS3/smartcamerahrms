@echo off
title AI Camera Face Attendance System - MSNV 4642
color 0A
cd /d "%~dp0"

echo =====================================================================
echo    KHOI CHAY HE THONG NHAN DIEN KHUON MAT CHAM CONG CAMERA
echo    Tu dong quet CSDL: luxand\Release\Image User
echo =====================================================================
echo.

python camera_face_attendance.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh bi loi hoac can kiem tra lai moi truong Python.
    pause
)
