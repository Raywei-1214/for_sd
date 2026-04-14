import asyncio
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

from seedance.core.config import DEFAULT_MAX_WORKERS, DEFAULT_TOTAL_COUNT, MAX_WORKERS, MIN_WORKERS, REPORT_DIR, SUCCESS_DIR, TEMP_MAIL_HEALTH_FILE, TEMP_EMAIL_PROVIDERS
from seedance.core.logger import get_logger
from seedance.core.models import BatchSummary, RegistrationResult, RuntimeOptions
from seedance.infra.account_store import AccountStore
from seedance.infra.browser_detector import find_chrome_browser, load_browser_config, save_browser_config
from seedance.infra.report_writer import RunReportWriter, build_failure_reason
from seedance.infra.temp_mail_health import TempMailHealthStore
logger = get_logger()


def run_single_registration(
    thread_id: int,
    runtime_options: RuntimeOptions,
    chrome_path: str | None,
    account_store: AccountStore,
    timestamp_filename: str,
    assigned_email_provider: str | None,
) -> RegistrationResult:
    try:
        logger.info(f"[线程{thread_id}] 开始注册")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _register() -> RegistrationResult:
            from seedance.services.registration_service import RegistrationService

            service = RegistrationService(
                thread_id=thread_id,
                headless=runtime_options.headless,
                debug_mode=runtime_options.debug_mode,
                chrome_path=chrome_path,
                specified_email=assigned_email_provider,
            )
            return await service.register()

        result = loop.run_until_complete(_register())
        loop.close()
        result.thread_id = thread_id

        if result.success:
            save_result = account_store.save_success(result, timestamp_filename=timestamp_filename)
            if not save_result.success:
                logger.error(f"[线程{thread_id}] 账号已注册成功，但 Notion 与本地备份均失败")
            elif not save_result.fully_synced:
                if save_result.notion_enabled and not save_result.notion_ok and not save_result.notion_skipped:
                    logger.warning(f"[线程{thread_id}] 账号已注册成功，Notion 写入失败，但本地 txt 已保留")
                if save_result.notion_skipped and not save_result.backup_ok:
                    logger.warning(f"[线程{thread_id}] 账号未满足 Notion 写入条件，且本地 txt 备份失败")
                elif not save_result.backup_ok:
                    logger.warning(f"[线程{thread_id}] 账号已注册成功，Notion 已写入，但本地 txt 备份失败")
        else:
            save_result = account_store.save_failure(result)
            if save_result.notion_enabled and not save_result.notion_ok and not save_result.notion_skipped:
                logger.warning(f"[线程{thread_id}] 注册失败结果未能写入 Notion")

        logger.info(f"[线程{thread_id}] {'✅ 注册成功' if result.success else '❌ 注册失败'}")
        return result
    except Exception as exc:
        logger.error(f"[线程{thread_id}] 执行出错: {exc}", exc_info=True)
        return RegistrationResult(
            success=False,
            thread_id=thread_id,
            failed_step="thread_runner",
            error_message=str(exc),
        )

