# sd 新同事使用说明

## 适用对象

这份文档给第一次接手 `sd` 项目的同事使用。目标只有一个：

- 从 git 拉下项目后，尽快把环境跑起来

不需要先理解全部源码，先按本文把项目启动成功即可。

## 项目入口

当前项目有 3 个主要入口：

- Windows 首次初始化：`初始化sd环境.bat`
- Windows 构建 EXE：`构建Windows-EXE.bat`
- mac 启动：`启动sd.command`

核心代码入口：

- GUI 启动入口：`seedance_gui.py`
- CLI 薄入口：`dreamina_register_playwright_usa.py`

## 命名说明

- 当前项目面向 Dreamina 国际站，不强制要求美国节点。
- 项目里仍保留少量历史遗留命名，例如：
  - `dreamina_register_playwright_usa.py`
  - `dreamina_register_usa.log`
  - `registered_accounts_usa/`
- 这些名字目前只是历史文件名，不代表程序会校验“必须美国 IP”。

## 先决条件

### Windows

- 已安装 `Python 3.11+`
- 已安装 `Google Chrome`
- 可以正常访问项目依赖下载源

### mac

- 已安装 `Python 3.11+`
- 已安装 `Google Chrome`
- 终端可执行 `python3`

## 从 git 拉下来之后的第一步

进入项目根目录：

```bash
cd Seedance2.0
```

## Windows 使用流程

### 1. 首次初始化

双击运行：

```text
初始化sd环境.bat
```

它会自动完成：

- 升级 `pip`
- 安装 `requirements.txt`
- 安装 `Playwright Chromium`
- 可选生成 `.env.local`
- 可选直接启动 GUI

### 2. 配置 Notion

如果需要启用 Notion，推荐直接在 GUI 右上角点击 `Notion 设置`：

- 输入 `Notion Token`
- 粘贴数据库链接
- 程序会自动提取 `Database ID`
- 保存后自动写入同目录 `.env.local`

也可以手工准备 `.env.local`：

```env
NOTION_TOKEN=你的 Notion Token
NOTION_DATABASE_ID=你的 Notion Database ID
```

注意：

- `.env.local` 不会提交到 git
- 当前 Notion 只会写入“积分为 0 且有 sessionid”的成功账号
- Notion 表只保留 6 列：
  - `账号`
  - `密码`
  - `国家`
  - `注册时间`
  - `邮箱站点`
  - `使用状态`（默认 `未使用`）

如果暂时不想配 Notion：

- 可以先不创建 `.env.local`
- 启动 GUI 时把 `Notion` 开关关掉

### 3. 直接跑源码版 GUI

```bat
py -3 seedance_gui.py
```

推荐首次先这样跑，方便排错。

### 4. 构建 EXE

源码版确认正常后，再构建：

```text
构建Windows-EXE.bat
```

构建后得到：

```text
dist\sd.exe
```

构建脚本会自动处理：

- 构建 `sd.exe`
- 如果根目录存在 `.env.local`，自动复制到 `dist\`
- 如果根目录不存在 `.env.local`，自动复制 `.env.local.example` 到 `dist\`

### 5. 运行 EXE

双击：

```text
dist\sd.exe
```

## mac 使用流程

### 1. 安装依赖

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m playwright install chromium
```

### 2. 配置 Notion（可选）

推荐先启动 GUI，点击右上角 `Notion 设置` 直接填写。

如果你更习惯手工方式，也可以在项目根目录创建：

```env
NOTION_TOKEN=你的 Notion Token
NOTION_DATABASE_ID=你的 Notion Database ID
```

### 3. 启动

方式 1：双击

```text
启动sd.command
```

方式 2：命令行

```bash
python3 seedance_gui.py
```

## 默认运行参数

GUI 默认值：

- 注册数量：`999`
- 并发线程：`5`
- 邮箱站点：`7 - 随机`
- 浏览器模式：隐藏
- Notion：开启

建议第一次验证时改成：

- 注册数量：`1`
- 并发线程：`1`
- 显示浏览器：开启

这样更容易看清页面到底卡在哪一步。

## 当前输出位置

### 源码运行时

输出会写到项目根目录：

- `dreamina_register_usa.log`
- `registered_accounts_usa/`
- `run_reports/`
- `screenshots_usa/`（仅 debug 模式）

### Windows EXE 运行时

输出会写到 `sd.exe` 同目录：

- `dreamina_register_usa.log`
- `registered_accounts_usa/`
- `run_reports/`
- `screenshots_usa/`（仅 debug 模式）

## 当前账号保存规则

### 本地 txt

本地 txt 逻辑保持原样，不受 Notion 规则影响。

### Notion

只有满足以下条件的成功账号才会写入 Notion：

- `credits == 0`
- `sessionid` 有值

不满足条件时：

- 本地 txt 仍照常写入
- Notion 会跳过，不算报错

失败任务不会写入 Notion。

## 常见问题

### 1. GUI 提示 “Notion 无法连接”

先检查 `.env.local` 位置是否正确：

- 源码运行：放在项目根目录
- `sd.exe` 运行：放在 `sd.exe` 同目录

再检查：

- `NOTION_TOKEN` 是否有效
- `NOTION_DATABASE_ID` 是否正确
- 当前集成是否已经被加入目标数据库权限

### 2. `dreamina_register_usa.log` 没内容

先看运行方式：

- 源码运行：日志在项目根目录
- `sd.exe` 运行：日志在 `sd.exe` 同目录

### 3. 浏览器打不开

先检查：

- 本机是否安装 Chrome
- 是否已经执行过 `playwright install chromium`

### 4. Notion 没写入，但 txt 有

先看是否命中了跳过条件：

- 没拿到 `sessionid`
- `credits` 不是 `0`

这是当前规则，不是程序异常。

从现在开始，也可以直接看 `run_reports/` 里的明细字段：

- `notion_ok`
- `notion_skipped`
- `notion_error`
- `notion_skip_reason`

这样能直接区分“规则跳过”和“真正写入失败”。

## 新同事建议的接手顺序

1. 先跑 `seedance_gui.py`
2. 用 `1 个任务 + 1 线程 + 显示浏览器` 做最小验证
3. 确认日志、txt、报告输出正常
4. 再决定要不要构建 `sd.exe`
5. 真要排注册问题时，优先看：
   - `dreamina_register_usa.log`
   - `run_reports/`
   - `registered_accounts_usa/`

## 当前推荐入口

为了避免多入口并存造成混乱，当前推荐只使用下面这些：

- Windows 初始化：`初始化sd环境.bat`
- Windows 构建：`构建Windows-EXE.bat`
- Windows / mac GUI：`seedance_gui.py`
- mac 双击启动：`启动sd.command`

不要再找旧的“一键启动”脚本，它们已经从项目中移除了。
