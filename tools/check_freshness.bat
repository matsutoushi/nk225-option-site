@echo off
rem Checks whether the published site has caught up with JPX, and mails if not.
rem Called from Windows Task Scheduler.
rem
rem Comments here are ASCII on purpose: cmd.exe reads .bat in the system ANSI
rem codepage, so UTF-8 Japanese comments get mangled and cmd tries to run the
rem fragments as commands. See tools/README.md for the Japanese documentation.
rem
rem The last run's output is overwritten into tools\check_freshness.log.

cd /d "%~dp0.."
python tools\check_freshness.py > "tools\check_freshness.log" 2>&1
exit /b 0
