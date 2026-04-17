# sd 架构说明

## 目标

当前项目从 `CC_AutoCut` 仓库中拆出，独立为 `/Users/yanwei/Seedance2.0`。第一阶段重构目标不是改业务，而是把原本 1174 行的单文件脚本拆成可维护的职责边界，并补上 mac 兼容基础设施。

## 目录职责

- `dreamina_register_playwright_usa.py`
  - 薄入口，保留原命令调用方式，兼容 CLI 与 mac `.command` 启动。
- `seedance/app/cli.py`
  - 处理命令行参数，调用注册批量调度入口，或进入 `watermark` 子命令执行去水印批次。
- `seedance/app/gui.py`
  - 负责 PySide6 图形面板、参数控件、实时日志、运行概览、Notion 预检提示，以及 `Dreamina 去水印` Tab。
- `seedance_gui.py`
  - GUI 薄入口，供 Windows `exe` 打包使用。
- `seedance/orchestration/batch_runner.py`
  - 负责交互输入、邮箱站点选择、线程池调度、按失败原因聚合统计，并显式固定工作线程事件循环类型。
- `seedance/orchestration/home_check_runner.py`
  - 负责 Dreamina 首页稳定性自检，只验证 `open_home` 阶段是否能进入可操作状态。
- `seedance/orchestration/watermark_runner.py`
  - 负责目录扫描、视频时长预检、去水印串行调度与 JSON 运行报告输出。
- `seedance/services/registration_service.py`
  - 负责 Dreamina 注册主流程、积分探测、`sessionid` 抓取。
  - `probe` 当前只保留视频工作区采样路径：优先尝试 `AI Video`，再尝试 `Start Creating`；并显式屏蔽 `agentic / generate / omniReference` 页面。若 URL 不是 `home?type=video&workspace=0`，该轮采样会直接判成无效，不再额外追加 `goto` 导航；若页面只剩 `Explore Create Assets` 这类半 ready 壳子，会先做 3 秒内的轻量 ready 等待，仍未出模型区/生成区时才补一次工作区引导再采。
- `seedance/services/watermark_service.py`
  - 负责单视频去水印调用、异常归一与结果对象构造。
- `seedance/services/email_service.py`
  - 负责临时邮箱获取与验证码提取。
- `seedance/infra/browser_detector.py`
  - 负责浏览器配置读写与跨平台本地浏览器探测，并在 Windows GUI 模式下优先读取注册表、避免 `where chrome` 弹黑窗。
- `seedance/infra/browser_factory.py`
  - 负责创建 Playwright browser/context，并收敛高风险启动参数。
- `seedance/infra/magiceraser_driver.py`
  - 负责 `magiceraser.org` 页面自动化：打开站点、上传视频、框选固定区域、触发处理并保存下载结果。
- `seedance/infra/video_probe.py`
  - 负责通过 `ffprobe` 读取本地视频时长，在进入网页前做免费额度边界校验。
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
- `初始化sd环境.bat`
  - 负责 Windows 首次环境初始化，自动安装依赖、安装 Playwright 并可选生成 `.env.local`。
- `构建Windows-EXE.bat`
  - 负责 Windows 构建 `sd.exe`，并自动把本机 `.env.local` 同步到 `dist/`。

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
- Windows 构建已关闭 `UPX`，优先降低公开分发场景下的误报率。
- 旧的“一键启动”批处理与单独安装 Playwright 脚本已移除，避免多入口并存。
- mac 继续保持双击 `.command` 启动，不强推桌面壳。
- 去水印能力已补入 GUI 与 CLI，但能力边界明确限制为 `Dreamina 固定右下角水印 + 单视频 <= 30 秒`，不对任意水印位置做泛化承诺。

## 已识别的病灶

- `register()` 原先职责过多，属于典型的流程、IO、状态、采集逻辑混杂。
- 页面稳定性问题被大量 `sleep + 模糊 selector + except: pass` 掩盖。
- 原实现把 `_timestamp_filename`、`_specified_email`、`_ip_country` 作为类变量共享，不适合并发。
- 旧实现只偏向 Windows，`where chrome`、`.bat`、便携 Python 都不适合 mac。
- GUI 打包场景下若继续使用 `print()` 和有窗口的子进程调用，会带来黑窗闪烁和日志丢失风险。

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

