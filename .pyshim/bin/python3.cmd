@echo off
REM Alias of python.cmd. See that file for why this shim exists.
setlocal
set "PYTHONPATH=%~dp0.."
"%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" %*
exit /b %ERRORLEVEL%
