import argparse

from seedance.core.config import DEFAULT_MAX_WORKERS, DEFAULT_TOTAL_COUNT, TEMP_EMAIL_PROVIDERS
from seedance.core.logger import get_logger
from seedance.orchestration.batch_runner import main as run_batch

logger = get_logger()


def main() -> None:
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
        help="指定临时邮箱网站: mail.tm, 10minutemail.net, internxt, mailpoof, tempmail.lol, crazymailing",
    )
    parser.add_argument(
        "--no-notion",
        action="store_true",
        help="关闭 Notion 同步，仅保留本地 txt 与运行报告",
    )
    args = parser.parse_args()

    if args.email:
        valid_emails = [provider["name"] for provider in TEMP_EMAIL_PROVIDERS]
        if args.email not in valid_emails:
            raise SystemExit(f"错误: 无效的邮箱网站 '{args.email}'，有效选项: {', '.join(valid_emails)}")

    headless = not args.show_browser
    if args.show_browser:
        logger.info("=" * 60)
        logger.info("⚙️ 检测到 --show-browser 参数，将显示浏览器窗口")
        logger.info("=" * 60)

    run_batch(
        headless=headless,
        debug_mode=args.debug,
        total_count=args.count,
        max_workers=args.threads,
        specified_email=args.email,
        notion_enabled=not args.no_notion,
    )
