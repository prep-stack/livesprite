@echo off
echo LiveSprite - Build to EXE
echo =========================
echo.

cd /d "%~dp0"

REM Check PyInstaller
python -c "import PyInstaller" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo PyInstaller not found! Installing...
    pip install pyinstaller
    if %ERRORLEVEL% neq 0 (
        echo Failed to install PyInstaller.
        goto :error
    )
)

REM Clean previous builds
echo Cleaning previous build...
if exist "build" rmdir /S /Q "build" 2>nul
if exist "dist" rmdir /S /Q "dist" 2>nul

REM Build
echo Building executable...
pyinstaller LiveSprite.spec --noconfirm
if %ERRORLEVEL% neq 0 (
    echo Build failed!
    goto :error
)

REM Copy assets, config and icon next to the exe (kept as editable files)
echo Copying assets, config and icon...
xcopy /E /I /Y "assets" "dist\LiveSprite\assets" >nul
if exist "config" xcopy /E /I /Y "config" "dist\LiveSprite\config" >nul
copy /Y "soda.png" "dist\LiveSprite\" >nul

echo.
echo Build completed successfully!
echo The program is in:  dist\LiveSprite\LiveSprite.exe
echo Add new sprites by dropping GIF folders into dist\LiveSprite\assets\
echo.
goto :end

:error
echo.
if not "%~1"=="nopause" pause
exit /b 1

:end
if not "%~1"=="nopause" pause
exit /b 0
