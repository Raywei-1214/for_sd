import os
import re
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

    def _parse_credits(self, credits: str | None) -> float | None:
        if credits is None:
            return None

        text = str(credits).strip()
        if not text:
            return None

        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None

        try:
            return float(match.group(0))
        except ValueError:
            return None

    def _can_sync_success_to_notion(self, result: RegistrationResult) -> tuple[bool, str | None]:
        # ================================
        # 这里只允许“可直接使用的合格账号”进入 Notion 主表
        # 触发条件: 积分为 0、成功拿到 sessionid，且出口国家不包含 China
        # 边界: 不影响本地 txt 备份，txt 仍按原逻辑完整保留
        # ================================
        if not result.sessionid:
            return False, "缺少 sessionid"

        country_text = (result.country or "").strip()
        if "china" in country_text.lower():
            return False, f"国家命中 China: {country_text}"

        credits_value = self._parse_credits(result.credits)
        if credits_value is None:
            return False, "积分缺失或无法识别"

        if credits_value != 0:
            return False, f"积分不为0: {result.credits}"

        return True, None

    def is_notion_eligible(self, result: RegistrationResult) -> bool:
        eligible, _ = self._can_sync_success_to_notion(result)
        return eligible

    def _write_backup_file(self, result: RegistrationResult, timestamp_filename: str | None = None) -> None:
        self._write_backup_line(
            self._build_backup_line(result),
            timestamp_filename=timestamp_filename,
        )

    def _build_backup_line(self, result: RegistrationResult) -> str:
        date_str = datetime.now().strftime("%Y%m%d")
        sessionid_str = f"Sessionid={result.sessionid}" if result.sessionid else ""
        credits_str = f"{result.credits}积分" if result.credits is not None else ""
        country_str = result.country or ""
        seedance_str = result.seedance_value or ""
        return (
            f"{result.email}----{result.password}----{sessionid_str}"
            f"----{credits_str}----{country_str}----{seedance_str}\n"
        )

    def _write_backup_line(self, content: str, timestamp_filename: str | None = None) -> None:
        date_str = datetime.now().strftime("%Y%m%d")
        filename = self.success_dir / f"accounts_{date_str}.txt"

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
            backup_line = self._build_backup_line(result)
            try:
                self._write_backup_line(backup_line, timestamp_filename=timestamp_filename)
                save_result.backup_ok = True
            except Exception as exc:
                save_result.backup_error = str(exc)
                logger.error(f"本地备份写入失败: {exc}", exc_info=True)

            if self.notion_enabled:
                can_sync, skip_reason = self._can_sync_success_to_notion(result)
                if not save_result.backup_ok:
                    save_result.notion_error = "本地 txt 备份失败，未执行 Notion 同步"
                    logger.error(f"Notion 未执行: {result.email}，原因: 本地 txt 备份失败")
                elif can_sync:
                    try:
                        self.notion_client.create_result_page_from_backup(
                            backup_line=backup_line,
                            provider_name=result.provider_name,
                            registered_at=result.finished_at or result.started_at,
                        )
                        save_result.notion_ok = True
                    except Exception as exc:
                        save_result.notion_error = str(exc)
                        logger.error(f"Notion 写入失败: {exc}", exc_info=True)
                else:
                    save_result.notion_skipped = True
                    save_result.notion_skip_reason = skip_reason
                    logger.info(f"ℹ Notion 跳过写入: {result.email}，原因: {skip_reason}")
            else:
                logger.info("ℹ Notion 已关闭，本次仅写入本地 txt 备份")

            if save_result.fully_synced:
                if save_result.notion_skipped:
                    logger.info(f"✓ 账号已保存到本地 txt，未写入 Notion: {result.email}")
                elif self.notion_enabled:
                    logger.info(f"✓ 账号信息已保存到 Notion 与本地备份: {result.email}")
                else:
                    logger.info(f"✓ 账号信息已保存到本地 txt 备份: {result.email}")
            elif save_result.backup_ok:
                logger.warning(f"⚠ 已保存本地备份，但 Notion 写入失败: {result.email}")
            elif save_result.notion_ok:
                logger.warning(f"⚠ 已写入 Notion，但本地备份失败: {result.email}")
            elif save_result.notion_skipped:
                logger.error(f"× 本地 txt 备份失败，且账号未满足 Notion 写入条件: {result.email}")
            else:
                logger.error(f"× Notion 与本地备份均失败: {result.email}")

            return save_result

    def save_failure(self, result: RegistrationResult) -> SaveResult:
        with self._file_lock:
            save_result = SaveResult(notion_enabled=self.notion_enabled)
            save_result.notion_skipped = True
            save_result.notion_skip_reason = "失败任务不再写入 Notion"
            logger.info("ℹ 跳过失败任务 Notion 上报")
            return save_result
