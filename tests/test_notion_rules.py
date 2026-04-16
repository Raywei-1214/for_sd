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


if __name__ == "__main__":
    unittest.main()
