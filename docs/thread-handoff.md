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
- 每次运行会额外输出 JSON/CSV 报告到 `run_reports/`
- Windows 已补 `PyInstaller` 打包链路，mac 保持 `.command` 启动
- 随机邮箱模式已升级为“健康度优先但不垄断”的轮盘调度
- 成功账号已改为 Notion + 本地 txt 独立双写，任一链路失败不会阻断另一条
- Notion 已切到证书链上下文，专门处理 mac Python 环境的 SSL 根证书问题
- 失败任务现在也会写入 Notion，新增字段包含结果、线程号、失败步骤、失败原因
- Notion schema 补齐已改为按缺失字段增量更新，避免重复生成同名列
- Windows 启动入口已切换为 PySide6 图形面板，默认参数为 200 个任务 / 2 线程 / 隐藏浏览器 / 随机邮箱 / Notion 开启
- 项目已初始化 git，并已推送到公开仓库 `git@github.com:Raywei-1214/for_sd.git`
- 推送路线与 `CC_AutoCut` 保持一致，统一复用 GitHub SSH 凭据，不走 `https`
- `.gitignore` 已明确排除 `.env.local`、运行日志、账号备份、报告目录和 `python_portable/`

## 当前风险

- 注册页面仍然依赖大量弱 selector，稳定性问题还未做根因级治理
- mac 上虽然已有启动入口和浏览器探测，但依赖安装与 Playwright 浏览器安装仍需真实机器验证
- Windows `.bat` 启动器仍保留旧提示词逻辑，后续可考虑统一到跨平台启动脚本

## 建议新线程接续方向

1. 先在 mac 上验证 `python3 dreamina_register_playwright_usa.py --show-browser --count 1 --threads 1`
2. 为高频邮箱站点补真实 DOM 校验，进一步减少通用兼容扫描
3. 为 mac 增加依赖自检与一键初始化脚本
