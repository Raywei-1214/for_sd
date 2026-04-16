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
    # 当前轮次只拦截高流量但低注册价值的静态资源
    # 目的: 在不动脚本和接口请求的前提下，先压掉图片/字体/媒体/ping 流量
    # 边界: 不拦 script/xhr/fetch/stylesheet，避免再次把主流程打坏
    # ================================
    if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    await route.continue_()
