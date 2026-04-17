from seedance.core.runtime import get_runtime_root_dir

ROOT_DIR = get_runtime_root_dir()
DOCS_DIR = ROOT_DIR / "docs"
SCREENSHOT_DIR = ROOT_DIR / "screenshots_usa"
SUCCESS_DIR = ROOT_DIR / "registered_accounts_usa"
REPORT_DIR = ROOT_DIR / "run_reports"
TEMP_MAIL_HEALTH_FILE = ROOT_DIR / "temp_mail_health.json"
LOG_FILE = ROOT_DIR / "dreamina_register_usa.log"
BROWSER_CONFIG_FILE = ROOT_DIR / "browser_config.json"

DREAMINA_HOME_URL = "https://dreamina.capcut.com/ai-tool/home"
DREAMINA_VIDEO_URL = "https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0"
IP_COUNTRY_URL = "http://ip-api.com/json/?fields=country"

TEMP_EMAIL_PROVIDERS = [
    {"name": "mail.tm", "url": "https://mail.tm/zh/"},
    {"name": "tempmail.lol", "url": "https://tempmail.lol/"},
    {"name": "internxt", "url": "https://internxt.com/temporary-email"},
    {"name": "tempemail.cc", "url": "https://www.tempemail.cc/fr"},
    # ================================
    # 70 积分占比过高，当前轮次先停用
    # 目的: 降低无效站点对整体可用率和流量的消耗
    # 边界: 只从启用池移除，不删除适配器实现，方便后续恢复观察
    # ================================
    # {"name": "10minutemail.net", "url": "https://10minutemail.net/"},
    # {"name": "guerrillamail", "url": "https://www.guerrillamail.com/"},
]

DEFAULT_TOTAL_COUNT = 999
DEFAULT_MAX_WORKERS = 5
MIN_WORKERS = 1
MAX_WORKERS = 5
EMAIL_SCAN_SECONDS = 30
VERIFICATION_WAIT_ATTEMPTS = 20
EMAIL_LIGHT_REFRESH_INTERVAL = 2
EMAIL_HARD_RELOAD_INTERVAL = 6

STEP_RETRY_COUNT = 5
PAGE_READY_WAIT_SECONDS = 3
OPEN_HOME_READY_WAIT_SECONDS = 20
PROFILE_READY_WAIT_SECONDS = 15
FORM_SETTLE_WAIT_SECONDS = 2
CONFIRMATION_POLL_ATTEMPTS = 10
CONFIRMATION_POLL_INTERVAL_SECONDS = 3
REGISTRATION_RESULT_POLL_ATTEMPTS = 10
REGISTRATION_RESULT_POLL_INTERVAL_SECONDS = 4
PROBE_RETRY_COUNT = 5
PROBE_NAVIGATION_RETRY_COUNT = 3

POPUP_CLOSE_SELECTORS = (
    "button[aria-label='Close']",
    "button[aria-label='close']",
    "button[class*='close-btn']",
    "button[class*='close']",
    "div[class*='close-icon']",
    "div[class*='close-btn']",
    "button:has-text('×')",
    "button:has-text('✕')",
    "*[class*='close-icon']",
    "div[role='dialog'] button[class*='close']",
    "div[class*='modal'] button[class*='close']",
    "div[class*='popup'] button[class*='close']",
)

CREDIT_SELECTORS = (
    "xpath=//div[contains(@class, 'credit-display-container')]//div[1]",
    "div.credit-display-container div:first-child",
    "div[class*='credit-display-container'] div:first-child",
    "*[class*='credit-display'] div:first-child",
    "*[class*='credit'] div:first-child",
    "xpath=//*[contains(@class, 'credit')]",
)

CREATE_MENU_SELECTORS = (
    "#AIGeneratedRecord",
    'div.lv-menu-item:has-text("Create")',
)

EMAIL_LOGIN_TRIGGER_SELECTOR = "div.lv_new_third_part_sign_in_expand-button"
EMAIL_LOGIN_BUTTON_TEXT = "Continue with email"
SIGN_UP_TRIGGER_SELECTOR = "span.new-forget-pwd-btn"
SIGN_UP_TRIGGER_TEXT = "Sign up"

HOME_READY_SELECTORS = CREATE_MENU_SELECTORS
HOME_READY_TEXT_MARKERS = (
    "explore",
    "create assets",
)

EMAIL_INPUT_SELECTORS = (
    "input[placeholder='Enter email']",
    "input[type='email']",
)

PASSWORD_INPUT_SELECTORS = (
    "input[placeholder='Enter password']",
    "input[placeholder='Password']",
)
SIGNUP_FORM_READY_SELECTORS = EMAIL_INPUT_SELECTORS + PASSWORD_INPUT_SELECTORS

CONFIRMATION_READY_SELECTORS = (
    "input[autocomplete='one-time-code']",
    "input[inputmode='numeric']",
    "input[inputmode='tel']",
    "input[placeholder*='code' i]",
    "input[aria-label*='code' i]",
    "input[name*='code' i]",
    "input[maxlength='6'][inputmode='numeric']",
    "div[class*='verification'] input",
    "div[class*='code'] input",
    "div[class*='otp'] input",
    "[data-testid*='verification'] input",
)
CONFIRMATION_READY_TEXT_MARKERS = (
    "confirm",
    "verification code",
    "验证码",
    "enter code",
    "one-time code",
    "6-digit",
    "check your inbox",
    "resend code",
    "sent to",
)

