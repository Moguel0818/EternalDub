# EternalDub

> Open-source tool to add dubbed audio tracks to high-quality video releases (**BDRemux, WEB-DL, BDRip**) **without re-encoding anything**. The video stays bit-for-bit identical; the dub is synchronized automatically.

🇧🇷 **[Leia em português](README.pt-BR.md)**

---

## Why does this project exist?

As an archivist, **media preservation and file integrity are core principles I take very seriously.**

Over time, I noticed a recurring issue: many classic dubs only circulate attached to low-quality video (bad DVD/BD rips, heavy re-encodes). Because of that, a lot of films look much older than they are. Better releases already exist (BDRemux, 35 mm scans), but they don't have the dub.

Putting a dub on a better release usually means juggling several programs, one to measure the delay, another to adjust it, another to mux, and a player to check the result. EternalDub does all of it in a single window.

I also created EternalDub for a personal reason: **my brother has dyslexia**, and reading fast subtitles during foreign films is exhausting for him. Good image and the right dub help many people with reading difficulties.

Brazilian dubbing (and dubbing culture worldwide) is a true treasure that deserves top-tier treatment. You shouldn't have to sacrifice image quality to watch a movie in your own language.

---

## Features

- **Lossless.** The movie's video, audio and subtitle tracks are copied, never re-encoded. A built-in hash check proves they are identical in the final file.
- **Automatic delay detection.** EternalDub compares the music and sound effects of the dub with the movie's original audio (cross-correlation), so it works even though the voices are different. It reads only short excerpts of the movie, which keeps it fast even with large UHD remuxes.
- **Speed differences.** It detects speed differences such as PAL (25 fps) against film (23.976 fps) and offers to correct them. Only the dub is converted (to lossless FLAC); the video is never touched.
- **Different cuts.** When the versions have different cuts, it warns you and shows where the delay changes.
- **Waveform view** in the style of Subtitle Edit. Drag the dub to adjust the delay by hand, or use the ±10/100/1000 ms buttons.
- **Several dubs at once,** from one or many files, each with its own name, language and default flag.
- **Track selection.** You choose which of the movie's own audio and subtitle tracks go into the final file.
- **Test and automatic check.** It makes a 5-minute test file first. After muxing, it checks that every dub has sound and is in sync inside the final file.
- **All in one place.** Detection, manual adjustment, muxing and verification happen in a single window.
- **Interface languages:** Portuguese (Brazil) and English.

---

## Requirements

| What | Notes |
|---|---|
| **Windows 10/11** | Tested. Linux/macOS should work by running `EternalDub_gui.py` directly, but this hasn't been tested yet. |
| **Python 3.10+** | From [python.org](https://www.python.org/downloads/). Check **"Add python.exe to PATH"** during installation. 3.12 or 3.13 recommended. |
| **FFmpeg** | `ffmpeg` and `ffprobe` in the PATH. On Windows: `winget install Gyan.FFmpeg` |
| **numpy, PySide6** | Installed automatically by `Iniciar_EternalDub.bat` on the first run (or `pip install -r requirements.txt`). |

---

## Installation

**Option A: download (easiest)**
1. Click **Code ▸ Download ZIP** on this page (or get it from **Releases**).
2. Extract it to a new folder.
3. Double-click **`Iniciar_EternalDub.bat`**.

**Option B: git**
```bash
git clone https://github.com/Moguel0818/EternalDub.git
cd EternalDub
pip install -r requirements.txt
python EternalDub_gui.py
```

The interface opens in your system language (Portuguese or English). You can change it in **Options ▸ Idioma / Language**.

---

## How to use

1. **Open movie.** Choose the high-quality release, or drag it into the window.
2. **Add dub.** Choose the file(s) that contain the dub: an MKV/MP4 with video, or audio only (MP3, AC3, E-AC3, DTS, FLAC, WAV…). If a file has several audio tracks, tick the ones that are dubs.
3. **Detect delay (F5).** The result appears in the list and in the **Log** tab.
   - *Tip:* if the dub's file also contains the original-language track (e.g. English), use **Sync ▸ Detect using another track of the file** with that track. It's more reliable and applies the result to every dub from that file.
4. **Check the waveforms.** The movie is green and the dub is orange. Fine-tune by dragging the orange waveform or with the buttons.
5. **Choose the movie tracks to keep** in the **Movie** tab (for example, untick audio tracks or subtitles you don't want).
6. **Make test (5 min)** and listen in your player.
7. **Make final file.** The automatic check runs at the end.
8. *(Optional)* **Tools ▸ Verify integrity** proves that the original video, audio and subtitles are bit-identical.

Projects can be saved (`.eternaldub`) and reopened later.

---

## How it works (technical)

- **Analysis** uses a lightweight copy of the audio (mono, 8 kHz), used only to measure, never written to the output. Band-energy envelopes from the spectrum are cross-correlated with FFT. Several speed ratios are tested (PAL, 24 ↔ 23.976). The quick analysis reads about 1 minute plus four 40-second excerpts of the movie and searches for each one in a larger window of the dub.
- **Muxing** uses FFmpeg with `-c copy` and `-itsoffset` for the delay. Negative delays are applied with a copy-only trim of the dub.
- **Cache:** waveforms are stored in `~/.eternaldub/cache`, so a movie is read in full only once. You can clear it in **Tools**.
- **Files:** `EternalDub_gui.py` (interface), `EternalDub_core.py` (reading, detection, muxing, checks), `detectar_atraso.py` (delay detection, also usable from the command line), `EternalDub_i18n.py` (translations).

Command line example:
```bash
python detectar_atraso.py MOVIE.mkv DUB.mkv --faixa-dub 1 --idioma en
```

---

## Limitations

- **Different cuts between versions** are detected and shown, but joining sections with different delays (anchor points) is **not implemented yet**. The 5-minute test only covers the beginning, so if the log shows varying delays, check later scenes too.
- Detection relies on music and sound effects shared by both versions. If the dub has a re-recorded soundtrack, use manual alignment or **Detect by video**.
- On slow disks (for example, an external HDD on USB 2.0), reading a UHD remux takes time. Saving the final file to a different disk helps a lot.

## Roadmap

- Anchor points: different delays per section, for versions with different cuts
- Audio playback inside the app
- Standalone `.exe` (no Python needed)
- More interface languages

---

## Contributing

Issues and pull requests are welcome, especially from people with experience in audio/DSP, FFmpeg or desktop UI.

- **Bugs:** open an [Issue](https://github.com/Moguel0818/EternalDub/issues) and paste the contents of the **Log** tab (plus `~/.eternaldub/erro.log`, if it exists).
- **Translations:** see `EternalDub_i18n.py`. Copy the `EN` dictionary and translate the values.
- Everyone who helps is credited in [CREDITS.md](CREDITS.md) and in the program's **About** window.

## Transparency

The code was written with AI assistance (Claude, by Anthropic). The project was conceived, directed and tested by the author on real files. Reviews from experienced developers are very welcome.

## Legal note

EternalDub does not include, download or distribute any media. Use it only with files you have the right to use.

## License

[MIT](LICENSE). EternalDub calls FFmpeg as an external program and uses PySide6 and NumPy as libraries; none of them is included here, and each keeps its own license.
