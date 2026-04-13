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
echo.
echo [4/4] 同步运行配置...
if exist ".env.local" (
    copy /y ".env.local" "dist\\.env.local" >nul
    if %errorlevel% neq 0 (
        echo [×] .env.local 复制到 dist 失败
        pause
        exit /b 1
    )
    echo [✓] 已将 .env.local 复制到 dist 目录
) else (
    echo [!] 未找到 .env.local，sd.exe 运行时将无法连接 Notion
    if exist ".env.local.example" (
        copy /y ".env.local.example" "dist\\.env.local.example" >nul
        echo [i] 已将 .env.local.example 复制到 dist 目录，便于后续填写
    )
)

echo.
echo [√] 构建完成
echo EXE 路径: %cd%\dist\sd.exe
echo.
echo 说明:
echo 1. 双击 EXE 后将直接打开图形面板
echo 2. 优先使用系统 Chrome，避免额外打包浏览器
echo 3. 如果目标机器没有 Chrome，请先安装 Chrome
echo 4. 日志、账号、报告会写到 exe 同目录
echo 5. Notion 配置文件需要放在 dist 目录，与 sd.exe 同级
echo.
pause