## 当前命名说明

- 当前项目实际面向 Dreamina 国际站，不强制要求美国 IP。
- 代码和运行目录里仍保留少量 `*_usa` 命名：
  - `dreamina_register_usa.log`
  - `registered_accounts_usa/`
  - `screenshots_usa/`
- 这些名称目前仅作为历史遗留文件名使用，不再表示“必须美区节点”。

## 当前页面断言策略

- 主页：优先等待 `Create` 菜单等稳定元素出现。
- 注册主流程里的 `open_home` 在首页壳打开后，会额外等待最多 `20` 秒去命中主页 ready selector。
- 当首页稳定元素暂时未出现时，`open_home` 会额外用正文文本标记 `Explore / Create Assets` 作为二级 ready 信号。
- 注册表单页：等待邮箱输入框与密码输入框出现。
- 验证码页：优先等待验证码输入相关元素，文本 `confirm / verification code / 验证码` 作为兜底。
- `wait_confirmation` 现在会显式区分两种后续状态：
  - 进入验证码页
  - 直接进入资料页（跳过验证码输入）
- `wait_confirmation` 失败时会额外记录页面上下文，并标记当时是否仍停留在注册表单、Continue 按钮是否仍可见、资料页/验证码页元素是否已出现。
- 资料页：等待 `Year / Month / Day` 相关表单元素出现。
- 资料页：等待 `Year / Month / Day` 相关稳定元素，文本 `year / month / day / birthday / tell us about yourself` 作为兜底，并在失败时采集页面上下文。
- `fill_profile` 当前已改为专用等待链路：
  - 资料页等待窗口独立拉长到 `15` 秒
  - 若页面仍停留在验证码页，会继续等待过渡，不再过早判成资料页失败
  - 失败时会额外记录：
    - `signup_form=visible`
    - `continue_button=visible`
    - `confirmation_input=visible`
    - `profile_form=visible`
    - `year_input=visible`
    - `month_select=visible`
    - `day_select=visible`
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
- GUI 当前支持显式配置每个邮箱站点的触发比率：
  - 所有站点比率之和必须为 `100%`
  - 配置后随机调度优先按用户比率分配任务，不再额外套健康度 bonus 轮盘
  - 若用户未提供比例，仍走原有健康度轮盘
  - 默认冷启动比例当前为：
    - `mail.chatgpt.org.uk = 60%`
    - `tempmail.lol = 20%`
    - 其他启用站点平分剩余 `20%`
  - GUI 提供 `概率均分` 快捷入口：
    - 一键切到所有启用站点平分 `100%`
    - 同时持久化保存“均分前快照”，供 `概率复原默认` 恢复
- 当前启用的站点池为：
  - `mail.tm`
  - `tempmail.lol`
  - `mail.chatgpt.org.uk`
  - `internxt`
  - `tempemail.cc`
- `mail.chatgpt.org.uk` 当前已接入：
  - 真实浏览器可自动跳到专属邮箱 URL
  - 邮箱地址可从 `URL / 标题 / #emailDisplay` 多路提取
  - 验证码正文位于弹层 `iframe`，当前已补专用预览与 iframe 正文提取
- `mailticking.com` 当前已暂停：
  - 最新一轮跑测可用率仅 `10%`
  - 当前先从启用池移除，避免继续消耗注册流量
- `mailticking.com` 虽已接入，但当前暂停：
  - 入口页可直接打开，真实浏览器实测未先落到 Cloudflare 安全挑战页
  - 邮箱地址位于 `#active-mail`，同时会写入 `data-clipboard-text`
  - 收件箱主列表位于 `#message-list`，站内刷新主入口为 `#refresh-button`
  - 页面收件链路会命中 `/get-messages` 与 `/mail/view/...`，适合沿现有页面型 provider 模型接入
  - 当前已补专属邮箱提取、收件箱轻刷新与邮件预览入口
- `tempmail.plus` 当前已暂停：
  - 最新一轮跑测结果全部为 `70积分`
  - 当前先从启用池移除，避免继续消耗注册流量
