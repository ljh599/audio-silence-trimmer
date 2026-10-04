from __future__ import annotations

import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .audio_processor import AudioProcessingError, process_audio
from .settings import validate_settings


class AudioTrimmerWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title="音訊靜音剪輯器")
        self.set_default_size(640, 600)
        self.set_resizable(True)
        self.source: Path | None = None
        self.processing = False
        self.connect("close-request", self._on_close_request)

        self._load_styles()
        self._build_ui()

    def _load_styles(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_string(
            """
            .title { font-size: 26px; font-weight: 700; }
            .subtitle { color: alpha(currentColor, 0.65); }
            .section { font-weight: 700; margin-top: 8px; }
            .primary { font-weight: 700; padding: 10px; }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self) -> None:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)
        outer.set_margin_start(28)
        outer.set_margin_end(28)
        self.set_child(outer)

        title = Gtk.Label(label="音訊靜音剪輯器", xalign=0)
        title.add_css_class("title")
        outer.append(title)
        subtitle = Gtk.Label(label="移除完全無聲或低於指定音量的片段", xalign=0)
        subtitle.add_css_class("subtitle")
        outer.append(subtitle)

        file_title = Gtk.Label(label="音檔", xalign=0)
        file_title.add_css_class("section")
        outer.append(file_title)
        file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.file_label = Gtk.Label(label="尚未選擇音檔", xalign=0, hexpand=True)
        self.file_label.set_ellipsize(3)
        file_row.append(self.file_label)
        self.choose_button = Gtk.Button(label="選擇音檔")
        self.choose_button.connect("clicked", self._choose_file)
        file_row.append(self.choose_button)
        outer.append(file_row)

        mode_title = Gtk.Label(label="處理模式", xalign=0)
        mode_title.add_css_class("section")
        outer.append(mode_title)
        self.zero_mode = Gtk.CheckButton(label="只刪除完全無聲片段（−90 dB）")
        self.zero_mode.set_active(True)
        outer.append(self.zero_mode)
        self.threshold_mode = Gtk.CheckButton(label="刪除低於指定音量的片段")
        self.threshold_mode.set_group(self.zero_mode)
        self.threshold_mode.connect("toggled", self._mode_changed)
        outer.append(self.threshold_mode)

        settings_title = Gtk.Label(label="設定", xalign=0)
        settings_title.add_css_class("section")
        outer.append(settings_title)
        grid = Gtk.Grid(column_spacing=18, row_spacing=10)
        grid.set_column_homogeneous(True)
        outer.append(grid)

        grid.attach(Gtk.Label(label="音量門檻（dB）", xalign=0), 0, 0, 1, 1)
        self.threshold_input = Gtk.SpinButton.new_with_range(-80, -5, 1)
        self.threshold_input.set_value(-40)
        self.threshold_input.set_sensitive(False)
        grid.attach(self.threshold_input, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="最短靜音時間（秒）", xalign=0), 0, 1, 1, 1)
        self.minimum_input = Gtk.SpinButton.new_with_range(0.05, 30, 0.05)
        self.minimum_input.set_digits(2)
        self.minimum_input.set_value(0.5)
        grid.attach(self.minimum_input, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="切點前後保留（秒）", xalign=0), 0, 2, 1, 1)
        self.padding_input = Gtk.SpinButton.new_with_range(0, 5, 0.05)
        self.padding_input.set_digits(2)
        self.padding_input.set_value(0.1)
        grid.attach(self.padding_input, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="輸出格式", xalign=0), 0, 3, 1, 1)
        self.format_input = Gtk.DropDown.new_from_strings(["MP3", "WAV"])
        grid.attach(self.format_input, 1, 3, 1, 1)

        self.start_button = Gtk.Button(label="選擇儲存位置並開始處理")
        self.start_button.add_css_class("suggested-action")
        self.start_button.add_css_class("primary")
        self.start_button.connect("clicked", self._start)
        outer.append(self.start_button)

        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_fraction(0)
        self.progress.set_text("0%")
        outer.append(self.progress)
        self.status = Gtk.Label(label="請先選擇音檔", xalign=0, wrap=True)
        outer.append(self.status)
        self.result = Gtk.Label(label="", xalign=0, wrap=True)
        self.result.add_css_class("subtitle")
        outer.append(self.result)

    def _choose_file(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileChooserNative.new(
            "選擇音檔", self, Gtk.FileChooserAction.OPEN, "選擇", "取消"
        )
        audio_filter = Gtk.FileFilter()
        audio_filter.set_name("音訊檔案")
        for pattern in ("*.mp3", "*.wav", "*.m4a", "*.aac", "*.flac", "*.ogg", "*.opus", "*.wma"):
            audio_filter.add_pattern(pattern)
        dialog.add_filter(audio_filter)
        dialog.connect("response", self._file_chosen)
        dialog.show()

    def _file_chosen(self, dialog: Gtk.FileChooserNative, response: int) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            selected = dialog.get_file()
            path = selected.get_path() if selected else None
            if path:
                self.source = Path(path)
                self.file_label.set_text(self.source.name)
                self.file_label.set_tooltip_text(str(self.source))
                self.status.set_text("已選擇音檔")
                self.result.set_text("")
        dialog.destroy()

    def _mode_changed(self, _button: Gtk.CheckButton) -> None:
        self.threshold_input.set_sensitive(self.threshold_mode.get_active())

    def _settings(self) -> tuple[str, float, float, float]:
        mode = "threshold" if self.threshold_mode.get_active() else "zero"
        return (
            mode,
            self.threshold_input.get_value(),
            self.minimum_input.get_value(),
            self.padding_input.get_value(),
        )

    def _start(self, _button: Gtk.Button) -> None:
        mode, threshold, minimum, padding = self._settings()
        error = validate_settings(self.source, mode, threshold, minimum, padding)
        if error:
            self._message("設定錯誤", error, Gtk.MessageType.ERROR)
            return
        assert self.source is not None
        extension = ".wav" if self.format_input.get_selected() == 1 else ".mp3"
        dialog = Gtk.FileChooserNative.new(
            "儲存處理後的音檔", self, Gtk.FileChooserAction.SAVE, "開始處理", "取消"
        )
        dialog.set_current_folder(Gio.File.new_for_path(str(self.source.parent)))
        dialog.set_current_name(f"{self.source.stem}_trimmed{extension}")
        output_filter = Gtk.FileFilter()
        output_filter.set_name(extension.upper().removeprefix("."))
        output_filter.add_pattern(f"*{extension}")
        dialog.add_filter(output_filter)
        dialog.connect("response", self._save_chosen, (mode, threshold, minimum, padding, extension))
        dialog.show()

    def _save_chosen(
        self, dialog: Gtk.FileChooserNative, response: int, settings: tuple
    ) -> None:
        if response != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return
        selected = dialog.get_file()
        path = selected.get_path() if selected else None
        dialog.destroy()
        if not path or self.source is None:
            return
        mode, threshold, minimum, padding, extension = settings
        destination = Path(path)
        if destination.suffix.lower() != extension:
            destination = destination.with_suffix(extension)
        if destination.resolve() == self.source.resolve():
            self._message("儲存錯誤", "輸出檔不能覆蓋原始音檔。", Gtk.MessageType.ERROR)
            return
        self._begin_processing(destination, mode, threshold, minimum, padding)

    def _begin_processing(
        self, destination: Path, mode: str, threshold: float, minimum: float, padding: float
    ) -> None:
        assert self.source is not None
        self.processing = True
        self.choose_button.set_sensitive(False)
        self.start_button.set_sensitive(False)
        self.progress.set_fraction(0)
        self.progress.set_text("0%")
        self.status.set_text("正在準備")
        self.result.set_text("")
        threading.Thread(
            target=self._worker,
            args=(self.source, destination, mode, threshold, minimum, padding),
            daemon=True,
        ).start()

    def _worker(
        self, source: Path, destination: Path, mode: str,
        threshold: float, minimum: float, padding: float,
    ) -> None:
        def report(percent: float, message: str) -> None:
            GLib.idle_add(self._update_progress, percent, message)

        try:
            stats = process_audio(
                source, destination, mode, threshold, minimum, padding, report
            )
            GLib.idle_add(self._completed, destination, stats)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            message = str(exc) if isinstance(exc, AudioProcessingError) else f"處理失敗：{exc}"
            GLib.idle_add(self._failed, message)

    def _update_progress(self, percent: float, message: str) -> bool:
        self.progress.set_fraction(max(0, min(1, percent / 100)))
        self.progress.set_text(f"{round(percent)}%")
        self.status.set_text(message)
        return GLib.SOURCE_REMOVE

    def _completed(self, destination: Path, stats: dict) -> bool:
        self._finish()
        self.progress.set_fraction(1)
        self.progress.set_text("100%")
        self.status.set_text("處理完成")
        self.result.set_text(
            f"原長 {stats['original_duration']} 秒｜輸出 {stats['output_duration']} 秒｜"
            f"移除 {stats['removed_duration']} 秒"
        )
        self._message("處理完成", f"音檔已儲存至：\n{destination}", Gtk.MessageType.INFO)
        return GLib.SOURCE_REMOVE

    def _failed(self, message: str) -> bool:
        self._finish()
        self.status.set_text("處理失敗")
        self._message("處理失敗", message, Gtk.MessageType.ERROR)
        return GLib.SOURCE_REMOVE

    def _finish(self) -> None:
        self.processing = False
        self.choose_button.set_sensitive(True)
        self.start_button.set_sensitive(True)

    def _message(self, title: str, detail: str, message_type: Gtk.MessageType) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self, modal=True, message_type=message_type,
            buttons=Gtk.ButtonsType.OK, text=title,
        )
        dialog.format_secondary_text(detail)
        dialog.connect("response", lambda item, _response: item.destroy())
        dialog.present()

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self.processing:
            self._message("正在處理", "音訊仍在處理中，請等待完成後再關閉。", Gtk.MessageType.WARNING)
            return True
        return False


class AudioTrimmerApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="local.audio.silence_trimmer")

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = AudioTrimmerWindow(self)
        window.present()


def run_app() -> int:
    return AudioTrimmerApplication().run(None)
