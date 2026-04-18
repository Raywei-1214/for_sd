import asyncio
import re
from typing import Awaitable, Callable

from playwright.async_api import BrowserContext, Page

from seedance.core.config import (
    EMAIL_HARD_RELOAD_INTERVAL,
    EMAIL_LIGHT_REFRESH_INTERVAL,
    EMAIL_SCAN_SECONDS,
    TEMP_EMAIL_PROVIDERS,
    VERIFICATION_WAIT_ATTEMPTS,
)
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

    def _extract_email_from_multiline_text(
        self,
        body_text: str,
        *,
        max_line_length: int = 120,
    ) -> str | None:
        # ================================
        # 部分邮箱站把真实邮箱拆在短文本行里
        # 目的: 从短行文本中提取真实邮箱，降低对脆弱 DOM 结构的依赖
        # 边界: 只扫描短行，避免把大段营销文案里的示例邮箱误判成临时邮箱
        # ================================
        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"

        for raw_line in body_text.splitlines():
            compact_line = re.sub(r"\s+", " ", raw_line).strip()
            if not compact_line or len(compact_line) > max_line_length:
                continue

            for candidate in re.findall(email_pattern, compact_line):
                if self._is_valid_email(candidate):
                    return candidate

        return None

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

    async def _wait_for_mailtm_email_ready(self, page: Page, adapter: TempMailAdapter) -> None:
        # ================================
        # mail.tm 偶发先进入 inbox 壳子，真实邮箱稍后才落地
        # 目的: 等待真实邮箱出现，并在卡住时优先点站内刷新
        # 边界: 仅对 mail.tm 生效，刷新次数受限，避免额外烧流量
        # ================================
        for attempt in range(20):
            extracted_email = await self._extract_email_with_adapter(page, adapter)
            if extracted_email:
                return

            body_text = await self._get_body_text(page)
            lowered_text = body_text.lower()
            if (
                "收件箱" in body_text
                or "刷新" in body_text
                or "inbox" in lowered_text
                or "refresh" in lowered_text
            ) and attempt in {4, 9, 14}:
                await self._refresh_mailtm_inbox(page)
            await asyncio.sleep(1)

    async def _refresh_gptmail_inbox(self, page: Page) -> None:
        try:
            refresh_button = page.locator("#refreshInboxBtn").first
            if await refresh_button.count() and await refresh_button.is_visible():
                await refresh_button.click(timeout=5000)
                await asyncio.sleep(2)
        except Exception:
            return

    async def _refresh_mailticking_inbox(self, page: Page) -> None:
        # ================================
        # MailTicking 的收件箱刷新入口固定挂在左侧 Refresh 按钮
        # 目的: 优先命中站点自己的收件箱刷新链路，避免整页 reload 打断当前邮箱态
        # 边界: 仅对 mailticking.com 生效，刷新失败时交给通用刷新逻辑继续兜底
        # ================================
        refresh_selectors = (
            "#refresh-button",
            "a#refresh-button",
            "a:has-text('Refresh')",
        )
        for selector in refresh_selectors:
            try:
                refresh_button = page.locator(selector).first
                if await refresh_button.count() and await refresh_button.is_visible():
                    await refresh_button.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

    async def _refresh_internxt_inbox(self, page: Page) -> None:
        try:
            refresh_button = page.locator("button:has-text('Refresh')").first
            if await refresh_button.count() and await refresh_button.is_visible():
                await refresh_button.click(timeout=5000)
                await asyncio.sleep(2)
        except Exception:
            return

    async def _refresh_mailtm_inbox(self, page: Page) -> None:
        # ================================
        # mail.tm 有站内刷新入口
        # 目的: 优先触发站内刷新，避免整页 reload 打断邮箱生成态
        # 边界: 只点击可见刷新控件，失败交给上层自然重试
        # ================================
        refresh_selectors = (
            "button:has-text('刷新')",
            "button:has-text('Refresh')",
            "a:has-text('刷新')",
            "a:has-text('Refresh')",
            "button[aria-label*='refresh' i]",
        )
        for selector in refresh_selectors:
            try:
                refresh_button = page.locator(selector).first
                if await refresh_button.count() and await refresh_button.is_visible():
                    await refresh_button.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

    async def _light_refresh_email_page(self, page: Page, adapter: TempMailAdapter) -> bool:
        # ================================
        # 验证码等待阶段优先走站点内轻刷新
        # 目的: 用站内按钮/Ajax 刷新代替整页 reload，减少流量和页面重建抖动
        # 边界: 只要 provider 有专属刷新链路就优先命中；没有再尝试通用刷新控件
        # ================================
        if adapter.name == "mail.chatgpt.org.uk":
            await self._refresh_gptmail_inbox(page)
            return True

        if adapter.name == "mailticking.com":
            await self._refresh_mailticking_inbox(page)
            return True

        if adapter.name == "internxt":
            await self._refresh_internxt_inbox(page)
            return True

        if adapter.name == "mail.tm":
            await self._refresh_mailtm_inbox(page)
            return True

        if adapter.name == "10minutemail.net":
            await self._refresh_10minutemail_inbox(page)
            return True

        refresh_selectors = (
            "button:has-text('Refresh')",
            "a:has-text('Refresh')",
            "button:has-text('Reload')",
            "a:has-text('Reload')",
            "button[aria-label*='refresh' i]",
            "a[aria-label*='refresh' i]",
            "[class*='refresh']",
        )
        for selector in refresh_selectors:
            try:
                refresh_node = page.locator(selector).first
                if await refresh_node.count() and await refresh_node.is_visible():
                    await refresh_node.click(timeout=5000)
                    await asyncio.sleep(2)
                    return True
            except Exception:
                continue

        return False

    async def _refresh_10minutemail_inbox(self, page: Page) -> None:
        # ================================
        # 10minutemail.net 自带 mailbox.ajax.php 刷新逻辑
        # 目的: 优先触发站内轻刷新，而不是频繁整页 reload 烧流量
        # 边界: 若站内刷新函数不存在，再退回到页面内刷新链接
        # ================================
        try:
            refreshed = await page.evaluate(
                """
                () => {
                    if (typeof updatemailbox === 'function') {
                        updatemailbox();
                        return true;
                    }
                    return false;
                }
                """
            )
            if refreshed:
                await asyncio.sleep(2)
                return
        except Exception:
            pass

        refresh_selectors = (
            "a:has-text('Refresh this page.')",
            "a:has-text('Refresh this page')",
            "a[href='/?lang=en']",
        )
        for selector in refresh_selectors:
            try:
                refresh_link = page.locator(selector).first
                if await refresh_link.count() and await refresh_link.is_visible():
                    await refresh_link.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

    async def _open_10minutemail_mail_preview(self, page: Page) -> None:
        # ================================
        # 10minutemail.net 验证码邮件通常在 InBox 表格里
        # 目的: 优先点开 Dreamina / CapCut / verification 相关邮件，避免正文一直停留在欢迎邮件
        # 边界: 关键词未命中时，回退点最新一封邮件；仍然只做轻量尝试，不把预览失败当成硬错误
        # ================================
        if "readmail.html" in (page.url or ""):
            return

        preview_selectors = (
            "a.row-link:has-text('Dreamina')",
            "a.row-link:has-text('CapCut')",
            "a.row-link:has-text('verification')",
            "a.row-link:has-text('Verification')",
            "a.row-link:has-text('confirm')",
            "a.row-link:has-text('Confirm')",
            "a.row-link:has-text('code')",
            "a.row-link:has-text('Code')",
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

        fallback_selectors = (
            "#maillist a.row-link",
            "table#maillist a.row-link",
        )
        for selector in fallback_selectors:
            try:
                preview = page.locator(selector).first
                if await preview.count() and await preview.is_visible():
                    await preview.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

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

    async def _open_gptmail_mail_preview(self, page: Page) -> None:
        # ================================
        # GPTMail 邮件正文在弹层 iframe 中
        # 目的: 先点开候选邮件，再读取 iframe 正文里的验证码
        # 边界: 只做轻量点击，不把弹层失败当成硬错误
        # ================================
        preview_selectors = (
            "#emailList li:has-text('Dreamina')",
            "#emailList li:has-text('CapCut')",
            "#emailList li:has-text('verification')",
            "#emailList li:has-text('Verification')",
            "#emailList li:has-text('confirm')",
            "#emailList li:has-text('Confirm')",
            "#emailList li:has-text('code')",
            "#emailList li:has-text('Code')",
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

        fallback_selectors = (
            "#emailList li:not(.skeleton-email-item):not(.empty-state)",
            ".email-list li",
        )
        for selector in fallback_selectors:
            try:
                preview = page.locator(selector).first
                if await preview.count() and await preview.is_visible():
                    await preview.click(timeout=5000)
                    await asyncio.sleep(2)
                    return
            except Exception:
                continue

    async def _open_mailticking_mail_preview(self, page: Page) -> None:
        # ================================
        # MailTicking 的邮件正文需要先点列表链接进入 /mail/view/...
        # 目的: 优先点开 Dreamina / CapCut / verification 相关邮件，帮助验证码进入正文页
        # 边界: 只做轻量点击；关键词未命中时再退回最新一封邮件
        # ================================
        preview_selectors = (
            "#message-list a:has-text('Dreamina')",
            "#message-list a:has-text('CapCut')",
            "#message-list a:has-text('verification')",
            "#message-list a:has-text('Verification')",
            "#message-list a:has-text('confirm')",
            "#message-list a:has-text('Confirm')",
            "#message-list a:has-text('code')",
            "#message-list a:has-text('Code')",
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

        fallback_selectors = (
            "#message-list a",
            "table tbody#message-list a",
        )
        for selector in fallback_selectors:
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
        if adapter.name == "mail.chatgpt.org.uk":
            return await self._wait_for_gptmail_ready(page, adapter)

        if adapter.name == "internxt":
            return await self._wait_for_internxt_ready(page, adapter)

        if adapter.name == "mail.tm":
            return await self._wait_for_mailtm_ready(page, adapter)

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

    async def _wait_for_mailtm_ready(
        self,
        page: Page,
        adapter: TempMailAdapter,
    ) -> bool:
        # ================================
        # mail.tm 不能只看 inbox 壳子，还要确认真实邮箱已经落地
        # 目的: 避免把“收件箱 / 刷新已出现但邮箱未生成”误判成 ready
        # 边界: 仅对 mail.tm 生效，不改变其他站点 ready 契约
        # ================================
        for _ in range(EMAIL_SCAN_SECONDS):
            extracted_email = await self._extract_mailtm_email(page)
            if extracted_email:
                return True

            for selector in adapter.ready_selectors:
                try:
                    node = await page.query_selector(selector)
                    if not node or not await node.is_visible():
                        continue

                    text = ((await node.text_content()) or "").strip()
                    value = (await node.get_attribute("value") or "").strip()
                    clipboard_text = (await node.get_attribute("data-clipboard-text") or "").strip()
                    if any(
                        self._is_valid_email(candidate)
                        for candidate in (text, value, clipboard_text)
                    ):
                        return True
                except Exception:
                    continue
            await asyncio.sleep(1)
        return False

    async def _wait_for_gptmail_ready(
        self,
        page: Page,
        adapter: TempMailAdapter,
    ) -> bool:
        # ================================
        # GPTMail 会先自动跳到专属邮箱 URL
        # 目的: 只有真实邮箱或收件箱控件出现时，才视为页面 ready
        # 边界: 仅对 GPTMail 生效，不改其他站点的 ready 口径
        # ================================
        for _ in range(EMAIL_SCAN_SECONDS):
            extracted_email = await self._extract_gptmail_email(page)
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
        if adapter.name == "mail.chatgpt.org.uk":
            gptmail_email = await self._extract_gptmail_email(page)
            if gptmail_email:
                return gptmail_email
        if adapter.name == "mailticking.com":
            mailticking_email = await self._extract_mailticking_email(page)
            if mailticking_email:
                return mailticking_email
        if adapter.name == "mail.tm":
            mailtm_email = await self._extract_mailtm_email(page)
            if mailtm_email:
                return mailtm_email
        if adapter.name == "internxt":
            internxt_email = await self._extract_internxt_email(page)
            if internxt_email:
                return internxt_email
        if adapter.name == "tempmail.plus":
            tempmail_plus_email = await self._extract_tempmail_plus_email(page)
            if tempmail_plus_email:
                return tempmail_plus_email

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

    async def capture_verification_context(self, page: Page | None) -> str | None:
        if page is None:
            return "context_capture_page_missing"

        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        try:
            title = await page.title()
        except Exception:
            title = ""

        try:
            body_text = await page.evaluate("() => document.body?.innerText || ''")
            body_preview = re.sub(r"\s+", " ", body_text).strip()[:160]
        except Exception:
            body_preview = ""

        context_parts: list[str] = []
        if current_url:
            context_parts.append(f"url={current_url}")
        if title:
            context_parts.append(f"title={title}")
        if body_preview:
            context_parts.append(f"body={body_preview}")

        if self.provider_name == "10minutemail.net":
            # ================================
            # 10minutemail.net 的验证码失败需要区分“还在邮箱列表”还是“已打开邮件正文”
            # 目的: 下次报告能直接判断是收件箱没刷新出来，还是点开邮件后正文不含验证码
            # 边界: 只做只读探测，不触发额外网络请求
            # ================================
            try:
                if await page.locator("#maillist").count():
                    context_parts.append("mailbox_table=visible")
            except Exception:
                pass

            try:
                mail_rows = await page.locator("#maillist a.row-link").count()
                if mail_rows:
                    context_parts.append(f"mail_rows={mail_rows}")
            except Exception:
                pass

            try:
                if await page.locator("a.row-link:has-text('Dreamina')").count():
                    context_parts.append("dreamina_mail=visible")
            except Exception:
                pass

            if "readmail.html" in current_url:
                context_parts.append("mail_preview=open")
            else:
                context_parts.append("mail_preview=closed")

        if not context_parts:
            try:
                if page.is_closed():
                    return "context_capture_page_closed"
            except Exception:
                pass
            return "context_capture_empty"
        return " | ".join(context_parts)

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

    async def _extract_gptmail_email(self, page: Page) -> str | None:
        # ================================
        # GPTMail 会把邮箱同时写进 URL / 标题 / 页面展示节点
        # 目的: 多通道提取真实邮箱，降低单一 selector 漂移风险
        # 边界: 只提取首个合法邮箱，不对营销文本做额外猜测
        # ================================
        candidate_sources = [page.url or ""]

        try:
            candidate_sources.append(await page.title())
        except Exception:
            pass

        for selector in ("#emailDisplay", ".email-address", "#modalTo"):
            try:
                node = page.locator(selector).first
                if await node.count():
                    candidate_sources.append((await node.inner_text()).strip())
            except Exception:
                continue

        for candidate_source in candidate_sources:
            match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", candidate_source)
            if match and self._is_valid_email(match.group(0)):
                return match.group(0)

        return None

    async def _extract_mailticking_email(self, page: Page) -> str | None:
        # ================================
        # MailTicking 会把真实邮箱写在 active-mail 输入框和复制属性里
        # 目的: 优先读取收件箱主输入框，避免把登录弹窗里的邮箱输入框误判成临时邮箱
        # 边界: 只依赖收件箱主区域和复制属性，不扫描营销说明文本
        # ================================
        candidate_selectors = (
            ("#active-mail", "value"),
            ("#active-mail", "data-clipboard-text"),
            ("input#active-mail", "value"),
            ("[data-clipboard-text*='@']", "data-clipboard-text"),
        )

        for selector, attribute_name in candidate_selectors:
            try:
                node = page.locator(selector).first
                if not await node.count():
                    continue

                if attribute_name == "value":
                    candidate = (await node.input_value()).strip()
                else:
                    candidate = (await node.get_attribute(attribute_name) or "").strip()

                if self._is_valid_email(candidate):
                    return candidate
            except Exception:
                continue

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
            "button",
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

        body_text = await self._get_body_text(page)
        return self._extract_email_from_multiline_text(body_text)

    async def _extract_mailtm_email(self, page: Page) -> str | None:
        # ================================
        # mail.tm 当前真实邮箱可能挂在 value / clipboard / 短文本节点里
        # 目的: 先按站点结构抓取，再退回整页短行文本扫描
        # 边界: 仅在 mail.tm 适配器内扩展，不污染其他站点邮箱提取口径
        # ================================
        selector_attribute_pairs = (
            ("input[readonly]", "value"),
            ("input[value*='@']", "value"),
            ("[data-clipboard-text*='@']", "data-clipboard-text"),
            ("[title*='@']", "title"),
            ("[aria-label*='@']", "aria-label"),
        )

        for selector, attribute_name in selector_attribute_pairs:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    attribute_value = (await element.get_attribute(attribute_name) or "").strip()
                    if self._is_valid_email(attribute_value):
                        return attribute_value
            except Exception:
                continue

        text_selectors = (
            "#address",
            ".email",
            ".address",
            "button",
            "span",
            "p",
            "div",
        )
        for selector in text_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for element in elements:
                    text = re.sub(r"\s+", " ", (await element.inner_text()).strip())
                    if not text or len(text) > 120:
                        continue
                    if self._is_valid_email(text):
                        return text
            except Exception:
                continue

        body_text = await self._get_body_text(page)
        return self._extract_email_from_multiline_text(body_text)

    async def _extract_tempmail_plus_email(self, page: Page) -> str | None:
        # ================================
        # TempMail.Plus 当前把邮箱拆成“用户名输入框 + 域名文本”
        # 目的: 直接按站点真实结构拼接邮箱，避免把说明文案误判成邮箱
        # 边界: 仅依赖 #pre_button 与 #domain，不对其他文本块做模糊猜测
        # ================================
        try:
            prefix_node = page.locator("#pre_button").first
            domain_node = page.locator("#domain").first
            if not await prefix_node.count() or not await domain_node.count():
                return None

            prefix = (await prefix_node.input_value()).strip()
            domain = (await domain_node.inner_text()).strip()
            candidate = f"{prefix}{domain}".strip()
            if self._is_valid_email(candidate):
                return candidate
        except Exception:
            pass

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

    async def _collect_gptmail_verification_text(self, page: Page) -> str:
        text_parts: list[str] = []

        try:
            text_parts.append(await page.evaluate("() => document.body.innerText"))
        except Exception:
            pass

        for selector in ("#modalSubject", "#modalFrom", "#modalTo"):
            try:
                node = page.locator(selector).first
                if await node.count():
                    text_parts.append((await node.inner_text()).strip())
            except Exception:
                continue

        try:
            iframe_body = await page.frame_locator("#emailFrame").locator("body").inner_text(timeout=3000)
            if iframe_body:
                text_parts.append(iframe_body.strip())
        except Exception:
            pass

        return "\n".join(part for part in text_parts if part)

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
            if self.provider_name == "mail.tm":
                await self._wait_for_mailtm_email_ready(page, adapter)
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
            verification_attempts = VERIFICATION_WAIT_ATTEMPTS
            if adapter.name == "internxt":
                verification_attempts += 10
            if adapter.name == "mail.chatgpt.org.uk":
                verification_attempts += 4
            if adapter.name == "10minutemail.net":
                verification_attempts += 4
            for attempt in range(verification_attempts):
                await asyncio.sleep(3)
                try:
                    if attempt == 0 or attempt % EMAIL_LIGHT_REFRESH_INTERVAL == 0:
                        await self._light_refresh_email_page(email_page, adapter)

                    if adapter.name == "internxt":
                        await self._open_internxt_mail_preview(email_page)
                    elif adapter.name == "mailticking.com" and attempt >= 1:
                        await self._open_mailticking_mail_preview(email_page)
                    elif adapter.name == "mail.chatgpt.org.uk" and attempt >= 1:
                        await self._open_gptmail_mail_preview(email_page)
                    elif adapter.name == "10minutemail.net" and attempt >= 1:
                        await self._open_10minutemail_mail_preview(email_page)

                    page_text = await email_page.evaluate("() => document.body.innerText")
                    if adapter.name == "mail.chatgpt.org.uk":
                        page_text = await self._collect_gptmail_verification_text(email_page)
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

                    if attempt > 0 and attempt % EMAIL_HARD_RELOAD_INTERVAL == 0:
                        logger.info(f"[线程{self.thread_id}] 轻刷新未命中，执行整页刷新以获取新邮件...")
                        await email_page.reload(wait_until="domcontentloaded")
                except Exception as exc:
                    logger.debug(f"[线程{self.thread_id}] 提取验证码过程报错: {exc}")

            logger.error(f"[线程{self.thread_id}] 超时仍未在页面上匹配到验证码")
            await self.save_screenshot(email_page, "06_code_timeout")
            return None
        except Exception as exc:
            logger.error(f"[线程{self.thread_id}] 获取验证码函数异常: {exc}")
            return None
