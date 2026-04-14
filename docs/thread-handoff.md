# sd 线程续接上下文

## 当前状态

- 项目已从 `CC_AutoCut` 独立移动到 `/Users/yanwei/Seedance2.0`
- 第一阶段重构已开始，目标是“拆结构，不先改业务行为”
- mac 兼容已纳入本轮改造范围

## 已完成事项

- 将入口脚本改为薄入口，保留 `dreamina_register_playwright_usa.py` 的原调用路径
- 新增 `seedance/` 包，按 `app / orchestration / services / infra / core` 分层
- 浏览器探测已兼容 Windows / macOS / Linux 基础路径
- 账号保存已从共享类变量迁出，改为线程安全的独立存储对象
- 注册流程已改为显式步骤状态机，失败会落到具体步骤名
- selector 与 timeout 已集中到 `seedance/core/config.py`
- 页面状态判定已升级为“稳定元素优先，文本兜底”
- 临时邮箱已引入站点适配器注册表，通用扫描仅作为兼容兜底
- 批量统计已升级为失败分类统计，可按步骤和原因聚合
- 每次运行会额外输出 JSON/CSV 报告和 `notion_failures_<timestamp>.json` 到 `run_reports/`
- Windows 已补 `PyInstaller` 打包链路，mac 保持 `.command` 启动
- 随机邮箱模式已升级为“健康度优先但不垄断”的轮盘调度
- 成功账号仍保留本地 txt 备份；Notion 只接收“积分为0且带 sessionid”的成功账号
- Notion 已切到证书链上下文，专门处理 mac Python 环境的 SSL 根证书问题
- 失败任务不再写入 Notion
- Notion 表结构已收敛为 `账号 / 密码 / 国家 / 注册时间 / 邮箱站点 / 使用状态` 6 列，并会清理冗余列
- Windows 启动入口已切换为 PySide6 图形面板，默认参数为 999 个任务 / 5 线程 / 隐藏浏览器 / 随机邮箱 / Notion 开启
- Windows 已补 `初始化sd环境.bat`，用于首次自动安装依赖和生成 `.env.local`
- 旧的“一键启动”批处理、单独安装 Playwright 脚本、历史性测试脚本已从项目根目录清理
- 项目已初始化 git，并已推送到公开仓库 `git@github.com:Raywei-1214/for_sd.git`
- 推送路线与 `CC_AutoCut` 保持一致，统一复用 GitHub SSH 凭据，不走 `https`
- `.gitignore` 已明确排除 `.env.local`、运行日志、账号备份、报告目录和 `python_portable/`

## 当前风险

- 注册页面仍然依赖大量弱 selector，稳定性问题还未做根因级治理
- mac 上虽然已有启动入口和浏览器探测，但依赖安装与 Playwright 浏览器安装仍需真实机器验证
- Windows 侧仍存在初始化脚本与构建脚本两步流，后续可再评估是否合并为单一向导

## 建议新线程接续方向

1. 先在 mac 上验证 `python3 dreamina_register_playwright_usa.py --show-browser --count 1 --threads 1`
2. 为高频邮箱站点补真实 DOM 校验，进一步减少通用兼容扫描
3. 为 mac 增加依赖自检与一键初始化脚本
