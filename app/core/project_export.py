"""
Stage 3: export a multi-track Project to a video+multi-audio file.

Scope (locked, out-of-range projects raise):
    - Exactly one VideoAsset with an embedded AudioTrack.
    - Master MUST be the embedded track (so master timeline == video timeline).
    - video_offset_to_master MUST be 0 (so -c:v copy stays valid).
    - Any number (0..N) of EXTERNAL tracks laid out on the master timeline.

Export-only rules:
    - Embedded audio reuses the video input (no separate file).
    - External tracks use their source_path. extracted_wav_path is ignored
      here — that belongs to the sync/cache path, not export.
"""

from __future__ import annotations

from pathlib import Path

from app.core.exporter import _ensure_extension, _find_audio_stream_indices
from app.core.ffmpeg_utils import get_ffmpeg_executable, run_ffmpeg
from app.core.project import InvalidProjectState, Project, SourceKind

MP4_FAMILY = {".mp4", ".m4v", ".ismv"}


def export_project(
    project: Project,
    output_path: str,
    *,
    volumes: dict[str, float],
) -> None:
    """Validate scope, probe video audio streams, build argv, run ffmpeg."""
    _validate_scope(project)
    ffmpeg = get_ffmpeg_executable()
    assert project.video_asset is not None  # checked in _validate_scope
    indices = _find_audio_stream_indices(ffmpeg, project.video_asset.path)
    cmd = build_export_cmd(
        project,
        output_path,
        volumes=volumes,
        video_audio_indices=indices,
        ffmpeg=ffmpeg,
    )
    run_ffmpeg(cmd)


def build_export_cmd(
    project: Project,
    output_path: str,
    *,
    volumes: dict[str, float],
    video_audio_indices: list[int],
    ffmpeg: str,
) -> list[str]:
    """
    Pure command builder — no I/O, no probing. Given the project and the list
    of video audio stream indices (as probed externally), return the ffmpeg argv.

    Raises InvalidProjectState if the project is outside Stage 3 scope.
    """
    _validate_scope(project)

    video = project.video_asset
    embedded = project.embedded_audio_track()
    assert video is not None and embedded is not None  # _validate_scope

    externals = [
        t for t in project.audio_tracks
        if t.source_kind is SourceKind.EXTERNAL
    ]

    trim_start = project.project_trim_start
    trim_end = project.project_trim_end

    filter_parts: list[str] = []

    embedded_volume = volumes.get(embedded.id, 1.0)
    va_labels: list[str] = []
    for k, j in enumerate(video_audio_indices):
        label = f"[va{k}_out]"
        filter_parts.append(f"[0:{j}]volume={embedded_volume:.6f}{label}")
        va_labels.append(label)

    ex_labels: list[str] = []
    for i, ext in enumerate(externals):
        input_idx = i + 1
        label = f"[ex{i}_out]"
        vol = volumes.get(ext.id, 1.0)
        # Position on master timeline, shifted by the project trim so the
        # export's t=0 aligns with project_trim_start.
        offset = (ext.offset_to_master or 0.0) - (trim_start or 0.0)
        filter_parts.append(_external_filter(input_idx, vol, offset, label))
        ex_labels.append(label)

    filter_complex = ";".join(filter_parts)

    out = _ensure_extension(output_path)
    ext_lower = Path(out).suffix.lower()
    force_aac_for_video_audio = ext_lower in MP4_FAMILY

    codec_args: list[str] = ["-c:v", "copy"]
    for k in range(len(video_audio_indices)):
        codec_args += [
            f"-c:a:{k}",
            "aac" if force_aac_for_video_audio else "copy",
        ]
    n_va = len(video_audio_indices)
    for i in range(len(externals)):
        codec_args += [f"-c:a:{n_va + i}", "aac"]

    input_seek_args: list[str] = []
    output_trim_args: list[str] = []
    if trim_start is not None:
        input_seek_args = ["-ss", str(trim_start)]
        if trim_end is not None:
            output_trim_args = ["-t", str(trim_end - trim_start)]
    elif trim_end is not None:
        output_trim_args = ["-to", str(trim_end)]

    input_args: list[str] = ["-i", video.path]
    for ext in externals:
        input_args += ["-i", ext.source_path]

    return [
        ffmpeg, "-y",
        *input_seek_args,
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        *[a for lbl in va_labels for a in ("-map", lbl)],
        *[a for lbl in ex_labels for a in ("-map", lbl)],
        *codec_args,
        *output_trim_args,
        "-avoid_negative_ts", "make_zero",
        out,
    ]


# ---------------------------------------------------------------------------


def _external_filter(input_idx: int, volume: float, offset: float, label: str) -> str:
    vol = f"volume={volume:.6f},"
    if offset >= 0:
        delay_ms = int(round(offset * 1000))
        return f"[{input_idx}:a]{vol}adelay={delay_ms}:all=1{label}"
    start = abs(offset)
    return (
        f"[{input_idx}:a]{vol}atrim=start={start:.6f},"
        f"asetpts=PTS-STARTPTS{label}"
    )


def _validate_scope(project: Project) -> None:
    if project.video_asset is None:
        raise InvalidProjectState("export requires a video asset")
    embedded = project.embedded_audio_track()
    if embedded is None:
        raise InvalidProjectState("export requires an embedded audio track linked")
    if project.master_track_id != embedded.id:
        raise InvalidProjectState(
            "export requires master to be the embedded track (Stage 3 scope)"
        )
    if project.video_offset_to_master != 0.0:
        raise InvalidProjectState(
            "export requires video_offset_to_master == 0 (Stage 3 scope)"
        )
    for t in project.audio_tracks:
        if t.id == embedded.id:
            continue
        if t.source_kind is not SourceKind.EXTERNAL:
            raise InvalidProjectState(
                "export only supports one embedded + external tracks (Stage 3 scope)"
            )
