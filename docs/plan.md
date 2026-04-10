# Phase 1 Plan

Core modules:
- extractor: extract wav and parse duration from ffmpeg stderr
- sync_engine: estimate offset and confidence via normalized cross-correlation
- length_checker: classify alignment/overflow using 0.5s tolerance
- exporter: build ffmpeg command for dual-track output with shift handling
