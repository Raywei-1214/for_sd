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
    {"name": "10minutemail.net", "url": "https://10minutemail.net/"},
    {"name": "tempmail.lol", "url": "https://tempmail.lol/"},
    {"name": "crazymailing", "url": "https://www.crazymailing.com/"},
    {"name": "guerrillamail", "url": "https://www.guerrillamail.com/"},
    {"name": "tempemail.cc", "url": "https://www.tempemail.cc/fr"},
]

DEFAULT_TOTAL_COUNT = 999
DEFAULT_MAX_WORKERS = 5
MIN_WORKERS = 1
MAX_WORKERS = 5
EMAIL_SCAN_SECONDS = 30
VERIFICATION_WAIT_ATTEMPTS = 20

STEP_RETRY_COUNT = 5
PAGE_READY_WAIT_SECONDS = 3
FORM_SETTLE_WAIT_SECONDS = 2
CONFIRMATION_POLL_ATTEMPTS = 10
CONFIRMATION_POLL_INTERVAL_SECONDS = 3
REGISTRATION_RESULT_POLL_ATTEMPTS = 10
REGISTRATION_RESULT_POLL_INTERVAL_SECONDS = 4
PROBE_RETRY_COUNT = 5

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
    "div[class*='verification'] input",
    "div[class*='code'] input",
)
CONFIRMATION_READY_TEXT_MARKERS = (
    "confirm",
    "verification code",
    "验证码",
)

CONTINUE_BUTTON_SELECTORS = (
    "button:has-text('Continue')",
    "button[class*='continue']",
)

NEXT_BUTTON_SELECTORS = (
    "button:has-text('Next')",
    "button[class*='next']",
)

YEAR_INPUT_SELECTOR = "input[placeholder='Year']"
MONTH_SELECT_SELECTORS = (
    "div.lv-select-view:has-text('Month')",
    "div[placeholder='Month']",
)
DAY_SELECT_SELECTORS = (
    "div.lv-select-view:has-text('Day')",
    "div[placeholder='Day']",
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
