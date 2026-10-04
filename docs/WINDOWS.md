# Windows 移植計畫

目前桌面介面使用 GTK 4，版本目標是現有的 Linux 環境。請勿直接在 Windows
執行 `python -m app`；音訊處理核心則已避免使用 Linux 專屬路徑，可繼續沿用。

## 建議移植順序

1. 在 Windows clone 此儲存庫。
2. 建立新的 Windows GUI，例如 `app/windows_gui.py`。
3. GUI 呼叫 `app.audio_processor.process_audio()`，不要複製剪輯邏輯。
4. 將 Windows 版 `ffmpeg.exe`、`ffprobe.exe` 和選用的 `ffplay.exe` 放入
   `vendor/ffmpeg/`；這些大型執行檔已由 `.gitignore` 排除。
5. 執行不依賴 GTK 的核心測試。
6. 在 Windows 上用 PyInstaller 建置並測試 `.exe`。

## GUI 選擇

- Tkinter：Windows Python 通常可直接使用，應用體積較小，適合簡單介面。
- PySide6：介面較完整，但相依套件與輸出檔會比較大。

目前需求簡單，建議先使用 Tkinter。可以保留 Linux GTK 介面，讓兩個 GUI
共用 `audio_processor.py` 與 `settings.py`。

## Windows 開發環境草案

```powershell
git clone <repository-url>
cd audio-silence-trimmer
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m unittest discover -s tests -v
```

完成 Windows GUI 後，再加入及驗證 PyInstaller 設定。不要在 Linux 上交叉
建置 Windows `.exe`。