CONTINUE_BUTTON_SELECTORS = (
    "button:has-text('Continue')",
    "button[class*='continue']",
)

NEXT_BUTTON_SELECTORS = (
    "button:has-text('Next')",
    "button[class*='next']",
)

YEAR_INPUT_SELECTORS = (
    "input[placeholder='Year']",
    "input[placeholder*='Year' i]",
    "input[aria-label*='Year' i]",
    "input[name*='year' i]",
    "input[autocomplete='bday-year']",
    "input[inputmode='numeric'][maxlength='4']",
    "[data-testid*='year'] input",
)
YEAR_INPUT_SELECTOR = YEAR_INPUT_SELECTORS[0]
MONTH_SELECT_SELECTORS = (
    "div.lv-select-view:has-text('Month')",
    "div[placeholder='Month']",
    "div[role='combobox']:has-text('Month')",
    "div[aria-label*='Month' i]",
    "input[placeholder='Month']",
    "[data-testid*='month']",
)
DAY_SELECT_SELECTORS = (
    "div.lv-select-view:has-text('Day')",
    "div[placeholder='Day']",
    "div[role='combobox']:has-text('Day')",
    "div[aria-label*='Day' i]",
    "input[placeholder='Day']",
    "[data-testid*='day']",
)
MONTH_OPTION_TEMPLATE_SELECTORS = (
    "div.lv-select-option:text-is('{value}')",
    "*[class*='option']:text-is('{value}')",
)
DAY_OPTION_TEMPLATE_SELECTORS = (
    "div.lv-select-option:text-is('{value}')",
    "*[class*='option']:text-is('{value}')",
)
PROFILE_READY_SELECTORS = (
    YEAR_INPUT_SELECTOR,
) + MONTH_SELECT_SELECTORS + DAY_SELECT_SELECTORS
PROFILE_READY_TEXT_MARKERS = (
    "year",
    "month",
    "day",
    "birth",
    "birthday",
    "date of birth",
    "tell us about yourself",
)

CONFIRMATION_BODY_TEXT = "confirm"
LOGIN_RELATED_URL_SEGMENTS = ("login", "signup")

PROBE_BALANCE_SELECTORS = (
    "div[class*='credit-amount']",
    "div[class*='credit-text']",
    "div[class*='balance']",
)
PROBE_MODEL_DROPDOWN_SELECTOR = "div.lv-select-view"
PROBE_MODEL_DROPDOWN_TEXT = "Dreamina Seedance"
PROBE_MODEL_OPTION_SELECTOR = "li[role='option']"
PROBE_MODEL_OPTION_TEXT = "2.0 Fast"
PROBE_BLOCKED_TEXT_MARKERS = (
    "sign in start creating",
    "creative partner program",
    "ai agent auto trends",
    "see the prompt guide",
    "1080p is now available",
)
PROBE_BLOCKED_URL_MARKERS = (
    "/ai-tool/generate",
    "type=agentic",
)
PROBE_VIDEO_ENTRY_SELECTORS = (
    "a[href*='type=video']",
    "button:has-text('AI Video')",
    "a:has-text('AI Video')",
    "div[role='tab']:has-text('AI Video')",
    "div[role='button']:has-text('AI Video')",
)
PROBE_START_CREATING_SELECTORS = (
    "button:has-text('Start Creating')",
    "a:has-text('Start Creating')",
    "div[role='button']:has-text('Start Creating')",
)
PROBE_WORKSPACE_ENTRY_WAIT_SECONDS = 2
PROBE_GENERATE_BUTTON_SELECTORS = (
    "div[class*='commercial-button']",
    "button:has-text('Generate')",
)
SUCCESS_READY_SELECTORS = CREDIT_SELECTORS + PROBE_GENERATE_BUTTON_SELECTORS + CREATE_MENU_SELECTORS
SUCCESS_READY_TEXT_MARKERS = (
    "generate",
    "credit",
)

# ================================
# 省流相关常量
# 目的: 统一收口当前轮次的资源拦截范围，方便后续单独回滚
# 边界: 只拦截图片/字体/媒体/ping，不碰脚本和接口请求
# ================================
BLOCKED_RESOURCE_TYPES = (
    "image",
    "font",
    "media",
    "ping",
)

# ================================
# 去水印（magiceraser.org）相关常量
# 目的: 把站点 URL、水印相对坐标、超时阈值集中管理
# 边界: 仅影响 watermark 子模块，不干扰注册流程
# ================================
MAGICERASER_URL = "https://magiceraser.org/remove-watermark-from-video/"
WATERMARK_SUPPORTED_SUFFIXES = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")
WATERMARK_OUTPUT_SUBDIR = "cleaned"
WATERMARK_REPORT_DIR = REPORT_DIR
# Dreamina 生成视频的水印固定在右下角，坐标为相对于视频画面的比例
WATERMARK_DEFAULT_REGION_RATIO = (0.80, 0.86, 0.18, 0.11)  # (x, y, w, h)
WATERMARK_UPLOAD_TIMEOUT_MS = 120_000
WATERMARK_PROCESS_TIMEOUT_MS = 300_000
WATERMARK_DOWNLOAD_TIMEOUT_MS = 180_000
WATERMARK_MAX_FREE_SECONDS = 30
WATERMARK_FFPROBE_TIMEOUT_SECONDS = 10
