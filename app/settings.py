from __future__ import annotations

from pathlib import Path


ALLOWED_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


def validate_settings(
    source: Path | None,
    mode: str,
    threshold_db: float,
    minimum_silence: float,
    padding: float,
) -> str | None:
    """Validate user input without importing a platform-specific GUI."""
    if source is None or not source.is_file():
        return "請選擇有效的音檔。"
    if source.suffix.lower() not in ALLOWED_SUFFIXES:
        return "不支援此檔案格式。"
    if mode not in {"zero", "threshold"}:
        return "未知的處理模式。"
    if not -80 <= threshold_db <= -5:
        return "音量門檻必須介於 -80 至 -5 dB。"
    if not 0.05 <= minimum_silence <= 30:
        return "最短靜音時間必須介於 0.05 至 30 秒。"
    if not 0 <= padding <= 5:
        return "前後保留時間必須介於 0 至 5 秒。"
    return None
