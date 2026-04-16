from playwright.async_api import Browser, BrowserContext, Playwright, Route

from seedance.core.config import BLOCKED_RESOURCE_TYPES
from seedance.core.logger import get_logger

logger = get_logger()


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


async def _configure_context_network(context: BrowserContext) -> None:
    # ================================
    # 省流模式优先拦截大体积静态资源
    # 目的: 减少图片、媒体、字体重复下载带来的流量消耗
    # 边界: 不拦截脚本、XHR、样式表，避免直接破坏注册主流程
    # ================================
    async def handle_route(route: Route) -> None:
        request = route.request
        if request.resource_type in BLOCKED_RESOURCE_TYPES:
            await route.abort()
            return
        await route.continue_()

    await context.route("**/*", handle_route)


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
    await _configure_context_network(context)
    return browser, context
