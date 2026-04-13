# Windows EXE 打包说明

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

- `构建Windows-EXE.bat`

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

当前 Notion 表会同时记录：
- 成功账号
- 失败任务

其中失败任务会额外写入：
- `结果`
- `线程号`
- `失败步骤`
- `失败原因`
