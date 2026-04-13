@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 安装Playwright浏览器

cd /d "%~dp0"

color 0A
echo.
echo ============================================================
echo          安装Playwright浏览器
echo       首次使用必须运行此脚本！
echo ============================================================
echo.

set "PORTABLE_PYTHON=%~dp0python_portable"
set "PYTHON_EXE=%PORTABLE_PYTHON%\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [✗] 未找到便携版Python
    echo 请确保此脚本放在正确目录下
    pause
    exit /b 1
)

echo [✓] 找到便携版Python
echo.
echo 正在安装Playwright浏览器...
echo 此过程需要下载约150MB数据，请耐心等待...
echo.

"%PYTHON_EXE%" -m playwright install chromium

if errorlevel 1 (
    echo.
    echo [✗] 安装失败，请检查网络连接
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [✓] Playwright浏览器安装完成！
echo ============================================================
echo.
echo 现在可以运行以下脚本开始注册：
echo   - 一键启动(美区版-显示窗口).bat
echo   - 一键启动(美区版-隐藏窗口).bat
echo.
pause
