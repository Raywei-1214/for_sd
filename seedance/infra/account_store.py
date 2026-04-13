import os
import threading
from datetime import datetime
from pathlib import Path

from seedance.core.logger import get_logger
from seedance.core.models import RegistrationResult, SaveResult
from seedance.infra.notion_client import NotionClient

logger = get_logger()


class AccountStore:
    def __init__(self, success_dir: Path, notion_enabled: bool = True):
        self.success_dir = success_dir
        self.success_dir.mkdir(parents=True, exist_ok=True)
        self._file_lock = threading.Lock()
        self.notion_enabled = notion_enabled
        self.notion_client = NotionClient()

    def _write_backup_file(self, result: RegistrationResult, timestamp_filename: str | None = None) -> None:
        date_str = datetime.now().strftime("%Y%m%d")
        filename = self.success_dir / f"accounts_{date_str}.txt"

        sessionid_str = f"Sessionid={result.sessionid}" if result.sessionid else ""
        credits_str = f"{result.credits}积分" if result.credits is not None else ""
        country_str = result.country or ""
        seedance_str = result.seedance_value or ""
        content = (
            f"{result.email}----{result.password}----{sessionid_str}"
            f"----{credits_str}----{country_str}----{seedance_str}\n"
        )

        with filename.open("a", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if timestamp_filename:
            timestamp_path = self.success_dir / timestamp_filename
            with timestamp_path.open("a", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

    def save_success(self, result: RegistrationResult, timestamp_filename: str | None = None) -> SaveResult:
        if not result.email or not result.password:
            logger.error("保存账号失败: 缺少邮箱或密码")
            return SaveResult(
                notion_ok=False,
                backup_ok=False,
                notion_enabled=self.notion_enabled,
                notion_error="缺少邮箱或密码",
                backup_error="缺少邮箱或密码",
            )

        with self._file_lock:
            save_result = SaveResult(notion_enabled=self.notion_enabled)

            # ================================
            # 本地 txt 先写入，确保外部 API 抖动时账号不会丢
            # 触发条件: 注册成功且拿到邮箱/密码后立即执行
            # 边界: 本地备份只做保险，不替代 Notion 主表
            # ================================
            try:
                self._write_backup_file(result, timestamp_filename=timestamp_filename)
                save_result.backup_ok = True
            except Exception as exc:
                save_result.backup_error = str(exc)
                logger.error(f"本地备份写入失败: {exc}", exc_info=True)

            if self.notion_enabled:
                try:
                    self.notion_client.create_result_page(result)
                    save_result.notion_ok = True
                except Exception as exc:
                    save_result.notion_error = str(exc)
                    logger.error(f"Notion 写入失败: {exc}", exc_info=True)
            else:
                logger.info("ℹ Notion 已关闭，本次仅写入本地 txt 备份")

            if save_result.fully_synced:
                if self.notion_enabled:
                    logger.info(f"✓ 账号信息已保存到 Notion 与本地备份: {result.email}")
                else:
                    logger.info(f"✓ 账号信息已保存到本地 txt 备份: {result.email}")
            elif save_result.backup_ok:
                logger.warning(f"⚠ 已保存本地备份，但 Notion 写入失败: {result.email}")
            elif save_result.notion_ok:
                logger.warning(f"⚠ 已写入 Notion，但本地备份失败: {result.email}")
            else:
                logger.error(f"× Notion 与本地备份均失败: {result.email}")

            return save_result

    def save_failure(self, result: RegistrationResult) -> SaveResult:
        with self._file_lock:
            save_result = SaveResult(notion_enabled=self.notion_enabled)

            if not self.notion_enabled:
                logger.info("ℹ Notion 已关闭，跳过失败任务上报")
                return save_result

            try:
                self.notion_client.create_result_page(result)
                save_result.notion_ok = True
                logger.info(
                    "✓ 失败结果已写入 Notion: 线程=%s 步骤=%s",
                    result.thread_id if result.thread_id is not None else "unknown",
                    result.failed_step or result.current_step or "unknown_step",
                )
            except Exception as exc:
                save_result.notion_error = str(exc)
                logger.error(f"失败结果写入 Notion 失败: {exc}", exc_info=True)

            return save_result
