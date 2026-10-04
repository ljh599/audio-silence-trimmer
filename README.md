# Audio Silence Trimmer

本機桌面音訊靜音剪輯器。使用 Python、GTK 4 與 FFmpeg，音檔只在本機處理。

> 目前狀態：Linux/GTK 版本可用；Windows GUI 尚未完成。Windows 後續工作請見
> [docs/WINDOWS.md](docs/WINDOWS.md)。

## 功能

- 只刪除完全無聲片段，以 `-90 dB` 近似數位靜音
- 刪除低於自訂音量門檻的片段
- 設定最短靜音時間與切點前後保留時間
- 輸出 MP3 或 WAV
- 顯示處理進度與移除秒數
- 串流處理長音檔，不將整個檔案載入記憶體
- 支援 MP3、WAV、M4A、AAC、FLAC、OGG、OPUS 與 WMA 輸入

## 專案結構

```text
app/
├── __main__.py          # 應用程式入口
├── main.py              # Linux GTK 4 桌面介面
├── audio_processor.py   # 跨平台 FFmpeg 處理核心
└── settings.py          # 不依賴 GUI 的輸入驗證
docs/
└── WINDOWS.md           # Windows 移植計畫
tests/                   # 單元測試
vendor/ffmpeg/           # 可選的 FFmpeg 執行檔位置
run.sh                   # Linux 啟動腳本
```

## Linux 需求

- Python 3.10 或更新版本
- GTK 4
- Python PyGObject
- FFmpeg 與 FFprobe

目前開發環境已具備以上系統套件。FFmpeg 可以位於系統 `PATH`，或放入
`vendor/ffmpeg/`。

## 執行

```bash
git clone <repository-url>
cd audio-silence-trimmer
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./run.sh
```

`--system-site-packages` 讓虛擬環境使用作業系統提供的 PyGObject。應用程式不會
啟動網頁服務或將音檔上傳到網路。

## 測試

```bash
.venv/bin/python -m unittest discover -s tests -v
```

測試涵蓋靜音區段計算、切點保留、重疊區段合併及輸入設定驗證。

## 產生測試音檔

以下指令產生「1 秒聲音、2 秒靜音、1 秒聲音」的 WAV：

```bash
ffmpeg \
  -f lavfi -i "sine=frequency=440:duration=1" \
  -f lavfi -i "anullsrc=r=44100:cl=mono:d=2" \
  -f lavfi -i "sine=frequency=440:duration=1" \
  -filter_complex "[0:a][1:a][2:a]concat=n=3:v=0:a=1" \
  -y test-with-silence.wav
```

使用「完全無聲」、最短靜音 `0.5` 秒、前後保留 `0.1` 秒處理時，預期輸出
長度約為 `2.2` 秒。

## 注意事項

MP3、AAC 等有損格式的靜音不一定是數值上的絕對零，因此完全無聲模式使用
極低的 `-90 dB` 門檻。輸出會重新編碼，請保留原始音檔。

## 授權

目前尚未選擇開源授權。在加入 LICENSE 前，GitHub 上公開可見不代表他人可以
自由修改或重新散布此專案。FFmpeg 的授權取決於所使用的建置版本。
