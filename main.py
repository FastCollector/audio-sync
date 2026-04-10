"""
Phase 1 CLI — audio-sync pipeline without GUI.

Usage:
    python main.py <video> <audio_b.wav> <output>

Extracts reference audio from the video, cross-correlates with audio B to
find the time offset, checks for length mismatches, then exports a new video
with all original audio tracks plus audio B as an additional synced track.
"""

import os
import sys

import soundfile as sf

from app.core.extractor import extract_audio
from app.core.sync_engine import compute_offset
from app.core.length_checker import check_lengths, MismatchType
from app.core.exporter import export

CONFIDENCE_THRESHOLD = 0.5


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: python main.py <video> <audio_b.wav> <output>")
        sys.exit(1)

    video_path, audio_b_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    # --- Step 1: extract reference audio from video ---
    print("Extracting reference audio from video...")
    ref_wav, video_duration = extract_audio(video_path)

    try:
        # --- Step 2: compute sync offset ---
        print("Computing sync offset...")
        offset, confidence = compute_offset(ref_wav, audio_b_path)

        direction = "after" if offset >= 0 else "before"
        print(f"  Offset:     audio B starts {abs(offset):.3f}s {direction} video start")
        print(f"  Confidence: {confidence:.3f}")

        if confidence < CONFIDENCE_THRESHOLD:
            print(
                f"\nWARNING: Sync confidence is low ({confidence:.3f})."
                f" The recordings may not match."
            )
            print("Proceed anyway? [y/N] ", end="", flush=True)
            if input().strip().lower() != "y":
                print("Aborted.")
                sys.exit(0)

        # --- Step 3: check for length mismatches ---
        audio_b_duration = sf.info(audio_b_path).duration
        mismatch = check_lengths(video_duration, audio_b_duration, offset)

        trim_audio_end: float | None = None
        trim_video_end: float | None = None

        if mismatch.mismatch_type == MismatchType.AUDIO_OVERFLOW:
            print(
                f"\nLength mismatch: audio B extends {mismatch.overflow_seconds:.2f}s"
                f" beyond video end."
            )
            print("Options:")
            print("  [t] Trim the extra audio (default)")
            print("  [b] Fill missing video with black screen  (not yet supported)")
            print("Choice [t]: ", end="", flush=True)
            choice = input().strip().lower() or "t"
            if choice == "b":
                print("Black screen fill is not yet implemented. Trimming audio instead.")
            # Keep only the audio B content that overlaps with the video.
            trim_audio_end = video_duration - max(offset, 0.0)

        elif mismatch.mismatch_type == MismatchType.VIDEO_OVERFLOW:
            audio_b_end = offset + audio_b_duration
            print(
                f"\nLength mismatch: video extends {mismatch.overflow_seconds:.2f}s"
                f" beyond the aligned audio B."
            )
            print(
                f"Audio B ends at {audio_b_end:.2f}s."
                f" Enter video out-point in seconds [{audio_b_end:.2f}]: ",
                end="",
                flush=True,
            )
            raw = input().strip()
            trim_video_end = float(raw) if raw else audio_b_end

        # --- Step 4: export ---
        print("\nExporting...")
        export(
            video_path,
            audio_b_path,
            offset,
            output_path,
            trim_audio_end=trim_audio_end,
            trim_video_end=trim_video_end,
        )
        print(f"Done: {output_path}")

    finally:
        os.unlink(ref_wav)


if __name__ == "__main__":
    main()
