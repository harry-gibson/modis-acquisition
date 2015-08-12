REM this isn't the best way of doing it... use ppx to run the commands in the GRAB_all_modis.txt file instead.
@echo off
for /l %%i in (2000,1,2014) do call :loop %%i
goto :eof

:loop 
call :checkinstances
if %INSTANCES% LSS 5 (
    echo Starting processing for %1
    REM start /min wait.exe 5 sec
    start /min python "O:\My Documents\MODIS_Processing\modisdownload\get_modis-1.3.0\get_modis.py" -s MOTA -p MCD43B4.005 -y %1 -b 001 -e 366)
    goto :eof
)
echo Waiting for others to close...
ping -n 3 ::1 >nul 2>&1
goto loop
goto :eof

:checkinstances
for /f "usebackq" %%t in (`tasklist /fo csv /fi "imagename eq python.exe"^|find /c /v ""`) do set INSTANCES=%%t
goto :eof