@echo off
rem Launcher: installs uv (the toolkit's runner) if missing, then runs
rem normalize-tabular-data in an ephemeral uvx environment.
rem Windows launcher (batch); double-click it or run from a terminal.
rem EXTRA: "--add-shortcut" (or /add-shortcut) creates a Desktop icon
rem pointing at this file, using normalize-tabular-data.ico beside it
rem when that icon file is present.

setlocal

set "ARG1=%~1"
if "%ARG1%"=="--add-shortcut" goto shortcut
if "%ARG1%"=="/add-shortcut" goto shortcut

where uvx >nul 2>nul
if %errorlevel%==0 goto run

echo uv is not installed yet; retrieving the installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if %errorlevel% neq 0 goto failed

rem the installer does not update the PATH of a running session
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uvx >nul 2>nul
if %errorlevel% neq 0 goto failed

:run
uvx normalize-tabular-data %*
goto end

:shortcut
rem a .lnk shortcut on the Desktop is the native Windows icon; only
rem PowerShell can create one programmatically, via WScript.Shell COM
set "SELF=%~f0"
set "ICON=%~dp0normalize-tabular-data.ico"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Normalize Tabular Data.lnk'); $s.TargetPath = '%SELF%'; $s.WorkingDirectory = [IO.Path]::GetDirectoryName('%SELF%'); $s.Save()"
if %errorlevel% neq 0 goto shortcut_failed
rem a .cmd cannot carry an icon itself; the shortcut points at a .ico
rem file shipped next to this launcher when one exists
if exist "%ICON%" powershell -NoProfile -ExecutionPolicy Bypass -Command "$w = New-Object -ComObject WScript.Shell; $s = $w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Normalize Tabular Data.lnk'); $s.IconLocation = '%ICON%,0'; $s.Save()"
echo Created desktop shortcut "Normalize Tabular Data".
echo Double-clicking it starts the application (its first run installs
echo uv if it is not present yet).
goto end

:shortcut_failed
echo Could not create the Desktop shortcut. >&2
pause
exit /b 1

:failed
echo uv could not be installed automatically; install it first from
echo https://docs.astral.sh/uv/getting-started/installation/
pause
exit /b 1

:end
endlocal
