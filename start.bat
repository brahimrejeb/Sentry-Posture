@echo off
REM Wrapper around run.py.
REM
REM   start.bat            -> background launch (terminal returns immediately,
REM                           closing the window does NOT kill the app).
REM   start.bat foreground -> classic foreground run (Ctrl+C kills it).
REM
REM Either way, run.py handles dependency sync, model download, UI build
REM and then starts the backend + tray.

cd /d "%~dp0"

if /I "%~1"=="foreground" (
    shift
    where py >nul 2>&1
    if %errorlevel%==0 (
        py run.py %*
    ) else (
        python run.py %*
    )
    goto :eof
)

REM Background: detach via "start" so closing the terminal doesn't kill us.
if exist .venv\Scripts\pythonw.exe (
    start "Sentry" /B "" .venv\Scripts\pythonw.exe run.py %*
) else (
    where pythonw >nul 2>&1
    if %errorlevel%==0 (
        start "Sentry" /B "" pythonw run.py %*
    ) else (
        REM Last resort — first run probably, .venv doesn't exist yet.
        start "Sentry" /MIN python run.py %*
    )
)

echo.
echo Sentry is starting in the background.
echo Once it's up:
echo   - the dashboard will open in your default browser, OR
echo   - click the Sentry icon in your system tray (look for hidden icons),
echo   - or open http://127.0.0.1:47821/ manually.
echo Quit Sentry from the tray icon.
echo.
