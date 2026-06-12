@echo off
title Gate.io Capital Preservation Bot
color 0A
cls

echo ============================================================
echo   Gate.io Capital Preservation Bot
echo ============================================================
echo.
echo   [1] Paper Trading  (Simulasyon - Risksiz)
echo   [2] Live Trading   (Gercek Para - Dikkat!)
echo   [3] Full Dev Mode  (Tum servisler)
echo   [4] Durdur         (Tum servisleri durdur)
echo   [5] Log Goster     (Son loglar)
echo   [6] Cikis
echo.
echo ============================================================

set /p CHOICE="Seciminiz (1-6): "

if "%CHOICE%"=="1" goto PAPER
if "%CHOICE%"=="2" goto LIVE
if "%CHOICE%"=="3" goto DEV
if "%CHOICE%"=="4" goto STOP
if "%CHOICE%"=="5" goto LOGS
if "%CHOICE%"=="6" goto EOF

echo Gecersiz secim!
pause
goto EOF

rem ============================================================
rem  PAPER TRADING
rem ============================================================
:PAPER
cls
echo.
echo [PAPER TRADING] Baslatiliyor...
echo   - Backend API : http://localhost:8000
echo   - Dashboard   : http://localhost:3000
echo   - Paper Worker: Aktif (simulasyon)
echo   - Scheduler   : KAPALI (gercek islem yok)
echo.

if not exist .env (
    echo [HATA] .env dosyasi bulunamadi!
    echo .env.example dosyasini .env olarak kopyalayin.
    pause
    goto EOF
)

docker compose --profile paper up --build -d
echo.
echo [PAPER TRADING] Baslatildi!
echo   Dashboard: http://localhost:3000
echo.
pause
goto EOF

rem ============================================================
rem  LIVE TRADING
rem ============================================================
:LIVE
cls
echo.
echo ***************************************************
echo *  DKKAT: GERCEK PARA ILE ISLEM YAPILACAKTIR!    *
echo *  Bot, Gate.io uzerinden gercek alim-satim       *
echo *  yapacaktir. Devam etmeden once:                 *
echo *                                                   *
echo *  1. .env dosyasinda API key/secret dogru mu?     *
echo *  2. BOT_ENABLED=true olarak ayarlandi mi?        *
echo *  3. Risk parametreleri kontrol edildi mi?         *
echo ***************************************************
echo.
set /p CONFIRM="Devam etmek istediginize emin misiniz? (E/H): "
if /I not "%CONFIRM%"=="E" goto EOF

echo.
echo [LIVE TRADING] Baslatiliyor...
echo   - Backend API : http://localhost:8000
echo   - Dashboard   : http://localhost:3000
echo   - Scheduler   : Aktif (gercek islem)
echo   - Paper Worker: KAPALI
echo.

if not exist .env (
    echo [HATA] .env dosyasi bulunamadi!
    echo .env.example dosyasini .env olarak kopyalayin.
    pause
    goto EOF
)

docker compose --profile live up --build -d
echo.
echo [LIVE TRADING] Baslatildi!
echo   Dashboard: http://localhost:3000
echo.
pause
goto EOF

rem ============================================================
rem  FULL DEV MODE
rem ============================================================
:DEV
cls
echo.
echo [DEV MODE] Tum servisler baslatiliyor...
echo   - Backend API  : http://localhost:8000
echo   - Dashboard    : http://localhost:3000
echo   - Paper Worker : Aktif
echo   - Scheduler    : Aktif
echo.

if not exist .env (
    echo [UYARI] .env dosyasi bulunamadi, ornek kopyalanıyor...
    copy .env.example .env >nul 2>&1
)

docker compose --profile paper --profile live up --build -d
echo.
echo [DEV MODE] Baslatildi!
echo.
pause
goto EOF

rem ============================================================
rem  STOP
rem ============================================================
:STOP
cls
echo.
echo Tum servisler durduruluyor...
docker compose --profile paper --profile live down
echo.
echo Tamamlandi!
pause
goto EOF

rem ============================================================
rem  LOGS
rem ============================================================
:LOGS
cls
echo.
echo Hangi servisin loglarini gormek istersiniz?
echo   [1] Backend
echo   [2] Scheduler
echo   [3] Paper Worker
echo   [4] Tumu
echo.
set /p LOG_CHOICE="Seciminiz (1-4): "

if "%LOG_CHOICE%"=="1" docker compose logs -f --tail=50 backend
if "%LOG_CHOICE%"=="2" docker compose --profile live logs -f --tail=50 scheduler
if "%LOG_CHOICE%"=="3" docker compose --profile paper logs -f --tail=50 paper-worker
if "%LOG_CHOICE%"=="4" docker compose --profile paper --profile live logs -f --tail=50

pause
goto EOF

:EOF
