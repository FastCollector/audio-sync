from app.core.ffmpeg_utils import _best_ffmpeg_error_line


def test_best_ffmpeg_error_line_skips_generic_tail() -> None:
    stderr = "Could not find tag for codec pcm_s16le in stream #1\nError opening output files: Invalid argument\n"
    assert _best_ffmpeg_error_line(stderr) == "Could not find tag for codec pcm_s16le in stream #1"


def test_best_ffmpeg_error_line_falls_back_when_only_generic() -> None:
    stderr = "Error opening output files: Invalid argument\n"
    assert _best_ffmpeg_error_line(stderr) == "Error opening output files: Invalid argument"
