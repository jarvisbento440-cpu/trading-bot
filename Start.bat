@echo off
rem Krypto-Signal-Bot starten (Doppelklick)
cd /d "%~dp0"
title Krypto-Signal-Bot

set "PY=python"
where py >/dev/null 2>/dev/null && set "PY=py -3"

if not exist ".venv\Scripts\python.exe" (
  echo Erster Start: Python-Umgebung wird eingerichtet, bitte warten...
  %PY% -m venv .venv
  if errorlevel 1 goto nopython
)

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

:nopython
echo.
echo Python wurde nicht gefunden.
echo Bitte Python von https://www.python.org/downloads/ installieren
echo und bei der Installation "Add python.exe to PATH" anhaken.
pause
exit /b 1

:fail
echo.
echo Installation der Pakete fehlgeschlagen. Bitte die Meldung oben an Claude schicken.
pause
exit /b 1
