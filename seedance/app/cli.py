from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from seedance.core.config import (
    DEFAULT_MAX_WORKERS,
    DEFAULT_TOTAL_COUNT,
    TEMP_EMAIL_PROVIDERS,
    WATERMARK_MAX_FREE_SECONDS,
)
from seedance.core.logger import get_logger
from seedance.core.models import WatermarkRunOptions
from seedance.orchestration.batch_runner import main as run_batch
from seedance.orchestration.home_check_runner import run_home_check
from seedance.orchestration.watermark_runner import run_watermark_batch

logger = get_logger()


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(argv if argv is not None else sys.argv[1:])
    if raw_args and raw_args[0] == "watermark":
        return _run_watermark_command(raw_args[1:])
    if raw_args and raw_args[0] == "home-check":
        return _run_home_check_command(raw_args[1:])
    return _run_registration_command(raw_args)


def _run_registration_command(argv: Sequence[str]) -> int:
    provider_names = ", ".join(provider["name"] for provider in TEMP_EMAIL_PROVIDERS)
    parser = argparse.ArgumentParser(
        description="即梦国际站自动注册脚本 - sd 国际站版 v6.8"
    )
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口")
    parser.add_argument("--headless", action="store_true", help="无头模式，不显示浏览器窗口（默认）")
    parser.add_argument("--debug", action="store_true", help="调试模式，保存截图")
    parser.add_argument("--count", type=int, default=DEFAULT_TOTAL_COUNT, help="总运行次数（默认999次）")
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="并发线程数（默认5个，范围1-5个）",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help=f"指定临时邮箱网站: {provider_names}",
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="关闭 Notion 同步，仅保留本地 txt 与运行报告",
    )
    args = parser.parse_args(list(argv))

    if args.email:
        valid_emails = [provider["name"] for provider in TEMP_EMAIL_PROVIDERS]
        if args.email not in valid_emails:
            raise SystemExit(f"错误: 无效的邮箱网站 '{args.email}'，有效选项: {', '.join(valid_emails)}")

    if args.show_browser:
        logger.info("=" * 60)
        logger.info("⚙️ 检测到 --show-browser 参数，将显示浏览器窗口")
        logger.info("=" * 60)

    run_batch(
        headless=not args.show_browser,
        debug_mode=args.debug,
        total_count=args.count,
        max_workers=args.threads,
        specified_email=args.email,
        notion_enabled=not args.no_notion,
    )
    return 0


def _run_watermark_command(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dreamina_register_playwright_usa.py watermark",
        description="Dreamina 固定右下角水印去除工具（magiceraser.org）",
    )
    parser.add_argument("input_dir", type=Path, help="待处理视频所在目录")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口，便于调试站点行为")
    args = parser.parse_args(list(argv))

    input_dir = args.input_dir.expanduser().resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"错误: 目录不存在或不是文件夹: {input_dir}")

    # ================================
    # CLI 明确暴露当前能力边界
    # 目的: 避免把固定坐标方案误当成通用去水印器
    # 边界: 这里只做提示，不替代 runner 内部的预检与报告
    # ================================
    logger.info("=" * 60)
    logger.info("去水印模式仅支持 Dreamina 视频右下角固定水印")
    logger.info(f"单视频时长必须 <= {WATERMARK_MAX_FREE_SECONDS} 秒")
    logger.info(f"输入目录: {input_dir}")
    logger.info("=" * 60)

    summary = run_watermark_batch(
        options=WatermarkRunOptions(
            input_dir=input_dir,
            headless=not args.show_browser,
        )
    )

    logger.info("=" * 60)
    logger.info(
        "去水印完成: 总数=%s 成功=%s 失败=%s 报告=%s 输出=%s",
        summary.total,
        summary.success_count,
        summary.fail_count,
        summary.report_path,
        summary.output_dir,
    )
    if summary.abort_reason:
        logger.error("批次中止原因: %s", summary.abort_reason)
    logger.info("=" * 60)

    return 1 if summary.aborted or summary.fail_count > 0 else 0


def _run_home_check_command(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="dreamina_register_playwright_usa.py home-check",
        description="Dreamina 首页稳定性自检工具",
    )
    parser.add_argument("--attempts", type=int, default=10, help="连续检测次数（默认10次）")
    parser.add_argument("--concurrency", type=int, default=5, help="首页并发检测数（默认5）")
    parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口，便于观察页面状态")
    parser.add_argument("--timeout", type=int, default=15, help="单次等待主页 ready 的秒数（默认15秒）")
    parser.add_argument("--pause", type=int, default=2, help="每次检测间隔秒数（默认2秒）")
    args = parser.parse_args(list(argv))

    summary = run_home_check(
        attempts=args.attempts,
        concurrency=args.concurrency,
        headless=not args.show_browser,
        timeout_seconds=args.timeout,
        pause_seconds=args.pause,
    )

    return 0 if summary.success_count == summary.attempts else 1
