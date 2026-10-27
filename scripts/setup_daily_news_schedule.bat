@echo off
chcp 65001 > nul
echo ======================================================================
echo   HAIZFLOW - ĐĂNG KÝ LỊCH TỰ ĐỘNG LÀM BẢN TIN THỜI SỰ (05:00 SÁNG)
echo ======================================================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_daily_news_schedule.ps1" -Time "05:00"
echo.
pause
