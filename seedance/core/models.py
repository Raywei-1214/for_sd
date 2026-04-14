from dataclasses import dataclass
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
    specified_email: Optional[str] = None
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
    timestamp_filename: str
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
    notion_enabled: Optional[bool] = None


@dataclass(frozen=True)
class ProjectContext:
    root_dir: Path
    screenshot_dir: Path
    success_dir: Path
    log_file: Path
    browser_config_file: Path
