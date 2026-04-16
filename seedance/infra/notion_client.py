import json
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from seedance.core.env import get_env_value
from seedance.core.logger import get_logger
from seedance.core.models import RegistrationResult
from seedance.core.notion_rules import NOTION_SYNC_SUFFIX, backup_line_has_notion_sync_suffix

logger = get_logger()

NOTION_VERSION = "2022-06-28"
DESIRED_RESULT_PROPERTY_NAMES = {"账号", "密码", "国家", "注册时间", "邮箱站点", "使用状态"}
REQUIRED_RESULT_PROPERTIES = {
    "密码": {"rich_text": {}},
    "国家": {"rich_text": {}},
    "注册时间": {"rich_text": {}},
    "邮箱站点": {"rich_text": {}},
    "使用状态": {
        "select": {
            "options": [
                {"name": "未使用", "color": "default"},
                {"name": "已使用", "color": "green"},
            ]
        }
    },
}


@dataclass(frozen=True)
class BackupRecord:
    email: str
    password: str
    sessionid: str
    credits: str
    country: str
    seedance_value: str


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
        self._title_property_name = "账号"

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
        patch_properties: dict[str, dict | None] = {}

        title_property_name = None
        title_property_id = None
        for property_name, property_schema in existing_properties.items():
            if property_schema.get("type") == "title":
                title_property_name = property_name
                title_property_id = property_schema.get("id")
                break

        if title_property_name:
            self._title_property_name = title_property_name

        # ================================
        # 这里把 Notion 表强制收敛为 6 列
        # 目的: 表结构只保留账号、密码、国家、注册时间、邮箱站点、使用状态，避免继续膨胀
        # 边界: 标题列必须保留，其他非目标列统一清理
        # ================================
        if title_property_name and title_property_name != "账号" and title_property_id:
            patch_properties[title_property_id] = {
                "name": "账号",
                "title": {},
            }
            self._title_property_name = "账号"

        for name, schema in REQUIRED_RESULT_PROPERTIES.items():
            if name not in existing_properties:
                patch_properties[name] = schema

        for property_name, property_schema in existing_properties.items():
            if property_schema.get("type") == "title":
                continue
            if property_name in DESIRED_RESULT_PROPERTY_NAMES:
                continue
            patch_properties[property_name] = None

        # ================================
        # 这里同时做“补齐缺失字段 + 清理冗余字段”
        # 触发条件: 表结构不满足 账号/密码/国家/注册时间/邮箱站点/使用状态 六列模型
        # 边界: 只调整当前数据库，不影响本地 txt 备份策略
        # ================================
        if patch_properties:
            self._request_json(
                "PATCH",
                f"https://api.notion.com/v1/databases/{self.database_id}",
                payload={"properties": patch_properties},
            )
        self._schema_ensured = True

    def get_database_metadata(self) -> dict:
        if not self.is_configured():
            raise RuntimeError("Notion 未配置：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")

        return self._request_json(
            "GET",
            f"https://api.notion.com/v1/databases/{self.database_id}",
        )

    def parse_backup_line(self, backup_line: str) -> BackupRecord:
        line = backup_line.strip()
        parts = line.split("----")
        if len(parts) < 6:
            raise ValueError(f"备份行格式无效: {line}")

        email = parts[0].strip()
        password = parts[1].strip()
        sessionid = parts[2].strip().removeprefix("Sessionid=")
        credits = parts[3].strip().removesuffix("积分")
        country = parts[4].strip()
        seedance_value = parts[5].strip()
        return BackupRecord(
            email=email,
            password=password,
            sessionid=sessionid,
            credits=credits,
            country=country,
            seedance_value=seedance_value,
        )

    def _build_result_properties(self, result: RegistrationResult) -> dict:
        return {
            self._title_property_name: {
                "title": [
                    {"text": {"content": result.email or ""}}
                ]
            },
            "密码": {
                "rich_text": [
                    {"text": {"content": result.password or ""}}
                ]
            },
            "国家": {
                "rich_text": [
                    {"text": {"content": result.country or ""}}
                ]
            },
            "注册时间": {
                "rich_text": [
                    {"text": {"content": result.finished_at or result.started_at or ""}}
                ]
            },
            "邮箱站点": {
                "rich_text": [
                    {"text": {"content": result.provider_name or ""}}
                ]
            },
            "使用状态": {
                "select": {
                    "name": "未使用"
                }
            },
        }

    def _build_properties_from_backup(
        self,
        backup_record: BackupRecord,
        provider_name: str | None,
        registered_at: str | None,
    ) -> dict:
        return {
            self._title_property_name: {
                "title": [
                    {"text": {"content": backup_record.email}}
                ]
            },
            "密码": {
                "rich_text": [
                    {"text": {"content": backup_record.password}}
                ]
            },
            "国家": {
                "rich_text": [
                    {"text": {"content": backup_record.country}}
                ]
            },
            "注册时间": {
                "rich_text": [
                    {"text": {"content": registered_at or ""}}
                ]
            },
            "邮箱站点": {
                "rich_text": [
                    {"text": {"content": provider_name or ""}}
                ]
            },
            "使用状态": {
                "select": {
                    "name": "未使用"
                }
            },
        }

    def has_account(self, email: str) -> bool:
        if not self.is_configured():
            raise RuntimeError("Notion 未配置：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")

        self.ensure_database_schema()
        payload = {
            "filter": {
                "property": self._title_property_name,
                "title": {
                    "equals": email,
                },
            },
            "page_size": 1,
        }
        response = self._request_json(
            "POST",
            f"https://api.notion.com/v1/databases/{self.database_id}/query",
            payload=payload,
        )
        return bool(response.get("results"))

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
            "✓ 已写入 Notion: 账号=%s 国家=%s",
            result.email or "unknown",
            result.country or "",
        )

    def create_result_page_from_backup(
        self,
        backup_line: str,
        provider_name: str | None,
        registered_at: str | None,
        max_attempts: int = 5,
    ) -> None:
        if not self.is_configured():
            raise RuntimeError("Notion 未配置：缺少 NOTION_TOKEN 或 NOTION_DATABASE_ID")

        # ================================
        # 客户端层再做一次硬校验，防止上游漏判后把脏数据写进主表
        # 触发条件: 任何调用方尝试直接拿备份行写入 Notion
        # 边界: 只拒绝不满足 ----0 结尾的数据，不改本地备份
        # ================================
        if not backup_line_has_notion_sync_suffix(backup_line):
            raise RuntimeError(f"Notion 写入拒绝：备份行未以 {NOTION_SYNC_SUFFIX} 结尾")

        backup_record = self.parse_backup_line(backup_line)
        self.ensure_database_schema()

        if self.has_account(backup_record.email):
            logger.info("ℹ Notion 已存在同账号，跳过重复写入: %s", backup_record.email)
            return

        payload = {
            "parent": {"database_id": self.database_id},
            "properties": self._build_properties_from_backup(
                backup_record=backup_record,
                provider_name=provider_name,
                registered_at=registered_at,
            ),
        }

        # ================================
        # 外层重试负责覆盖“单次创建页”级别的瞬时异常
        # 目的: 避免请求层有限重试后，整条账号记录仍因为短暂抖动丢失
        # 边界: 查重只做一次，最多重试 5 次，不吞最终异常
        # ================================
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                self._request_json(
                    "POST",
                    "https://api.notion.com/v1/pages",
                    payload=payload,
                )
                logger.info(
                    "✓ 已从本地备份写入 Notion: 账号=%s 国家=%s",
                    backup_record.email,
                    backup_record.country,
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts - 1:
                    break
                time.sleep(2 * (attempt + 1))

        if last_error is not None:
            raise last_error
