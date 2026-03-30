@echo off
:: stop_trading.bat — stop the trading system and generate the session report.
:: Called by Task Scheduler at market close (weekdays 4:05 PM ET).

cd /D "C:\Users\ironm\claude\DayTrading"

:: Load API keys (needed for session report generation)
call deploy\env.bat

for /f %%i in ('powershell -noprofile -command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%i
set LOGFILE=logs\session_%TODAY%.log

if not exist trading.pid (
    echo [WARN] trading.pid not found — system may not be running. >> %LOGFILE%
    goto report
)

:: Read PID and kill the process
for /f %%i in (trading.pid) do set PID=%%i
echo Stopping trading system ^(PID: %PID%^)... >> %LOGFILE%
taskkill /PID %PID% /F >nul 2>&1
del trading.pid >nul 2>&1

:: Brief pause to let the process exit
timeout /t 3 /nobreak >nul

:report
echo Generating session report... >> %LOGFILE%
py -3 main.py --paper --report >> %LOGFILE% 2>&1
echo Done. >> %LOGFILE%
