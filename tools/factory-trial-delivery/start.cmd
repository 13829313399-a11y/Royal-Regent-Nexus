@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "TRIAL_ROOT=%~dp0"
if not exist "%TRIAL_ROOT%runtime\python.exe" goto missing_runtime
if not exist "%TRIAL_ROOT%launch.py" goto incomplete
if not exist "%TRIAL_ROOT%trial.json" goto incomplete
if not exist "%TRIAL_ROOT%backend\app\main.py" goto incomplete
if not exist "%TRIAL_ROOT%web\index.html" goto incomplete
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
"%TRIAL_ROOT%runtime\python.exe" -X utf8 "%TRIAL_ROOT%launch.py" %*
set "TRIAL_EXIT=%ERRORLEVEL%"
if "%TRIAL_EXIT%"=="0" exit /b 0
echo.
echo Startup failed. Exit code: %TRIAL_EXIT%
echo Send STARTUP-ERROR.txt and data\startup-error.log for support.
>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo Startup failed. Exit code: %TRIAL_EXIT%
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" ver
>>"%TRIAL_ROOT%STARTUP-ERROR.txt" echo CPU: %PROCESSOR_ARCHITECTURE%
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