def _log_failure_statistics(results: list[RegistrationResult]) -> None:
    failed_results = [result for result in results if not result.success]
    if not failed_results:
        return

    report_writer = RunReportWriter(REPORT_DIR)
    failure_counter = {}
    for result in failed_results:
        failure_reason = build_failure_reason(result)
        failure_counter[failure_reason] = failure_counter.get(failure_reason, 0) + 1

    logger.info("=" * 60)
    logger.info("失败分类统计")
    logger.info("=" * 60)
    for failure_reason, count in sorted(
        failure_counter.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        logger.info(f"{failure_reason}: {count} 个")

    logger.info("=" * 60)
    logger.info("失败任务明细")
    logger.info("=" * 60)

    # ================================
    # 这里输出逐任务失败明细，便于快速定位瓶颈步骤
    # ================================
    for result in failed_results:
        logger.info(
            "[线程%s] 步骤=%s 原因=%s 邮箱=%s 邮箱站点=%s",
            result.thread_id or "unknown",
            result.failed_step or result.current_step or "unknown_step",
            result.error_message or "未记录失败原因",
            result.email or "unknown",
            result.provider_name or "unknown",
        )


def _build_provider_plan(
    runtime_options: RuntimeOptions,
    total_count: int,
) -> list[str | None]:
    if runtime_options.specified_email:
        return [runtime_options.specified_email for _ in range(total_count)]

    provider_names = [provider["name"] for provider in TEMP_EMAIL_PROVIDERS]
    provider_plan = TempMailHealthStore(TEMP_MAIL_HEALTH_FILE).build_provider_plan(
        provider_names,
        total_count=total_count,
    )

    logger.info("本次邮箱站点调度: %s", ", ".join(provider_plan))
    return provider_plan


def _update_provider_health(results: list[RegistrationResult]) -> None:
    health_store = TempMailHealthStore(TEMP_MAIL_HEALTH_FILE)

    for result in results:
        if not result.provider_name:
            continue

        if result.success:
            health_store.record_provider_result(
                result.provider_name,
                success=True,
                hard_failure=False,
            )
            continue

        hard_failure = result.failed_step in {
            "acquire_temp_email",
            "fill_verification_code",
        }
        health_store.record_provider_result(
            result.provider_name,
            success=False,
            hard_failure=hard_failure,
        )


def _prompt_runtime_options(runtime_options: RuntimeOptions) -> RuntimeOptions:
    try:
        input_count = input(
            f"\n请输入需注册的账号总数 (直接回车默认 {runtime_options.total_count}): "
        ).strip()
        if input_count:
            runtime_options.total_count = int(input_count)

        input_threads = input(
            f"请输入并发执行的线程数 (直接回车默认 {runtime_options.max_workers}，建议1-5): "
        ).strip()
        if input_threads:
            runtime_options.max_workers = int(input_threads)
    except ValueError:
        print("输入无效，将使用默认值运行。")

    return runtime_options


def _sanitize_runtime_options(runtime_options: RuntimeOptions) -> RuntimeOptions:
    runtime_options.total_count = max(1, int(runtime_options.total_count))
    runtime_options.max_workers = max(
        MIN_WORKERS,
        min(MAX_WORKERS, int(runtime_options.max_workers)),
    )

    if runtime_options.notion_enabled is None:
        runtime_options.notion_enabled = True

    return runtime_options


def _select_email_provider() -> str | None:
    email_config = load_browser_config()
    saved_email_choice = email_config.get("email_choice")

    print("=" * 60)
    print("请选择要使用的临时邮箱网站：")
    print("=" * 60)

    for index, provider in enumerate(TEMP_EMAIL_PROVIDERS, start=1):
        print(f"  {index} - {provider['name']}")
    print(f"  {len(TEMP_EMAIL_PROVIDERS) + 1} - 随机")

    print("=" * 60)
    print("说明：")
    print("  - 选择 1-6 将固定使用该邮箱网站")
    print("  - 选择随机将按顺序轮流使用所有邮箱网站")
    print("  - 多线程时会自动分配不同的邮箱避免冲突")
    print("=" * 60)

    if saved_email_choice:
        print(f"上次选择的邮箱: {saved_email_choice}")
        print("=" * 60)

    while True:
        choice = input("\n请输入选项 (1/2/3/4/5/6/7，输入q退出): ").strip()

        if choice.lower() == "q":
            print("已退出程序")
            sys.exit(0)

        if choice.isdigit():
            choice_index = int(choice)
            if 1 <= choice_index <= len(TEMP_EMAIL_PROVIDERS):
                selected_email = TEMP_EMAIL_PROVIDERS[choice_index - 1]["name"]
                print(f"[✓] 已选择: {selected_email}")
                email_config["email_choice"] = selected_email
                save_browser_config(email_config)
                return selected_email

            if choice_index == len(TEMP_EMAIL_PROVIDERS) + 1:
                print("[✓] 已选择: 随机模式（按顺序轮流使用）")
                email_config["email_choice"] = "随机"
                save_browser_config(email_config)
                return None

        print("× 无效选项，请输入 1、2、3、4、5、6、7 或 q")


def main(
    headless: bool = True,
    debug_mode: bool = False,
    total_count: int = DEFAULT_TOTAL_COUNT,
    max_workers: int = DEFAULT_MAX_WORKERS,
    specified_email: str | None = None,
    notion_enabled: bool | None = None,
    stop_event = None,
    interactive: bool = True,
) -> BatchSummary:
    script_start_time = time.time()
    script_start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp_filename = f"accounts_{run_timestamp}.txt"
    runtime_options = RuntimeOptions(
        headless=headless,
        debug_mode=debug_mode,
        total_count=total_count,
        max_workers=max_workers,
        specified_email=specified_email,
        notion_enabled=notion_enabled,
        stop_event=stop_event,
    )

    logger.info("=" * 60)
    logger.info("即梦国际版自动注册脚本启动 v6.8")
    logger.info(f"脚本启动时间: {script_start_datetime}")
    logger.info(f"本次独立文件: {timestamp_filename}")
    logger.info("=" * 60)

    if interactive:
        runtime_options = _prompt_runtime_options(runtime_options)
    runtime_options = _sanitize_runtime_options(runtime_options)

    logger.info(f"总运行次数将为: {runtime_options.total_count} 次")
    logger.info(f"并发线程数将为: {runtime_options.max_workers} 个")
    logger.info("🔇 无头模式已启用（浏览器在后台运行，不显示窗口）" if headless else "🖥️ 显示浏览器窗口")
    logger.info("☁️ Notion 同步: 开启" if runtime_options.notion_enabled else "🗂️ Notion 同步: 关闭，仅保留本地输出")

    if debug_mode:
        logger.info("📷 调试模式已启用（将保存截图）")

    chrome_path = find_chrome_browser()
    if chrome_path:
        logger.info(f"[✓] 自动使用本地浏览器: {chrome_path}")
    else:
        logger.warning("[!] 未检测到本地浏览器，将使用 Playwright 内置 Chromium")

    if interactive and runtime_options.specified_email is None:
        runtime_options.specified_email = _select_email_provider()

    account_store = AccountStore(
        SUCCESS_DIR,
        notion_enabled=bool(runtime_options.notion_enabled),
    )
    results: list[RegistrationResult] = []
    provider_plan = _build_provider_plan(runtime_options, runtime_options.total_count)

    stop_requested = False

    # ================================
    # 这里改成增量调度，配合 stop_event 实现软中断
    # 目的: 用户点击停止后，不再继续提交新任务
    # 边界: 已经在跑的浏览器任务仍需自然收尾，避免强杀导致脏状态
    # ================================
    with ThreadPoolExecutor(max_workers=runtime_options.max_workers) as executor:
        next_task_index = 0
        running_futures: dict = {}

        def _submit_next_task() -> bool:
            nonlocal next_task_index
            if next_task_index >= runtime_options.total_count:
                return False

            thread_id = next_task_index + 1
            future = executor.submit(
                run_single_registration,
                thread_id=thread_id,
                runtime_options=runtime_options,
                chrome_path=chrome_path,
                account_store=account_store,
                timestamp_filename=timestamp_filename,
                assigned_email_provider=provider_plan[next_task_index],
            )
            running_futures[future] = thread_id
            next_task_index += 1
            return True

        for _ in range(runtime_options.max_workers):
            if not _submit_next_task():
                break

        while running_futures:
            done_futures, _ = wait(
                set(running_futures.keys()),
                timeout=0.5,
                return_when=FIRST_COMPLETED,
            )

            if runtime_options.stop_event and runtime_options.stop_event.is_set() and not stop_requested:
                stop_requested = True
                logger.warning("收到停止请求：不再提交新任务，等待进行中的线程收尾")

            if not done_futures:
                continue

            for future in done_futures:
                thread_id = running_futures.pop(future)
                try:
                    results.append(future.result())
                except Exception as exc:
                    logger.error(f"[任务{thread_id}] 获取结果失败: {exc}")
                    results.append(
                        RegistrationResult(
                            success=False,
                            thread_id=thread_id,
                            failed_step="future_result",
                            error_message=str(exc),
                        )
                    )

                if stop_requested:
                    continue

                _submit_next_task()

    completed_count = len(results)
    success_count = sum(1 for result in results if result.success)
    fail_count = completed_count - success_count
    script_end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_total_time = time.time() - script_start_time
    script_minutes = int(script_total_time // 60)
    script_seconds = int(script_total_time % 60)

    logger.info("=" * 60)
    logger.info("程序结束 - 执行统计")
    logger.info(f"脚本启动时间: {script_start_datetime}")
    logger.info(f"脚本结束时间: {script_end_datetime}")
    logger.info(f"脚本总运行时间: {script_minutes}分{script_seconds}秒 ({script_total_time:.2f}秒)")
    logger.info(f"总运行次数: {runtime_options.total_count} 次")
    logger.info(f"并发线程数: {runtime_options.max_workers} 个")
    if stop_requested:
        logger.warning(f"本次运行被用户中断，实际完成任务数: {completed_count}")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {fail_count} 个")
    if results:
        logger.info(f"成功率: {success_count / len(results) * 100:.1f}%")
    _log_failure_statistics(results)
    _update_provider_health(results)
    json_report_path, csv_report_path = RunReportWriter(REPORT_DIR).write(
        timestamp=run_timestamp,
        results=results,
        script_start_datetime=script_start_datetime,
        script_end_datetime=script_end_datetime,
        script_total_seconds=script_total_time,
    )
    logger.info("=" * 60)
    return BatchSummary(
        total_count=completed_count,
        success_count=success_count,
        fail_count=fail_count,
        success_rate=round((success_count / completed_count * 100), 1) if completed_count else 0.0,
        started_at=script_start_datetime,
        finished_at=script_end_datetime,
        duration_seconds=round(script_total_time, 2),
        json_report_path=json_report_path,
        csv_report_path=csv_report_path,
        timestamp_filename=timestamp_filename,
        stop_requested=stop_requested,
    )
