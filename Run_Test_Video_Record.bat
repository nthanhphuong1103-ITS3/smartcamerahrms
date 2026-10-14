@echo off
title AI Face Recognition - Video Record Analyzer
color 0B
cd /d "%~dp0"

echo =====================================================================
echo    HE THONG KIEM TEST NHAN DIEN KHUON MAT TU FILE RECORD VIDEO
echo    Thu muc video: %~dp0videos\
echo =====================================================================
echo.
echo  Chon che do kiem test:
echo.
echo  [1] Mo cua so xem truc quan (GUI Player - Mac dinh)
echo      - Tua, tam dung, doi toc do (1x, 2x, 4x), soi goc mat va do net px
echo.
echo  [2] Quet sieu toc toan bo video (Fast Auto-Scan)
echo      - Quet nhanh video 1 tieng chi trong vai phut
echo      - Tu dong chup anh nhan vien va xuat file bao cao CSV
echo.
set /p choice="Nhap lua chon [1 hoac 2, mac dinh 1]: "

if "%choice%"=="2" (
    echo.
    echo [*] Dang khoi dong che do Quet sieu toc (Fast Scan)...
    python test_video_record.py --fast --step 10
) else (
    echo.
    echo [*] Dang khoi dong Trinh xem va kiem test video truc quan (GUI Player)...
    python test_video_record.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Chuong trinh bi loi hoac dung dot ngot. Ma loi: %ERRORLEVEL%
    pause
) else (
    echo.
    echo [*] Hoan tat kiem test.
    pause
)
