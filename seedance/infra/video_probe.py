from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from seedance.core.config import WATERMARK_FFPROBE_TIMEOUT_SECONDS


class VideoProbeError(RuntimeError):
    pass


def probe_video_duration_seconds(
    video_path: Path,
    timeout_seconds: int = WATERMARK_FFPROBE_TIMEOUT_SECONDS,
) -> float:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path is None:
        raise VideoProbeError("未找到 ffprobe，无法在本地校验视频时长")

    # ================================
    # 只读取媒体元数据中的总时长
    # 目的: 在进入网页前就拦截超过免费额度的视频
    # 边界: 不解码视频内容，不承担修复损坏文件的职责
    # ================================
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoProbeError(f"读取视频时长超时: {video_path.name}") from exc
    except Exception as exc:
        raise VideoProbeError(f"读取视频时长失败: {video_path.name} ({exc})") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "ffprobe 返回非 0"
        raise VideoProbeError(f"读取视频时长失败: {video_path.name} ({detail})")

    return _parse_duration_seconds(result.stdout)


def _parse_duration_seconds(raw_text: str) -> float:
    duration_text = raw_text.strip()
    if not duration_text:
        raise VideoProbeError("ffprobe 未返回视频时长")

    try:
        duration_seconds = float(duration_text)
    except ValueError as exc:
        raise VideoProbeError(f"无法解析视频时长: {duration_text}") from exc

    if duration_seconds <= 0:
        raise VideoProbeError(f"视频时长无效: {duration_text}")

    return duration_seconds
