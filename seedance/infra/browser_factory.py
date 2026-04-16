from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Playwright, Route

from seedance.core.config import BLOCKED_RESOURCE_TYPES
from seedance.core.logger import get_logger

logger = get_logger()
ALLOWED_DREAMINA_HOSTS = (
    "dreamina.capcut.com",
    "capcut.com",
    "byteoversea.com",
    "bytedance.com",
)


def build_launch_args(headless: bool) -> list[str]:
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-extensions",
        "--disable-features=IsolateOrigins,site-per-process",
    ]

    if headless:
        launch_args.append("--headless=new")

    return launch_args


async def create_browser_context(
    playwright: Playwright,
    chrome_path: str | None,
    headless: bool,
) -> tuple[Browser, BrowserContext]:
    launch_args = build_launch_args(headless=headless)
    use_system_browser = chrome_path is not None

    if use_system_browser:
        try:
            browser = await playwright.chromium.launch(
                executable_path=chrome_path,
                headless=headless,
                args=launch_args,
            )
        except Exception as exc:
            logger.warning(f"启动本地浏览器失败，回退到内置 Chromium: {exc}")
            browser = await playwright.chromium.launch(
                headless=headless,
                args=launch_args,
            )
    else:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=launch_args,
        )

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        permissions=["clipboard-read", "clipboard-write"],
        geolocation={"latitude": 37.7749, "longitude": -122.4194},
    )
    await context.route("**/*", _handle_resource_route)
    return browser, context


async def _handle_resource_route(route: Route) -> None:
    # ================================
    # 当前轮次只对临时邮箱站点拦截高流量静态资源
    # 目的: Dreamina 主站及依赖全部放行，避免再次打断验证码/资料页渲染
    # 边界: 只拦 image/font/media/ping，且 document 导航请求永远放行
    # ================================
    request = route.request
    if request.resource_type == "document":
        await route.continue_()
        return

    hostname = (urlparse(request.url).hostname or "").lower()
    if _is_allowed_dreamina_host(hostname):
        await route.continue_()
        return

    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    await route.continue_()


def _is_allowed_dreamina_host(hostname: str) -> bool:
    return any(
        hostname == allowed_host or hostname.endswith(f".{allowed_host}")
        for allowed_host in ALLOWED_DREAMINA_HOSTS
    )
