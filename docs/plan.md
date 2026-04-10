# audio-sync: Project Plan

## Project Overview

A local desktop tool for music recording workflows that automatically synchronizes an external audio recording (WAV) with a video file. The core value is **fully automatic sync** — no manual waveform scrubbing. The user imports two files and gets a synced export.

**Assumed context:** Music recordings produce clean, high-amplitude waveforms, making cross-correlation-based sync reliable and accurate without human intervention.

---

## Assumptions (stated explicitly)

| Assumption | Rationale |
|---|---|
| Desktop GUI app, not CLI | The workflow (import → preview → export) implies interactive use |
| Python stack | Best fit for audio signal processing; FFmpeg handles video I/O |
| Windows primary target | Workspace is Windows; Python is cross-platform so Linux/macOS come nearly free |
| Export keeps both audio tracks | Audio A (original from video) + audio B (external WAV) as separate tracks in output |
| Preview includes video + audio | Full video preview via QMediaPlayer — confirmed |
| FFmpeg bundled via `imageio-ffmpeg` | Ships its own binary; path exposed programmatically — makes PyInstaller packaging clean |
| Packaged as Windows .exe | PyInstaller; no Python install required on target machine |

---

## Tech Stack

### Core

| Component | Choice | Reasoning |
|---|---|---|
| Language | Python 3.11+ | Best ecosystem for audio DSP; cross-platform |
| Audio extraction & export | FFmpeg via `imageio-ffmpeg` + `subprocess` | `imageio-ffmpeg` ships FFmpeg binary; path works inside PyInstaller bundle |
| Sync algorithm | `scipy.signal.correlate` | Cross-correlation is the standard approach (same as PluralEyes); `librosa` for loading audio |
| Audio loading | `librosa` + `soundfile` | Reliable WAV/audio decoding; resamples to common rate for correlation |
| GUI framework | PySide6 (Qt6) | Mature, good media playback support via `QMediaPlayer` |
| Video preview | PySide6 `QMediaPlayer` + `QVideoWidget` | Native Qt video playback; no extra dep |
| Audio preview mixing | `sounddevice` | Real-time per-track volume control; simpler than Qt audio for mixing two streams |
| Packaging | PyInstaller | Bundles Python + deps + FFmpeg binary into a single Windows .exe |

### Why not Electron?
Electron gives better UI flexibility but audio DSP would need a Python subprocess anyway. The boundary complexity isn't worth it for this tool's scope.

### Why not tkinter?
No native video playback widget. Would require embedding VLC or similar — more complexity than PySide6 provides out of the box.

---

## Architecture

```
audio-sync/
├── main.py                  # Entry point, launches GUI
├── app/
│   ├── ui/
│   │   ├── main_window.py   # Top-level window, ties modules together
│   │   ├── import_panel.py  # File import controls
│   │   ├── preview_panel.py # Video/audio preview + volume sliders
│   │   └── export_panel.py  # Export controls + progress
│   ├── core/
│   │   ├── extractor.py     # Extract audio from video via FFmpeg
│   │   ├── sync_engine.py   # Cross-correlation, returns offset in seconds
│   │   ├── length_checker.py# Detect & classify length mismatches
│   │   └── exporter.py      # Apply offset + export via FFmpeg
│   └── utils/
│       └── ffmpeg.py        # FFmpeg subprocess wrapper
├── docs/
│   └── plan.md
├── requirements.txt
└── CLAUDE.md
```

### Data flow

```
[Video A] ──► extractor.py ──► ref_audio.wav ──┐
                                                ├──► sync_engine.py ──► offset (seconds)
[Audio B (WAV)] ────────────────────────────────┘
                                                         │
                                                         ▼
                                              length_checker.py
                                              (compare durations)
                                                         │
                                              ┌──────────┴──────────┐
                                         mismatch?              no mismatch
                                              │                      │
                                         ask user             exporter.py
                                              │                (ffmpeg mux)
                                         user decides               │
                                              └──────────┬──────────┘
                                                         ▼
                                                   [synced output]
```

---

## Core Modules

### `extractor.py`
- Input: video file path
- Output: temporary WAV file (mono, 44.1kHz or original rate)
- Uses FFmpeg to strip audio track
- Acceptance: extracted WAV is playable and duration matches video

### `sync_engine.py`
- Input: two audio file paths (reference from video, external WAV)
- Output: `(offset_seconds: float, confidence: float)` — offset is positive if audio B starts after video A; confidence is the peak-to-noise ratio of the cross-correlation (0–1 scale)
- Algorithm: load both at same sample rate → compute cross-correlation → find peak → convert sample offset to seconds; confidence = peak value / mean of top-10% of correlation values
- Acceptance: offset accurate to within ±1 frame (±42ms at 24fps) on clean music recordings; confidence > 0.8 for clean recordings, reliably < 0.5 for unrelated audio

