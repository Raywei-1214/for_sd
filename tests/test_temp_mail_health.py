import json
import tempfile
import unittest
from pathlib import Path

from seedance.infra.temp_mail_health import TempMailHealthStore


class TempMailHealthTests(unittest.TestCase):
    def test_record_provider_result_tracks_attempt_failure_and_70_credit_stats(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TempMailHealthStore(Path(temp_dir) / "temp_mail_health.json")

            store.record_provider_result(
                "mail.chatgpt.org.uk",
                success=True,
                hard_failure=False,
                credits_observed=True,
                credits_70=True,
            )
            store.record_provider_result(
                "mail.chatgpt.org.uk",
                success=False,
                hard_failure=True,
            )
            stats = store.build_provider_risk_snapshot(["mail.chatgpt.org.uk"])[0]

        self.assertEqual(stats["attempt_count"], 2)
        self.assertEqual(stats["success_count"], 1)
        self.assertEqual(stats["hard_failure_count"], 1)
        self.assertEqual(stats["total_failure_count"], 1)
        self.assertEqual(stats["credits_observed_count"], 1)
        self.assertEqual(stats["credits_70_count"], 1)
        self.assertAlmostEqual(stats["failure_rate"], 0.5)
        self.assertAlmostEqual(stats["credits_70_rate"], 1.0)

    def test_soft_failure_counts_into_failure_rate_but_not_hard_failure_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TempMailHealthStore(Path(temp_dir) / "temp_mail_health.json")

            store.record_provider_result(
                "mail.tm",
                success=False,
                hard_failure=False,
            )
            stats = store.build_provider_risk_snapshot(["mail.tm"])[0]

        self.assertEqual(stats["attempt_count"], 1)
        self.assertEqual(stats["hard_failure_count"], 0)
        self.assertEqual(stats["total_failure_count"], 1)
        self.assertAlmostEqual(stats["failure_rate"], 1.0)

    def test_list_high_risk_providers_supports_legacy_health_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            health_path = Path(temp_dir) / "temp_mail_health.json"
            health_path.write_text(
                json.dumps(
                    {
                        "rotation_index": 0,
                        "providers": {
                            "legacy-mail": {
                                "success_count": 2,
                                "failure_count": 2,
                                "consecutive_failures": 1,
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            store = TempMailHealthStore(health_path)
            high_risk_providers = store.list_high_risk_providers(["legacy-mail"])

        self.assertEqual(len(high_risk_providers), 1)
        self.assertEqual(high_risk_providers[0]["provider_name"], "legacy-mail")
        self.assertAlmostEqual(high_risk_providers[0]["failure_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
