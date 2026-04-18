import asyncio
import json
import random
import re
import time
import urllib.request
from collections import Counter
from datetime import datetime

from playwright.async_api import Page, async_playwright

from seedance.core.config import (
    CONFIRMATION_BODY_TEXT,
    CONFIRMATION_SETTLE_WAIT_SECONDS,
    CONFIRMATION_POLL_ATTEMPTS,
    CONFIRMATION_POLL_INTERVAL_SECONDS,
    CONTINUE_BUTTON_SELECTORS,
    CREATE_MENU_SELECTORS,
    CREDIT_SELECTORS,
    DAY_OPTION_TEMPLATE_SELECTORS,
    DAY_SELECT_SELECTORS,
    DREAMINA_HOME_URL,
    DREAMINA_VIDEO_URL,
    EMAIL_INPUT_SELECTORS,
    EMAIL_LOGIN_BUTTON_TEXT,
    EMAIL_LOGIN_TRIGGER_SELECTOR,
    FORM_SETTLE_WAIT_SECONDS,
    IP_COUNTRY_URL,
    LOGIN_RELATED_URL_SEGMENTS,
    MONTH_OPTION_TEMPLATE_SELECTORS,
    MONTH_SELECT_SELECTORS,
    NEXT_BUTTON_SELECTORS,
    OPEN_HOME_READY_WAIT_SECONDS,
    PAGE_READY_WAIT_SECONDS,
    PROFILE_READY_WAIT_SECONDS,
    POPUP_CLOSE_SELECTORS,
    PROBE_BALANCE_SELECTORS,
    PROBE_GENERATE_BUTTON_SELECTORS,
    PROBE_BLOCKED_TEXT_MARKERS,
    PROBE_BLOCKED_URL_MARKERS,
    PROBE_MODEL_DROPDOWN_SELECTOR,
    PROBE_MODEL_DROPDOWN_TEXT,
    PROBE_MODEL_OPTION_SELECTOR,
    PROBE_MODEL_OPTION_TEXT,
    PROBE_NAVIGATION_RETRY_COUNT,
    PROBE_READY_WAIT_ATTEMPTS,
    PROBE_READY_WAIT_SECONDS,
    PROBE_REQUIRED_URL_MARKERS,
    PROBE_RETRY_COUNT,
    PROBE_SHALLOW_SHELL_WAIT_SECONDS,
    PROBE_SOFT_BLOCKED_SHELL_WAIT_SECONDS,
    PROBE_START_CREATING_SELECTORS,
    PROBE_VIDEO_ENTRY_SELECTORS,
    PROBE_WORKSPACE_ENTRY_WAIT_SECONDS,
    REGISTRATION_RESULT_POLL_ATTEMPTS,
    REGISTRATION_RESULT_POLL_INTERVAL_SECONDS,
    SCREENSHOT_DIR,
    SESSIONID_AUTH_COOKIE_MARKERS,
    SESSIONID_AUTH_STORAGE_MARKERS,
    SESSIONID_LATE_RETRY_PROVIDERS,
    SESSIONID_LATE_RETRY_SECONDS,
    SIGNUP_FORM_READY_SELECTORS,
    SIGN_UP_TRIGGER_SELECTOR,
    SIGN_UP_TRIGGER_TEXT,
    STEP_RETRY_COUNT,
    SUBMIT_CLICK_RETRY_COUNT,
    SUBMIT_TRANSITION_WAIT_ATTEMPTS,
    SUCCESS_READY_SELECTORS,
    SUCCESS_READY_TEXT_MARKERS,
    YEAR_INPUT_SELECTORS,
    PASSWORD_INPUT_SELECTORS,
    HOME_READY_SELECTORS,
    HOME_READY_TEXT_MARKERS,
    CONFIRMATION_READY_SELECTORS,
    CONFIRMATION_READY_TEXT_MARKERS,
    PROFILE_READY_SELECTORS,
    PROFILE_READY_TEXT_MARKERS,
)
from seedance.core.logger import get_logger
from seedance.core.models import RegistrationResult, RegistrationStep
from seedance.infra.browser_factory import create_browser_context
from seedance.services.email_service import TempEmailService

logger = get_logger()


class NetworkStatsCollector:
    def __init__(self) -> None:
        self.request_count = 0
        self.response_count = 0
        self.failed_request_count = 0
        self.transferred_bytes = 0
        self.request_type_counts: Counter[str] = Counter()

    def attach(self, context) -> None:
        context.on("request", self._handle_request)
        context.on("requestfailed", self._handle_request_failed)
        context.on("response", lambda response: asyncio.create_task(self._handle_response(response)))

    def _handle_request(self, request) -> None:
        resource_type = request.resource_type or "unknown"
        self.request_count += 1
        self.request_type_counts[resource_type] += 1

    def _handle_request_failed(self, _request) -> None:
        self.failed_request_count += 1

    async def _handle_response(self, response) -> None:
        self.response_count += 1
        try:
            header_value = await response.header_value("content-length")
            if header_value and header_value.isdigit():
                self.transferred_bytes += int(header_value)
        except Exception:
            return

    def apply_to_result(self, result: RegistrationResult) -> None:
        result.request_count = self.request_count
        result.response_count = self.response_count
        result.failed_request_count = self.failed_request_count
        result.transferred_bytes = self.transferred_bytes
        result.request_type_counts = dict(self.request_type_counts)


