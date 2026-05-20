@echo off
chcp 65001 >nul
echo Building ScreenshotTool...
pyinstaller screenshot_tool.spec --clean
echo Done. Check dist\ScreenshotTool.exe
pause
