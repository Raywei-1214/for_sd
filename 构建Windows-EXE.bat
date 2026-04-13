@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title sd - 构建 Windows EXE

cd /d "%~dp0"

echo.
echo ============================================================
echo   sd - Windows EXE 构建器
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel% neq 0 (
    echo [×] 未检测到 Python Launcher ^(py^)
    echo 请先安装 Python 3.11+ 并勾选 Add Python to PATH
    pause
    exit /b 1
)

echo [1/4] 安装/更新打包依赖...
py -3 -m pip install --upgrade pip pyinstaller playwright PySide6 aiohttp certifi
if %errorlevel% neq 0 (
    echo [×] 安装打包依赖失败
    pause
    exit /b 1
)

echo.
echo [2/4] 清理旧构建目录...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo.
echo [3/4] 构建 EXE...
py -3 -m PyInstaller --noconfirm seedance_windows.spec
if %errorlevel% neq 0 (
    echo [×] EXE 构建失败
    pause
    exit /b 1
)

echo.
echo [4/4] 构建完成
echo EXE 路径: %cd%\dist\sd.exe
echo.
echo 说明:
echo 1. 双击 EXE 后将直接打开图形面板
echo 2. 优先使用系统 Chrome，避免额外打包浏览器
echo 3. 如果目标机器没有 Chrome，请先安装 Chrome
echo 4. 日志、账号、报告会写到 exe 同目录
echo.
pause