### `length_checker.py`
- Input: video duration, audio B duration, computed offset
- Output: one of three states:
  1. **Aligned** — audio B fits within video after offset applied
  2. **Audio overflow** — audio B extends beyond video end → ask user: trim or black-screen fill
  3. **Video overflow** — video extends beyond aligned audio end → ask user to select final video range
- Acceptance: correctly classifies all three states; never silently clips or drops content

### `exporter.py`
- Input: video file, audio B file, offset (seconds), user's mismatch decision
- Output: exported video file (same container as input) with **two audio tracks**: track 0 = original video audio (A), track 1 = external audio (B) at computed offset
- FFmpeg mapping: `-map 0:v -map 0:a -map 1:a` with `adelay` filter on audio B stream; video stream is copied, not re-encoded
- If offset is negative (audio B starts before video): prepend silence to audio A instead of negative delay on B
- Acceptance: output plays in VLC with both audio tracks selectable; video codec unchanged; audio B is in sync

### `preview_panel.py`
- Two volume sliders: original video audio, external audio B
- Video playback synced to computed offset
- Play/pause/seek controls
- Acceptance: both audio tracks are audible independently; video plays at correct time

---

## Feature Breakdown & Acceptance Criteria

### F1: Import
- User can select a video file (MP4, MOV, MKV, AVI)
- User can select an audio file (WAV; MP3/FLAC as stretch)
- Invalid files show a clear error message
- **AC:** Both file paths displayed in UI after selection

### F2: Auto Sync
- Single "Sync" button triggers extraction + cross-correlation
- Progress indicator shown during processing
- Computed offset displayed (e.g., "Audio B starts 2.34s after video")
- If confidence < 0.5: show a clearly visible warning ("Sync quality is low — the recordings may not match. Proceed anyway?"); user must explicitly confirm to continue
- **AC:** Offset computed without user input; result shown in under 30s for a 10-minute recording; low-confidence result never silently proceeds to export

### F3: Length Mismatch Detection & Resolution
- If audio overflows: modal dialog "External audio extends 4.2s beyond video end. Trim the extra audio, or fill video with black screen?"
- If video overflows: UI lets user drag or type the video out-point
- If no mismatch: proceed silently
- **AC:** No content is silently clipped; user is always informed of mismatch

### F4: Preview
- Preview panel shows video with synced audio B mixed in
- Independent volume sliders for video audio track and audio B
- **AC:** Adjusting either slider changes volume in real-time without restart

### F5: Export
- User selects output file path
- Progress bar during export
- Success/failure notification
- **AC:** Exported file contains two audio tracks (A = original video audio, B = external audio at computed offset); video codec/container unchanged (no re-encode); both tracks selectable in VLC

---

## Implementation Phases

### Phase 1 — Core pipeline (no GUI)
Build and validate the sync engine as a script.

```
1. extractor.py: extract audio from test video    → verify: output WAV matches video duration
2. sync_engine.py: cross-correlate two audios     → verify: offset matches known ground truth (test with hand-shifted WAV)
3. length_checker.py: classify mismatch states    → verify: all 3 states detected correctly
4. exporter.py: apply offset, export              → verify: VLC plays result in sync
```

**Exit criterion:** CLI script takes video + WAV, prints offset, exports synced file.

### Phase 2 — Basic GUI shell
Wire Phase 1 pipeline into a minimal PySide6 window.

```
1. Import panel with file pickers                 → verify: paths appear in UI
2. "Sync" button runs pipeline, shows offset      → verify: offset displayed after run
3. Mismatch dialogs appear when needed            → verify: both overflow cases trigger correct dialog
4. Export button triggers exporter                → verify: file written to chosen path
```

**Exit criterion:** End-to-end workflow runs without touching the terminal.

### Phase 3 — Preview player
Add the preview panel with video + audio mixing.

```
1. QMediaPlayer shows video at correct offset     → verify: video plays from right timestamp
2. Volume sliders control each track independently → verify: muting one track silences only it
3. Play/pause/seek work correctly                 → verify: seek doesn't desync audio
```

**Exit criterion:** User can audition the sync before committing to export.

### Phase 4 — Polish & edge cases
- Drag-and-drop file import
- Keyboard shortcuts (Space = play/pause)
- Error handling for corrupt files, missing FFmpeg
- Support MP3/FLAC as audio B input

---

## Decisions Log

| # | Decision |
|---|---|
| 1 | Preview: full video playback via QMediaPlayer |
| 2 | Packaging: PyInstaller .exe; FFmpeg bundled via `imageio-ffmpeg` |
| 3 | Export: keep both audio tracks (A + B) as separate tracks in output container |
| 4 | Confidence score: warn user and require confirmation if score < 0.5; never silent |
| 5 | Multiple audio tracks: keep all original audio tracks from video (`-map 0:a`), append audio B as an additional track |

## Open Questions / Decisions Needed

_All decisions resolved. No open questions remaining._
