from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable


ProgressCallback = Callable[[float, str], None]
SILENCE_RE = re.compile(r"silence_(start|end):\s*(-?[0-9.]+)")
TIME_RE = re.compile(r"time=(\d+):(\d+):([0-9.]+)")


class AudioProcessingError(RuntimeError):
    pass


def executable(name: str) -> str:
    """Find a bundled FFmpeg executable first, then fall back to PATH."""
    suffix = ".exe" if os.name == "nt" else ""
    executable_name = f"{name}{suffix}"
    candidates = [
        Path(__file__).resolve().parent.parent / "vendor" / "ffmpeg" / executable_name,
        Path(getattr(__import__("sys"), "_MEIPASS", "")) / "vendor" / "ffmpeg" / executable_name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(executable_name)
    if found:
        return found
    raise AudioProcessingError(
        f"找不到 {executable_name}。請安裝 FFmpeg，或放到 vendor/ffmpeg/ 目錄。"
    )


def probe_duration(source: Path) -> float:
    command = [
        executable("ffprobe"), "-v", "error", "-show_entries", "format=duration",
        "-of", "json", str(source),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise AudioProcessingError("無法讀取音檔：" + result.stderr.strip()[-500:])
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AudioProcessingError("無法取得音檔長度。") from exc
    if duration <= 0:
        raise AudioProcessingError("音檔長度必須大於 0。")
    return duration


def _timestamp_seconds(match: re.Match[str]) -> float:
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def detect_silence(
    source: Path,
    duration: float,
    threshold_db: float,
    minimum_silence: float,
    progress: ProgressCallback,
) -> list[tuple[float, float]]:
    command = [
        executable("ffmpeg"), "-hide_banner", "-nostdin", "-i", str(source),
        "-vn", "-af", f"silencedetect=noise={threshold_db}dB:d={minimum_silence}",
        "-f", "null", "-",
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    events: list[tuple[str, float]] = []
    tail: list[str] = []
    assert process.stderr is not None
    for line in process.stderr:
        tail.append(line.rstrip())
        tail = tail[-15:]
        silence_match = SILENCE_RE.search(line)
        if silence_match:
            events.append((silence_match.group(1), max(0.0, float(silence_match.group(2)))))
        time_match = TIME_RE.search(line)
        if time_match:
            progress(min(35.0, _timestamp_seconds(time_match) / duration * 35.0), "正在分析音量")
    return_code = process.wait()
    if return_code != 0:
        raise AudioProcessingError("FFmpeg 分析失敗：" + "\n".join(tail)[-1200:])

    intervals: list[tuple[float, float]] = []
    active_start: float | None = None
    for event, value in events:
        if event == "start":
            active_start = value
        elif active_start is not None:
            intervals.append((active_start, min(value, duration)))
            active_start = None
    if active_start is not None:
        intervals.append((active_start, duration))
    return intervals


def intervals_to_keep(
    silence_intervals: Iterable[tuple[float, float]], duration: float, padding: float
) -> list[tuple[float, float]]:
    """Return the complement of removable silence, preserving padding at each cut."""
    removable: list[tuple[float, float]] = []
    for start, end in silence_intervals:
        # Padding protects nearby audible material. There is no reason to retain
        # padding at the outer file boundary when silence starts/ends there.
        cut_start = 0.0 if start <= 0.001 else min(duration, start + padding)
        cut_end = duration if end >= duration - 0.001 else max(0.0, end - padding)
        if cut_end > cut_start:
            if removable and cut_start <= removable[-1][1]:
                removable[-1] = (removable[-1][0], max(removable[-1][1], cut_end))
            else:
                removable.append((cut_start, cut_end))

    kept: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in removable:
        if start > cursor:
            kept.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        kept.append((cursor, duration))
    return [(start, end) for start, end in kept if end - start >= 0.01]


def _filter_script(segments: list[tuple[float, float]]) -> str:
    filters: list[str] = []
    labels: list[str] = []
    for index, (start, end) in enumerate(segments):
        label = f"a{index}"
        filters.append(
            f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[outa]")
    return ";\n".join(filters)


def _filter_file_arguments(ffmpeg_path: str, script_path: Path) -> list[str]:
    """FFmpeg 9 replaced -filter_complex_script with generic file loading."""
    help_result = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-h", "full"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
    )
    if "-filter_complex_script" in help_result.stdout:
        return ["-filter_complex_script", str(script_path)]
    return ["-/filter_complex", str(script_path)]


def render_segments(
    source: Path,
    destination: Path,
    segments: list[tuple[float, float]],
    output_duration: float,
    progress: ProgressCallback,
) -> None:
    if not segments:
        raise AudioProcessingError("設定會移除整段音訊，請降低門檻或縮短最短靜音時間。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ffscript", encoding="utf-8", delete=False) as handle:
        handle.write(_filter_script(segments))
        script_path = Path(handle.name)
    codec_args = ["-c:a", "pcm_s16le"] if destination.suffix.lower() == ".wav" else ["-c:a", "libmp3lame", "-q:a", "2"]
    ffmpeg_path = executable("ffmpeg")
    command = [
        ffmpeg_path, "-hide_banner", "-nostdin", "-y", "-i", str(source),
        *_filter_file_arguments(ffmpeg_path, script_path), "-map", "[outa]", *codec_args,
        "-progress", "pipe:1", "-nostats", str(destination),
    ]
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if key in {"out_time_us", "out_time_ms"}:
                try:
                    seconds = int(value) / 1_000_000
                    progress(35.0 + min(64.0, seconds / max(output_duration, 0.001) * 64.0), "正在輸出音檔")
                except ValueError:
                    pass
        _, stderr = process.communicate()
        if process.returncode != 0:
            destination.unlink(missing_ok=True)
            raise AudioProcessingError("FFmpeg 輸出失敗：" + stderr.strip()[-1200:])
    finally:
        script_path.unlink(missing_ok=True)


def process_audio(
    source: Path,
    destination: Path,
    mode: str,
    threshold_db: float,
    minimum_silence: float,
    padding: float,
    progress: ProgressCallback,
) -> dict[str, float | int]:
    if mode not in {"zero", "threshold"}:
        raise AudioProcessingError("未知的處理模式。")
    effective_threshold = -90.0 if mode == "zero" else threshold_db
    duration = probe_duration(source)
    progress(1.0, "正在準備分析")
    silence = detect_silence(source, duration, effective_threshold, minimum_silence, progress)
    segments = intervals_to_keep(silence, duration, padding)
    output_duration = sum(end - start for start, end in segments)
    render_segments(source, destination, segments, output_duration, progress)
    progress(100.0, "處理完成")
    return {
        "original_duration": round(duration, 3),
        "output_duration": round(output_duration, 3),
        "removed_duration": round(max(0.0, duration - output_duration), 3),
        "silence_segments": len(silence),
    }
