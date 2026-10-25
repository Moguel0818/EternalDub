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
- **Different cuts, synced section by section.** When the versions have different cuts (or the dub was re-edited by whoever uploaded it), the delay changes along the movie. EternalDub measures it at every second, finds each change and assembles the dub piece by piece: where the dub is missing a piece of the movie, silence goes in; where it has something that doesn't exist in the movie, that piece is removed, preferably during a pause. Only the dub becomes FLAC (lossless); the movie is not touched.
- **Waveform view** in the style of Subtitle Edit. Drag the dub to adjust the delay by hand, or use the ±10/100/1000 ms buttons.
- **Several dubs at once,** from one or many files, each with its own name, language and default flag.
- **Track selection.** You choose which of the movie's own audio and subtitle tracks go into the final file.
- **Test and automatic check.** It makes a 5-minute test file first. After muxing, it checks that every dub has sound, is in sync and is well interleaved with the video inside the final file (audio written far away from its video makes some players go silent).
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
   - If it says the versions have **different cuts**, choose **Sync section by section** (also available in **Sync ▸ Sync section by section**, Ctrl+M). The waveform then shows the dub already in place, with every splice marked in red, and the Log lists each splice.
4. **Check the waveforms.** The movie is green and the dub is orange. Fine-tune by dragging the orange waveform or with the buttons.
5. **Choose the movie tracks to keep** in the **Movie** tab (for example, untick audio tracks or subtitles you don't want).
6. **Make test (5 min)** and listen in your player.
7. **Make final file.** The automatic check runs at the end.
8. *(Optional)* **Tools ▸ Verify integrity** proves that the original video, audio and subtitles are bit-identical.

Projects can be saved (`.eternaldub`) and reopened later.

---

## How it works (technical)

- **Analysis** uses a lightweight copy of the audio (mono, 8 kHz), used only to measure, never written to the output. Band-energy envelopes from the spectrum are cross-correlated with FFT. Several speed ratios are tested (PAL, 24 ↔ 23.976). The quick analysis reads about 1 minute plus four 40-second excerpts of the movie and searches for each one in a larger window of the dub.
- **Section sync** measures the delay every second (6-second windows, up to ±20 s around the main delay), picks the most likely path with a Viterbi search (the delay only changes when the evidence pays for the change, so stretches with dialogue only don't create false splices), then finds the exact point of each change frame by frame (20 ms) and, among near-ties, prefers a pause in the dub. The dub is decoded once on the same timeline used by the analysis, assembled with 8 ms crossfades at the splices (no clicks) and written to FLAC (24-bit for lossy sources, 16-bit for 16-bit sources).
- **Muxing** uses FFmpeg with `-c copy` and `-itsoffset` for the delay. Negative delays are applied with a copy-only trim of the dub. Dubs with speed correction or section sync go in as the FLAC described above, already on the movie's timeline. The movie's subtitles come in through a second read of the same file: without it, FFmpeg stops reading the dub while the subtitle track has no line, and the audio of that gap ends up far away from its video inside the file.
- **Cache:** waveforms are stored in `~/.eternaldub/cache`, so a movie is read in full only once. You can clear it in **Tools**.
- **Files:** `EternalDub_gui.py` (interface), `EternalDub_core.py` (reading, detection, muxing, checks), `detectar_atraso.py` (delay detection, also usable from the command line), `EternalDub_i18n.py` (translations).

Command line example:
```bash
python detectar_atraso.py MOVIE.mkv DUB.mkv --faixa-dub 1 --idioma en
# section-by-section map (reads both whole tracks):
python detectar_atraso.py MOVIE.mkv DUB.mp4 --mapa --idioma en
```

---

## Limitations

- **Section sync** depends on music and sound effects shared by both versions. In long stretches with dialogue only, the exact point of a change can be a few seconds off (in doubt, the program keeps the previous delay instead of guessing). The 5-minute test only covers the beginning, so listen to a few of the splices listed in the Log in the final file.
- Detection relies on music and sound effects shared by both versions. If the dub has a re-recorded soundtrack, use manual alignment or **Detect by video**.
- On slow disks (for example, an external HDD on USB 2.0), reading a UHD remux takes time. Saving the final file to a different disk helps a lot.

## Roadmap

- Editing the splice points by hand on the waveform
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
