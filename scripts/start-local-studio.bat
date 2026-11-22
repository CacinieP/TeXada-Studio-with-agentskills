@echo off
setlocal
chcp 65001 >nul
REM Portable double-click entry for Windows. Install dependencies explicitly, never silently.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_DIR=%%~fI"
cd /d "%REPO_DIR%" || exit /b 1

if defined TEXADA_STUDIO_PYTHON (
    if exist "%TEXADA_STUDIO_PYTHON%" (
        set "STUDIO_PYTHON=%TEXADA_STUDIO_PYTHON%"
        goto :run
    )
)

if exist "%REPO_DIR%\.venv\Scripts\python.exe" (
    set "STUDIO_PYTHON=%REPO_DIR%\.venv\Scripts\python.exe"
    goto :run
)

echo 未找到项目虚拟环境。请先在此项目目录执行：
echo py -3.13 -m venv .venv
echo .venv\Scripts\python.exe -m pip install -r webui\requirements.txt
echo 完成后重新双击此文件。
set /p "STUDIO_REPLY=按回车关闭…"
exit /b 2

:run
"%STUDIO_PYTHON%" "%REPO_DIR%\scripts\run-local-studio.py" %*
exit /b %ERRORLEVEL%
