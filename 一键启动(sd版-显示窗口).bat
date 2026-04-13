@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 即梦自动注册 - 一键启动(sd版-显示窗口)

cd /d "%~dp0"

color 0B
echo.
echo ============================================================
echo          即梦自动注册脚本 v6.0 sd专用版
echo           无需安装Python，开箱即用！
echo            【sd 注册 - 显示浏览器窗口】
echo ============================================================
echo.
echo ⭐ sd 注册模式 ⭐
echo 注册URL: https://dreamina.capcut.com/ai-tool/home
echo 优势：注册后账号有积分！
echo.

::: 设置便携版Python路径
set "PORTABLE_PYTHON=%~dp0python_portable"
set "PYTHON_EXE=%PORTABLE_PYTHON%\python.exe"
set "SCRIPTS_DIR=%PORTABLE_PYTHON%\Scripts"

::: 检查是否已有便携版Python
if exist "%PYTHON_EXE%" (
    echo [✓] 检测到便携版Python
    goto :check_playwright
)

::: 检查系统是否已安装Python
echo [1/2] 正在检查Python环境...
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [✓] 检测到系统已安装Python
    set "USE_SYSTEM_PYTHON=1"
    goto :check_playwright
) else (
    echo [!] 未检测到Python环境
    echo.
    echo ============================================================
    echo    需要下载便携版Python（约25MB）
    echo ============================================================
    echo.
    echo 选项1: 自动下载便携版Python（推荐）
    echo 选项2: 手动安装Python后重新运行
    echo.
    set /p choice="请选择 (1/2，默认1): " || set choice=1

    if "!choice!"=="2" (
        echo.
        echo 请访问: https://www.python.org/downloads/
        echo 下载并安装Python，务必勾选 "Add Python to PATH"
        echo 安装完成后重新运行本脚本
        pause
        exit /b 1
    )

    echo.
    echo [正在准备下载Python便携版...]
    goto :download_python
)

:download_python
echo.
echo ============================================================
echo    下载Python便携版（约25MB，请稍候...）
echo ============================================================
echo.
echo 正在创建临时下载脚本...

::: 创建PowerShell下载脚本
echo $ProgressPreference = 'SilentlyContinue' > "%temp%\download_python.ps1"
echo $url = 'https://www.python.org/ftp/python/3.11.6/python-3.11.6-embed-amd64.zip' >> "%temp%\download_python.ps1"
echo $output = '%~dp0python_embed.zip' >> "%temp%\download_python.ps1"
echo Write-Host '[下载中] Python 3.11 便携版...' >> "%temp%\download_python.ps1"
echo try { >> "%temp%\download_python.ps1"
echo     Invoke-WebRequest -Uri $url -OutFile $output -TimeoutSec 300 >> "%temp%\download_python.ps1"
echo     Write-Host '[成功] Python下载完成' >> "%temp%\download_python.ps1"
echo     exit 0 >> "%temp%\download_python.ps1"
echo } catch { >> "%temp%\download_python.ps1"
echo     Write-Host '[失败] 下载失败: ' $_.Exception.Message >> "%temp%\download_python.ps1"
echo     exit 1 >> "%temp%\download_python.ps1"
echo } >> "%temp%\download_python.ps1"

echo 开始下载...
powershell -ExecutionPolicy Bypass -File "%temp%\download_python.ps1"