- `tempmail.plus` 虽已接入，但当前暂停：
  - 入口页可直接打开，不会先落到 Cloudflare 安全挑战页
  - 邮箱地址不是单节点展示，而是由 `#pre_button + #domain` 组合得到
  - `New random name` 可直接切换新邮箱，当前主路径未见 reCAPTCHA 阻塞
  - 收件箱主路径会命中 `/api/mails?email=...&epin=...`，适合沿现有页面型 provider 模型接入
  - 注册状态机当前有一组显式绑定修复，仅对 `tempmail.plus` 生效：
    - `wait_confirmation` 识别“确认元素残留，但首页壳已出现”的混合态
    - `fill_profile` 识别“验证码后直接回首页，不再出现生日资料页”的分支
    - `complete_registration` 在已进入成功首页时直接放行，不再点击 `Next`
    - 首页壳当前只作为弱信号使用，必须等 `sessionid / faceu-commerce-user-info / 足量 cookie` 落地后，才允许判定注册已完成
  - 上述分支当前不复用到其他邮箱站点：
    - 目的: 避免把 `tempmail.plus` 的页面切换特性误扩散到其他已稳定站点
    - 边界: 其他 provider 继续沿用原有公共注册状态机
- `tempadd.com` 当前不接入：
  - 真实浏览器会先落到 Cloudflare 安全验证页
  - 当前主要问题是风控阻塞，不是简单 selector 失效
- `10minutemail.net` 当前已暂停：
  - 最近多轮 `70积分` 占比过高
  - 当前先从启用池移除，避免继续消耗流量
- `guerrillamail` 当前已暂停：
  - 最近多轮 `70积分` 占比偏高
  - 当前先从启用池移除，后续再决定是否恢复观察
- `crazymailing` 当前已停用：
  - 多次命中 Cloudflare 安全验证页
  - 当前主要问题是风控，不是单纯 selector 失效
- `internxt` 当前已补专用提取逻辑：
  - 页面邮箱是前端渲染后的纯文本节点
  - 先等待真实邮箱、`Change email` 或 `Refresh` 按钮出现
  - 若页面停在 `Generating random email...`，会继续等待邮箱生成，并主动点击 `Refresh` 拉起前端刷新
  - 验证码阶段会先刷新收件箱，再尝试点开 `Dreamina / CapCut / verification` 相关邮件正文
  - Internxt 的验证码等待窗口会比普通站点更长，避免把慢收件箱过早判成失败
  - 最后再从短文本节点和正文文本中提取真实邮箱与验证码
- `guerrillamail` 虽已补专用提取逻辑，但当前暂停：
  - 优先读取 `#email-widget`
  - 其次读取 `input[name='show_email']`
  - 最后回退到 `#inbox-id + #gm-host-select` 组合邮箱
- `mailpoof` 当前继续停用：
  - 其首页需要先触发 `create/random` 才会创建邮箱
  - 但当前真实站点在该路径返回空白页
  - 这说明它不只是旧适配器过期，还存在站点端流程不可用问题
- `10minutemail.net` 虽已补超时错误页识别，但当前暂停：
  - 若页面落到 `chrome-error://` 或出现 `ERR_CONNECTION_TIMED_OUT`
  - 会直接判定为加载失败并重试，而不是误当成“页面已打开”
- `10minutemail.net` 虽已补专用验证码链路，但当前暂停：
  - 邮箱地址优先读取 `#fe_text` 与复制按钮 `data-clipboard-text`
  - 验证码阶段优先触发站内 `updatemailbox()` 轻刷新
  - 再尝试点开 `Dreamina / CapCut / verification / code` 相关邮件预览
  - 若关键词邮件未命中，会回退点开最新一封邮件，避免一直卡在邮箱列表页
  - 只有连续多轮仍无验证码时，才做整页 `reload()`
- 验证码等待阶段当前统一改为“站点内轻刷新优先，整页 reload 降频”：
  - 有专属刷新能力的站点优先走站内刷新
  - 只有轻刷新连续多轮仍未命中时，才执行整页刷新
- `tempmail.lol` 当前已补真实邮箱就绪等待：
  - 页面打开后若仍显示 `Loading...`
  - 会先等待邮箱真实生成，再进入适配器提取流程

## 当前失败统计策略

