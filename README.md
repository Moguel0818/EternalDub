<p align="center">
  <img src="logo.png" alt="EternalDub" width="128">
</p>

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
- **Edit the splices by hand.** In section-by-section sync, every splice is a red line on the waveform: drag it, nudge it with the arrow keys (10 ms; Shift 100 ms; Ctrl 1 ms), type its exact time or amount, add a splice anywhere (right-click) or remove a false one. Ctrl+drag slides only one section. A magnet snaps splices into the pauses of the dub, and the **Splices** tab tells you whether each one falls in a pause or in the middle of speech or music, so a line is never cut by accident. Everything has Undo/Redo.
- **Listen inside the program.** Press **F8** to hear the dub exactly as it will end up in the file (delay, speed correction and splices applied), the movie's reference audio, or both mixed (if their music and effects match, the sync is right). Click the ruler to choose where to start; **F9** plays 3 seconds before and after the selected splice. No test file needed.
- **Several dubs at once,** from one or many files, each with its own name, language and default flag.
- **Organize the final file.** The **Final file** tab lists every track that can go into the MKV (the movie's own, the dubs and the added subtitles) in the order they will have: tick what goes in (**Check all** / **Uncheck all** buttons), change the order with **Up/Down** and pick the default audio and subtitle. With the interface in Portuguese it starts in the PT-BR BDRemux layout: 1) PT-BR audio, 2) the original-language audio, 3) PT-BR subtitles. It can also just reorganize a movie, with no dub at all.
- **Add subtitles** like you add dubs: `.srt`, `.ass`, `.ssa`, `.vtt`, `.sup`, `.idx/.sub` or a subtitle track from another MKV/MP4, each with a name, language, delay and *forced* flag. Text subtitles in Windows-1252 or UTF-16 are converted to UTF-8 so accents come out right.
- **Music videos: the high-quality song in place of the poor sound.** Open the music video (VHS, TV, internet) and use **Add music** with the FLAC or MP3 of the same song (from a CD, a digitized LP...). EternalDub measures the delay to the millisecond, finds small speed differences (tape, capture card, NTSC/PAL) and corrects them like a tape (resampling: exact timing and no artifacts), makes the song start and end as in the clip (fade-in, fade-out or cut) and ends it together with the video. The clip's original sound stays in the file as a second track.
- **Test and automatic check.** It makes a 5-minute test file first. After muxing, it checks that every dub has sound, is in sync and is well interleaved with the video inside the final file (audio written far away from its video makes some players go silent).
- **All in one place.** Detection, manual adjustment, muxing and verification happen in a single window.
- **Interface languages:** Portuguese (Brazil), English, Spanish, French, Italian and German. Each language is a plain `.json` file in `idiomas/`, so anyone can add another one without programming.
- **Runs without Python.** A standalone Windows program (`EternalDub.exe`) is available; see Installation.

---

## Requirements

| What | Notes |
|---|---|
| **Windows 10/11** | Tested. Linux/macOS should work by running `EternalDub_gui.py` directly, but this hasn't been tested yet. |
| **FFmpeg** | `ffmpeg` and `ffprobe`: in the PATH (on Windows: `winget install Gyan.FFmpeg`) **or next to `EternalDub.exe`** (or `EternalDub_gui.py`). EternalDub also looks in the folders where winget puts it. |
| **Python 3.10+** | Only to run from source (not needed for the standalone program). From [python.org](https://www.python.org/downloads/); check **"Add python.exe to PATH"**. 3.12 or 3.13 recommended. |
| **numpy, PySide6** | Only to run from source. Installed automatically by `Iniciar_EternalDub.bat` on the first run (or `pip install -r requirements.txt`). |

---

## Installation

**Option A: standalone program (no Python needed)**
1. On the **Releases** page, download `EternalDub-Windows-pasta.zip` (or `EternalDub-Windows-um-arquivo.zip`, a single `.exe` that opens a bit slower).
2. Extract it and double-click **`EternalDub.exe`**.
3. Make sure FFmpeg is available (see Requirements).

> The program is not code-signed, so Windows SmartScreen may warn on the first run: click **More info ▸ Run anyway**.

**Option B: download the source (needs Python)**
1. Click **Code ▸ Download ZIP** on this page.
2. Extract it to a new folder.
3. Double-click **`Iniciar_EternalDub.bat`**.

**Option C: git**
```bash
git clone https://github.com/Moguel0818/EternalDub.git
cd EternalDub
pip install -r requirements.txt
python EternalDub_gui.py
```

The interface opens in your system language when a translation exists (otherwise English). You can change it in **Options ▸ Idioma / Language**.

**Building the standalone program yourself**
- With Python installed: double-click **`Gerar_EXE.bat`** (the result is in `dist\EternalDub\`).
- Without installing anything: on GitHub, go to **Actions ▸ Gerar EternalDub.exe ▸ Run workflow**; in about 5 minutes the zip appears under **Artifacts**. Publishing a version tag (e.g. `v1.4`) also attaches the zips to **Releases**.

---

## How to use

1. **Open movie.** Choose the high-quality release, or drag it into the window.
2. **Add dub.** Choose the file(s) that contain the dub: an MKV/MP4 with video, or audio only (MP3, AC3, E-AC3, DTS, FLAC, WAV…). If a file has several audio tracks, tick the ones that are dubs.
3. **Detect delay (F5).** The result appears in the list and in the **Log** tab.
   - *Tip:* if the dub's file also contains the original-language track (e.g. English), use **Sync ▸ Detect using another track of the file** with that track. It's more reliable and applies the result to every dub from that file.
   - If it says the versions have **different cuts**, choose **Sync section by section** (also available in **Sync ▸ Sync section by section**, Ctrl+M). The waveform then shows the dub already in place, with every splice marked in red, and the Log lists each splice.
4. **Check the waveforms.** The movie is green and the dub is orange. Fine-tune by dragging the orange waveform or with the buttons.
   - **Listen:** click the ruler to put the blue line where you want to start and press **F8** (again to stop). Choose what you hear in the toolbar: the dub already synced, the movie, or both together.
   - **Fine-tune the splices** (when you used section sync): drag the red lines, use the arrow keys, or pick one in the **Splices** tab (time, amount, *Find pause*, *Listen (F9)*). Right-click the waveform to add a splice or remove a wrong one. **Ctrl+Z / Ctrl+Y** undo and redo.
5. **Organize the final file** in the **Final file** tab: tick the tracks that go in, change the order with **Up/Down**, pick the default track, and add subtitles with **Add subtitle...** (Ctrl+L) or by dragging `.srt` files into the window.
6. **Make test (5 min)** and listen in your player.
7. **Make final file.** The automatic check runs at the end.
8. *(Optional)* **Tools ▸ Verify integrity** proves that the original video, audio and subtitles are bit-identical.

Projects can be saved (`.eternaldub`) and reopened later.

### Music videos (the high-quality song in place of the poor sound)

1. **Open movie**: choose the music video (for example, the capture of the VHS tape).
2. **Add music** (Ctrl+Shift+M): choose the FLAC, MP3, M4A, OGG or WAV of the same song. Dragging the file onto the window also works: files with artist or album tags come in as music by themselves. The track gets the song's name (tags) and the final file uses the **music video layout**: 1) the song (plays automatically), 2) the clip's original sound.
3. **Detect delay (F5)**: reads both files in full (they are short) and measures more strictly than for a dub. If the speed differs (a tape running a little slow, NTSC 0.1%, PAL 4%), choose **Correct like a tape** (recommended: the pitch changes with it, 0.1% = 1.7 cents, inaudible; the timing is exact and the sound has no artifacts) or **Correct keeping the pitch**.
4. Right after that, EternalDub measures **the start and end**: how the clip makes the song come in and go out (fade-in, fade-out, hard cut, even with the TV announcer talking over it). The high-quality song does the same, and the orange waveform shows the volume it will have. The middle of the song is never touched. You can turn it off in **Follow the clip at the start and the end** or measure again.
5. Listen with **F8** (choose *Movie + dub* to hear both together) and use **Make test** / **Make final file**. The suggested file name ends in `_music`.

If the clip uses another edit of the song (one chorus less, an extra pause), detection says so and **section-by-section sync** assembles the song like the clip. When the song fits in the video with no fades and no speed correction, it goes in by exact copy (the original file, not re-encoded); otherwise only the song becomes FLAC (lossless).

---

## How it works (technical)

- **Analysis** uses a lightweight copy of the audio (mono, 8 kHz), used only to measure, never written to the output. Band-energy envelopes from the spectrum are cross-correlated with FFT. Several speed ratios are tested (PAL, 24 ↔ 23.976). The quick analysis reads about 1 minute plus four 40-second excerpts of the movie and searches for each one in a larger window of the dub.
- **Section sync** measures the delay every second (6-second windows, up to ±20 s around the main delay), picks the most likely path with a Viterbi search (the delay only changes when the evidence pays for the change, so stretches with dialogue only don't create false splices), then finds the exact point of each change frame by frame (20 ms) and, among near-ties, prefers a pause in the dub. The dub is decoded once on the same timeline used by the analysis, assembled with 8 ms crossfades at the splices (no clicks) and written to FLAC (24-bit for lossy sources, 16-bit for 16-bit sources).
- **Muxing** uses FFmpeg with `-c copy` and `-itsoffset` for the delay. Negative delays are applied with a copy-only trim of the dub; since a copy can only cut between audio frames, the leftover part of the frame is given back with `-itsoffset` (exact, within 0.5 ms). Dubs with speed correction or section sync go in as the FLAC described above, already on the movie's timeline. The movie's subtitles come in through a second read of the same file: without it, FFmpeg stops reading the dub while the subtitle track has no line, and the audio of that gap ends up far away from its video inside the file.
- **Track layout:** the order of the `-map` options is the order of the tracks in the MKV (videos, then audios, then subtitles). Every audio and subtitle track gets explicit flags (`-disposition`): exactly one default audio, at most one default subtitle, and the movie's *forced*, *commentary*, *hearing impaired* and *visual impaired* flags are kept; `-default_mode infer_no_subs` stops the MKV from turning a subtitle on by itself. External subtitles are separate inputs: a positive delay uses `-itsoffset`, a negative one skips the beginning of the subtitle (`-ss`). MP4 subtitles (`mov_text`) become SRT, the only change the MKV requires. The integrity check matches every original track by hash wherever it ended up.
- **Splice editing** (`EternalDub_emendas.py`): a section map is edited as a list of splices (time, silence inserted, piece removed). Moving a splice never changes the alignment of any section, only where one alignment hands over to the next; the dub always moves forward in time and no section is shorter than 50 ms. A splice whose amount is about 0 ms is removed (it would only leave a 16 ms dip in the sound). The *sound at the splice* check measures the dub's level around the cut point (the removed piece plus 50 ms on each side), and the magnet looks for the nearest spot where that level is a pause. A map that was not edited is saved exactly as it came.
- **Preview** (`EternalDub_audio.py`): it uses the same assembler as the final file (same delay, speed correction and 8 ms crossfades). FFmpeg starts at the blue line (`-ss`) and 0.25 s blocks are played as they are decoded (mono, 48 kHz). The automated tests compare it with the real output: identical samples without speed correction, within 1 ms with it (the `atempo` filter picks its own overlap points).
- **Music videos** (`EternalDub_musica.py` and `detectar_atraso.analisar_musica`): the song and the clip's sound are the same recording, so detection compares sections of the **clip** (1/15 of its length, 8 to 30 s) with the song, near where they should be (±5 s) and, if they don't match, across the whole song (different edit). Sections without the song (speech, station idents) simply don't count. A robust line (Theil-Sen) through the sections gives the delay and the exact speed, with a 25 ms tolerance. Speed is corrected by resampling (`asetrate` on the audio brought up to 16 times its rate, so rounding the rate never costs more than 0.5 ms). The start and end are measured from the coherent gain ⟨clip, song⟩/⟨song, song⟩ in 100 ms frames (80 to 1000 Hz, zero-phase filter with smooth edges, ±2 ms search for tape wow): speech and hiss don't look like the song and barely count. A linear, cosine or exponential curve is fitted; a hard cut is located with 20 ms frames. The volume curve is applied by the same assembler as the final file and the preview.
- **Cache:** waveforms are stored in `~/.eternaldub/cache`, so a movie is read in full only once. You can clear it in **Tools**.
- **Files:** `EternalDub_gui.py` (interface), `EternalDub_core.py` (reading, detection, muxing, checks), `EternalDub_emendas.py` (splice editing), `EternalDub_audio.py` (preview), `EternalDub_musica.py` (music videos: start/end, name from tags), `detectar_atraso.py` (delay detection, also usable from the command line), `EternalDub_i18n.py` + `idiomas/*.json` (translations), `EternalDub.spec` + `Gerar_EXE.bat` + `.github/workflows` (standalone program), `tests/` (automated tests).

Command line example:
```bash
python detectar_atraso.py MOVIE.mkv DUB.mkv --faixa-dub 1 --idioma en
# section-by-section map (reads both whole tracks):
python detectar_atraso.py MOVIE.mkv DUB.mp4 --mapa --idioma en
# a song in a music video:
python detectar_atraso.py CLIP.mkv SONG.flac --musica --idioma en
```

---

## Limitations

- **Section sync** depends on music and sound effects shared by both versions. In long stretches with dialogue only, the exact point of a change can be a few seconds off (in doubt, the program keeps the previous delay instead of guessing). The 5-minute test only covers the beginning, so listen to a few of the splices listed in the Log in the final file.
- Detection relies on music and sound effects shared by both versions. If the dub has a re-recorded soundtrack, use manual alignment or **Detect by video**.
- On slow disks (for example, an external HDD on USB 2.0), reading a UHD remux takes time. Saving the final file to a different disk helps a lot.
- The preview is mono (FFmpeg's downmix). With speed correction the timing matches the final file to about 1 ms, but the waveform is not sample-identical.
- **Music videos:** where the clip has sound that is not the song (speech in the intro, effects), the music track is silent; the clip's original sound stays as the second track. The start and end copied from the clip are a smooth curve: a very irregular (hand-made) fade comes out approximate, and the start of a long fade can be off by about 1 s when the two masters have very different dynamics (the end of the fade stays within 1 s, a hard cut within about 10 ms).
- While you listen, the waveform reading pauses (one disk, one job) and continues when you stop.
- The Windows program is not code-signed, and it was built by the project's automatic workflow: please report anything odd.

## Roadmap

- Stereo / 5.1 preview (it is mono for now)
- Code-signed `.exe` and an update notice
- Testing on Linux and macOS
- More interface languages (send yours: it is just a `.json` file)

---

## Contributing

Issues and pull requests are welcome, especially from people with experience in audio/DSP, FFmpeg or desktop UI.

- **Bugs:** open an [Issue](https://github.com/Moguel0818/EternalDub/issues) and paste the contents of the **Log** tab (plus `~/.eternaldub/erro.log`, if it exists).
- **Translations:** copy `idiomas/en.json` to `idiomas/<code>.json` (e.g. `fr.json`), change `codigo`, `nome` and `tradutores`, and translate the values. The language appears by itself in **Options ▸ Idioma / Language**. Run `python tests/test_idiomas.py` to see what is missing or wrong, and open a pull request.
- **Tests:** `python -m unittest discover -s tests -t .` (needs FFmpeg; the interface tests run without a screen). They check the splice editor, the preview against the real output, the translations, the main window and music videos (with a synthetic song and tape sound).
- Everyone who helps is credited in [CREDITS.md](CREDITS.md) and in the program's **About** window.

## Transparency

The code was written with AI assistance (Claude, by Anthropic). The project was conceived, directed and tested by the author on real files. Reviews from experienced developers are very welcome.

## Legal note

EternalDub does not include, download or distribute any media (nor FFmpeg). Use it only with files you have the right to use.

## License

[MIT](LICENSE). EternalDub calls FFmpeg as an external program and uses PySide6 and NumPy as libraries; none of them is included here, and each keeps its own license.
