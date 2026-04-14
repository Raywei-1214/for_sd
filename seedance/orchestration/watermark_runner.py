from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from seedance.core.config import (
    WATERMARK_FFPROBE_TIMEOUT_SECONDS,
    WATERMARK_MAX_FREE_SECONDS,
    WATERMARK_OUTPUT_SUBDIR,
    WATERMARK_REPORT_DIR,
    WATERMARK_SUPPORTED_SUFFIXES,
)
from seedance.core.logger import get_logger
from seedance.core.models import (
    WatermarkProgress,
    WatermarkResult,
    WatermarkRunOptions,
    WatermarkSummary,
    WatermarkTask,
)
from seedance.infra.magiceraser_driver import MagicEraserDriver
from seedance.infra.video_probe import VideoProbeError, probe_video_duration_seconds
from seedance.services.watermark_service import (
    WatermarkService,
    collect_video_files,
    plan_output_path,
)

logger = get_logger()

ProgressCallback = Optional[Callable[[WatermarkProgress], None]]


# ================================
# 去水印批处理调度
# 目的: 串行扫描一个目录下的视频并依次调用 magiceraser 驱动
# 边界: 任意一个视频失败就停止整批（按产品决策 5）
# ================================


def _create_event_loop() -> asyncio.AbstractEventLoop:
    # 与注册流程保持同一套 Windows 兼容策略
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def run_watermark_batch(
    options: WatermarkRunOptions,
    progress_callback: ProgressCallback = None,
) -> WatermarkSummary:
    loop = _create_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_async(options, progress_callback))
    finally:
        try:
            loop.close()
        finally:
            asyncio.set_event_loop(None)


async def _run_async(
    options: WatermarkRunOptions,
    progress_callback: ProgressCallback,
) -> WatermarkSummary:
    input_dir = options.input_dir
    output_dir = input_dir / WATERMARK_OUTPUT_SUBDIR
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at_dt = datetime.now()
    started_at = started_at_dt.isoformat(timespec="seconds")
    start_ts = time.time()

    video_files = collect_video_files(input_dir, WATERMARK_SUPPORTED_SUFFIXES)
    total = len(video_files)
    results: list[WatermarkResult] = []

    def emit(current_index: int, current_file: Optional[str], phase: str) -> None:
        if progress_callback is None:
            return
        success_count = sum(1 for result in results if result.success)
        fail_count = sum(1 for result in results if not result.success)
        progress_callback(
            WatermarkProgress(
                total=total,
                completed=len(results),
                success_count=success_count,
                fail_count=fail_count,
                current_index=current_index,
                current_file=current_file,
                phase=phase,
                elapsed_seconds=round(time.time() - start_ts, 2),
                stop_requested=bool(options.stop_event and options.stop_event.is_set()),
            )
        )

    stop_requested = False
    aborted = False
    abort_reason: Optional[str] = None

    if total == 0:
        logger.warning(f"[去水印] 目录内未发现视频文件: {input_dir}")
        emit(current_index=0, current_file=None, phase="no_files")
    else:
        precheck_failures = _run_precheck(video_files, emit)
        if precheck_failures:
            results.extend(precheck_failures)
            aborted = True
            abort_reason = _build_precheck_abort_reason(precheck_failures)
            logger.error(f"[去水印] 预检中止: {abort_reason}")
        else:
            emit(current_index=0, current_file=None, phase="launching")
            try:
                async with MagicEraserDriver(headless=options.headless) as driver:
                    service = WatermarkService(driver)

                    for index, video_path in enumerate(video_files, start=1):
                        if options.stop_event and options.stop_event.is_set():
                            stop_requested = True
                            logger.info("[去水印] 收到停止信号，中止后续任务")
                            break

                        output_path = plan_output_path(video_path, output_dir)
                        task = WatermarkTask(
                            index=index,
                            input_path=video_path,
                            output_path=output_path,
                        )
                        emit(current_index=index, current_file=video_path.name, phase="processing")
                        result = await service.process(task)
                        results.append(result)
                        emit(
                            current_index=index,
                            current_file=video_path.name,
                            phase="done" if result.success else "failed",
                        )

                        if not result.success:
                            aborted = True
                            abort_reason = (
                                f"{video_path.name} 失败 phase={result.failed_phase} "
                                f"原因={result.error_message}"
                            )
                            logger.error(f"[去水印] 批次中止: {abort_reason}")
                            break
            except Exception as exc:
                aborted = True
                abort_reason = f"浏览器驱动异常: {exc}"
                logger.error(f"[去水印] 驱动异常中止: {exc}", exc_info=True)

    finished_at_dt = datetime.now()
    finished_at = finished_at_dt.isoformat(timespec="seconds")
    duration_seconds = round(time.time() - start_ts, 2)
    timestamp = started_at_dt.strftime("%Y%m%d_%H%M%S")

    report_path = _write_report(
        timestamp=timestamp,
        input_dir=input_dir,
        output_dir=output_dir,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        total=total,
        results=results,
        stop_requested=stop_requested,
        aborted=aborted,
        abort_reason=abort_reason,
    )

    success_count = sum(1 for result in results if result.success)
    fail_count = sum(1 for result in results if not result.success)

    return WatermarkSummary(
        total=total,
        success_count=success_count,
        fail_count=fail_count,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        report_path=report_path,
        output_dir=output_dir,
        stop_requested=stop_requested,
        aborted=aborted,
        abort_reason=abort_reason,
    )


