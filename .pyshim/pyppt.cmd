@echo off
REM Wrapper: run ppt-master scripts with the bundled Python 3.12 runtime that
REM has the skill's dependencies installed in <workspace>\.deps.
REM
REM Usage:  .pyshim\pyppt.cmd <script.py> [args...]
REM         .pyshim\pyppt.cmd -c "print(1)"
REM
REM Why: system Python 3.13 cannot see .deps (cp312 binary wheels), and the
REM sandbox blocks writes to any site-packages.  The bundled runtime plus
REM PYTHONPATH=<workspace>\.pyshim gives us deps + the tempfile DACL fix.
setlocal
set "PYS=%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
set "ROOT=%~dp0.."
set "PYTHONPATH=%~dp0"
endlocal & set "PYS=%PYS%" & set "PYTHONPATH=%~dp0" & set "ROOT=%~dp0.."
"%PYS%" %*
exit /b %ERRORLEVEL%
