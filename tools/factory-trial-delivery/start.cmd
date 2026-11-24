@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "TRIAL_ROOT=%~dp0"
if not exist "%TRIAL_ROOT%runtime\python.exe" goto missing_runtime
if not exist "%TRIAL_ROOT%launch.py" goto incomplete
if not exist "%TRIAL_ROOT%trial.json" goto incomplete
if not exist "%TRIAL_ROOT%backend\app\main.py" goto incomplete
if not exist "%TRIAL_ROOT%web\index.html" goto incomplete
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set "PYTHONIOENCODING=utf-8:backslashreplace"
set PYTHONUNBUFFERED=1
if not exist "%TRIAL_ROOT%data" mkdir "%TRIAL_ROOT%data"
if not exist "%TRIAL_ROOT%data" goto unwritable
"%ComSpec%" /d /c exit 0
>>"%TRIAL_ROOT%data\startup-console.log" echo --- Trial start ---
if errorlevel 1 goto unwritable
>>"%TRIAL_ROOT%data\startup-console.log" echo CPU: %PROCESSOR_ARCHITECTURE%
echo Starting local trial. The page will open automatically.
echo Keep this window open. Press Ctrl+C to stop.
echo Startup details: data\startup-console.log
"%TRIAL_ROOT%runtime\python.exe" -X utf8 "%TRIAL_ROOT%launch.py" %* >>"%TRIAL_ROOT%data\startup-console.log" 2>&1
set "TRIAL_EXIT=%ERRORLEVEL%"
if "%TRIAL_EXIT%"=="0" exit /b 0
echo.
echo Startup failed. Exit code: %TRIAL_EXIT%
echo Send STARTUP-ERROR.txt for support. It will open automatically.
>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo Startup failed. Exit code: %TRIAL_EXIT%
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo CPU: %PROCESSOR_ARCHITECTURE%
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo Full interpreter output: data\startup-console.log
if exist "%TRIAL_ROOT%data\startup-console.log" type "%TRIAL_ROOT%data\startup-console.log" >>"%TRIAL_ROOT%STARTUP-ERROR.txt"
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo --- Original exception ---
if exist "%TRIAL_ROOT%data\startup-error.log" type "%TRIAL_ROOT%data\startup-error.log" >>"%TRIAL_ROOT%STARTUP-ERROR.txt"
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo --- Application startup log ---
if exist "%TRIAL_ROOT%data\startup.log" type "%TRIAL_ROOT%data\startup.log" >>"%TRIAL_ROOT%STARTUP-ERROR.txt"
start "" notepad.exe "%TRIAL_ROOT%STARTUP-ERROR.txt"
pause
exit /b %TRIAL_EXIT%
:missing_runtime
echo Missing runtime\python.exe. Extract the WHOLE ZIP again.
>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo Missing runtime\python.exe. Extract the whole ZIP again.
pause
exit /b 2
:incomplete
echo Package incomplete. Extract the WHOLE ZIP to a short local folder.
>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo Missing launch.py, trial.json, backend\app\main.py or web\index.html.
pause
exit /b 3
:unwritable
echo Cannot write the data folder. Extract the WHOLE ZIP to a writable local folder.
pause
exit /b 4