def _write_report(
    timestamp: str,
    input_dir: Path,
    output_dir: Path,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
    total: int,
    results: list[WatermarkResult],
    stop_requested: bool,
    aborted: bool,
    abort_reason: Optional[str],
) -> Path:
    WATERMARK_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = WATERMARK_REPORT_DIR / f"watermark_run_{timestamp}.json"

    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "total": total,
        "success_count": sum(1 for result in results if result.success),
        "fail_count": sum(1 for result in results if not result.success),
        "stop_requested": stop_requested,
        "aborted": aborted,
        "abort_reason": abort_reason,
        "results": [_result_to_dict(result) for result in results],
    }
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[去水印] 运行报告: {report_path}")
    return report_path


def _result_to_dict(result: WatermarkResult) -> dict:
    data = asdict(result)
    # Path 不是 JSON 原生可序列化，统一转字符串
    data["input_path"] = str(result.input_path)
    data["output_path"] = str(result.output_path) if result.output_path else None
    return data


def _run_precheck(
    video_files: list[Path],
    emit: Callable[[int, Optional[str], str], None],
) -> list[WatermarkResult]:
    failures: list[WatermarkResult] = []
    for index, video_path in enumerate(video_files, start=1):
        emit(current_index=index, current_file=video_path.name, phase="precheck")
        failure = _precheck_video_file(index=index, video_path=video_path)
        if failure is not None:
            failures.append(failure)
            emit(current_index=index, current_file=video_path.name, phase="precheck_failed")
        else:
            emit(current_index=index, current_file=video_path.name, phase="precheck_ok")
    return failures


def _precheck_video_file(index: int, video_path: Path) -> Optional[WatermarkResult]:
    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        duration_seconds = probe_video_duration_seconds(
            video_path=video_path,
            timeout_seconds=WATERMARK_FFPROBE_TIMEOUT_SECONDS,
        )
    except VideoProbeError as exc:
        return WatermarkResult(
            success=False,
            index=index,
            input_path=video_path,
            output_path=None,
            duration_seconds=0.0,
            started_at=started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
            failed_phase="precheck",
            error_message=str(exc),
        )

    if duration_seconds <= WATERMARK_MAX_FREE_SECONDS:
        return None

    return WatermarkResult(
        success=False,
        index=index,
        input_path=video_path,
        output_path=None,
        duration_seconds=round(duration_seconds, 2),
        started_at=started_at,
        finished_at=datetime.now().isoformat(timespec="seconds"),
        failed_phase="precheck",
        error_message=(
            f"视频时长 {duration_seconds:.2f} 秒，超过 magiceraser 免费上限 "
            f"{WATERMARK_MAX_FREE_SECONDS} 秒"
        ),
    )


def _build_precheck_abort_reason(results: list[WatermarkResult]) -> str:
    messages = [
        f"{result.input_path.name}: {result.error_message}"
        for result in results
        if result.error_message
    ]
    return "预检未通过；请先修正以下视频后重试：" + "；".join(messages)
