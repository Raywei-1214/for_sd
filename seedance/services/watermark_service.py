from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from seedance.core.logger import get_logger
from seedance.core.models import WatermarkResult, WatermarkTask
from seedance.infra.magiceraser_driver import MagicEraserDriver, MagicEraserError

logger = get_logger()


# ================================
# 单视频去水印服务
# 目的: 把 driver 调用、结果对象构造、异常归一收敛到一处
# 边界: 不处理批量、不做停止事件判定，只负责一次视频
# ================================


class WatermarkService:
    def __init__(self, driver: MagicEraserDriver) -> None:
        self._driver = driver

    async def process(self, task: WatermarkTask) -> WatermarkResult:
        started_at = datetime.now().isoformat(timespec="seconds")
        start_ts = time.time()

        logger.info(f"[去水印#{task.index}] 开始处理: {task.input_path.name}")
        try:
            await self._driver.remove_watermark(
                input_path=task.input_path,
                output_path=task.output_path,
            )
        except MagicEraserError as exc:
            duration = round(time.time() - start_ts, 2)
            logger.error(
                f"[去水印#{task.index}] 失败 phase={exc.phase} 原因={exc.detail}",
            )
            return WatermarkResult(
                success=False,
                index=task.index,
                input_path=task.input_path,
                output_path=None,
                duration_seconds=duration,
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                failed_phase=exc.phase,
                error_message=exc.detail,
            )
        except Exception as exc:
            duration = round(time.time() - start_ts, 2)
            logger.error(
                f"[去水印#{task.index}] 未分类异常: {exc}",
                exc_info=True,
            )
            return WatermarkResult(
                success=False,
                index=task.index,
                input_path=task.input_path,
                output_path=None,
                duration_seconds=duration,
                started_at=started_at,
                finished_at=datetime.now().isoformat(timespec="seconds"),
                failed_phase="unknown",
                error_message=str(exc),
            )

        duration = round(time.time() - start_ts, 2)
        logger.info(
            f"[去水印#{task.index}] 成功 输出={task.output_path.name} 用时={duration}s",
        )
        return WatermarkResult(
            success=True,
            index=task.index,
            input_path=task.input_path,
            output_path=task.output_path,
            duration_seconds=duration,
            started_at=started_at,
            finished_at=datetime.now().isoformat(timespec="seconds"),
        )


def collect_video_files(input_dir: Path, supported_suffixes: tuple[str, ...]) -> list[Path]:
    # 目录内按文件名排序，保证两次运行顺序一致
    if not input_dir.exists() or not input_dir.is_dir():
        return []

    files = [
        item
        for item in sorted(input_dir.iterdir())
        if item.is_file() and item.suffix.lower() in supported_suffixes
    ]
    return files


def plan_output_path(input_file: Path, output_dir: Path) -> Path:
    # 命名策略: 与源同名，避免重复生成时覆盖的话会由上层先判断
    return output_dir / input_file.name
