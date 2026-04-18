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
from seedance.services.email_service import TempEmailService
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


class ReadySignalService(RegistrationService):
    def __init__(self) -> None:
        pass

    async def _capture_page_context(self, page):  # type: ignore[override]
        return page.context_text

    async def _has_visible_selector(self, page, selectors):  # type: ignore[override]
        return page.visible


class ReadySignalPage:
    def __init__(self, context_text: str, visible: bool) -> None:
        self.context_text = context_text
        self.visible = visible

    async def query_selector_all(self, _selector: str):
        return []


class SequencedReadySignalPage:
    def __init__(self, context_texts: list[str], visible: bool) -> None:
        self._context_texts = context_texts
        self._index = 0
        self.visible = visible

    @property
    def context_text(self) -> str:
        value = self._context_texts[min(self._index, len(self._context_texts) - 1)]
        self._index += 1
        return value

    async def query_selector_all(self, _selector: str):
        return []


class ProbeSnapshotService(RegistrationService):
    def __init__(self, ready: bool, context_text: str) -> None:
        self._ready = ready
        self._context_text = context_text

    async def _wait_for_probe_workspace_ready(self, page):  # type: ignore[override]
        return self._ready

    async def _capture_page_context(self, page):  # type: ignore[override]
        return self._context_text


class FakeButtonNode:
    def __init__(
        self,
        *,
        visible: bool = True,
        disabled: str | None = None,
        aria_disabled: str | None = None,
        signup_candidate: bool = False,
    ) -> None:
        self.visible = visible
        self.disabled = disabled
        self.aria_disabled = aria_disabled
        self.signup_candidate = signup_candidate
        self.clicked = False

    async def is_visible(self):
        return self.visible

    async def get_attribute(self, name: str):
        if name == "disabled":
            return self.disabled
        if name == "aria-disabled":
            return self.aria_disabled
        return None

    async def evaluate(self, _script: str):
        return self.signup_candidate

    async def click(self, timeout: int = 10000):
        _ = timeout
        self.clicked = True


class SubmitButtonPage:
    def __init__(self, selector_nodes: dict[str, list[FakeButtonNode]]) -> None:
        self.selector_nodes = selector_nodes

    async def query_selector_all(self, selector: str):
        return list(self.selector_nodes.get(selector, []))


class SubmitTransitionService(RegistrationService):
    def __init__(self, transitions: list[bool], click_ok: bool = True) -> None:
        self.thread_id = 1
        self.temp_email_service = Mock(temp_email=None, password=None, provider_name=None)
        self._transitions = transitions
        self._transition_index = 0
        self._click_ok = click_ok
        self.click_count = 0

    async def _click_signup_continue(self, page, timeout: int = 10000):  # type: ignore[override]
        _ = page, timeout
        self.click_count += 1
        return self._click_ok

    async def _wait_for_submit_transition(self, page):  # type: ignore[override]
        _ = page
        value = self._transitions[min(self._transition_index, len(self._transitions) - 1)]
        self._transition_index += 1
        return value

    async def _capture_confirmation_context(self, page):  # type: ignore[override]
        _ = page
        return "submit_context"


