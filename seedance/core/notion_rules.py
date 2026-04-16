import re

from seedance.core.models import RegistrationResult

NOTION_SYNC_SUFFIX = "----0"


def parse_credits_value(credits: str | None) -> float | None:
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


def build_backup_line_from_result(result: RegistrationResult) -> str:
    sessionid_str = f"Sessionid={result.sessionid}" if result.sessionid else ""
    credits_str = f"{result.credits}积分" if result.credits is not None else ""
    country_str = result.country or ""
    seedance_str = result.seedance_value or ""
    return (
        f"{result.email}----{result.password}----{sessionid_str}"
        f"----{credits_str}----{country_str}----{seedance_str}\n"
    )


def get_backup_line_seedance_value(backup_line: str) -> str:
    parts = backup_line.rstrip("\r\n").split("----")
    if len(parts) < 6:
        return ""
    return parts[-1].strip()


def backup_line_has_notion_sync_suffix(backup_line: str) -> bool:
    return backup_line.rstrip("\r\n").endswith(NOTION_SYNC_SUFFIX)


def evaluate_notion_sync_eligibility(
    result: RegistrationResult,
    backup_line: str | None = None,
) -> tuple[bool, str | None]:
    # ================================
    # Notion 主表只接收“可直接消费”的成功账号
    # 规则收口在这里，避免保存逻辑和报表逻辑再次分叉
    # ================================
    if not result.success:
        return False, "任务未成功"

    if not result.sessionid:
        return False, "缺少 sessionid"

    country_text = (result.country or "").strip()
    if "china" in country_text.lower():
        return False, f"国家命中 China: {country_text}"

    credits_value = parse_credits_value(result.credits)
    if credits_value is None:
        return False, "积分缺失或无法识别"

    if credits_value != 0:
        return False, f"积分不为0: {result.credits}"

    effective_backup_line = backup_line or build_backup_line_from_result(result)
    if not backup_line_has_notion_sync_suffix(effective_backup_line):
        seedance_value = get_backup_line_seedance_value(effective_backup_line) or "<empty>"
        return False, f"备份行未以 {NOTION_SYNC_SUFFIX} 结尾，末段值={seedance_value}"

    return True, None
