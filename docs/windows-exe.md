# Windows EXE 打包说明

如果你是第一次接手项目，建议先看：

- [新同事使用说明](/Users/yanwei/Seedance2.0/docs/new-colleague-onboarding.md)

## 目标

Windows 侧改为通过 `PyInstaller` 构建 `sd.exe`，mac 继续保持双击 [启动sd.command](/Users/yanwei/Seedance2.0/启动sd.command:1)。

## 当前方案

- 入口文件：`seedance_gui.py`
- 打包规格：`seedance_windows.spec`
- 一键构建脚本：`构建Windows-EXE.bat`
- 运行目录策略：
  - 开发态使用项目根目录
  - 打包后使用 `exe` 所在目录

## 构建步骤

在 Windows 上打开项目目录，双击：

- `初始化sd环境.bat`
- `构建Windows-EXE.bat`

建议顺序：

1. 先运行 `初始化sd环境.bat`
2. 再运行 `构建Windows-EXE.bat`

当前 Windows 侧只保留这两份批处理：

- `初始化sd环境.bat`
- `构建Windows-EXE.bat`

旧的“一键启动”脚本和单独安装 Playwright 的脚本已移除，避免入口重复。

`初始化sd环境.bat` 会自动完成：

- 升级 `pip`
- 安装 `requirements.txt`
- 安装 `Playwright Chromium`
- 可选生成 `.env.local`
- 可选直接启动 `seedance_gui.py`

`构建Windows-EXE.bat` 会自动完成：

- 构建 `dist\sd.exe`
- 如果项目根目录存在 `.env.local`，自动复制到 `dist\`
- 如果项目根目录不存在 `.env.local`，自动复制 `.env.local.example` 到 `dist\`

或手动执行：

```bat
py -3 -m pip install --upgrade pip pyinstaller playwright PySide6 aiohttp certifi
py -3 -m PyInstaller --noconfirm seedance_windows.spec
```

构建完成后得到：

- `dist\sd.exe`

## 运行说明

- 双击 `sd.exe` 后会直接打开图形面板
- 推荐目标机器安装系统 Chrome
- 当前程序会优先探测系统 Chrome，再回退到 Playwright Chromium
- 如果目标机器没有 Chrome，且也没有 Playwright 浏览器缓存，运行会失败
- 图形面板默认值：
  - 注册数量：`200`
  - 并发线程：`2`
  - 浏览器模式：隐藏
  - 邮箱站点：`7 - 随机`
  - Notion：开启
- 若启动前 Notion 无法连通，会提示是否关闭 Notion 后继续

## 打包边界

- 这次先做“可构建的 exe 启动器”，不是完整安装包
- 没有把 Playwright 浏览器二进制一起塞进 exe
- 因此最稳的生产用法是：
  - 目标机器提前安装 Chrome
  - exe 只负责业务逻辑执行

## 输出目录

打包后程序运行时会在 exe 同目录输出：

- `dreamina_register_usa.log`
- `registered_accounts_usa/`（与 Notion 独立双写的本地 txt 备份）
- `run_reports/`
- `screenshots_usa/`（仅 debug 模式）

## Notion 配置

程序会优先从 exe 同目录的 `.env.local` 读取：

```env
NOTION_TOKEN=...
NOTION_DATABASE_ID=...
```

如果缺少这两个值，账号将无法写入 Notion，但本地 txt 备份仍会继续落盘。

出于安全原因：

- 真实 `.env.local` 不会提交到 git
- 仓库只保留 `.env.local.example`
- Windows 构建时会把你本机的 `.env.local` 自动复制到 `dist\`

当前 Notion 只会记录：
- 积分为 `0`
- 且带有 `sessionid`
- 且注册成功的账号

当前 Notion 表仅保留 3 列：
- `账号`
- `密码`
- `国家`
