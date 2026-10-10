@echo off
rem Krypto-Signal-Bot starten (Doppelklick)
cd /d "%~dp0"
title Krypto-Signal-Bot

if exist ".venv\Scripts\python.exe" goto install

call :findpy
if defined PY goto makevenv

echo Python ist nicht installiert. Es wird jetzt automatisch installiert...
echo (Falls Windows fragt, bitte mit "Ja" bestaetigen.)
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpy
if not defined PY goto nopython

:makevenv
echo Erster Start: Python-Umgebung wird eingerichtet, bitte warten...
%PY% -m venv .venv
if errorlevel 1 goto nopython

:install
echo Pruefe Pakete...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail

echo.
echo Oberflaeche startet. Dieses Fenster offen lassen, solange der Bot laufen soll.
echo Beim allerersten Start werden 2 Jahre Kursdaten geladen, das dauert einige Minuten.
echo.
".venv\Scripts\python.exe" -m signalbot ui
pause
exit /b 0

:findpy
rem Sucht ein echtes Python (nicht den Microsoft-Store-Platzhalter)
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3" && exit /b 0
python --version >nul 2>nul && set "PY=python" && exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY="%%D\python.exe""
exit /b 0

:nopython
echo.
echo Python konnte nicht automatisch installiert werden.
echo Bitte Python von https://www.python.org/downloads/ installieren,
echo bei der Installation "Add python.exe to PATH" anhaken
echo und danach Start.bat noch einmal doppelklicken.
pause
exit /b 1

:fail
echo.
echo Installation der Pakete fehlgeschlagen. Bitte die Meldung oben an Claude schicken.
pause
exit /b 1
