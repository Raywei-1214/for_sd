import asyncio
import json
import random
import re
import time
import urllib.request
from datetime import datetime

from playwright.async_api import Page, async_playwright

from seedance.core.config import (
    CONFIRMATION_BODY_TEXT,
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
    OPEN_HOME_MAX_ATTEMPTS,
    PAGE_READY_WAIT_SECONDS,
    POPUP_CLOSE_SELECTORS,
    PROBE_BALANCE_SELECTORS,
    PROBE_GENERATE_BUTTON_SELECTORS,
    PROBE_MODEL_DROPDOWN_SELECTOR,
    PROBE_MODEL_DROPDOWN_TEXT,
    PROBE_MODEL_OPTION_SELECTOR,
    PROBE_MODEL_OPTION_TEXT,
    PROBE_RETRY_COUNT,
    REGISTRATION_RESULT_POLL_ATTEMPTS,
    REGISTRATION_RESULT_POLL_INTERVAL_SECONDS,
    SCREENSHOT_DIR,
    SIGNUP_FORM_READY_SELECTORS,
    SIGN_UP_TRIGGER_SELECTOR,
    SIGN_UP_TRIGGER_TEXT,
    STEP_RETRY_COUNT,
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
        result.failed_step = step.value
        result.error_message = error_message
        result.failure_context = failure_context
        logger.error(f"[线程{self.thread_id}] 步骤失败 {step.value}: {error_message}")
        if failure_context:
            logger.error(f"[线程{self.thread_id}] 失败上下文 {step.value}: {failure_context}")
        return result

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
                if require_enabled and await node.get_attribute("disabled"):
                    continue
                await node.click(timeout=timeout)
                return True
            except Exception:
                continue
        return False

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

    async def get_sessionid(self, context) -> str | None:
        try:
            cookies = await context.cookies()
            for cookie in cookies or []:
                if cookie["name"].lower() == "sessionid":
                    logger.info(f"✓✓✓ 成功获取sessionid: {cookie['value']}")
                    return cookie["value"]
            return None
        except Exception:
            return None

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

    async def _probe_account_state(self, page: Page) -> tuple[str | None, str | None]:
        seedance2_cost = None
        seedance_credits = None

        await page.goto(DREAMINA_VIDEO_URL, timeout=60000)
        await asyncio.sleep(5)
        await self.close_popups(page)

        # ================================
        # 这里仍是模糊探测，但选择器已统一收口到配置层
        # 下一阶段可以继续替换为站点能力探针
        # ================================
        for _ in range(PROBE_RETRY_COUNT):
            try:
                for selector in PROBE_BALANCE_SELECTORS:
                    credit_elements = await page.query_selector_all(selector)
                    for element in credit_elements:
                        text = await element.text_content()
                        if text and text.strip().isdigit():
                            seedance_credits = text.strip()
                            break
                    if seedance_credits:
                        break
                if seedance_credits:
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
                        numbers = re.findall(r"\d+", text or "")
                        if numbers:
                            seedance2_cost = numbers[0]
                            break
                    if seedance2_cost:
                        break
                if seedance2_cost:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        return seedance2_cost, seedance_credits

    async def _open_home_page(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.OPEN_HOME)

        # ================================
        # 页面进入是所有后续动作的前置条件
        # 这里只做“是否成功进入主页”的职责
        # ================================
        for attempt in range(OPEN_HOME_MAX_ATTEMPTS):
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
                if attempt < OPEN_HOME_MAX_ATTEMPTS - 1:
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
        await asyncio.sleep(max(FORM_SETTLE_WAIT_SECONDS - 1, 0))
        return True

    async def _submit_credentials(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.SUBMIT_CREDENTIALS)
        clicked = await self._click_first_visible(
            page,
            CONTINUE_BUTTON_SELECTORS,
            require_enabled=True,
        )
        if not clicked:
            self._fail_step(result, RegistrationStep.SUBMIT_CREDENTIALS, "Continue 按钮不可点击")
            return False
        return True

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
        return base_context

    async def _fill_verification_code(
        self,
        page: Page,
        email_page: Page,
        result: RegistrationResult,
    ) -> bool:
        self._mark_step(result, RegistrationStep.FILL_VERIFICATION_CODE)
        verification_code = await self.temp_email_service.wait_verification_code(email_page)
        if not verification_code:
            self._fail_step(result, RegistrationStep.FILL_VERIFICATION_CODE, "验证码获取失败")
            return False
        await page.keyboard.type(verification_code, delay=100)
        return True

    async def _complete_profile(
        self,
        page: Page,
        result: RegistrationResult,
    ) -> tuple[bool, tuple[int, str, int] | None]:
        self._mark_step(result, RegistrationStep.FILL_PROFILE)
        profile_ready = await self._wait_for_page_state(
            page,
            selectors=PROFILE_READY_SELECTORS,
            text_markers=PROFILE_READY_TEXT_MARKERS,
            attempts=max(PAGE_READY_WAIT_SECONDS * 2, 6),
            interval_seconds=1,
        )
        if not profile_ready:
            await self.save_screenshot(page, "error_fill_profile")
            failure_context = await self._capture_page_context(page)
            self._fail_step(
                result,
                RegistrationStep.FILL_PROFILE,
                "生日资料表单未出现",
                failure_context=failure_context,
            )
            return False, None
        birth_date = await self._fill_birth_date(page)
        return True, birth_date

    async def _complete_registration(self, page: Page, result: RegistrationResult) -> bool:
        self._mark_step(result, RegistrationStep.COMPLETE_REGISTRATION)
        clicked = await self._click_first_visible(
            page,
            NEXT_BUTTON_SELECTORS,
            require_enabled=True,
        )
        if not clicked:
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
        seedance2_cost, seedance_credits = await self._probe_account_state(page)
        sessionid = await self.get_sessionid(context)

        result.success = True
        result.sessionid = sessionid
        result.country = ip_country
        result.seedance_value = seedance2_cost
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
            profile_ready, birth_date = await self._complete_profile(main_page, result)
            if not profile_ready:
                result.email = self.temp_email_service.temp_email
                result.password = self.temp_email_service.password
                self._log_result_summary(result, birth_date)
                return result
            if not await self._complete_registration(main_page, result):
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
