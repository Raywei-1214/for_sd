@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title sd - 初始化 Windows 环境

cd /d "%~dp0"

echo.
echo ============================================================
echo   sd - Windows 环境初始化
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel% neq 0 (
    echo [×] 未检测到 Python Launcher ^(py^)
    echo 请先安装 Python 3.11+，并勾选 Add Python to PATH
    pause
    exit /b 1
)

echo [1/4] 升级 pip...
py -3 -m pip install --upgrade pip
if %errorlevel% neq 0 (
    echo [×] pip 升级失败
    pause
    exit /b 1
)

echo.
echo [2/4] 安装项目依赖...
py -3 -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [×] 项目依赖安装失败
    pause
    exit /b 1
)

echo.
echo [3/4] 安装 Playwright Chromium...
py -3 -m playwright install chromium
if %errorlevel% neq 0 (
    echo [×] Playwright 浏览器安装失败
    pause
    exit /b 1
)

echo.
echo [4/4] 配置 Notion ^(可选^)
echo.

set "CONFIGURE_NOTION="
choice /c YN /n /m "是否现在配置 Notion？(Y/N): "
if errorlevel 2 (
    set "CONFIGURE_NOTION=N"
) else (
    set "CONFIGURE_NOTION=Y"
)

if /i "!CONFIGURE_NOTION!"=="Y" (
    if exist ".env.local" (
        echo 检测到已存在 .env.local
        choice /c YN /n /m "是否覆盖现有 .env.local？(Y/N): "
        if errorlevel 2 goto after_notion
    )

    echo.
    set /p NOTION_TOKEN="请输入 NOTION_TOKEN: "
    set /p NOTION_DATABASE_RAW="请输入 NOTION_DATABASE_ID 或粘贴 Notion 数据库链接: "

    if "!NOTION_TOKEN!"=="" (
        echo [×] NOTION_TOKEN 不能为空
        goto after_notion
    )

    if "!NOTION_DATABASE_RAW!"=="" (
        echo [×] NOTION_DATABASE_ID 不能为空
        goto after_notion
    )

    set "NORMALIZED_DATABASE_ID="
    for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$raw=$env:NOTION_DATABASE_RAW; if ($raw -match '([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})') { $Matches[1].ToLower() } elseif ($raw -match '([0-9a-fA-F]{32})') { $id=$Matches[1].ToLower(); '{0}-{1}-{2}-{3}-{4}' -f $id.Substring(0,8),$id.Substring(8,4),$id.Substring(12,4),$id.Substring(16,4),$id.Substring(20,12) }"` ) do (
        set "NORMALIZED_DATABASE_ID=%%I"
    )

    if "!NORMALIZED_DATABASE_ID!"=="" (
        echo [×] 无法识别 Notion 数据库 ID，请重新运行并输入原始 ID 或数据库链接
        goto after_notion
    )

    (
        echo NOTION_TOKEN=!NOTION_TOKEN!
        echo NOTION_DATABASE_ID=!NORMALIZED_DATABASE_ID!
    ) > ".env.local"

    echo [✓] 已生成 .env.local
    echo [!] 注意：.env.local 仅保留在本机，不会进入 git
) else (
    echo [!] 已跳过 Notion 配置
    echo [!] 你后续可以手动编辑 .env.local，或在 GUI 里关闭 Notion
)

:after_notion

echo.
echo ============================================================
echo   初始化完成
echo ============================================================
echo.
echo 现在你可以执行：
echo   1. py -3 seedance_gui.py
echo   2. 或双击 构建Windows-EXE.bat 生成 sd.exe
echo.

choice /c YN /n /m "是否立即启动 GUI？(Y/N): "
if errorlevel 2 goto end

start "" py -3 seedance_gui.py

:end
echo.
pause