- 批量执行不再只返回布尔值，而是返回 `RegistrationResult`。
- 汇总阶段按 `failed_step + error_message` 聚合失败原因。
- 统计输出分两层：
  - 分类统计：看哪类失败最多。
  - 任务明细：看具体线程失败在哪一步、用了哪个邮箱站点。
- 注册运行结束后额外落盘三份报告：
  - `run_reports/run_report_<timestamp>.json`
  - `run_reports/run_report_<timestamp>.csv`
  - `run_reports/notion_failures_<timestamp>.json`
- 首页自检运行结束后额外落盘一份报告：
  - `run_reports/home_check_<timestamp>.json`
- 首页自检支持显式指定并发数，默认按 `5` 个首页并发去模拟批量注册的公共前置压力。
- 首页自检支持将 `goto` 超时和 `ready` 等待拆开调参，便于判断到底是“首页没打开”还是“页面壳到了但没 ready”。
- 注册主流程与首页自检现在都支持显式切换浏览器内核：
  - `auto`：自动优先本地 Chrome
  - `chrome`：强制本地 Chrome
  - `chromium`：强制 Playwright 内置 Chromium
- 浏览器上下文当前已接入资源拦截：
  - Dreamina 主站及其依赖域名默认放行
  - 当前只对临时邮箱站点拦截 `image / font / media / ping`
  - 不拦 `script / xhr / fetch / stylesheet`
  - 目的: 优先压掉邮箱站点静态资源流量，不再误伤 Dreamina 注册主流程
- 去水印运行结束后额外落盘一份报告：
  - `run_reports/watermark_run_<timestamp>.json`
- `run_report.summary` 当前会输出：
  - `total_count`
  - `success_count`
  - `fail_count`
  - `available_count`
  - `success_rate`
  - `available_rate`
  - `duration_seconds`
  - `notion_written_count`
  - `notion_skipped_count`
  - `notion_failed_count`
  - `network_request_count`
  - `network_response_count`
  - `network_failed_request_count`
  - `network_transferred_bytes`
  - `network_transferred_megabytes`
  - `network_request_type_counts`
- `temp_mail_health.json` 当前已额外记录：
  - `attempt_count`
  - `available_count`
  - `total_failure_count`
  - `credits_observed_count`
  - `credits_70_count`
  - 其中调度仍只使用 `success_count / failure_count / consecutive_failures`
  - `运行概览` 站点质量列表使用 `失败率 / 可用率 / 70积分概率`
- 报告明细会同时记录每条任务的保存结果：
  - `notion_ok`
  - `notion_skipped`
  - `notion_error`
  - `notion_skip_reason`
  - `sessionid_context`
  - `probe_context`
  - `account_quality`
  - `account_quality_reason`
  - `backup_ok`
  - `backup_error`
  - `request_count`
  - `response_count`
  - `failed_request_count`
  - `transferred_bytes`
  - `request_type_counts`
- 对于 `主页加载失败` 与 `临时邮箱获取失败`，报告会额外记录：
  - `failure_context`
  - 内容包含当时的 `url / title / body 片段`
- 对于 `验证码获取失败`，报告现在也会记录邮箱页上下文：
  - `url / title / body 片段`
  - 若是 `10minutemail.net`，还会额外标记：
    - `mailbox_table=visible`
    - `mail_rows=<数量>`
    - `dreamina_mail=visible`
    - `mail_preview=open/closed`
  - 若邮箱页无法访问或未采到有效内容，也会显式写出：
    - `context_capture_page_missing`
    - `context_capture_page_closed`
    - `context_capture_empty`
- `wait_confirmation` 当前已改为强制页面采样：
  - 即使未命中额外状态标记，也会至少写入 `context_capture_empty`，避免报告里继续出现完全空白上下文
- `probe_context` 当前会显式记录：
  - `probe_navigation_attempt`
  - `seedance_credits`
  - `seedance2_cost`
  - `model_dropdown_found`
  - `model_fast_selected`
  - `balance_samples`
  - `generate_button_samples`
- `probe` 当前只接受“非首页壳子 + 至少采到一个数值型 credits/cost”的结果：
  - 如果还停在 `Sign in / Creative Partner Program / AI Agent Auto / 1080P banner`
  - 或者页面里只有按钮文本、没有采到数值
  - 都会继续重试，而不是把空值直接当成可用采样

