import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seedance.app.cli import main
from seedance.core.models import WatermarkSummary


class CliTests(unittest.TestCase):
    def test_registration_mode_calls_batch_runner(self) -> None:
        with patch("seedance.app.cli.run_batch") as mock_run_batch:
            exit_code = main(["--count", "1", "--threads", "1"])

        self.assertEqual(exit_code, 0)
        mock_run_batch.assert_called_once()

    def test_watermark_mode_calls_watermark_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary = WatermarkSummary(
                total=1,
                success_count=1,
                fail_count=0,
                started_at="2026-04-14T00:00:00",
                finished_at="2026-04-14T00:00:03",
                duration_seconds=3.0,
                report_path=Path(temp_dir) / "run_reports" / "watermark_run_20260414_000000.json",
                output_dir=Path(temp_dir) / "cleaned",
                stop_requested=False,
                aborted=False,
                abort_reason=None,
            )
            with patch("seedance.app.cli.run_watermark_batch", return_value=summary) as mock_run_watermark:
                exit_code = main(["watermark", temp_dir])

        self.assertEqual(exit_code, 0)
        mock_run_watermark.assert_called_once()
        options = mock_run_watermark.call_args.kwargs["options"]
        self.assertEqual(options.input_dir, Path(temp_dir).resolve())
        self.assertTrue(options.headless)


if __name__ == "__main__":
    unittest.main()
