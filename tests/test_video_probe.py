import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from seedance.infra.video_probe import VideoProbeError, _parse_duration_seconds, probe_video_duration_seconds


class VideoProbeTests(unittest.TestCase):
    def test_parse_duration_seconds_success(self) -> None:
        self.assertAlmostEqual(_parse_duration_seconds("12.34\n"), 12.34)

    def test_parse_duration_seconds_rejects_empty_output(self) -> None:
        with self.assertRaises(VideoProbeError):
            _parse_duration_seconds(" \n")

    def test_probe_video_duration_seconds_requires_ffprobe(self) -> None:
        with patch("seedance.infra.video_probe.shutil.which", return_value=None):
            with self.assertRaises(VideoProbeError):
                probe_video_duration_seconds(Path("/tmp/demo.mp4"))

    def test_probe_video_duration_seconds_reads_ffprobe_output(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout="8.5\n",
            stderr="",
        )
        with patch("seedance.infra.video_probe.shutil.which", return_value="/usr/bin/ffprobe"):
            with patch("seedance.infra.video_probe.subprocess.run", return_value=completed) as mock_run:
                duration = probe_video_duration_seconds(Path("/tmp/demo.mp4"), timeout_seconds=3)

        self.assertEqual(duration, 8.5)
        mock_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
