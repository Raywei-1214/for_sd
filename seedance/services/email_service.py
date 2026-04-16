import asyncio
import re
from typing import Awaitable, Callable

from playwright.async_api import BrowserContext, Page

from seedance.core.config import EMAIL_SCAN_SECONDS, TEMP_EMAIL_PROVIDERS, VERIFICATION_WAIT_ATTEMPTS
from seedance.core.logger import get_logger
from seedance.infra.temp_mail_adapters import GENERIC_TEMP_MAIL_ADAPTER, TempMailAdapter, get_temp_mail_adapter

logger = get_logger()

ScreenshotSaver = Callable[[Page, str], Awaitable[None]]


class TempEmailService:
    def __init__(
        self,
        thread_id: int,
        specified_email: str | None,
        save_screenshot: ScreenshotSaver,
    ):
        self.thread_id = thread_id
        self.specified_email = specified_email
        self.save_screenshot = save_screenshot
        self.temp_email: str | None = None
        self.password: str | None = None
        self.provider_name: str | None = None
        self._adapter_fallback_logged: set[str] = set()

    async def _get_body_text(self, page: Page) -> str:
        try:
            return await page.evaluate("() => document.body?.innerText || ''")
        except Exception:
            return ""

    async def _is_timeout_error_page(self, page: Page) -> bool:
        body_text = await self._get_body_text(page)
        lowered_text = body_text.lower()
        current_url = (page.url or "").lower()
        return current_url.startswith("chrome-error://") or any(
            marker in lowered_text
            for marker in (
                "err_connection_timed_out",
                "this site can’t be reached",
                "this site can't be reached",
                "took too long to respond",
            )
        )

    async def _wait_for_tempmail_email_ready(self, page: Page, adapter: TempMailAdapter) -> None:
        # ================================
        # tempmail.lol 会先展示 Loading...，之后才真正生成邮箱
        # 目的: 等待真实邮箱出现，而不是把占位文本误当成页面已准备好
        # 边界: 仅对 tempmail.lol 生效，不改变其他站点的扫描节奏
        # ================================
        for _ in range(15):
            extracted_email = await self._extract_email_with_adapter(page, adapter)
            if extracted_email:
                return

            body_text = await self._get_body_text(page)
            if "loading..." not in body_text.lower():
                return
            await asyncio.sleep(1)

    async def _wait_for_internxt_email_ready(self, page: Page, adapter: TempMailAdapter) -> None:
        # ================================
        # Internxt 邮箱不是秒出，而是先停在 Generating random email...
        # 目的: 等待邮箱真实生成，并在卡住时主动点击 Refresh 拉起前端刷新
        # 边界: 仅对 internxt 生效，不改变其他邮箱站点的等待路径
        # ================================
        for attempt in range(20):
            extracted_email = await self._extract_email_with_adapter(page, adapter)
            if extracted_email:
                return

            body_text = await self._get_body_text(page)
            lowered_text = body_text.lower()
            if (
                "generating random email" in lowered_text
                or "you have 0 new messages" in lowered_text
            ) and attempt in {4, 9, 14}:
                await self._refresh_internxt_inbox(page)
            await asyncio.sleep(1)

    async def _refresh_internxt_inbox(self, page: Page) -> None:
        try:
            refresh_button = page.locator("button:has-text('Refresh')").first
            if await refresh_button.count() and await refresh_button.is_visible():
                await refresh_button.click(timeout=5000)
                await asyncio.sleep(2)
        except Exception:
            return

    async def _open_internxt_mail_preview(self, page: Page) -> None:
        # ================================
        # Internxt 邮件内容可能需要先点进列表项才会展开正文
        # 目的: 优先点开 Dreamina / CapCut / verification 相关邮件，帮助验证码落到正文
        # 边界: 只做轻量尝试，不把站点异常点击当成硬失败
        # ================================
        preview_selectors = (
            "text=/Dreamina/i",
            "text=/CapCut/i",
            "text=/verification/i",
            "text=/confirm/i",
            "text=/code/i",
        )
        for selector in preview_selectors:
            try:
                preview = page.locator(selector).first
                if await preview.count() and await preview.is_visible():
                    await preview.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

    def _pick_provider(self) -> dict:
        if self.specified_email:
            return next(
                (
                    provider
                    for provider in TEMP_EMAIL_PROVIDERS
                    if provider["name"] == self.specified_email
                ),
                TEMP_EMAIL_PROVIDERS[0],
            )

        provider_index = (self.thread_id - 1) % len(TEMP_EMAIL_PROVIDERS)
        return TEMP_EMAIL_PROVIDERS[provider_index]

    def _is_valid_email(self, candidate: str | None) -> bool:
        if not candidate:
            return False

        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(email_pattern, candidate.strip()) is not None

    async def _wait_for_adapter_ready(
        self,
        page: Page,
        adapter: TempMailAdapter,
    ) -> bool:
        if adapter.name == "internxt":
            return await self._wait_for_internxt_ready(page, adapter)

        for _ in range(EMAIL_SCAN_SECONDS):
            for selector in adapter.ready_selectors:
                try:
                    node = await page.query_selector(selector)
                    if node and await node.is_visible():
                        return True
                except Exception:
                    continue
            await asyncio.sleep(1)
        return False

    async def _wait_for_internxt_ready(
        self,
        page: Page,
        adapter: TempMailAdapter,
    ) -> bool:
        # ================================
        # Internxt 不能再用“营销页里有个 p 标签”判 ready
        # 目的: 只有真实邮箱或邮箱操作按钮出现时，才认为页面已进入收件箱态
        # 边界: 仅对 internxt 生效，不改变其他站点就绪策略
        # ================================
        for _ in range(EMAIL_SCAN_SECONDS):
            extracted_email = await self._extract_internxt_email(page)
            if extracted_email:
                return True

            for selector in adapter.ready_selectors:
                try:
                    node = await page.query_selector(selector)
                    if node and await node.is_visible():
                        return True
                except Exception:
                    continue
            await asyncio.sleep(1)
        return False

    async def _extract_email_with_adapter(
        self,
        page: Page,
        adapter: TempMailAdapter,
    ) -> str | None:
        # ================================
        # Guerrilla Mail 当前页面是“显示邮箱 + 收件箱 ID/域名分离”
        # 目的: 优先读取真实展示邮箱，再退回到 inbox-id + 域名拼接
        # 边界: 仅对 guerrillamail 生效，不污染其他站点适配器
        # ================================
        if adapter.name == "guerrillamail":
            guerrilla_email = await self._extract_guerrillamail_email(page)
            if guerrilla_email:
                return guerrilla_email
        if adapter.name == "internxt":
            internxt_email = await self._extract_internxt_email(page)
            if internxt_email:
                return internxt_email

        for selector in adapter.email_value_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    value = await element.get_attribute("value")
                    if self._is_valid_email(value):
                        return value.strip()
            except Exception:
                continue

        for selector in adapter.email_text_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = (await element.inner_text()).strip()
                    if self._is_valid_email(text):
                        return text
            except Exception:
                continue

        for selector, attribute_name in adapter.email_attribute_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    attribute_value = await element.get_attribute(attribute_name)
                    if self._is_valid_email(attribute_value):
                        return attribute_value.strip()
            except Exception:
                continue

        return None

    async def _extract_guerrillamail_email(self, page: Page) -> str | None:
        display_selectors = (
            "#email-widget",
            "input[name='show_email']",
        )

        for selector in display_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    value = await element.get_attribute("value")
                    if self._is_valid_email(value):
                        return value.strip()

                    text = (await element.inner_text()).strip()
                    if self._is_valid_email(text):
                        return text
            except Exception:
                continue

        try:
            inbox_node = await page.query_selector("#inbox-id")
            domain_node = await page.query_selector("#gm-host-select")
            if inbox_node and domain_node:
                inbox_id = (await inbox_node.inner_text()).strip()
                selected_domain = await domain_node.evaluate(
                    "(node) => node.options[node.selectedIndex]?.value || ''"
                )
                candidate = f"{inbox_id}@{selected_domain}".strip()
                if self._is_valid_email(candidate):
                    return candidate
        except Exception:
            pass

        return None

    async def _extract_internxt_email(self, page: Page) -> str | None:
        # ================================
        # Internxt 当前邮箱是前端渲染后的纯文本节点
        # 目的: 从短文本节点中提取真实邮箱，而不是继续依赖 input/readonly 结构
        # 边界: 只扫描短文本节点，避免把整段营销文案误判成邮箱
        # ================================
        text_selectors = (
            "p",
            "span",
            "div",
        )

        for selector in text_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = (await element.inner_text()).strip()
                    if len(text) > 120:
                        continue
                    if self._is_valid_email(text):
                        return text
            except Exception:
                continue

        return None

    async def _extract_email_with_generic_scan(self, page: Page) -> str | None:
        try:
            all_inputs = await page.query_selector_all("input")
            for input_node in all_inputs:
                value = await input_node.get_attribute("value")
                if value and "search" not in value.lower() and self._is_valid_email(value):
                    return value.strip()
        except Exception:
            pass

        return await self._extract_email_with_adapter(page, GENERIC_TEMP_MAIL_ADAPTER)

    async def _extract_email(self, page: Page, adapter: TempMailAdapter) -> str | None:
        provider_email = await self._extract_email_with_adapter(page, adapter)
        if provider_email:
            return provider_email

        # ================================
        # 适配器未命中只记录一次
        # 目的: 避免轮询扫描时刷满日志，掩盖真正的失败信号
        # 边界: 不影响后续继续退回通用兼容扫描
        # ================================
        if adapter.name not in self._adapter_fallback_logged:
            logger.warning(
                f"[线程{self.thread_id}] 站点适配器未命中，退回通用兼容扫描: {adapter.name}"
            )
            self._adapter_fallback_logged.add(adapter.name)
        return await self._extract_email_with_generic_scan(page)

    def _extract_code_from_text(
        self,
        page_text: str,
        adapter: TempMailAdapter,
    ) -> str | None:
        regex_patterns = [
            r"verification\s+code\s+(?:is|:|：)\s*([A-Z0-9]{6})",
            r"验证码(?:是|:|：)\s*([A-Z0-9]{6})",
            r"code\s*(?:is|:|：)\s*([A-Z0-9]{6})",
        ]

        if adapter.verification_text_markers:
            lowered_text = page_text.lower()
            if not any(marker.lower() in lowered_text for marker in adapter.verification_text_markers):
                return None

        for pattern in regex_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1).upper()

        return None

    async def acquire_email(self, context: BrowserContext) -> tuple[Page | None, bool]:
        try:
            provider = self._pick_provider()
            self.provider_name = provider["name"]
            adapter = get_temp_mail_adapter(self.provider_name)
            logger.info(f"[线程{self.thread_id}] 正在创建临时邮箱（{self.provider_name}）...")

            page = await context.new_page()
            page_loaded = False

            # ================================
            # 先保证邮箱页能打开，再进入页面内容扫描
            # ================================
            for retry_count in range(3):
                try:
                    if retry_count > 0:
                        logger.info(
                            f"[线程{self.thread_id}] 第 {retry_count + 1} 次尝试访问临时邮箱网站..."
                        )
                        await asyncio.sleep(3)

                    await page.goto(
                        provider["url"],
                        timeout=150000,
                        wait_until="domcontentloaded",
                    )
                    await asyncio.sleep(2)

                    if self.provider_name == "10minutemail.net" and await self._is_timeout_error_page(page):
                        logger.warning(
                            f"[线程{self.thread_id}] 10minutemail.net 返回超时错误页，准备重试"
                        )
                        continue

                    page_loaded = True
                    logger.info(f"[线程{self.thread_id}] ✓ 临时邮箱页面加载成功")
                    break
                except Exception as exc:
                    logger.warning(
                        f"[线程{self.thread_id}] 临时邮箱页面加载失败 "
                        f"({retry_count + 1}/3): {str(exc)[:100]}"
                    )

            if not page_loaded:
                logger.error(f"[线程{self.thread_id}] 无法访问临时邮箱网站")
                return page, False

            await self.save_screenshot(page, "01_temp_email_page")
            adapter_ready = await self._wait_for_adapter_ready(page, adapter)
            if not adapter_ready:
                logger.warning(f"[线程{self.thread_id}] 站点适配器等待超时，继续尝试兼容扫描")

            if self.provider_name == "tempmail.lol":
                await self._wait_for_tempmail_email_ready(page, adapter)
            if self.provider_name == "internxt":
                await self._wait_for_internxt_email_ready(page, adapter)

            logger.info(f"[线程{self.thread_id}] 正在通过站点适配器提取邮箱...")

            for _ in range(EMAIL_SCAN_SECONDS):
                try:
                    self.temp_email = await self._extract_email(page, adapter)
                except Exception:
                    pass

                if self.temp_email:
                    break
                await asyncio.sleep(1)

            if self.temp_email and "@" in self.temp_email:
                prefix = self.temp_email.split("@")[0][:10]
                self.password = prefix + "Aa1!"
                logger.info(f"[线程{self.thread_id}] ✓ 成功提取邮箱: {self.temp_email}")
                logger.info(f"[线程{self.thread_id}] ✓ 生成密码: {self.password}")
                await self.save_screenshot(page, "02_email_created")
                return page, True

            logger.error(f"[线程{self.thread_id}] 30秒内未检测到邮箱地址")
            await self.save_screenshot(page, "error_email_extract_failed")
            return page, False
        except Exception as exc:
            logger.error(f"[线程{self.thread_id}] 临时邮箱模块发生异常: {exc}", exc_info=True)
            return None, False

    async def wait_verification_code(self, email_page: Page) -> str | None:
        try:
            logger.info(f"[线程{self.thread_id}] 正在收件箱等待验证码 (最多等待60秒)...")
            adapter = get_temp_mail_adapter(self.provider_name or "")
            verification_attempts = VERIFICATION_WAIT_ATTEMPTS + 10 if adapter.name == "internxt" else VERIFICATION_WAIT_ATTEMPTS
            for attempt in range(verification_attempts):
                await asyncio.sleep(3)
                try:
                    if adapter.name == "internxt":
                        await self._refresh_internxt_inbox(email_page)
                        await self._open_internxt_mail_preview(email_page)

                    page_text = await email_page.evaluate("() => document.body.innerText")
                    verification_code = self._extract_code_from_text(page_text, adapter)
                    if not verification_code and adapter.name != GENERIC_TEMP_MAIL_ADAPTER.name:
                        verification_code = self._extract_code_from_text(
                            page_text,
                            GENERIC_TEMP_MAIL_ADAPTER,
                        )

                    if verification_code:
                        logger.info(f"[线程{self.thread_id}] ✓✓✓ 成功提取到验证码: {verification_code}")
                        await self.save_screenshot(email_page, "06_code_found")
                        return verification_code

                    if attempt > 0 and attempt % 3 == 0:
                        logger.info(f"[线程{self.thread_id}] 强制刷新邮箱页面以获取新邮件...")
                        await email_page.reload()
                except Exception as exc:
                    logger.debug(f"[线程{self.thread_id}] 提取验证码过程报错: {exc}")

            logger.error(f"[线程{self.thread_id}] 超时仍未在页面上匹配到验证码")
            await self.save_screenshot(email_page, "06_code_timeout")
            return None
        except Exception as exc:
            logger.error(f"[线程{self.thread_id}] 获取验证码函数异常: {exc}")
            return None
