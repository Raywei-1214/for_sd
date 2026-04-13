import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime

from seedance.core.env import get_env_value
from seedance.core.logger import get_logger
from seedance.core.models import RegistrationResult

logger = get_logger()

NOTION_VERSION = "2022-06-28"
REQUIRED_RESULT_PROPERTIES = {
    "结果": {"rich_text": {}},
    "线程号": {"number": {"format": "number"}},
    "失败步骤": {"rich_text": {}},
    "失败原因": {"rich_text": {}},
    "Sessionid": {"rich_text": {}},
    "Seedance值": {"number": {"format": "number"}},
    "邮箱站点": {"rich_text": {}},
    "开始时间": {"rich_text": {}},
    "结束时间": {"rich_text": {}},
    "耗时秒": {"number": {"format": "number"}},
}


def build_notion_ssl_context() -> ssl.SSLContext:
    # ================================
    # 使用 certifi 根证书优先构建 SSL 上下文
    # 目的: 修复 mac 某些 Python 发行版缺少系统证书链的问题
    # 边界: 仍然保持证书校验开启，不允许关闭 HTTPS 验证
    # ================================
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class NotionClient:
    def __init__(self):
        self.token = get_env_value("NOTION_TOKEN")
        self.database_id = get_env_value("NOTION_DATABASE_ID")
        self._schema_ensured = False
        self._ssl_context = build_notion_ssl_context()

    def is_configured(self) -> bool:
        return bool(self.token and self.database_id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
    ) -> dict:
        request_data = None
        if payload is not None:
            request_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=request_data,
            headers=self._headers(),
            method=method,
        )

        # ================================
        # 这里只对 Notion 的瞬时错误做有限重试
        # 触发条件: 429、5xx、临时网络错误
        # 边界: 最多 3 次，认证/参数错误不重试
        # ================================
        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=30,
                    context=self._ssl_context,
                ) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="ignore")
                if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Notion API 请求失败: {exc.code} {response_body}") from exc
            except urllib.error.URLError as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"Notion 网络请求失败: {exc}") from exc

        raise RuntimeError("Notion API 请求失败: 达到最大重试次数")

    def ensure_database_schema(self) -> None:
        if self._schema_ensured or not self.is_configured():
            return

        database = self.get_database_metadata()
        existing_properties = database.get("properties", {})
        missing_properties = {
            name: schema
            for name, schema in REQUIRED_RESULT_PROPERTIES.items()
            if name not in existing_properties
        }

        # ================================
        # 只补缺失字段，避免每次启动重复 PATCH 污染表结构
        # 触发条件: 数据库尚未具备目标字段
        # 边界: 已存在的列不重建、不改名，保留人工管理空间
        # ================================
        if missing_properties:
            self._request_json(
                "PATCH",
                f"https://api.notion.com/v1/databases/{self.database_id}",
                payload={"properties": missing_properties},
            )
        self._schema_ensured = True

    def get_database_metadata(self) -> dict:
        if not self.is_configured():
            raise RuntimeError("Notion 未配置：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")

        return self._request_json(
            "GET",
            f"https://api.notion.com/v1/databases/{self.database_id}",
        )

    def _parse_optional_number(self, value: str | float | int | None) -> float | None:
        if value is None or value == "":
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _build_result_title(self, result: RegistrationResult) -> str:
        if result.email:
            return result.email

        thread_suffix = f"线程{result.thread_id}" if result.thread_id is not None else "未知线程"
        timestamp = result.finished_at or result.started_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "成功" if result.success else "失败"
        return f"{status}任务-{thread_suffix}-{timestamp}"

    def _build_result_properties(self, result: RegistrationResult) -> dict:
        failure_step = result.failed_step or result.current_step or ""
        failure_reason = result.error_message or ""
        result_label = "成功" if result.success else "失败"

        return {
            "账号": {
                "title": [
                    {"text": {"content": self._build_result_title(result)}}
                ]
            },
            "结果": {
                "rich_text": [
                    {"text": {"content": result_label}}
                ]
            },
            "线程号": {
                "number": float(result.thread_id) if result.thread_id is not None else None
            },
            "密码": {
                "rich_text": [
                    {"text": {"content": result.password or ""}}
                ]
            },
            "积分": {
                "number": self._parse_optional_number(result.credits)
            },
            "国家": {
                "rich_text": [
                    {"text": {"content": result.country or ""}}
                ]
            },
            "失败步骤": {
                "rich_text": [
                    {"text": {"content": failure_step}}
                ]
            },
            "失败原因": {
                "rich_text": [
                    {"text": {"content": failure_reason}}
                ]
            },
            "Sessionid": {
                "rich_text": [
                    {"text": {"content": result.sessionid or ""}}
                ]
            },
            "Seedance值": {
                "number": self._parse_optional_number(result.seedance_value)
            },
            "邮箱站点": {
                "rich_text": [
                    {"text": {"content": result.provider_name or ""}}
                ]
            },
            "开始时间": {
                "rich_text": [
                    {"text": {"content": result.started_at or ""}}
                ]
            },
            "结束时间": {
                "rich_text": [
                    {"text": {"content": result.finished_at or ""}}
                ]
            },
            "耗时秒": {
                "number": round(result.duration_seconds, 2)
            },
        }

    def create_result_page(self, result: RegistrationResult) -> None:
        if not self.is_configured():
            raise RuntimeError("Notion 未配置：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")

        self.ensure_database_schema()

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": self._build_result_properties(result),
        }
        self._request_json(
            "POST",
            "https://api.notion.com/v1/pages",
            payload=payload,
        )
        logger.info(
            "✓ 已写入 Notion: 结果=%s 线程=%s 标题=%s",
            "成功" if result.success else "失败",
            result.thread_id if result.thread_id is not None else "unknown",
            self._build_result_title(result),
        )
