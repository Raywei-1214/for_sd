import asyncio
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from seedance.core.config import DREAMINA_HOME_URL, HOME_READY_SELECTORS, REPORT_DIR
from seedance.core.logger import get_logger
from seedance.infra.browser_detector import find_chrome_browser
from seedance.infra.browser_factory import create_browser_context

logger = get_logger()


@dataclass(frozen=True)
class HomeCheckAttempt:
    index: int
    success: bool
    duration_seconds: float
    url: str
    title: str
    ready_selector: str | None
    body_preview: str
    error_message: str | None = None


@dataclass(frozen=True)
class HomeCheckSummary:
    attempts: int
    concurrency: int
    success_count: int
    fail_count: int
    success_rate: float
    started_at: str
    finished_at: str
    duration_seconds: float
    report_path: Path


async def _capture_page_context(page) -> tuple[str, str, str]:
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
        body_preview = re.sub(r"\s+", " ", body_text).strip()[:220]
    except Exception:
        body_preview = ""

    return current_url, title, body_preview


async def _find_ready_selector(page) -> str | None:
    for selector in HOME_READY_SELECTORS:
        try:
            node = await page.query_selector(selector)
            if node and await node.is_visible():
                return selector
        except Exception:
            continue
    return None


async def _run_single_home_check(
    index: int,
    chrome_path: str | None,
    headless: bool,
    timeout_seconds: int,
) -> HomeCheckAttempt:
    started = time.time()
    current_url = ""
    title = ""
    body_preview = ""

    try:
        async with async_playwright() as playwright:
            browser, context = await create_browser_context(
                playwright=playwright,
                chrome_path=chrome_path,
                headless=headless,
            )
            try:
                page = await context.new_page()
                await page.goto(
                    DREAMINA_HOME_URL,
                    timeout=timeout_seconds * 1000,
                    wait_until="domcontentloaded",
                )

                ready_selector = None
                for _ in range(timeout_seconds):
                    ready_selector = await _find_ready_selector(page)
                    if ready_selector:
                        current_url, title, body_preview = await _capture_page_context(page)
                        return HomeCheckAttempt(
                            index=index,
                            success=True,
                            duration_seconds=round(time.time() - started, 2),
                            url=current_url,
                            title=title,
                            ready_selector=ready_selector,
                            body_preview=body_preview,
                        )
                    await asyncio.sleep(1)

                current_url, title, body_preview = await _capture_page_context(page)
                return HomeCheckAttempt(
                    index=index,
                    success=False,
                    duration_seconds=round(time.time() - started, 2),
                    url=current_url,
                    title=title,
                    ready_selector=None,
                    body_preview=body_preview,
                    error_message="主页已打开但未进入可操作状态",
                )
            finally:
                await context.close()
                await browser.close()
    except PlaywrightTimeoutError:
        return HomeCheckAttempt(
            index=index,
            success=False,
            duration_seconds=round(time.time() - started, 2),
            url=current_url,
            title=title,
            ready_selector=None,
            body_preview=body_preview,
            error_message="页面访问超时",
        )
    except Exception as exc:
        return HomeCheckAttempt(
            index=index,
            success=False,
            duration_seconds=round(time.time() - started, 2),
            url=current_url,
            title=title,
            ready_selector=None,
            body_preview=body_preview,
            error_message=str(exc),
        )


def run_home_check(
    attempts: int = 10,
    headless: bool = True,
    timeout_seconds: int = 15,
    pause_seconds: int = 2,
    concurrency: int = 5,
) -> HomeCheckSummary:
    # ================================
    # 首页自检只聚焦 open_home 这一个公共前置步骤
    # 目的: 快速判断当前节点对 Dreamina 首页是否稳定
    # 边界: 不进入注册、邮箱、验证码流程，不写账号结果
    # ================================
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    attempts = max(1, int(attempts))
    timeout_seconds = max(5, int(timeout_seconds))
    pause_seconds = max(0, int(pause_seconds))
    concurrency = max(1, min(int(concurrency), attempts))
    started_at = datetime.now()
    chrome_path = find_chrome_browser()
    results: list[HomeCheckAttempt] = []

    logger.info("=" * 60)
    logger.info("开始执行首页自检")
    logger.info("目标地址: %s", DREAMINA_HOME_URL)
    logger.info("检测次数: %s", attempts)
    logger.info("并发数: %s", concurrency)
    logger.info("单次超时: %s 秒", timeout_seconds)
    logger.info("浏览器模式: %s", "显示" if not headless else "隐藏")
    logger.info("本地浏览器: %s", chrome_path or "未找到，回退 Playwright Chromium")
    logger.info("=" * 60)

    async def _run_all_checks() -> list[HomeCheckAttempt]:
        # ================================
        # 首页自检要模拟“多线程一起开首页”的真实压力
        # 目的: 判断节点在并发场景下是否还能稳定把首页拉到 ready
        # 边界: 只测首页阶段，不进入注册、邮箱、验证码流程
        # ================================
        semaphore = asyncio.Semaphore(concurrency)
        collected_results: list[HomeCheckAttempt] = []

        async def _run_index(index: int) -> HomeCheckAttempt:
            async with semaphore:
                result = await _run_single_home_check(
                    index=index,
                    chrome_path=chrome_path,
                    headless=headless,
                    timeout_seconds=timeout_seconds,
                )

                if result.success:
                    logger.info(
                        "[首页自检 %s/%s] ✅ 成功，耗时 %ss，ready=%s",
                        index,
                        attempts,
                        result.duration_seconds,
                        result.ready_selector,
                    )
                else:
                    logger.warning(
                        "[首页自检 %s/%s] ❌ 失败，耗时 %ss，原因=%s，url=%s，title=%s",
                        index,
                        attempts,
                        result.duration_seconds,
                        result.error_message or "未记录失败原因",
                        result.url or "-",
                        result.title or "-",
                    )

                if pause_seconds:
                    await asyncio.sleep(pause_seconds)
                return result

        tasks = [asyncio.create_task(_run_index(index)) for index in range(1, attempts + 1)]
        for task in asyncio.as_completed(tasks):
            collected_results.append(await task)

        return sorted(collected_results, key=lambda item: item.index)

    results = asyncio.run(_run_all_checks())

    finished_at = datetime.now()
    success_count = sum(1 for item in results if item.success)
    fail_count = len(results) - success_count
    summary_payload = {
        "attempts": attempts,
        "concurrency": concurrency,
        "success_count": success_count,
        "fail_count": fail_count,
        "success_rate": round(success_count / attempts * 100, 1) if attempts else 0.0,
    }
    report_payload = {
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 2),
        "summary": summary_payload,
        "results": [asdict(item) for item in results],
    }
    report_name = f"home_check_{started_at.strftime('%Y%m%d_%H%M%S')}.json"
    report_path = REPORT_DIR / report_name
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("=" * 60)
    logger.info(
        "首页自检完成: 成功=%s 失败=%s 成功率=%s%% 报告=%s",
        success_count,
        fail_count,
        summary_payload["success_rate"],
        report_path,
    )
    logger.info("=" * 60)

    return HomeCheckSummary(
        attempts=attempts,
        concurrency=concurrency,
        success_count=success_count,
        fail_count=fail_count,
        success_rate=summary_payload["success_rate"],
        started_at=report_payload["started_at"],
        finished_at=report_payload["finished_at"],
        duration_seconds=report_payload["duration_seconds"],
        report_path=report_path,
    )
