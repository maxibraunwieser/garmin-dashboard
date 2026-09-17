@echo off
REM Runs the Garmin sync and appends the result to sync.log.
REM Called by the "Garmin morning sync" scheduled task; you can also double-click it.
cd /d "C:\Users\User\Desktop\Garmin"
echo. >> "C:\Users\User\Desktop\Garmin\sync.log"
echo ===== %DATE% %TIME% ===== >> "C:\Users\User\Desktop\Garmin\sync.log"
py sync_garmin.py --days 3 --sink files --out "C:\Users\User\Desktop\Garmin\garmin" >> "C:\Users\User\Desktop\Garmin\sync.log" 2>&1
py make_dashboard.py >> "C:\Users\User\Desktop\Garmin\sync.log" 2>&1
