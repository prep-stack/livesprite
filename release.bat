@echo off
REM LiveSprite release helper.
REM Usage: release.bat 2.1.0
REM   1. make sure version.py says VERSION = "2.1.0" first!
REM   2. builds the exe, zips it, commits, tags and pushes
REM   3. then create the GitHub release and attach the zip:
REM      https://github.com/prep-stack/livesprite/releases/new?tag=v%1

if "%~1"=="" (
    echo Usage: release.bat VERSION     e.g. release.bat 2.1.0
    exit /b 1
)
cd /d "%~dp0"

echo === Building exe...
call build_exe.bat nopause
if not exist "dist\LiveSprite\LiveSprite.exe" (
    echo Build failed!
    exit /b 1
)

echo === Zipping...
if exist "dist\LiveSprite-v%1.zip" del "dist\LiveSprite-v%1.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\LiveSprite\*' -DestinationPath 'dist\LiveSprite-v%1.zip'"

echo === Committing and tagging...
git add -A
git commit -m "Release v%1"
git tag v%1
git push origin main --tags

echo.
echo Done! Now open this page and attach dist\LiveSprite-v%1.zip:
echo   https://github.com/prep-stack/livesprite/releases/new?tag=v%1
start https://github.com/prep-stack/livesprite/releases/new?tag=v%1
pause
