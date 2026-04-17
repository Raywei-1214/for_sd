from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Event
from typing import Optional


@dataclass(frozen=True)
class TempEmailProvider:
    name: str
    url: str


@dataclass
class RuntimeOptions:
    headless: bool
    debug_mode: bool
    total_count: int
    max_workers: int
    browser_choice: str = "auto"
    specified_email: Optional[str] = None
    provider_ratios: Optional[dict[str, int]] = None
    notion_enabled: Optional[bool] = None
    stop_event: Optional[Event] = None


class RegistrationStep(str, Enum):
    OPEN_HOME = "open_home"
    OPEN_SIGNUP = "open_signup"
    ACQUIRE_TEMP_EMAIL = "acquire_temp_email"
    FILL_CREDENTIALS = "fill_credentials"
    SUBMIT_CREDENTIALS = "submit_credentials"
    WAIT_CONFIRMATION = "wait_confirmation"
    FILL_VERIFICATION_CODE = "fill_verification_code"
    FILL_PROFILE = "fill_profile"
    COMPLETE_REGISTRATION = "complete_registration"
    COLLECT_ACCOUNT_DATA = "collect_account_data"


@dataclass
class RegistrationResult:
    success: bool
    thread_id: Optional[int] = None
    current_step: Optional[str] = None
    failed_step: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    provider_name: Optional[str] = None
    sessionid: Optional[str] = None
    credits: Optional[str] = None
    country: Optional[str] = None
    seedance_value: Optional[str] = None
    duration_seconds: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error_message: Optional[str] = None
    failure_context: Optional[str] = None
    sessionid_context: Optional[str] = None
    probe_context: Optional[str] = None
    account_quality: Optional[str] = None
    account_quality_reason: Optional[str] = None
    notion_ok: bool = False
    notion_skipped: bool = False
    notion_error: Optional[str] = None
    notion_skip_reason: Optional[str] = None
    backup_ok: bool = False
    backup_error: Optional[str] = None
    request_count: int = 0
    response_count: int = 0
    failed_request_count: int = 0
    transferred_bytes: int = 0
    request_type_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class SaveResult:
    notion_ok: bool = False
    backup_ok: bool = False
    notion_enabled: bool = True
    notion_skipped: bool = False
    notion_error: Optional[str] = None
    notion_skip_reason: Optional[str] = None
    backup_error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.notion_ok or self.backup_ok

    @property
    def fully_synced(self) -> bool:
        notion_ready = self.notion_ok or not self.notion_enabled or self.notion_skipped
        return notion_ready and self.backup_ok


@dataclass(frozen=True)
class BatchSummary:
    total_count: int
    success_count: int
    fail_count: int
    available_count: int
    success_rate: float
    available_rate: float
    started_at: str
    finished_at: str
    duration_seconds: float
    json_report_path: Path
    csv_report_path: Path
    notion_failures_path: Path
    timestamp_filename: str
    network_request_count: int
    network_response_count: int
    network_failed_request_count: int
    network_transferred_bytes: int
    network_request_type_counts: dict[str, int]
    account_quality_counts: dict[str, int]
    stop_requested: bool = False


@dataclass(frozen=True)
class BatchProgress:
    planned_total: int
    completed_count: int
    success_count: int
    fail_count: int
    available_count: int
    active_count: int
    pending_count: int
    success_rate: float
    available_rate: float
    started_at: str
    elapsed_seconds: float
    stop_requested: bool = False


@dataclass
class BrowserConfig:
    browser_choice: Optional[str] = None
    browser_path: Optional[str] = None
    email_choice: Optional[str] = None
    provider_ratios: Optional[dict[str, int]] = None
    notion_enabled: Optional[bool] = None


@dataclass(frozen=True)
class ProjectContext:
    root_dir: Path
    screenshot_dir: Path
    success_dir: Path
    log_file: Path
    browser_config_file: Path


# ================================
# 去水印任务数据结构
# 目的: 让 GUI / runner / service 之间只通过强类型对象通信
# 边界: 与注册流程完全隔离，不复用 RegistrationResult
# ================================
@dataclass
class WatermarkTask:
    index: int
    input_path: Path
    output_path: Path


@dataclass
class WatermarkResult:
    success: bool
    index: int
    input_path: Path
    output_path: Optional[Path] = None
    duration_seconds: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    failed_phase: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class WatermarkProgress:
    total: int
    completed: int
    success_count: int
    fail_count: int
    current_index: int
    current_file: Optional[str]
    phase: str
    elapsed_seconds: float
    stop_requested: bool = False


@dataclass(frozen=True)
class WatermarkSummary:
    total: int
    success_count: int
    fail_count: int
    started_at: str
    finished_at: str
    duration_seconds: float
    report_path: Path
    output_dir: Path
    stop_requested: bool = False
    aborted: bool = False
    abort_reason: Optional[str] = None


@dataclass
class WatermarkRunOptions:
    input_dir: Path
    headless: bool = True
    stop_event: Optional[Event] = None
