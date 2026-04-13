# Seedance 2.0 架构说明

## 目标

当前项目从 `CC_AutoCut` 仓库中拆出，独立为 `/Users/yanwei/Seedance2.0`。第一阶段重构目标不是改业务，而是把原本 1174 行的单文件脚本拆成可维护的职责边界，并补上 mac 兼容基础设施。

## 目录职责

- `dreamina_register_playwright_usa.py`
  - 薄入口，保留原命令调用方式，兼容既有 `.bat` 启动器。
- `seedance/app/cli.py`
  - 处理命令行参数，调用批量调度入口。
- `seedance/app/gui.py`
  - 负责 PySide6 图形面板、参数控件、实时日志、运行概览与 Notion 预检提示。
- `seedance_gui.py`
  - GUI 薄入口，供 Windows `exe` 打包使用。
- `seedance/orchestration/batch_runner.py`
  - 负责交互输入、邮箱站点选择、线程池调度、按失败原因聚合统计。
- `seedance/services/registration_service.py`
  - 负责 Dreamina 注册主流程、积分探测、`sessionid` 抓取。
- `seedance/services/email_service.py`
  - 负责临时邮箱获取与验证码提取。
- `seedance/infra/browser_detector.py`
  - 负责浏览器配置读写与跨平台本地浏览器探测。
- `seedance/infra/browser_factory.py`
  - 负责创建 Playwright browser/context。
- `seedance/infra/account_store.py`
  - 负责线程安全地写入成功账号，按 “Notion + 本地 txt” 独立双写。
- `seedance/infra/temp_mail_adapters.py`
  - 负责临时邮箱站点适配器注册表，隔离各站点的页面差异。
- `seedance/infra/report_writer.py`
  - 负责将批量执行结果输出为 JSON/CSV 运行报告。
- `seedance/infra/notion_client.py`
  - 负责与 Notion Database 通信、补齐表结构、创建账号记录，并使用证书链上下文保障 HTTPS 可用性。
- `seedance/core/`
  - 放常量、日志、数据模型。
- `docs/windows-exe.md`
  - 负责说明 Windows EXE 打包和运行边界。

## 当前重构边界

- 保留原注册流程行为。
- 移除多线程共享类变量，改为显式参数传递。
- 保留原输出格式，避免影响现有使用习惯。
- 补上 mac 浏览器探测与 mac 启动脚本。
- 将注册流改造成显式步骤状态机。
- 将易变 selector 与 timeout 统一收口到 `seedance/core/config.py`。
- 将页面进入判定从“只看 URL/文本”提升为“优先稳定元素断言，文本兜底”。
- Windows 支持通过 `PyInstaller` 构建为独立 `exe`。
- Windows `exe` 启动入口已切换为 PySide6 图形面板。
- mac 继续保持双击 `.command` 启动，不强推桌面壳。

## 已识别的病灶

- `register()` 原先职责过多，属于典型的流程、IO、状态、采集逻辑混杂。
- 页面稳定性问题被大量 `sleep + 模糊 selector + except: pass` 掩盖。
- 原实现把 `_timestamp_filename`、`_specified_email`、`_ip_country` 作为类变量共享，不适合并发。
- 旧实现只偏向 Windows，`where chrome`、`.bat`、便携 Python 都不适合 mac。

## 当前流程状态机

1. `open_home`
2. `open_signup`
3. `acquire_temp_email`
4. `fill_credentials`
5. `submit_credentials`
6. `wait_confirmation`
7. `fill_verification_code`
8. `fill_profile`
9. `complete_registration`
10. `collect_account_data`

## 当前页面断言策略

- 主页：优先等待 `Create` 菜单等稳定元素出现。
- 注册表单页：等待邮箱输入框与密码输入框出现。
- 验证码页：优先等待验证码输入相关元素，文本 `confirm / verification code / 验证码` 作为兜底。
- 资料页：等待 `Year / Month / Day` 相关表单元素出现。
- 成功页：要求同时避开 `login/signup` URL，并等待积分区、生成按钮、菜单区等稳定元素之一出现。

## 当前邮箱适配策略

- 先按站点名命中专属 `TempMailAdapter`。
- 适配器负责三类提取入口：输入框值、文本节点、属性节点。
- 验证码提取优先使用站点文本标记，再走统一正则。
- 只有站点适配器未命中时，才退回通用兼容扫描。
- 通用兼容扫描的边界是“保留旧行为，避免未适配站点直接不可用”，不作为长期主路径。
- 随机模式下已引入健康度轮盘：
  - 所有站点保留基础出场机会
  - 健康站点会在轮盘 bonus 段获得更高优先级
  - 只有邮箱相关硬失败才会降低站点健康度

## 当前失败统计策略

- 批量执行不再只返回布尔值，而是返回 `RegistrationResult`。
- 汇总阶段按 `failed_step + error_message` 聚合失败原因。
- 统计输出分两层：
  - 分类统计：看哪类失败最多。
  - 任务明细：看具体线程失败在哪一步、用了哪个邮箱站点。
- 运行结束后额外落盘两份报告：
  - `run_reports/run_report_<timestamp>.json`
  - `run_reports/run_report_<timestamp>.csv`

## 当前账号输出策略

- 成功账号主写入 Notion Database。
- 成功账号同时写入本地 `registered_accounts_usa/`，两条链路彼此独立。
- 失败任务也会写入同一张 Notion 表，便于统一排查。
- 写入前会自动确保数据库包含以下列：
  - `结果`
  - `线程号`
  - `失败步骤`
  - `失败原因`
  - `Sessionid`
  - `Seedance值`
  - `邮箱站点`
  - `开始时间`
  - `结束时间`
  - `耗时秒`
- 当 Notion 暂时失败时，本地 txt 仍会先落盘，避免成功账号丢失。
- 当本地 txt 失败时，Notion 仍会继续尝试写入，不让单一路径拖垮整体保存。
- 失败任务不会写本地 txt，只会写入 Notion，避免把无效账号混入成功备份。
- Schema 补齐已改为“先读取现有列，只补缺失字段”，避免重复 PATCH 污染 Notion 表结构。
- Notion 通信优先使用 `certifi` 根证书，修复 mac 上常见的 SSL 证书链缺失问题。

## 当前桌面交互策略

- Windows：
  - `Seedance2.0.exe` 直接打开 PySide6 图形面板。
  - 参数面板默认值：
    - 注册数量 `200`
    - 并发线程 `2`
    - 浏览器模式 `隐藏`
    - 邮箱站点 `7 - 随机`
    - Notion `开启`
- GUI 在启动前会先做 Notion 预检：
  - 能连通则按开启状态执行。
  - 不能连通则弹窗提示是否关闭 Notion 后继续。
- mac：
  - 继续通过 `.command` 调用 CLI，不强制切换到 GUI。

## 下一阶段建议

1. 为 `mail.tm`、`10minutemail.net` 等高频站点补真实 DOM 校验，压缩通用兼容扫描触发率。
2. 为 mac 增加依赖自检与一键初始化脚本。
3. 给状态机补步骤级截图与失败快照策略。
4. 如需更像“程序”，再评估是否加本地 GUI 壳，而不是继续扩展批处理。
5. 如需继续提速，再评估浏览器复用，但必须先完成风控与隔离验证。
