from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Download,
    Page,
    Playwright,
    async_playwright,
)

from seedance.core.config import (
    MAGICERASER_URL,
    WATERMARK_DEFAULT_REGION_RATIO,
    WATERMARK_DOWNLOAD_TIMEOUT_MS,
    WATERMARK_PROCESS_TIMEOUT_MS,
    WATERMARK_UPLOAD_TIMEOUT_MS,
)
from seedance.core.logger import get_logger
from seedance.infra.browser_detector import find_chrome_browser
from seedance.infra.browser_factory import create_browser_context

logger = get_logger()


# ================================
# magiceraser.org 视频去水印 Playwright 驱动
# 目的: 把页面操作细节封装为"打开 → 上传 → 框选 → 处理 → 下载"四个阶段
# 边界: 不处理批量调度、不落盘报告、不直接与 GUI 通信
# ================================


class MagicEraserError(RuntimeError):
    def __init__(self, phase: str, message: str) -> None:
        super().__init__(f"[{phase}] {message}")
        self.phase = phase
        self.detail = message


FILE_INPUT_SELECTOR = "input[type='file']"

# 页面上承载视频预览与水印框选的元素，按优先级尝试
PREVIEW_SURFACE_SELECTORS = (
    "canvas",
    "video",
    "[class*='editor'] canvas",
    "[class*='preview'] canvas",
    "[class*='canvas']",
)

# 触发处理的按钮候选文案，涵盖常见英文 UI
PROCESS_BUTTON_TEXTS = (
    "Remove Watermark",
    "Remove watermark",
    "Remove",
    "Erase",
    "Start",
    "Process",
    "Generate",
    "Run",
)

# 下载按钮候选文案，兜底给事件监听
DOWNLOAD_BUTTON_TEXTS = (
    "Download",
    "Download Video",
    "Save",
    "Export",
)


class MagicEraserDriver:
    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def __aenter__(self) -> "MagicEraserDriver":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        chrome_path = find_chrome_browser()
        self._browser, self._context = await create_browser_context(
            playwright=self._playwright,
            chrome_path=chrome_path,
            headless=self._headless,
        )

    async def close(self) -> None:
        # 关闭顺序: context → browser → playwright，忽略单个资源的释放异常
        for closer in (self._context, self._browser):
            if closer is None:
                continue
            try:
                await closer.close()
            except Exception as exc:
                logger.warning(f"关闭 Playwright 资源失败: {exc}")
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning(f"停止 Playwright 失败: {exc}")
        self._context = None
        self._browser = None
        self._playwright = None

    async def remove_watermark(
        self,
        input_path: Path,
        output_path: Path,
        region_ratio: tuple[float, float, float, float] = WATERMARK_DEFAULT_REGION_RATIO,
    ) -> Path:
        if self._context is None:
            raise MagicEraserError("init", "driver 未启动")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        page = await self._context.new_page()
        try:
            await self._open_site(page)
            await self._upload_video(page, input_path)
            await self._draw_watermark_region(page, region_ratio)
            await self._trigger_process(page)
            await self._capture_download(page, output_path)
        finally:
            try:
                await page.close()
            except Exception:
                pass
        return output_path

    async def _open_site(self, page: Page) -> None:
        try:
            await page.goto(MAGICERASER_URL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            raise MagicEraserError("open_site", f"打开站点失败: {exc}") from exc

    async def _upload_video(self, page: Page, input_path: Path) -> None:
        try:
            input_locator = page.locator(FILE_INPUT_SELECTOR).first
            await input_locator.wait_for(state="attached", timeout=30_000)
            await input_locator.set_input_files(str(input_path))
        except Exception as exc:
            raise MagicEraserError("upload", f"视频上传失败: {exc}") from exc

        # 等待预览元素出现，认为上传被站点接收
        surface = await self._wait_for_preview(page, timeout_ms=WATERMARK_UPLOAD_TIMEOUT_MS)
        if surface is None:
            raise MagicEraserError("upload", "上传后未检测到视频预览元素")

    async def _wait_for_preview(self, page: Page, timeout_ms: int) -> Optional[str]:
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
        while asyncio.get_event_loop().time() < deadline:
            for selector in PREVIEW_SURFACE_SELECTORS:
                locator = page.locator(selector).first
                try:
                    if await locator.count() == 0:
                        continue
                    box = await locator.bounding_box()
                    if box and box["width"] > 50 and box["height"] > 50:
                        return selector
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return None

    async def _draw_watermark_region(
        self,
        page: Page,
        region_ratio: tuple[float, float, float, float],
    ) -> None:
        try:
            surface_selector = await self._wait_for_preview(page, timeout_ms=10_000)
            if surface_selector is None:
                raise MagicEraserError("select", "找不到可框选的视频预览元素")

            locator = page.locator(surface_selector).first
            box = await locator.bounding_box()
            if not box:
                raise MagicEraserError("select", "无法读取预览元素坐标")

            x_ratio, y_ratio, w_ratio, h_ratio = region_ratio
            start_x = box["x"] + box["width"] * x_ratio
            start_y = box["y"] + box["height"] * y_ratio
            end_x = start_x + box["width"] * w_ratio
            end_y = start_y + box["height"] * h_ratio

            # 预设的 Dreamina 水印相对位置，转成 page 绝对像素后拖选
            await page.mouse.move(start_x, start_y)
            await page.mouse.down()
            # 分两段移动，避免某些前端把单次 move 视作 click
            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            await page.mouse.move(mid_x, mid_y, steps=8)
            await page.mouse.move(end_x, end_y, steps=8)
            await page.mouse.up()
        except MagicEraserError:
            raise
        except Exception as exc:
            raise MagicEraserError("select", f"模拟框选失败: {exc}") from exc

    async def _trigger_process(self, page: Page) -> None:
        for text in PROCESS_BUTTON_TEXTS:
            locator = page.get_by_role("button", name=text, exact=False)
            try:
                if await locator.count() == 0:
                    continue
                await locator.first.click(timeout=5_000)
                return
            except Exception:
                continue
        # 兜底: 尝试任何 type=submit
        try:
            submit = page.locator("button[type='submit']").first
            if await submit.count() > 0:
                await submit.click(timeout=5_000)
                return
        except Exception:
            pass
        raise MagicEraserError("process", "未找到启动处理的按钮")

    async def _capture_download(self, page: Page, output_path: Path) -> None:
        try:
            async with page.expect_download(timeout=WATERMARK_PROCESS_TIMEOUT_MS) as download_info:
                # 处理完成后站点可能自动弹出下载，也可能需要点按钮，两条路径都留
                await self._try_click_download_button(page)
            download: Download = await download_info.value
            await download.save_as(str(output_path))
            await download.delete()
        except MagicEraserError:
            raise
        except Exception as exc:
            raise MagicEraserError("download", f"下载结果失败: {exc}") from exc

        # 最终校验: 文件要存在且有内容
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise MagicEraserError("download", "下载文件为空或不存在")

    async def _try_click_download_button(self, page: Page) -> None:
        # 轮询若干轮: 处理中 → 处理完成 → 下载按钮出现
        deadline = asyncio.get_event_loop().time() + WATERMARK_DOWNLOAD_TIMEOUT_MS / 1000
        while asyncio.get_event_loop().time() < deadline:
            for text in DOWNLOAD_BUTTON_TEXTS:
                locator = page.get_by_role("button", name=text, exact=False)
                try:
                    if await locator.count() == 0:
                        continue
                    if not await locator.first.is_enabled():
                        continue
                    await locator.first.click(timeout=3_000)
                    return
                except Exception:
                    continue
            await asyncio.sleep(1.0)
