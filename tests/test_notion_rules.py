import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from seedance.core.models import RegistrationResult
from seedance.core.notion_rules import (
    NOTION_SYNC_SUFFIX,
    build_backup_line_from_result,
    evaluate_notion_sync_eligibility,
)
from seedance.infra.account_store import AccountStore
from seedance.infra.report_writer import RunReportWriter
from seedance.services.registration_service import RegistrationService


class FakeCookieContext:
    def __init__(self, snapshots: list[list[dict]]) -> None:
        self._snapshots = snapshots
        self._index = 0

    async def cookies(self):
        if self._index < len(self._snapshots):
            snapshot = self._snapshots[self._index]
            self._index += 1
            return snapshot
        return self._snapshots[-1]


class FakePage:
    url = "https://dreamina.capcut.com/ai-tool/home/"

    async def title(self):
        return "Dreamina"

    async def evaluate(self, script: str):
        if "document.body?.innerText" in script:
            return "Dreamina workspace"
        if "window.localStorage" in script:
            return ["device_id", "user_profile"]
        if "window.sessionStorage" in script:
            return ["session_cache"]
        return None


class NotionRulesTests(unittest.TestCase):
    def _make_result(self, **overrides) -> RegistrationResult:
        payload = {
            "success": True,
            "email": "demo@example.com",
            "password": "Passw0rd!",
            "sessionid": "session-1",
            "credits": "0",
            "country": "Hong Kong",
            "seedance_value": "0",
            "provider_name": "demo-mail",
            "started_at": "2026-04-16T10:00:00",
            "finished_at": "2026-04-16T10:00:10",
        }
        payload.update(overrides)
        return RegistrationResult(**payload)

    def test_evaluate_notion_sync_eligibility_requires_backup_suffix_zero(self) -> None:
        invalid_result = self._make_result(seedance_value="")
        eligible, reason = evaluate_notion_sync_eligibility(invalid_result)

        self.assertFalse(eligible)
        self.assertIn(NOTION_SYNC_SUFFIX, reason or "")

    def test_save_success_skips_notion_when_backup_line_suffix_is_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AccountStore(Path(temp_dir), notion_enabled=True)
            store.notion_client = Mock()

            result = self._make_result(seedance_value="")
            save_result = store.save_success(result)

        self.assertTrue(save_result.backup_ok)
        self.assertTrue(save_result.notion_skipped)
        self.assertIn(NOTION_SYNC_SUFFIX, save_result.notion_skip_reason or "")
        store.notion_client.create_result_page_from_backup.assert_not_called()

    def test_save_success_writes_to_notion_when_all_conditions_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = AccountStore(Path(temp_dir), notion_enabled=True)
            store.notion_client = Mock()

            result = self._make_result()
            save_result = store.save_success(result)

        self.assertTrue(save_result.backup_ok)
        self.assertTrue(save_result.notion_ok)
        self.assertFalse(save_result.notion_skipped)
        backup_line = build_backup_line_from_result(result)
        store.notion_client.create_result_page_from_backup.assert_called_once_with(
            backup_line=backup_line,
            provider_name=result.provider_name,
            registered_at=result.finished_at or result.started_at,
        )

    def test_report_writer_available_count_respects_backup_suffix_rule(self) -> None:
        writer = RunReportWriter(Path("/tmp/seedance-report-test"))
        valid_result = self._make_result(email="valid@example.com", seedance_value="0")
        invalid_result = self._make_result(email="invalid@example.com", seedance_value="")

        summary = writer._build_summary([valid_result, invalid_result], script_total_seconds=12.0)

        self.assertEqual(summary["available_count"], 1)

    def test_get_sessionid_retries_until_cookie_is_available(self) -> None:
        service = RegistrationService.__new__(RegistrationService)
        service.thread_id = 1
        context = FakeCookieContext(
            [
                [{"name": "csrf", "value": "a", "domain": ".capcut.com"}],
                [{"name": "sessionid", "value": "sid-1", "domain": ".capcut.com"}],
            ]
        )

        sessionid, sessionid_context = asyncio.run(
            RegistrationService.get_sessionid(service, context, FakePage())
        )

        self.assertEqual(sessionid, "sid-1")
        self.assertIn("sessionid_found_attempt=2", sessionid_context)

    def test_report_writer_serializes_sessionid_and_probe_context(self) -> None:
        writer = RunReportWriter(Path("/tmp/seedance-report-test"))
        result = self._make_result(
            sessionid_context="sessionid_found_attempt=0 | cookie_count=0",
            probe_context="seedance_credits=0 | seedance2_cost=<empty>",
        )

        payload = writer._serialize_result(result)

        self.assertEqual(payload["sessionid_context"], result.sessionid_context)
        self.assertEqual(payload["probe_context"], result.probe_context)

    def test_probe_context_blocked_detects_sign_in_shell(self) -> None:
        service = RegistrationService.__new__(RegistrationService)

        self.assertTrue(
            RegistrationService._is_probe_context_blocked(
                service,
                "url=https://dreamina.capcut.com | body=Explore Create Assets Canvas Sign in Start Creating With AI Agent",
            )
        )
        self.assertFalse(
            RegistrationService._is_probe_context_blocked(
                service,
                "url=https://dreamina.capcut.com | body=Explore Create Assets Canvas 0 Upgrade Start Creating With AI Agent AI Image",
            )
        )


if __name__ == "__main__":
    unittest.main()