## 当前账号输出策略

- 成功账号会先写入本地 `registered_accounts_usa/`。
- Notion 不再直接吃运行时内存对象，而是以本地 txt 备份行为事实来源再写入。
- Notion 只接收同时满足以下条件的成功账号：
  - `积分 = 0`
  - 带有 `sessionid`
  - `国家` 不包含 `China`
  - 本地备份行必须以 `----0` 结尾
  - 上面这个结尾字段对应 `seedance_value = 0`
- 运行报告与 GUI 会额外按账号质量分层统计：
  - `usable`：0积分 + 有 `sessionid` + 非 China + 备份行以 `----0` 结尾
  - `credits_70`：70积分，正常但不可用
  - `missing_sessionid`：0积分但缺少 `sessionid`
  - `missing_suffix_zero`：0积分但尾部不是 `----0`
  - `missing_credits`：积分缺失或无法识别
  - `china_blocked`：0积分但国家命中 China
  - `other_credits`：其他积分异常
  - `task_failed`：任务本身失败，未形成成功账号
- 失败任务不再写入 Notion。
- Notion 表结构强制收敛为 6 列：
  - `账号`
  - `密码`
  - `国家`
  - `注册时间`
  - `邮箱站点`
  - `使用状态`（默认 `未使用`）
- 当 Notion 暂时失败时，本地 txt 仍会先落盘，避免成功账号丢失。
- 当本地 txt 失败时，Notion 不再继续单独写入，避免主表和本地事实源脱节。
- Schema 同步已改为“保留账号/密码/国家/注册时间/邮箱站点/使用状态，清理其余列”，避免 Notion 表继续膨胀。
- Notion 通信优先使用 `certifi` 根证书，修复 mac 上常见的 SSL 证书链缺失问题。

## 当前桌面交互策略

- Windows：
  - `sd.exe` 直接打开 PySide6 图形面板。
  - 浏览器探测和运行日志统一走 logger，不再依赖 `print()`。
  - 参数面板默认值：
    - 注册数量 `999`
    - 并发线程 `5`
    - 浏览器模式 `隐藏`
    - 邮箱站点 `动态随机`
    - Notion `开启`
- GUI 在启动前会先做 Notion 预检：
  - 能连通则按开启状态执行。
  - 不能连通则弹窗提示是否关闭 Notion 后继续。
- GUI 第二个 Tab 为 `Dreamina 去水印`：
  - 先扫描目录内视频
  - 逐个执行本地时长预检
  - 仅当全部通过预检时才启动浏览器自动化
  - 打断结束仅在当前视频收尾后停止后续任务
- mac：
  - 继续通过 `.command` 调用 CLI，不强制切换到 GUI。
  - CLI 新增 `watermark` 子命令，可直接执行去水印批次。

## 当前仓库发布策略

- 当前公开仓库地址：
  - `git@github.com:Raywei-1214/for_sd.git`
- 推送方式统一走 `SSH`，不走 `https` 用户名密码。
- 设计原因：
  - 当前机器上的 `CC_AutoCut` 已使用 GitHub SSH 凭据。
  - 直接复用 SSH 路线最稳定，避免 `https` 方式在终端里再次卡住认证。
- 公开仓库必须忽略以下本地运行产物与敏感配置：
  - `.env.local`
  - `python_portable/`
  - `dreamina_register_usa.log`
  - `debug.log`
  - `registered_accounts_usa/`
  - `run_reports/`
  - `screenshots_usa/`
  - `browser_config.json`
  - `temp_mail_health.json`
- `browser_config.json` 当前除浏览器偏好外，还会持久化：
  - GUI 侧各邮箱站点的触发比例
  - `概率均分` 之前的站点比例快照
  - 目的: 用户调整一次后，下次打开面板可直接沿用

## 下一阶段建议

1. 为 `mail.tm`、`10minutemail.net` 等高频站点补真实 DOM 校验，压缩通用兼容扫描触发率。
2. 为 mac 增加依赖自检与一键初始化脚本。
3. 给状态机补步骤级截图与失败快照策略。
4. 如需更像“程序”，再评估是否加本地 GUI 壳，而不是继续扩展批处理。
5. 如需继续提速，再评估浏览器复用，但必须先完成风控与隔离验证。
