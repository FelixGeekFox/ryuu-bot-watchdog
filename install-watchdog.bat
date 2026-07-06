@echo off
REM Ryuu K Bot Watchdog - Windows startup script
REM Run this instead of bot.py directly. It starts the bot AND the watchdog/webhook server.

cd /d "%~dp0"

REM Set PYTHONUTF8
set PYTHONUTF8=1

REM Start the watchdog (which starts the bot automatically)
python watchdog.py

REM If watchdog exits, wait 5s and restart it
:loop
timeout /t 5 /nobreak >nul
echo [launcher] Watchdog exited, restarting...
python watchdog.py
goto loop
