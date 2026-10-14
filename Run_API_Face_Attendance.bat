@echo off
title AI Face Recognition - API Smart HRMS Attendance System
color 0A
cd /d "%~dp0"

echo =====================================================================
echo    HE THONG NHAN DIEN KHUON MAT CHAM CONG - DONG BO API SMART HRMS
echo    API: Getdata_List_Employee_Full (Bao mat HMAC-MD5)
echo    Tu dong hien thi the nhan su: Ho ten, Phong ban, Chuc danh, Cong ty...
echo =====================================================================
echo.

python api_face_attendance.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh bi dung dot ngot hoac co loi.
    pause
) else (
    echo.
    echo [*] Da dong he thong an toan.
    pause
)
