@echo off
rem Krypto-Signal-Bot starten (Doppelklick)
cd /d "%~dp0"
title Krypto-Signal-Bot

if exist ".venv\Scripts\python.exe" goto install

call :findpy
if defined PY goto makevenv
if exist "%LOCALAPPDATA%\Programs\Python\Python3*" goto badvenv

echo Python ist nicht installiert. Es wird jetzt automatisch installiert...
echo Falls Windows fragt, bitte mit "Ja" bestaetigen.
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
echo.
echo Python wurde installiert. Bitte dieses Fenster schliessen
echo und Start.bat noch einmal doppelklicken.
pause
exit /b 0

:makevenv
echo Erster Start: Python-Umgebung wird eingerichtet, bitte warten...
%PY% -m venv .venv
if errorlevel 1 goto badvenv

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
rem Sucht ein funktionierendes Python (nicht den Microsoft-Store-Platzhalter)
set "PY="
py -3 -c "import encodings" >nul 2>nul && set "PY=py -3" && exit /b 0
python -c "import encodings" >nul 2>nul && set "PY=python" && exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  "%%D\python.exe" -c "import encodings" >nul 2>nul && set "PY="%%D\python.exe""
)
exit /b 0

:badvenv
if exist ".venv" rmdir /s /q ".venv"
echo.
echo Python ist installiert, aber beschaedigt.
echo So reparierst du es: Windows-Einstellungen, Apps, Installierte Apps,
echo "Python 3.12" suchen, auf die drei Punkte, "Aendern", dann "Repair".
echo Oder den Installer von https://www.python.org/downloads/ starten und "Repair" waehlen.
echo Danach Start.bat noch einmal doppelklicken.
pause
exit /b 1

:fail
echo.
echo Installation der Pakete fehlgeschlagen. Bitte die Meldung oben an Claude schicken.
pause
exit /b 1