class TempEmailTextService(TempEmailService):
    def __init__(self) -> None:
        pass


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
        service.temp_email_service = Mock(provider_name="demo-mail")
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

    def test_get_sessionid_runs_late_retry_for_mail_tm_when_auth_markers_exist(self) -> None:
        service = RegistrationService.__new__(RegistrationService)
        service.thread_id = 1
        service.temp_email_service = Mock(provider_name="mail.tm")
        context = FakeCookieContext(
            [
                [{"name": "sid_guard", "value": "guard-1", "domain": ".capcut.com"}],
                [{"name": "sid_guard", "value": "guard-1", "domain": ".capcut.com"}],
                [
                    {"name": "sid_guard", "value": "guard-1", "domain": ".capcut.com"},
                    {"name": "sessionid", "value": "sid-late", "domain": ".capcut.com"},
                ],
            ]
        )

        sessionid, sessionid_context = asyncio.run(
            RegistrationService.get_sessionid(service, context, FakePage())
        )

        self.assertEqual(sessionid, "sid-late")
        self.assertIn("sessionid_found_attempt=late", sessionid_context)
        self.assertIn("provider_name=mail.tm", sessionid_context)

    def test_get_sessionid_context_records_auth_markers_when_missing(self) -> None:
        service = RegistrationService.__new__(RegistrationService)
        service.thread_id = 1
        service.temp_email_service = Mock(provider_name="internxt")
        context = FakeCookieContext(
            [
                [{"name": "sid_guard", "value": "guard-1", "domain": ".capcut.com"}],
                [{"name": "sid_guard", "value": "guard-1", "domain": ".capcut.com"}],
            ]
        )

        sessionid, sessionid_context = asyncio.run(
            RegistrationService.get_sessionid(service, context, FakePage())
        )

        self.assertIsNone(sessionid)
        self.assertIn("provider_name=internxt", sessionid_context)
        self.assertIn("auth_cookie_markers=sid_guard", sessionid_context)
        self.assertIn("auth_storage_markers=device_id", sessionid_context)

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
        self.assertTrue(
            RegistrationService._is_probe_context_blocked(
                service,
                "url=https://dreamina.capcut.com/ai-tool/generate?type=agentic&workspace=0 | body=Explore Create Assets Canvas 0 Upgrade",
            )
        )

    def test_video_probe_context_requires_video_home_url(self) -> None:
        service = RegistrationService.__new__(RegistrationService)

        self.assertTrue(
            RegistrationService._is_video_probe_context(
                service,
                "url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets Canvas 0 Upgrade",
            )
        )
        self.assertFalse(
            RegistrationService._is_video_probe_context(
                service,
                "url=https://dreamina.capcut.com/ai-tool/generate?enter_from=ai_feature&from_page=explore&ai_feature_name=omniReference | body=Explore Create Assets Canvas 0 Upgrade",
            )
        )

    def test_probe_workspace_nudge_detects_half_ready_shell(self) -> None:
        service = RegistrationService.__new__(RegistrationService)

        self.assertTrue(
            RegistrationService._needs_probe_workspace_nudge(
                service,
                page_context="url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets",
                model_dropdown_found=False,
                generate_button_samples=[],
                has_numeric_signal=False,
            )
        )
        self.assertFalse(
            RegistrationService._needs_probe_workspace_nudge(
                service,
                page_context="url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets Canvas 0 Upgrade",
                model_dropdown_found=True,
                generate_button_samples=["Generate 0"],
                has_numeric_signal=True,
            )
        )

    def test_wait_for_probe_workspace_ready_accepts_half_ready_shell_after_signal(self) -> None:
        service = ReadySignalService()
        page = ReadySignalPage(
            context_text="url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets",
            visible=True,
        )

        ready = asyncio.run(RegistrationService._wait_for_probe_workspace_ready(service, page))

        self.assertTrue(ready)

    def test_wait_for_probe_workspace_ready_waits_for_signin_shell_to_hydrate(self) -> None:
        service = ReadySignalService()
        page = SequencedReadySignalPage(
            context_texts=[
                "url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets Canvas Sign in Start Creating With AI Agent",
                "url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets Canvas 0 Upgrade Start Creating With AI Agent AI Video",
            ],
            visible=True,
        )

        ready = asyncio.run(RegistrationService._wait_for_probe_workspace_ready(service, page))

        self.assertTrue(ready)

    def test_collect_probe_snapshot_refuses_partial_signal_when_workspace_not_ready(self) -> None:
        service = ProbeSnapshotService(
            ready=False,
            context_text="url=https://dreamina.capcut.com/ai-tool/home?type=video&workspace=0 | body=Explore Create Assets Canvas Sign in Start Creating With AI Agent",
        )

        snapshot = asyncio.run(
            RegistrationService._collect_probe_snapshot(
                service,
                page=object(),
                navigation_attempt=1,
                balance_samples=[],
                generate_button_samples=[],
            )
        )

        self.assertIsNone(snapshot["seedance2_cost"])
        self.assertIsNone(snapshot["seedance_credits"])
        self.assertFalse(snapshot["model_dropdown_found"])
        self.assertIn("seedance2_cost=<empty>", str(snapshot["probe_context"]))

    def test_click_signup_continue_prefers_form_scoped_enabled_button(self) -> None:
        service = RegistrationService.__new__(RegistrationService)
        wrong_node = FakeButtonNode(signup_candidate=False)
        disabled_signup_node = FakeButtonNode(signup_candidate=True, aria_disabled="true")
        correct_node = FakeButtonNode(signup_candidate=True)
        page = SubmitButtonPage(
            {
                "button:has-text('Continue')": [wrong_node, disabled_signup_node, correct_node],
            }
        )

        clicked = asyncio.run(RegistrationService._click_signup_continue(service, page))

        self.assertTrue(clicked)
        self.assertFalse(wrong_node.clicked)
        self.assertFalse(disabled_signup_node.clicked)
        self.assertTrue(correct_node.clicked)

    def test_submit_credentials_retries_until_transition_is_observed(self) -> None:
        service = SubmitTransitionService(transitions=[False, True])
        result = self._make_result(
            success=False,
            sessionid=None,
            credits=None,
            country=None,
            seedance_value=None,
        )

        submitted = asyncio.run(RegistrationService._submit_credentials(service, object(), result))

        self.assertTrue(submitted)
        self.assertEqual(service.click_count, 2)

    def test_submit_credentials_fails_when_transition_never_happens(self) -> None:
        service = SubmitTransitionService(transitions=[False, False])
        result = self._make_result(
            success=False,
            sessionid=None,
            credits=None,
            country=None,
            seedance_value=None,
        )

        submitted = asyncio.run(RegistrationService._submit_credentials(service, object(), result))

        self.assertFalse(submitted)
        self.assertEqual(result.failed_step, "submit_credentials")
        self.assertIn("页面未发生状态迁移", result.error_message or "")

    def test_numeric_probe_signal_requires_credits_or_cost(self) -> None:
        service = RegistrationService.__new__(RegistrationService)

        self.assertFalse(RegistrationService._has_numeric_probe_signal(service, None, None))
        self.assertTrue(RegistrationService._has_numeric_probe_signal(service, "0", None))
        self.assertTrue(RegistrationService._has_numeric_probe_signal(service, None, "70"))

    def test_extract_email_from_multiline_text_prefers_short_ready_line(self) -> None:
        service = TempEmailTextService()
        body_text = """
        Pricing Products Internxt Drive Internxt Antivirus Internxt VPN
        This is a very long marketing line that includes support@example.com but should be ignored because it is intentionally much longer than the short line threshold used for real inbox addresses in provider shells.
        demo-user@temp-mail.dev
        """

        extracted_email = TempEmailService._extract_email_from_multiline_text(service, body_text)

        self.assertEqual(extracted_email, "demo-user@temp-mail.dev")


if __name__ == "__main__":
    unittest.main()