if %errorlevel% neq 0 (
    echo.
    echo [×] Python下载失败
    echo.
    echo 可能原因：
    echo 1. 网络连接问题
    echo 2. 下载链接失效
    echo.
    echo 请选择：
    echo 1. 重试下载
    echo 2. 手动安装系统Python
    echo.
    set /p retry="请选择 (1/2): "
    if "!retry!"=="1" goto :download_python

    echo.
    echo 请访问: https://www.python.org/downloads/
    echo 下载并安装Python，务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

::: 解压Python
echo.
echo [解压中] 正在解压Python...
mkdir "%PORTABLE_PYTHON%" 2>nul
powershell -Command "Expand-Archive -Path '%~dp0python_embed.zip' -DestinationPath '%PORTABLE_PYTHON%' -Force"
if %errorlevel% neq 0 (
    echo [×] 解压失败
    pause
    exit /b 1
)
echo [✓] Python解压完成

::: 删除下载的zip文件
del "%~dp0python_embed.zip" 2>nul

::: 配置Python环境
echo [配置中] 正在配置Python环境...

::: 创建get-pip.py下载脚本
echo $url = 'https://bootstrap.pypa.io/get-pip.py' > "%temp%\download_getpip.ps1"
echo $output = '%PORTABLE_PYTHON%\get-pip.py' >> "%temp%\download_getpip.ps1"
echo Invoke-WebRequest -Uri $url -OutFile $output >> "%temp%\download_getpip.ps1"
powershell -ExecutionPolicy Bypass -File "%temp%\download_getpip.ps1"

::: 修改python311._pth文件以启用pip
if exist "%PORTABLE_PYTHON%\python311._pth" (
    echo import site >> "%PORTABLE_PYTHON%\python311._pth"
)

::: 安装pip
echo [安装pip...]
"%PYTHON_EXE%" "%PORTABLE_PYTHON%\get-pip.py" --no-warn-script-location
echo [✓] pip安装完成

::: 设置便携版Python环境变量
set "PATH=%PORTABLE_PYTHON%;%SCRIPTS_DIR%;%PATH%"
echo [✓] 便携版Python配置完成
echo.

:check_playwright
echo.
echo [3/3] 正在检查Chrome浏览器...

::: 设置Python命令
if defined USE_SYSTEM_PYTHON (
    set "PY_CMD=python"
) else (
    set "PY_CMD=%PYTHON_EXE%"
    set "PATH=%PORTABLE_PYTHON%;%SCRIPTS_DIR%;%PATH%"
)

::: 检查playwright是否已安装
"%PY_CMD%" -c "import playwright" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Playwright未安装，正在自动安装...
    echo.
    echo [安装中] Playwright浏览器（约30MB，请稍候...）

    :: 清除代理环境变量
    set HTTP_PROXY=
    set HTTPS_PROXY=
    set http_proxy=
    set https_proxy=

    :: 使用便携版或系统Python安装playwright
    "%PY_CMD%" -m pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn --no-warn-script-location

    if !errorlevel! neq 0 (
        echo [!] 清华镜像安装失败，尝试官方源...
        "%PY_CMD%" -m pip install playwright --no-warn-script-location
        if !errorlevel! neq 0 (
            echo [×] Playwright安装失败
            pause
            exit /b 1
        )
    )
    echo [✓] Playwright安装成功
) else (
    echo [✓] Playwright已安装
)

::: 检查Chrome浏览器
echo.
echo [3/3] 正在检查Chrome浏览器...

::: 检测Chrome浏览器路径
set "CHROME_PATH="
set "CHROME_FOUND="

::: 检查常见Chrome安装位置
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
    set "CHROME_FOUND=1"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
    set "CHROME_FOUND=1"
) else if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LocalAppData%\Google\Chrome\Application\chrome.exe"
    set "CHROME_FOUND=1"
)

::: 如果找到Chrome，尝试获取完整路径
if defined CHROME_FOUND (
    for %%i in ("%CHROME_PATH%") do set "CHROME_PATH=%%~fi"
    echo [✓] 检测到本地Chrome浏览器
    echo     路径: %CHROME_PATH%
) else (
    echo [✗] 未检测到本地Chrome浏览器
    echo     将使用Playwright内置Chromium浏览器
)

echo.

echo.
echo ============================================================
echo            环境检查完成，启动脚本
echo ============================================================
echo.
echo 运行参数设置:
echo.
set /p TOTAL_COUNT="注册账号数量 (默认200个): " || set TOTAL_COUNT=200

if not defined TOTAL_COUNT set TOTAL_COUNT=200
if "%TOTAL_COUNT%"=="" set TOTAL_COUNT=200

echo.
set /p MAX_THREADS="并发线程数 (默认2，范围1-3): " || set MAX_THREADS=2

if not defined MAX_THREADS set MAX_THREADS=2
if "%MAX_THREADS%"=="" set MAX_THREADS=2

echo.
echo ============================================================
echo 【确认运行配置】
echo ============================================================
echo   注册区域: ⭐ sd ⭐
echo   注册URL: https://dreamina.capcut.com/ai-tool/home
echo   临时邮箱: 随机
echo   注册数量: %TOTAL_COUNT% 个账号
echo   并发线程: %MAX_THREADS% 个
echo   运行模式: 显示浏览器（可观察注册过程）
echo   账号保存: Notion 表格 + registered_accounts_usa 本地备份
echo ============================================================
echo.
echo ⚠️ 注意：多线程模式会同时打开多个浏览器窗口
echo.
echo ⭐ sd 注册优势：注册后账号有积分！⭐
echo.
echo 按任意键开始执行...
pause >nul

echo.
echo ========================================
echo   开始执行sd注册任务
echo ========================================
echo.

::: 执行Python脚本（显示浏览器模式，多线程，随机邮箱）
"%PY_CMD%" dreamina_register_playwright_usa.py --count %TOTAL_COUNT% --threads %MAX_THREADS% --show-browser

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   ✓ 程序执行完毕
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   × 程序执行遇到错误
    echo ========================================
)

echo.
echo 日志文件: dreamina_register_usa.log
echo 成功账号: Notion 表格 + registered_accounts_usa 本地备份
echo.
pause
