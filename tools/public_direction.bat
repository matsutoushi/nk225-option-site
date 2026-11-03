@echo off
rem Accumulates the public-data-only dealer-direction estimate into
rem private\public_direction_history.csv. Called from Windows Task Scheduler.
rem
rem Comments here are ASCII on purpose: cmd.exe reads .bat in the system ANSI
rem codepage, so UTF-8 Japanese comments get mangled and cmd tries to run the
rem fragments as commands. See tools/README.md for the Japanese documentation.
rem
rem data\settle_*.csv and data\oi_*.csv are committed by GitHub Actions, so pull
rem first. A failed pull is not fatal: the script then runs on whatever is here.
rem
rem The last run's output is overwritten into tools\public_direction.log.

cd /d "%~dp0.."
git pull --ff-only > "tools\public_direction.log" 2>&1
python tools\public_direction.py --quiet >> "tools\public_direction.log" 2>&1
exit /b 0
