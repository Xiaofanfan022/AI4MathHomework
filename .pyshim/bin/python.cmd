@echo off
REM Convenience shim so ppt-master's documented "python <script>" and
REM "python3 <script>" commands work verbatim. Put this directory on PATH:
REM
REM   set "PATH=E:\AI4MathAgentHomework\.pyshim\bin;%PATH%"
REM
REM It forwards to the bundled Python 3.12 runtime with PYTHONPATH pointing at
REM .pyshim, which adds <workspace>\.deps to sys.path and fixes the sandbox's
REM restrictive temporary-directory permissions.
setlocal
set "PYTHONPATH=%~dp0.."
"%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe" %*
exit /b %ERRORLEVEL%
