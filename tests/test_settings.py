import tempfile
import unittest
from pathlib import Path

from app.settings import validate_settings


class SettingsValidationTests(unittest.TestCase):
    def test_accepts_valid_audio_settings(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            self.assertIsNone(validate_settings(Path(handle.name), "zero", -40, 0.5, 0.1))

    def test_rejects_missing_file(self):
        error = validate_settings(Path("does-not-exist.wav"), "zero", -40, 0.5, 0.1)
        self.assertEqual(error, "請選擇有效的音檔。")

    def test_rejects_unsupported_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt") as handle:
            error = validate_settings(Path(handle.name), "zero", -40, 0.5, 0.1)
        self.assertEqual(error, "不支援此檔案格式。")

    def test_rejects_invalid_threshold(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            error = validate_settings(Path(handle.name), "threshold", -100, 0.5, 0.1)
        self.assertIn("音量門檻", error)


if __name__ == "__main__":
    unittest.main()
