@echo off
title AI Face Attendance - Web HTML Dashboard (>= 75% Accuracy)
color 0B
cd /d "%~dp0"

echo =====================================================================
echo    HE THONG DIEM DANH AI CAMERA - GIAO DIEN WEB HTML SIEU NHE
echo    - 3 Luong RTSP Full HD 1080p (GPL, Nha An, Tang Tret Ham Xe 2)
echo    - Yeu cau do chinh xac toi thieu: >= 75.0%% de ghi nhan dung nguoi
echo    - Xuat bao cao diem danh kem anh chup khuon mat thuc te
echo    - Web Dashboard: http://localhost:5055
echo =====================================================================
echo.

python web_face_attendance.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh bi dung dot ngot hoac co loi.
    pause
) else (
    echo.
    echo [*] Da dong he thong an toan.
    pause
)