def get_ip_country() -> str:
    try:
        request = urllib.request.Request(
            IP_COUNTRY_URL,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            country = data.get("country", "")
            if country:
                logger.info(f"当前IP国家: {country}")
            return country
    except Exception as exc:
        logger.warning(f"获取IP国家失败: {exc}")
        return ""


class RegistrationService:
    def __init__(
        self,
        thread_id: int,
        headless: bool,
        debug_mode: bool,
        chrome_path: str | None,
        specified_email: str | None = None,
    ):
        self.thread_id = thread_id
        self.headless = headless
        self.debug_mode = debug_mode
        self.chrome_path = chrome_path
        self.specified_email = specified_email
        self.temp_email_service = TempEmailService(
            thread_id=thread_id,
            specified_email=specified_email,
            save_screenshot=self.save_screenshot,
        )

        if self.debug_mode:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    def _mark_step(self, result: RegistrationResult, step: RegistrationStep) -> None:
        result.current_step = step.value
        logger.info(f"[线程{self.thread_id}] 当前步骤: {step.value}")

    def _fail_step(
        self,
        result: RegistrationResult,
        step: RegistrationStep,
        error_message: str,
        failure_context: str | None = None,
    ) -> RegistrationResult:
        self._sync_temp_email_snapshot(result)
        result.failed_step = step.value
        result.error_message = error_message
        result.failure_context = failure_context
        logger.error(f"[线程{self.thread_id}] 步骤失败 {step.value}: {error_message}")
        if failure_context:
            logger.error(f"[线程{self.thread_id}] 失败上下文 {step.value}: {failure_context}")
        return result

    def _sync_temp_email_snapshot(self, result: RegistrationResult) -> None:
        # ================================
        # 失败结果需要尽量带上邮箱侧快照
        # 目的: 避免验证码失败时报告里 email/provider 仍是空，影响后续排查
        # 边界: 仅回填已经拿到的邮箱、密码、站点，不覆盖后续真实采集到的账号字段
        # ================================
        if self.temp_email_service.temp_email and not result.email:
            result.email = self.temp_email_service.temp_email
        if self.temp_email_service.password and not result.password:
            result.password = self.temp_email_service.password
        if self.temp_email_service.provider_name and not result.provider_name:
            result.provider_name = self.temp_email_service.provider_name

    async def _capture_page_context(self, page: Page | None) -> str | None:
        if page is None:
            return None

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

        context_parts = []
        if current_url:
            context_parts.append(f"url={current_url}")
        if title:
            context_parts.append(f"title={title}")
        if body_preview:
            context_parts.append(f"body={body_preview}")
        if not context_parts:
            return None
        return " | ".join(context_parts)

    def _compact_text(self, text: str | None, limit: int = 80) -> str:
        if not text:
            return ""
        compact = re.sub(r"\s+", " ", text).strip()
        return compact[:limit]

    async def _capture_storage_context(self, page: Page | None) -> str | None:
        if page is None:
            return None

        try:
            local_storage_keys = await page.evaluate(
                "() => Object.keys(window.localStorage || {}).slice(0, 10)"
            )
        except Exception:
            local_storage_keys = []

        try:
            session_storage_keys = await page.evaluate(
                "() => Object.keys(window.sessionStorage || {}).slice(0, 10)"
            )
        except Exception:
            session_storage_keys = []

        context_parts = []
        if local_storage_keys:
            context_parts.append(f"local_storage_keys={','.join(local_storage_keys)}")
        if session_storage_keys:
            context_parts.append(f"session_storage_keys={','.join(session_storage_keys)}")
        if not context_parts:
            return None
        return " | ".join(context_parts)

    def _format_cookie_snapshot(self, cookies: list[dict] | None) -> str:
        if not cookies:
            return "cookie_count=0 | cookie_names=<empty>"

        cookie_names = []
        for cookie in cookies[:12]:
            name = cookie.get("name") or "<unknown>"
            domain = cookie.get("domain") or "<no-domain>"
            cookie_names.append(f"{name}@{domain}")

        return f"cookie_count={len(cookies)} | cookie_names={','.join(cookie_names)}"

    def _format_probe_context(
        self,
        page_context: str | None,
        seedance_credits: str | None,
        seedance2_cost: str | None,
        navigation_attempt: int,
        model_dropdown_found: bool,
        model_fast_selected: bool,
        balance_samples: list[str],
        generate_button_samples: list[str],
    ) -> str:
        parts = []
        if page_context:
            parts.append(page_context)
        parts.append(f"probe_navigation_attempt={navigation_attempt}")
        parts.append(f"seedance_credits={seedance_credits or '<empty>'}")
        parts.append(f"seedance2_cost={seedance2_cost or '<empty>'}")
        parts.append(f"model_dropdown_found={'yes' if model_dropdown_found else 'no'}")
        parts.append(f"model_fast_selected={'yes' if model_fast_selected else 'no'}")
        parts.append(
            f"balance_samples={'; '.join(balance_samples[:3]) if balance_samples else '<empty>'}"
        )
        parts.append(
            "generate_button_samples="
            f"{'; '.join(generate_button_samples[:3]) if generate_button_samples else '<empty>'}"
        )
        return " | ".join(parts)

    def _is_probe_context_blocked(self, page_context: str | None) -> bool:
        return self._is_probe_context_soft_blocked(page_context) or self._is_probe_context_hard_blocked(
            page_context
        )

    def _is_probe_context_soft_blocked(self, page_context: str | None) -> bool:
        if not page_context:
            return False

        context_text = page_context.lower()
        return any(marker in context_text for marker in PROBE_BLOCKED_TEXT_MARKERS)

    def _is_probe_context_hard_blocked(self, page_context: str | None) -> bool:
        if not page_context:
            return False

        context_text = page_context.lower()
        return any(marker in context_text for marker in PROBE_BLOCKED_URL_MARKERS)

    def _is_video_probe_context(self, page_context: str | None) -> bool:
        if not page_context:
            return False

        context_text = page_context.lower()
        return all(marker in context_text for marker in PROBE_REQUIRED_URL_MARKERS)

    def _has_numeric_probe_signal(
        self,
        seedance_credits: str | None,
        seedance2_cost: str | None,
    ) -> bool:
        return bool(seedance_credits is not None or seedance2_cost is not None)

    def _needs_probe_workspace_nudge(
        self,
        page_context: str | None,
        model_dropdown_found: bool,
        generate_button_samples: list[str] | None,
        has_numeric_signal: bool,
    ) -> bool:
        if has_numeric_signal or model_dropdown_found or generate_button_samples:
            return False

        if not page_context:
            return True

        context_text = page_context.lower()
        return "explore create assets" in context_text or "start creating with ai agent" in context_text

    def _is_probe_context_shallow_shell(self, page_context: str | None) -> bool:
        if not page_context:
            return False

        context_text = page_context.lower()
        if "body=explore create assets" not in context_text:
            return False

        rich_workspace_markers = (
            "canvas 0 upgrade",
            "ai image",
            "ai video",
            "reference upload",
            "upload up to 12 references",
            "describe your video",
            "mimic motion",
        )
        return not any(marker in context_text for marker in rich_workspace_markers)

    def _is_probe_context_soft_shell(self, page_context: str | None) -> bool:
        if not page_context:
            return False

        context_text = page_context.lower()
        if not self._is_probe_context_soft_blocked(page_context):
            return False

        rich_workspace_markers = (
            "canvas 0 upgrade",
            "ai image",
            "ai video",
            "reference upload",
            "upload up to 12 references",
            "describe your video",
            "mimic motion",
        )
        return not any(marker in context_text for marker in rich_workspace_markers)

    async def _has_probe_workspace_ready_signal(self, page: Page) -> bool:
        if await self._has_visible_selector(page, PROBE_BALANCE_SELECTORS):
            return True

        if await self._has_visible_selector(page, PROBE_GENERATE_BUTTON_SELECTORS):
            return True

        try:
            dropdown_nodes = await page.query_selector_all(PROBE_MODEL_DROPDOWN_SELECTOR)
            for node in dropdown_nodes:
                text = await node.text_content()
                if PROBE_MODEL_DROPDOWN_TEXT in (text or "") and await node.is_visible():
                    return True
        except Exception:
            return False

        return False

    async def _wait_for_probe_workspace_ready(self, page: Page) -> bool:
        for _ in range(PROBE_READY_WAIT_ATTEMPTS):
            page_context = await self._capture_page_context(page)
            if self._is_probe_context_hard_blocked(page_context):
                return False
            if not self._is_video_probe_context(page_context):
                return False
            workspace_ready = await self._has_probe_workspace_ready_signal(page)
            soft_blocked = self._is_probe_context_soft_blocked(page_context)
            if workspace_ready and not soft_blocked:
                return True
            # ================================
            # Sign in 壳子属于“半 ready”状态
            # 目的: 先给前端一次短暂水合时间，再决定是否需要页面内引导
            # 边界: 这里只做同页等待，不增加额外导航
            # ================================
            if soft_blocked:
                await asyncio.sleep(PROBE_READY_WAIT_SECONDS)
                continue
            if not self._needs_probe_workspace_nudge(
                page_context=page_context,
                model_dropdown_found=False,
                generate_button_samples=[],
                has_numeric_signal=False,
            ):
                return False
            await asyncio.sleep(PROBE_READY_WAIT_SECONDS)
        return False

    async def _dismiss_probe_blockers(self, page: Page) -> None:
        # ================================
        # 探针页会被横幅/弹层/半登录态挡住
        # 目的: 进入真正可采集的工作区，而不是在首页壳子上误采 0 或空值
        # 边界: 这里只做轻量清场，不触发额外业务动作
        # ================================
        await self.close_popups(page, max_attempts=5)
        for _ in range(2):
            try:
                await page.keyboard.press("Escape")
            except Exception:
                break
            await asyncio.sleep(0.5)
        await self.close_popups(page, max_attempts=5)

    async def _enter_video_probe_workspace(self, page: Page) -> bool:
        # ================================
        # 只有 probe 落在首页壳子时，才执行一次轻量工作区引导
        # 目的: 尽量通过页面内点击进入视频工作区，避免反复 goto 增加流量
        # 边界: 这里只做 Start Creating / AI Video 两类入口点击，避免误入 agentic 工作区
        # ================================
        action_taken = False

        video_entry_clicked = await self._click_first_visible(
            page,
            PROBE_VIDEO_ENTRY_SELECTORS,
            timeout=3000,
        )
        if not video_entry_clicked:
            video_entry_clicked = await self._click_text_locator(page, "AI Video", timeout=3000)
        if video_entry_clicked:
            action_taken = True
            await asyncio.sleep(PROBE_WORKSPACE_ENTRY_WAIT_SECONDS)
            await self._dismiss_probe_blockers(page)

        start_creating_clicked = await self._click_first_visible(
            page,
            PROBE_START_CREATING_SELECTORS,
            timeout=3000,
        )
        if not start_creating_clicked:
            start_creating_clicked = await self._click_text_locator(
                page,
                "Start Creating",
                timeout=3000,
            )
        if start_creating_clicked:
            action_taken = True
            await asyncio.sleep(PROBE_WORKSPACE_ENTRY_WAIT_SECONDS)
            await self._dismiss_probe_blockers(page)

        return action_taken

    async def save_screenshot(self, page: Page, name: str) -> None:
        if not self.debug_mode:
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = SCREENSHOT_DIR / f"{timestamp}_{name}.png"
            await page.screenshot(path=str(filename))
            logger.info(f"截图已保存: {filename}")
        except Exception as exc:
            logger.warning(f"保存截图失败: {exc}")

    async def _query_first(self, page: Page, selectors: tuple[str, ...]):
        for selector in selectors:
            try:
                node = await page.query_selector(selector)
                if node:
                    return node
            except Exception:
                continue
        return None

    async def _click_first_visible(
        self,
        page: Page,
        selectors: tuple[str, ...],
        timeout: int = 10000,
        require_enabled: bool = False,
    ) -> bool:
        for selector in selectors:
            try:
                node = await page.query_selector(selector)
                if not node or not await node.is_visible():
                    continue
                if require_enabled and not await self._is_node_enabled(node):
                    continue
                await node.click(timeout=timeout)
                return True
            except Exception:
                continue
        return False

    async def _is_node_enabled(self, node) -> bool:
        try:
            if await node.get_attribute("disabled") is not None:
                return False
            aria_disabled = await node.get_attribute("aria-disabled")
            if (aria_disabled or "").strip().lower() in {"true", "1"}:
                return False
            aria_busy = await node.get_attribute("aria-busy")
            if (aria_busy or "").strip().lower() in {"true", "1"}:
                return False
            data_state = (await node.get_attribute("data-state") or "").strip().lower()
            if data_state in {"disabled", "loading", "submitting", "pending"}:
                return False
            class_name = (await node.get_attribute("class") or "").strip().lower()
            if any(
                marker in class_name
                for marker in ("disabled", "loading", "submitting", "pending")
            ):
                return False
            return True
        except Exception:
            return False

    async def _is_signup_continue_candidate(self, node) -> bool:
        try:
            return bool(
                await node.evaluate(
                    """
                    (el) => {
                        const container = el.closest(
                            "form, [role='dialog'], div[class*='modal'], div[class*='popup'], div[class*='drawer'], div[class*='panel']"
                        );
                        if (!container) {
                            return false;
                        }
                        const hasEmail = !!container.querySelector(
                            "input[type='email'], input[placeholder='Enter email'], input[autocomplete='email']"
                        );
                        const hasPassword = !!container.querySelector(
                            "input[type='password'], input[placeholder='Enter password'], input[placeholder='Password']"
                        );
                        return hasEmail && hasPassword;
                    }
                    """
                )
            )
        except Exception:
            return False

    async def _click_signup_continue(self, page: Page, timeout: int = 10000) -> bool:
        for selector in CONTINUE_BUTTON_SELECTORS:
            try:
                candidates = await page.query_selector_all(selector)
            except Exception:
                continue

            for node in candidates:
                try:
                    if not await node.is_visible():
                        continue
                    if not await self._is_node_enabled(node):
                        continue
                    if await self._is_signup_continue_candidate(node):
                        await node.click(timeout=timeout)
                        return True
                except Exception:
                    continue

        return False

    async def _has_signup_ready_continue(self, page: Page) -> bool:
        # ================================
        # Continue 不是可见就算 ready
        # 目的: 只有注册表单内、且真正可提交的 Continue 才允许进入点击阶段
        # 边界: 不再退回全页 fallback，避免误点首页壳子里的同名按钮
        # ================================
        for selector in CONTINUE_BUTTON_SELECTORS:
            try:
                candidates = await page.query_selector_all(selector)
            except Exception:
                continue

            for node in candidates:
                try:
                    if not await node.is_visible():
                        continue
                    if not await self._is_node_enabled(node):
                        continue
                    if await self._is_signup_continue_candidate(node):
                        return True
                except Exception:
                    continue

        return False

    async def _settle_signup_form_submission(self, page: Page, password_input) -> None:
        # ================================
        # 前端注册表单会在失焦后才完成校验态切换
        # 目的: 填完密码后显式触发一次失焦，并等待 Continue 进入可提交态
        # 边界: 这里只做表单状态收敛，不负责真正提交
        # ================================
        try:
            await password_input.press("Tab")
        except Exception:
            pass

        try:
            await password_input.evaluate("(el) => el.blur()")
        except Exception:
            pass

        for _ in range(max(FORM_SETTLE_WAIT_SECONDS + 1, 2)):
            if await self._has_signup_ready_continue(page):
                return
            await asyncio.sleep(1)

    async def _click_button_by_text(
        self,
        page: Page,
        container_selector: str,
        expected_text: str,
        timeout: int = 10000,
    ) -> bool:
        try:
            candidates = await page.query_selector_all(container_selector)
            for node in candidates:
                text = await node.inner_text() or ""
                if expected_text in text:
                    await node.click(timeout=timeout)
                    return True
        except Exception:
            return False
        return False

    async def _click_text_locator(
        self,
        page: Page,
        expected_text: str,
        timeout: int = 3000,
    ) -> bool:
        try:
            locator = page.get_by_text(expected_text, exact=False).first
            await locator.click(timeout=timeout)
            return True
        except Exception:
            return False

    async def _wait_for_body_text(
        self,
        page: Page,
        expected_text: str,
        attempts: int,
        interval_seconds: int,
    ) -> bool:
        for _ in range(attempts):
            await asyncio.sleep(interval_seconds)
            try:
                page_text = await page.evaluate("() => document.body.innerText")
                if expected_text in page_text.lower():
                    return True
            except Exception:
                continue
        return False

    async def _wait_for_submit_transition(self, page: Page) -> bool:
        for _ in range(SUBMIT_TRANSITION_WAIT_ATTEMPTS):
            post_submit_state = await self._wait_for_post_submit_state(page)
            if post_submit_state in {"confirmation", "profile"}:
                return True

            signup_form_visible = await self._has_visible_selector(page, SIGNUP_FORM_READY_SELECTORS)
            continue_button_visible = await self._has_visible_selector(page, CONTINUE_BUTTON_SELECTORS)
            if not signup_form_visible or not continue_button_visible:
                return True

        return False

    async def _settle_confirmation_submission(self, page: Page) -> None:
        # ================================
        # 验证码输入后，前端可能要等失焦或提交事件才会进入资料页
        # 目的: 显式触发一次验证码表单收敛，避免卡在 confirmation_input=visible
        # 边界: 只在验证码页停留时执行一次，不额外追加外网请求
        # ================================
        try:
            await page.keyboard.press("Tab")
        except Exception:
            pass

        try:
            await page.keyboard.press("Enter")
        except Exception:
            pass

        for _ in range(CONFIRMATION_SETTLE_WAIT_SECONDS):
            if await self._has_visible_selector(page, PROFILE_READY_SELECTORS):
                return
            if await self._has_text_marker(page, PROFILE_READY_TEXT_MARKERS):
                return
            if not await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
                return
            await asyncio.sleep(1)

    async def _nudge_confirmation_to_profile(self, page: Page) -> bool:
        # ================================
        # 资料页失败里最常见的是验证码页未真正提交
        # 目的: 仅在确认页仍可见时，补一次窄范围推进
        # 边界: 只负责“确认页 -> 资料页”收敛，不承担注册完成或成功页判定
        # ================================
        if not await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
            return False

        await self._settle_confirmation_submission(page)
        return True

    async def _has_visible_selector(self, page: Page, selectors: tuple[str, ...]) -> bool:
        for selector in selectors:
            try:
                node = await page.query_selector(selector)
                if node and await node.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _has_text_marker(self, page: Page, text_markers: tuple[str, ...]) -> bool:
        if not text_markers:
            return False

        try:
            page_text = (await page.evaluate("() => document.body.innerText")).lower()
        except Exception:
            return False

        return any(marker.lower() in page_text for marker in text_markers)

    async def _wait_for_page_state(
        self,
        page: Page,
        selectors: tuple[str, ...] = (),
        text_markers: tuple[str, ...] = (),
        attempts: int = 5,
        interval_seconds: int = 1,
        url_excludes: tuple[str, ...] = (),
    ) -> bool:
        for _ in range(attempts):
            current_url = page.url.lower()
            if url_excludes and any(segment in current_url for segment in url_excludes):
                await asyncio.sleep(interval_seconds)
                continue

            if selectors and await self._has_visible_selector(page, selectors):
                return True

            if text_markers and await self._has_text_marker(page, text_markers):
                return True

            await asyncio.sleep(interval_seconds)

        return False

    async def close_popups(self, page: Page, max_attempts: int = 3) -> bool:
        try:
            for _ in range(max_attempts):
                close_button_found = False
                for selector in POPUP_CLOSE_SELECTORS:
                    try:
                        close_button = await page.query_selector(selector)
                        if close_button and await close_button.is_visible():
                            await close_button.click(timeout=3000)
                            close_button_found = True
                            await asyncio.sleep(1)
                            break
                    except Exception:
                        continue

                if not close_button_found:
                    return True
            return True
        except Exception:
            return True

    async def get_credits(self, page: Page) -> str | None:
        try:
            for selector in CREDIT_SELECTORS:
                try:
                    credit_element = await page.wait_for_selector(
                        selector,
                        timeout=5000,
                        state="visible",
                    )
                    if credit_element:
                        credit_text = await credit_element.text_content()
                        numbers = re.findall(r"\d+", credit_text or "")
                        if numbers:
                            logger.info(f"✓✓✓ 成功获取积分: {numbers[0]}")
                            return numbers[0]
                except Exception:
                    continue
            return None
        except Exception:
            return None

    async def get_sessionid(self, context, page: Page | None = None) -> tuple[str | None, str]:
        try:
            last_snapshot = "cookie_count=0 | cookie_names=<empty>"
            last_cookies: list[dict] = []
            # ================================
            # sessionid 只做短轮询，不默认拉长异常样本耗时
            # 目的: 尽量等到刚落地的 cookie，同时避免把失败样本拖慢太多
            # 边界: 只轮询 2 次，未命中后立即落诊断信息
            # ================================
            for attempt, wait_seconds in enumerate((0.0, 0.8), start=1):
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                cookies = await context.cookies()
                last_cookies = cookies or []
                last_snapshot = self._format_cookie_snapshot(cookies)
                for cookie in cookies or []:
                    if cookie["name"].lower() == "sessionid":
                        logger.info(f"✓✓✓ 成功获取sessionid: {cookie['value']}")
                        return cookie["value"], f"sessionid_found_attempt={attempt} | {last_snapshot}"

            page_context = await self._capture_page_context(page)
            storage_context = await self._capture_storage_context(page)
            provider_name = self._get_current_provider_name()
            auth_marker_snapshot = self._format_session_auth_markers(
                cookies=last_cookies,
                storage_context=storage_context,
            )

            # ================================
            # mail.tm / internxt 偶发晚到登录态 cookie
            # 目的: 只对已确认存在登录态线索的 provider 追加一次窄范围重查
            # 边界: 不放宽准入规则，也不对所有站点默认拉长等待
            # ================================
            if self._should_run_late_sessionid_retry(
                provider_name=provider_name,
                cookies=last_cookies,
                page_context=page_context,
                storage_context=storage_context,
            ):
                await asyncio.sleep(SESSIONID_LATE_RETRY_SECONDS)
                cookies = await context.cookies()
                last_cookies = cookies or []
                last_snapshot = self._format_cookie_snapshot(cookies)
                auth_marker_snapshot = self._format_session_auth_markers(
                    cookies=last_cookies,
                    storage_context=storage_context,
                )
                for cookie in cookies or []:
                    if cookie["name"].lower() == "sessionid":
                        logger.info(f"✓✓✓ 成功获取晚到 sessionid: {cookie['value']}")
                        return (
                            cookie["value"],
                            f"sessionid_found_attempt=late | provider_name={provider_name or '<empty>'} | {last_snapshot} | {auth_marker_snapshot}",
                        )

            context_parts = [
                "sessionid_found_attempt=0",
                f"provider_name={provider_name or '<empty>'}",
                last_snapshot,
                auth_marker_snapshot,
            ]
            if page_context:
                context_parts.append(page_context)
            if storage_context:
                context_parts.append(storage_context)
            context_text = " | ".join(context_parts)
            logger.warning(f"[线程{self.thread_id}] 未采到 sessionid: {context_text}")
            return None, context_text
        except Exception:
            return None, "sessionid_capture_error"

    def _get_current_provider_name(self) -> str:
        temp_email_service = getattr(self, "temp_email_service", None)
        provider_name = getattr(temp_email_service, "provider_name", None)
        return str(provider_name or "").strip().lower()

    def _format_session_auth_markers(
        self,
        cookies: list[dict] | None,
        storage_context: str | None,
    ) -> str:
        cookie_markers = []
        cookie_name_set = {
            str(cookie.get("name", "")).lower()
            for cookie in (cookies or [])
            if cookie.get("name")
        }
        for marker in SESSIONID_AUTH_COOKIE_MARKERS:
            if marker in cookie_name_set:
                cookie_markers.append(marker)

        storage_markers = []
        lowered_storage_context = (storage_context or "").lower()
        for marker in SESSIONID_AUTH_STORAGE_MARKERS:
            if marker in lowered_storage_context:
                storage_markers.append(marker)

        cookie_part = ",".join(cookie_markers) if cookie_markers else "<empty>"
        storage_part = ",".join(storage_markers) if storage_markers else "<empty>"
        return f"auth_cookie_markers={cookie_part} | auth_storage_markers={storage_part}"

    def _should_run_late_sessionid_retry(
        self,
        provider_name: str,
        cookies: list[dict] | None,
        page_context: str | None,
        storage_context: str | None,
    ) -> bool:
        if provider_name not in SESSIONID_LATE_RETRY_PROVIDERS:
            return False

        auth_marker_snapshot = self._format_session_auth_markers(
            cookies=cookies,
            storage_context=storage_context,
        )
        if "auth_cookie_markers=<empty>" not in auth_marker_snapshot:
            return True

        lowered_page_context = (page_context or "").lower()
        lowered_storage_context = (storage_context or "").lower()
        if not self._is_video_probe_context(page_context):
            return False
        return "mstok" in lowered_storage_context or "device_id" in lowered_storage_context or "start creating" in lowered_page_context

    async def _fill_birth_date(self, page: Page) -> tuple[int, str, int]:
        year = random.randint(1990, 2000)
        month_num = random.randint(1, 12)
        month_name = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }[month_num]
        max_day = 28 if month_num == 2 else (30 if month_num in [4, 6, 9, 11] else 31)
        day = random.randint(1, max_day)

        try:
            year_input = await self._query_first(page, YEAR_INPUT_SELECTORS)
            if year_input:
                await year_input.fill(str(year))
        except Exception:
            pass
        await asyncio.sleep(1)

        try:
            month_select = await self._query_first(page, MONTH_SELECT_SELECTORS)
            if month_select:
                await month_select.click(force=True)
                await asyncio.sleep(1)
                month_option = await self._query_first(
                    page,
                    tuple(
                        selector.format(value=month_name)
                        for selector in MONTH_OPTION_TEMPLATE_SELECTORS
                    ),
                )
                if month_option:
                    await month_option.click(force=True)
        except Exception:
            pass
        await asyncio.sleep(1)

        try:
            day_select = await self._query_first(page, DAY_SELECT_SELECTORS)
            if day_select:
                await day_select.click(force=True)
                await asyncio.sleep(1)
                day_option = await self._query_first(
                    page,
                    tuple(
                        selector.format(value=day)
                        for selector in DAY_OPTION_TEMPLATE_SELECTORS
                    ),
                )
                if day_option:
                    await day_option.click(force=True)
        except Exception:
            pass
        await asyncio.sleep(2)
        return year, month_name, day

    async def _collect_probe_snapshot(
        self,
        page: Page,
        navigation_attempt: int,
        balance_samples: list[str],
        generate_button_samples: list[str],
    ) -> dict[str, object]:
        workspace_ready = await self._wait_for_probe_workspace_ready(page)
        current_seedance2_cost = None
        current_seedance_credits = None
        current_balance_samples: list[str] = []
        current_generate_button_samples: list[str] = []
        current_model_dropdown_found = False
        current_model_fast_selected = False

        # ================================
        # 工作区未 ready 时禁止继续抓取伪信号
        # 目的: 避免把首页壳子的 cost=0 / dropdown 当成真实积分依据
        # 边界: 这里只返回空采样，让外层决定是否引导或重试
        # ================================
        if not workspace_ready:
            page_context = await self._capture_page_context(page)
            probe_context = self._format_probe_context(
                page_context=page_context,
                seedance_credits=current_seedance_credits,
                seedance2_cost=current_seedance2_cost,
                navigation_attempt=navigation_attempt,
                model_dropdown_found=current_model_dropdown_found,
                model_fast_selected=current_model_fast_selected,
                balance_samples=current_balance_samples,
                generate_button_samples=current_generate_button_samples,
            )
            return {
                "seedance2_cost": current_seedance2_cost,
                "seedance_credits": current_seedance_credits,
                "model_dropdown_found": current_model_dropdown_found,
                "model_fast_selected": current_model_fast_selected,
                "generate_button_samples": current_generate_button_samples,
                "probe_context": probe_context,
                "page_context": page_context,
            }

        for _ in range(PROBE_RETRY_COUNT):
            try:
                for selector in PROBE_BALANCE_SELECTORS:
                    credit_elements = await page.query_selector_all(selector)
                    for element in credit_elements:
                        text = await element.text_content()
                        compact_text = self._compact_text(text)
                        if compact_text and compact_text not in current_balance_samples:
                            current_balance_samples.append(compact_text)
                        if compact_text and compact_text not in balance_samples:
                            balance_samples.append(compact_text)
                        if text and text.strip().isdigit():
                            current_seedance_credits = text.strip()
                            break
                    if current_seedance_credits:
                        break
                if current_seedance_credits:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        try:
            all_select_nodes = await page.query_selector_all(PROBE_MODEL_DROPDOWN_SELECTOR)
            dreamina_dropdown = None
            for select_node in all_select_nodes:
                text = await select_node.text_content()
                if PROBE_MODEL_DROPDOWN_TEXT in (text or ""):
                    dreamina_dropdown = select_node
                    current_model_dropdown_found = True
                    break

            if dreamina_dropdown:
                await dreamina_dropdown.click(timeout=5000)
                await asyncio.sleep(2)
                options = await page.query_selector_all(PROBE_MODEL_OPTION_SELECTOR)
                for option in options:
                    option_text = await option.text_content()
                    if PROBE_MODEL_OPTION_TEXT in (option_text or ""):
                        await option.scroll_into_view_if_needed()
                        await option.click(force=True)
                        current_model_fast_selected = True
                        logger.info(f"[线程{self.thread_id}] ✓ 成功选中 2.0 Fast 模型")
                        await asyncio.sleep(2)
                        break
        except Exception:
            pass

        for _ in range(PROBE_RETRY_COUNT):
            try:
                for selector in PROBE_GENERATE_BUTTON_SELECTORS:
                    buttons = await page.query_selector_all(selector)
                    for button in buttons:
                        text = await button.text_content()
                        compact_text = self._compact_text(text)
                        if compact_text and compact_text not in current_generate_button_samples:
                            current_generate_button_samples.append(compact_text)
                        if compact_text and compact_text not in generate_button_samples:
                            generate_button_samples.append(compact_text)
                        numbers = re.findall(r"\d+", text or "")
                        if numbers:
                            current_seedance2_cost = numbers[0]
                            break
                    if current_seedance2_cost:
                        break
                if current_seedance2_cost:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        page_context = await self._capture_page_context(page)
        probe_context = self._format_probe_context(
            page_context=page_context,
            seedance_credits=current_seedance_credits,
            seedance2_cost=current_seedance2_cost,
            navigation_attempt=navigation_attempt,
            model_dropdown_found=current_model_dropdown_found,
            model_fast_selected=current_model_fast_selected,
            balance_samples=current_balance_samples,
            generate_button_samples=current_generate_button_samples,
        )
        return {
            "seedance2_cost": current_seedance2_cost,
            "seedance_credits": current_seedance_credits,
            "model_dropdown_found": current_model_dropdown_found,
            "model_fast_selected": current_model_fast_selected,
            "generate_button_samples": current_generate_button_samples,
            "probe_context": probe_context,
            "page_context": page_context,
        }

    async def _probe_account_state(self, page: Page) -> tuple[str | None, str | None, str]:
        seedance2_cost = None
        seedance_credits = None
        balance_samples: list[str] = []
        generate_button_samples: list[str] = []
        model_dropdown_found = False
        model_fast_selected = False
        final_probe_context = ""

        for navigation_attempt in range(1, PROBE_NAVIGATION_RETRY_COUNT + 1):
            await page.goto(DREAMINA_VIDEO_URL, timeout=60000)
            await asyncio.sleep(5)
            await self._dismiss_probe_blockers(page)
            initial_page_context = await self._capture_page_context(page)
            if self._is_probe_context_blocked(initial_page_context):
                workspace_action_taken = await self._enter_video_probe_workspace(page)
                if workspace_action_taken:
                    logger.info(
                        f"[线程{self.thread_id}] 探针页命中首页壳子，已执行视频工作区引导"
                    )

            # ================================
            # 探针页必须先进入“真工作区”，否则读取到的 0 或空值都不可信
            # 触发条件: body 仍停在 Sign in / AI Agent Auto / 1080P banner 等首页壳子
            # 边界: 每次导航内最多追加一次页面内引导，不额外放大外网请求
            # ================================
            probe_snapshot = await self._collect_probe_snapshot(
                page=page,
                navigation_attempt=navigation_attempt,
                balance_samples=balance_samples,
                generate_button_samples=generate_button_samples,
            )
            probe_context = str(probe_snapshot["probe_context"])
            page_context = probe_snapshot["page_context"]
            current_seedance2_cost = probe_snapshot["seedance2_cost"]
            current_seedance_credits = probe_snapshot["seedance_credits"]
            current_model_dropdown_found = bool(probe_snapshot["model_dropdown_found"])
            current_model_fast_selected = bool(probe_snapshot["model_fast_selected"])
            current_generate_button_samples = list(probe_snapshot["generate_button_samples"])

            probe_context_blocked = self._is_probe_context_blocked(page_context)
            probe_has_numeric_signal = self._has_numeric_probe_signal(
                current_seedance_credits,
                current_seedance2_cost,
            )
            probe_is_video_context = self._is_video_probe_context(page_context)
            probe_needs_workspace_nudge = self._needs_probe_workspace_nudge(
                page_context=page_context,
                model_dropdown_found=current_model_dropdown_found,
                generate_button_samples=current_generate_button_samples,
                has_numeric_signal=probe_has_numeric_signal,
            )
            if probe_context_blocked or probe_needs_workspace_nudge:
                workspace_action_taken = await self._enter_video_probe_workspace(page)
                if workspace_action_taken:
                    logger.info(
                        f"[线程{self.thread_id}] 探针采样后工作区未 ready，追加一次工作区引导"
                    )
                    probe_snapshot = await self._collect_probe_snapshot(
                        page=page,
                        navigation_attempt=navigation_attempt,
                        balance_samples=balance_samples,
                        generate_button_samples=generate_button_samples,
                    )
                    probe_context = str(probe_snapshot["probe_context"])
                    page_context = probe_snapshot["page_context"]
                    current_seedance2_cost = probe_snapshot["seedance2_cost"]
                    current_seedance_credits = probe_snapshot["seedance_credits"]
                    current_model_dropdown_found = bool(probe_snapshot["model_dropdown_found"])
                    current_model_fast_selected = bool(probe_snapshot["model_fast_selected"])
                    current_generate_button_samples = list(probe_snapshot["generate_button_samples"])
                    probe_context_blocked = self._is_probe_context_blocked(page_context)
                    probe_has_numeric_signal = self._has_numeric_probe_signal(
                        current_seedance_credits,
                        current_seedance2_cost,
                    )
                    probe_is_video_context = self._is_video_probe_context(page_context)

            # ================================
            # Explore Create Assets 浅壳有时比普通半 ready 更慢
            # 目的: 对“视频页已对齐但工作区组件未水合”的样本补一次同页复采
            # 边界: 不新增 goto，只做一次清场、短等和重新采样
            # ================================
            if (
                probe_is_video_context
                and not probe_context_blocked
                and not probe_has_numeric_signal
                and self._is_probe_context_shallow_shell(page_context)
            ):
                await self._dismiss_probe_blockers(page)
                await asyncio.sleep(PROBE_SHALLOW_SHELL_WAIT_SECONDS)
                probe_snapshot = await self._collect_probe_snapshot(
                    page=page,
                    navigation_attempt=navigation_attempt,
                    balance_samples=balance_samples,
                    generate_button_samples=generate_button_samples,
                )
                probe_context = str(probe_snapshot["probe_context"])
                page_context = probe_snapshot["page_context"]
                current_seedance2_cost = probe_snapshot["seedance2_cost"]
                current_seedance_credits = probe_snapshot["seedance_credits"]
                current_model_dropdown_found = bool(probe_snapshot["model_dropdown_found"])
                current_model_fast_selected = bool(probe_snapshot["model_fast_selected"])
                current_generate_button_samples = list(probe_snapshot["generate_button_samples"])
                probe_context_blocked = self._is_probe_context_blocked(page_context)
                probe_has_numeric_signal = self._has_numeric_probe_signal(
                    current_seedance_credits,
                    current_seedance2_cost,
                )
                probe_is_video_context = self._is_video_probe_context(page_context)

            # ================================
            # AI Agent Auto Trends / prompt guide 属于软阻塞壳子
            # 目的: 对“视频页已对齐但仍被软阻塞文案覆盖”的样本补一次同页收敛
            # 边界: 只做清场、短等、复采，不新增 goto
            # ================================
            if (
                probe_is_video_context
                and probe_context_blocked
                and not probe_has_numeric_signal
                and self._is_probe_context_soft_shell(page_context)
            ):
                await self._dismiss_probe_blockers(page)
                await asyncio.sleep(PROBE_SOFT_BLOCKED_SHELL_WAIT_SECONDS)
                probe_snapshot = await self._collect_probe_snapshot(
                    page=page,
                    navigation_attempt=navigation_attempt,
                    balance_samples=balance_samples,
                    generate_button_samples=generate_button_samples,
                )
                probe_context = str(probe_snapshot["probe_context"])
                page_context = probe_snapshot["page_context"]
                current_seedance2_cost = probe_snapshot["seedance2_cost"]
                current_seedance_credits = probe_snapshot["seedance_credits"]
                current_model_dropdown_found = bool(probe_snapshot["model_dropdown_found"])
                current_model_fast_selected = bool(probe_snapshot["model_fast_selected"])
                current_generate_button_samples = list(probe_snapshot["generate_button_samples"])
                probe_context_blocked = self._is_probe_context_blocked(page_context)
                probe_has_numeric_signal = self._has_numeric_probe_signal(
                    current_seedance_credits,
                    current_seedance2_cost,
                )
                probe_is_video_context = self._is_video_probe_context(page_context)

            final_probe_context = probe_context
            if probe_has_numeric_signal and not probe_context_blocked and probe_is_video_context:
                seedance2_cost = current_seedance2_cost
                seedance_credits = current_seedance_credits
                model_dropdown_found = current_model_dropdown_found
                model_fast_selected = current_model_fast_selected
                break

            logger.warning(f"[线程{self.thread_id}] 探针页未稳定进入工作区，准备重试: {probe_context}")

        final_probe_context = self._format_probe_context(
            page_context=await self._capture_page_context(page),
            seedance_credits=seedance_credits,
            seedance2_cost=seedance2_cost,
            navigation_attempt=navigation_attempt,
            model_dropdown_found=model_dropdown_found,
            model_fast_selected=model_fast_selected,
            balance_samples=balance_samples,
            generate_button_samples=generate_button_samples,
        ) if not final_probe_context else final_probe_context
        if seedance2_cost is None:
            logger.warning(f"[线程{self.thread_id}] 未采到 seedance2_cost: {final_probe_context}")

        return seedance2_cost, seedance_credits, final_probe_context

    async def _open_home_page(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.OPEN_HOME)

        # ================================
        # 页面进入是所有后续动作的前置条件
        # 这里只做“是否成功进入主页”的职责
        # ================================
        for _ in range(STEP_RETRY_COUNT):
            try:
                await page.goto(DREAMINA_HOME_URL, timeout=60000)
                home_ready = await self._wait_for_page_state(
                    page,
                    selectors=HOME_READY_SELECTORS,
                    text_markers=HOME_READY_TEXT_MARKERS,
                    attempts=OPEN_HOME_READY_WAIT_SECONDS,
                    interval_seconds=1,
                )
                if home_ready:
                    return True
            except Exception:
                await asyncio.sleep(5)

        await self.save_screenshot(page, "error_open_home")
        failure_context = await self._capture_page_context(page)
        self._fail_step(
            result,
            RegistrationStep.OPEN_HOME,
            "主页加载失败",
            failure_context=failure_context,
        )
        return False

    async def _open_signup_flow(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.OPEN_SIGNUP)

        create_clicked = await self._click_first_visible(page, CREATE_MENU_SELECTORS)
        if not create_clicked:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "Create 菜单不可点击")
            return False

        create_flow_ready = await self._wait_for_page_state(
            page,
            selectors=(EMAIL_LOGIN_TRIGGER_SELECTOR,),
            attempts=PAGE_READY_WAIT_SECONDS,
            interval_seconds=1,
        )
        if not create_flow_ready:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "邮箱登录入口未出现")
            return False

        email_login_clicked = await self._click_button_by_text(
            page,
            EMAIL_LOGIN_TRIGGER_SELECTOR,
            EMAIL_LOGIN_BUTTON_TEXT,
        )
        if not email_login_clicked:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "Continue with email 不可点击")
            return False

        sign_up_ready = await self._wait_for_page_state(
            page,
            selectors=(SIGN_UP_TRIGGER_SELECTOR,),
            attempts=PAGE_READY_WAIT_SECONDS,
            interval_seconds=1,
        )
        if not sign_up_ready:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "Sign up 入口未出现")
            return False

        sign_up_clicked = await self._click_button_by_text(
            page,
            SIGN_UP_TRIGGER_SELECTOR,
            SIGN_UP_TRIGGER_TEXT,
        )
        if not sign_up_clicked:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "Sign up 不可点击")
            return False

        signup_form_ready = await self._wait_for_page_state(
            page,
            selectors=SIGNUP_FORM_READY_SELECTORS,
            attempts=PAGE_READY_WAIT_SECONDS,
            interval_seconds=1,
        )
        if not signup_form_ready:
            self._fail_step(result, RegistrationStep.OPEN_SIGNUP, "注册表单未出现")
            return False

        return True

    async def _acquire_temp_email(
        self,
        context,
        result: RegistrationResult,
    ) -> tuple[Page | None, bool]:
        self._mark_step(result, RegistrationStep.ACQUIRE_TEMP_EMAIL)
        email_page, email_ready = await self.temp_email_service.acquire_email(context)
        if not email_ready:
            failure_context = await self._capture_page_context(email_page)
            self._fail_step(
                result,
                RegistrationStep.ACQUIRE_TEMP_EMAIL,
                "临时邮箱获取失败",
                failure_context=failure_context,
            )
        return email_page, email_ready

    async def _fill_credentials(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.FILL_CREDENTIALS)
        email_input = await self._query_first(page, EMAIL_INPUT_SELECTORS)
        if not email_input:
            self._fail_step(result, RegistrationStep.FILL_CREDENTIALS, "邮箱输入框不存在")
            return False
        await email_input.fill(self.temp_email_service.temp_email or "")

        password_input = await self._query_first(page, PASSWORD_INPUT_SELECTORS)
        if not password_input:
            self._fail_step(result, RegistrationStep.FILL_CREDENTIALS, "密码输入框不存在")
            return False
        await password_input.fill(self.temp_email_service.password or "")
        await self._settle_signup_form_submission(page, password_input)
        return True

    async def _submit_credentials(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.SUBMIT_CREDENTIALS)
        for attempt in range(1, SUBMIT_CLICK_RETRY_COUNT + 1):
            clicked = await self._click_signup_continue(page)
            if not clicked:
                self._fail_step(result, RegistrationStep.SUBMIT_CREDENTIALS, "Continue 按钮不可点击")
                return False

            if await self._wait_for_submit_transition(page):
                return True

            logger.warning(
                f"[线程{self.thread_id}] Continue 点击后页面未迁移，准备重试提交 attempt={attempt}"
            )

        failure_context = await self._capture_confirmation_context(page)
        self._fail_step(
            result,
            RegistrationStep.SUBMIT_CREDENTIALS,
            "Continue 提交后页面未发生状态迁移",
            failure_context=failure_context,
        )
        return False

    async def _wait_confirmation(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.WAIT_CONFIRMATION)
        post_submit_state = await self._wait_for_post_submit_state(page)
        if post_submit_state == "confirmation":
            return True

        if post_submit_state == "profile":
            logger.info(f"[线程{self.thread_id}] 提交邮箱密码后直接进入资料页，跳过验证码输入")
            return True

        await self.save_screenshot(page, "error_wait_confirmation")
        failure_context = await self._capture_confirmation_context(page)
        self._fail_step(
            result,
            RegistrationStep.WAIT_CONFIRMATION,
            "未进入验证码确认页面",
            failure_context=failure_context,
        )
        return False

    # ================================
    # TempMail.Plus 当前存在验证码后直接回首页的特殊状态机
    # 目的: 把这轮修复严格显式绑定到单一 provider，避免影响其他稳定站点
    # 边界: 这里只做 provider 判定，不承载任何通用状态判断职责
    # ================================
    def _is_tempmail_plus_provider(self) -> bool:
        return self.temp_email_service.provider_name == "tempmail.plus"

    async def _is_tempmail_plus_home_shell(self, page: Page) -> bool:
        if not self._is_tempmail_plus_provider():
            return False

        current_url = (page.url or "").lower()
        if any(segment in current_url for segment in LOGIN_RELATED_URL_SEGMENTS):
            return False

        if await self._has_visible_selector(page, SUCCESS_READY_SELECTORS):
            return True
        if await self._has_text_marker(page, SUCCESS_READY_TEXT_MARKERS):
            return True
        return False

    async def _wait_for_tempmail_plus_login_ready(
        self,
        page: Page,
        attempts: int = 5,
        interval_seconds: int = 1,
    ) -> bool:
        # ================================
        # TempMail.Plus 的首页壳不等于注册已完成
        # 目的: 只有真正登录态 cookie 已落地时，才允许走 provider 专属首页成功旁路
        # 边界: 仅对 tempmail.plus 生效；其他站点不额外依赖 cookie 集合特征
        # ================================
        if not self._is_tempmail_plus_provider():
            return False

        for attempt in range(attempts):
            try:
                cookies = await page.context.cookies()
            except Exception:
                cookies = []

            cookie_names = {
                str(cookie.get("name", "")).lower()
                for cookie in cookies
                if cookie.get("name")
            }
            if (
                "sessionid" in cookie_names
                or "faceu-commerce-user-info" in cookie_names
                or len(cookies) >= 25
            ):
                return True

            if attempt < attempts - 1:
                await asyncio.sleep(interval_seconds)

        return False

    async def _is_tempmail_plus_home_state(self, page: Page) -> bool:
        if not await self._is_tempmail_plus_home_shell(page):
            return False
        return await self._wait_for_tempmail_plus_login_ready(page, attempts=3, interval_seconds=1)

    async def _wait_for_post_submit_state(self, page: Page) -> str | None:
        for _ in range(CONFIRMATION_POLL_ATTEMPTS):
            if await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
                return "confirmation"
            if await self._has_text_marker(
                page,
                CONFIRMATION_READY_TEXT_MARKERS + (CONFIRMATION_BODY_TEXT,),
            ):
                return "confirmation"

            if await self._has_visible_selector(page, PROFILE_READY_SELECTORS):
                return "profile"
            if await self._has_text_marker(page, PROFILE_READY_TEXT_MARKERS):
                return "profile"

            # ================================
            # TempMail.Plus 当前偶发“确认页元素残留，但主页面已切回首页壳”
            # 目的: 不把这种混合态误判成确认页超时，让后续继续走验证码链路
            # 边界: 仅对 tempmail.plus 生效，其他站点继续沿用原有状态机
            # ================================
            if await self._is_tempmail_plus_home_state(page):
                return "confirmation"

            await asyncio.sleep(CONFIRMATION_POLL_INTERVAL_SECONDS)

        return None

    async def _capture_confirmation_context(self, page: Page) -> str | None:
        base_context = await self._capture_page_context(page)
        extra_context: list[str] = []

        try:
            if await self._has_visible_selector(page, SIGNUP_FORM_READY_SELECTORS):
                extra_context.append("signup_form=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, CONTINUE_BUTTON_SELECTORS):
                extra_context.append("continue_button=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
                extra_context.append("confirmation_input=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, PROFILE_READY_SELECTORS):
                extra_context.append("profile_form=visible")
        except Exception:
            pass

        if base_context and extra_context:
            return f"{base_context} | {' | '.join(extra_context)}"
        if extra_context:
            return " | ".join(extra_context)
        if base_context:
            return base_context
        return "context_capture_empty"

    async def _capture_profile_context(self, page: Page) -> str | None:
        base_context = await self._capture_page_context(page)
        extra_context: list[str] = []

        try:
            if await self._has_visible_selector(page, SIGNUP_FORM_READY_SELECTORS):
                extra_context.append("signup_form=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, CONTINUE_BUTTON_SELECTORS):
                extra_context.append("continue_button=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
                extra_context.append("confirmation_input=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, PROFILE_READY_SELECTORS):
                extra_context.append("profile_form=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, YEAR_INPUT_SELECTORS):
                extra_context.append("year_input=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, MONTH_SELECT_SELECTORS):
                extra_context.append("month_select=visible")
        except Exception:
            pass

        try:
            if await self._has_visible_selector(page, DAY_SELECT_SELECTORS):
                extra_context.append("day_select=visible")
        except Exception:
            pass

        if base_context and extra_context:
            return f"{base_context} | {' | '.join(extra_context)}"
        if extra_context:
            return " | ".join(extra_context)
        if base_context:
            return base_context
        return "context_capture_empty"

    async def _wait_for_profile_state(self, page: Page) -> str | None:
        # ================================
        # 资料页不是所有时候都会在验证码输入后立刻稳定出现
        # 目的: 给“确认页 -> 资料页”的过渡留出更长窗口，并优先识别弱中间态
        # 边界: 只用于 fill_profile，不改变 open_home / wait_confirmation 节奏
        # ================================
        for _ in range(PROFILE_READY_WAIT_SECONDS):
            if await self._has_visible_selector(page, PROFILE_READY_SELECTORS):
                return "profile"
            if await self._has_text_marker(page, PROFILE_READY_TEXT_MARKERS):
                return "profile"

            # ================================
            # TempMail.Plus 验证码提交后，偶发直接回到已登录首页而不再出现生日资料页
            # 目的: 识别“资料页缺席但注册已完成”的分支，避免继续误判为 fill_profile 失败
            # 边界: 仅对 tempmail.plus 生效，且只在 fill_profile 阶段使用
            # ================================
            if await self._is_tempmail_plus_home_shell(page):
                if await self._wait_for_tempmail_plus_login_ready(
                    page,
                    attempts=3,
                    interval_seconds=1,
                ):
                    return "home"
                await asyncio.sleep(1)
                continue

            # 仍停留在验证码页时继续等待，不立即把它误判成资料页失败
            if await self._has_visible_selector(page, CONFIRMATION_READY_SELECTORS):
                await self._nudge_confirmation_to_profile(page)
                await asyncio.sleep(1)
                continue
            if await self._has_text_marker(
                page,
                CONFIRMATION_READY_TEXT_MARKERS + (CONFIRMATION_BODY_TEXT,),
            ):
                await asyncio.sleep(1)
                continue

            await asyncio.sleep(1)

        return None

    async def _fill_verification_code(
        self,
        page: Page,
        email_page: Page,
        result: RegistrationResult,
    ) -> bool:
        self._mark_step(result, RegistrationStep.FILL_VERIFICATION_CODE)
        verification_code = await self.temp_email_service.wait_verification_code(email_page)
        if not verification_code:
            # ================================
            # 验证码失败不仅要看主页面，也要看邮箱页当时停在哪
            # 目的: 下次能区分“邮件没刷新出来”还是“已打开邮件但正文无验证码”
            # 边界: 仅做页面采样，不引入新的外网请求
            # ================================
            failure_context = await self.temp_email_service.capture_verification_context(email_page)
            self._fail_step(
                result,
                RegistrationStep.FILL_VERIFICATION_CODE,
                "验证码获取失败",
                failure_context=failure_context or "context_capture_empty",
            )
            return False
        await page.keyboard.type(verification_code, delay=100)
        await self._settle_confirmation_submission(page)
        return True

    async def _complete_profile(
        self,
        page: Page,
        result: RegistrationResult,
    ) -> tuple[bool, tuple[int, str, int] | None, bool]:
        self._mark_step(result, RegistrationStep.FILL_PROFILE)
        profile_state = await self._wait_for_profile_state(page)
        if profile_state == "home":
            logger.info(
                f"[线程{self.thread_id}] TempMail.Plus 验证后已回到首页壳，跳过生日资料页"
            )
            return True, None, True

        if profile_state != "profile":
            await self.save_screenshot(page, "error_fill_profile")
            failure_context = await self._capture_profile_context(page)
            self._fail_step(
                result,
                RegistrationStep.FILL_PROFILE,
                "生日资料表单未出现",
                failure_context=failure_context,
            )
            return False, None, False
        birth_date = await self._fill_birth_date(page)
        return True, birth_date, False

    async def _complete_registration(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.COMPLETE_REGISTRATION)

        # ================================
        # TempMail.Plus 当前偶发“验证码后直接落到已登录首页”
        # 目的: 已处于成功态时直接放行，避免再去点击不存在的 Next 按钮
        # 边界: 仅对 tempmail.plus 生效，不改变其他站点的资料页提交流程
        # ================================
        if await self._is_tempmail_plus_home_shell(page):
            if await self._wait_for_tempmail_plus_login_ready(
                page,
                attempts=4,
                interval_seconds=1,
            ):
                logger.info(f"[线程{self.thread_id}] TempMail.Plus 已处于成功首页，跳过 Next 提交")
                return True

        clicked = await self._click_first_visible(
            page,
            NEXT_BUTTON_SELECTORS,
            require_enabled=True,
        )
        if not clicked:
            if self._is_tempmail_plus_provider() and await self._is_tempmail_plus_home_shell(page):
                failure_context = await self._capture_confirmation_context(page)
                self._fail_step(
                    result,
                    RegistrationStep.COMPLETE_REGISTRATION,
                    "TempMail.Plus 已回首页壳，但登录态 cookie 未落地",
                    failure_context=failure_context,
                )
                return False
            self._fail_step(result, RegistrationStep.COMPLETE_REGISTRATION, "Next 按钮不可点击")
            return False

        for _ in range(REGISTRATION_RESULT_POLL_ATTEMPTS):
            success_ready = await self._wait_for_page_state(
                page,
                selectors=SUCCESS_READY_SELECTORS,
                text_markers=SUCCESS_READY_TEXT_MARKERS,
                attempts=1,
                interval_seconds=REGISTRATION_RESULT_POLL_INTERVAL_SECONDS,
                url_excludes=LOGIN_RELATED_URL_SEGMENTS,
            )
            if success_ready:
                return True

        self._fail_step(result, RegistrationStep.COMPLETE_REGISTRATION, "页面仍停留在登录/注册态")
        return False

    async def _collect_account_data(self, page: Page, context, result: RegistrationResult) -> None:
        self._mark_step(result, RegistrationStep.COLLECT_ACCOUNT_DATA)
        await self.close_popups(page)
        credits = await self.get_credits(page)
        ip_country = get_ip_country()
        seedance2_cost, seedance_credits, probe_context = await self._probe_account_state(page)
        sessionid, sessionid_context = await self.get_sessionid(context, page)

        result.success = True
        result.sessionid = sessionid
        result.sessionid_context = sessionid_context
        result.country = ip_country
        result.seedance_value = seedance2_cost
        result.probe_context = probe_context
        result.credits = seedance2_cost or seedance_credits or credits

    def _log_result_summary(
        self,
        result: RegistrationResult,
        birth_date: tuple[int, str, int] | None,
    ) -> None:
        if result.success:
            logger.info("=" * 60)
            logger.info("✅✅✅ 注册成功！")
            logger.info(f"注册邮箱: {result.email}")
            logger.info(f"注册密码: {result.password}")
            if result.credits:
                logger.info(f"账号积分: {result.credits}积分")
            if result.sessionid:
                logger.info(f"Sessionid: Sessionid={result.sessionid}")
            if result.country:
                logger.info(f"IP国家: {result.country}")
            if result.seedance_value:
                logger.info(f"sd消耗数值: {result.seedance_value}")
            if birth_date:
                logger.info(f"出生日期: {birth_date[0]}-{birth_date[1]}-{birth_date[2]}")
            logger.info("=" * 60)
            return

        logger.info("=" * 60)
        logger.info("❌❌❌ 注册失败！")
        logger.info(f"失败邮箱: {result.email}")
        logger.info(f"测试密码: {result.password}")
        if result.failed_step:
            logger.info(f"失败步骤: {result.failed_step}")
        if result.error_message:
            logger.info(f"失败原因: {result.error_message}")
        if result.failure_context:
            logger.info(f"失败上下文: {result.failure_context}")
        logger.info("=" * 60)

    async def register(self) -> RegistrationResult:
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_time = time.time()

        logger.info(f"[线程{self.thread_id}] 开始时间: {started_at}")
        logger.info(f"[线程{self.thread_id}] ⭐ 国际站注册模式 ⭐")

        playwright = None
        browser = None
        context = None
        main_page = None
        email_page = None
        network_stats = NetworkStatsCollector()

        result = RegistrationResult(
            success=False,
            thread_id=self.thread_id,
            provider_name=self.specified_email,
            started_at=started_at,
        )

        try:
            playwright = await async_playwright().start()
            browser, context = await create_browser_context(
                playwright=playwright,
                chrome_path=self.chrome_path,
                headless=self.headless,
            )
            network_stats.attach(context)
            main_page = await context.new_page()

            # ================================
            # 这里改为显式步骤流，避免流程状态继续散落
            # 每一步都只回答一个问题：当前阶段是否完成
            # ================================
            if not await self._open_home_page(main_page, result):
                return result
            if not await self._open_signup_flow(main_page, result):
                return result

            email_page, email_ready = await self._acquire_temp_email(context, result)
            if not email_ready:
                return result
            self._sync_temp_email_snapshot(result)
            if not await self._fill_credentials(main_page, result):
                return result
            if not await self._submit_credentials(main_page, result):
                return result
            if not await self._wait_confirmation(main_page, result):
                return result
            profile_already_ready = await self._has_visible_selector(main_page, PROFILE_READY_SELECTORS) or await self._has_text_marker(main_page, PROFILE_READY_TEXT_MARKERS)
            if not profile_already_ready:
                if not await self._fill_verification_code(main_page, email_page, result):
                    return result
            profile_ready, birth_date, registration_already_complete = await self._complete_profile(
                main_page,
                result,
            )
            if not profile_ready:
                result.email = self.temp_email_service.temp_email
                result.password = self.temp_email_service.password
                self._log_result_summary(result, birth_date)
                return result
            if not registration_already_complete and not await self._complete_registration(main_page, result):
                result.email = self.temp_email_service.temp_email
                result.password = self.temp_email_service.password
                self._log_result_summary(result, birth_date)
                return result

            await self.save_screenshot(main_page, "10_final_page")

            result.email = self.temp_email_service.temp_email
            result.password = self.temp_email_service.password
            result.provider_name = self.temp_email_service.provider_name

            await self._collect_account_data(main_page, context, result)
            self._log_result_summary(result, birth_date)

            return result
        except Exception as exc:
            logger.error(f"[线程{self.thread_id}] 注册过程发生错误: {exc}", exc_info=True)
            result.error_message = str(exc)
            return result
        finally:
            network_stats.apply_to_result(result)
            finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            result.finished_at = finished_at
            result.duration_seconds = time.time() - start_time
            try:
                if browser:
                    await browser.close()
                    logger.info("浏览器已关闭")
                if playwright:
                    await playwright.stop()
            except Exception as exc:
                logger.error(f"关闭浏览器时出错: {exc}")
