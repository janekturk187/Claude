@echo off
:: start_paper.bat — launch the day trading system in paper mode.
:: Called by Task Scheduler at market open (weekdays 9:35 AM ET).

cd /D "C:\Users\ironm\claude\DayTrading"

:: Load API keys
call deploy\env.bat

:: Abort if keys are still placeholders
if "%ANTHROPIC_API_KEY%"=="YOUR_ANTHROPIC_API_KEY" (
    echo [ERROR] ANTHROPIC_API_KEY is not set in deploy\env.bat
    exit /b 1
)
if "%ALPACA_API_KEY%"=="YOUR_ALPACA_API_KEY" (
    echo [ERROR] ALPACA_API_KEY is not set in deploy\env.bat
    exit /b 1
)

:: Don't start if already running
if exist trading.pid (
    echo [WARN] trading.pid exists — system may already be running. Aborting.
    exit /b 1
)

:: Create logs directory
if not exist logs mkdir logs

:: Build a dated log filename using PowerShell (avoids locale issues with %%date%%)
for /f %%i in ('powershell -noprofile -command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
set LOGFILE=logs\session_%TODAY%.log

echo. >> %LOGFILE%
echo ============================================================ >> %LOGFILE%
echo  DayTrading Paper Session started %TODAY% >> %LOGFILE%
echo ============================================================ >> %LOGFILE%

:: Step 1: pre-market screener — picks today's watchlist, writes watchlist.json
echo [%date% %time%] Running pre-market screener... >> %LOGFILE%
py -3 screening/runner.py >> %LOGFILE% 2>&1
if errorlevel 1 echo [WARN] Screener found no picks — using config watchlist >> %LOGFILE%

:: Step 2: start trading (reads watchlist.json if it was written)
echo [%date% %time%] Starting paper trading session... >> %LOGFILE%
py -3 main.py --paper >> %LOGFILE% 2>&1

echo ============================================================ >> %LOGFILE%
echo  Session ended >> %LOGFILE%
echo ============================================================ >> %LOGFILE%
