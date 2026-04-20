"""
Export a multi-track Project to a video+multi-audio file.

Scope:
    - Exactly one VideoAsset with an embedded AudioTrack.
    - Master MAY be any track (embedded or external).
    - Any number (0..N) of EXTERNAL tracks on the master timeline.

Two code paths:
    1. Zero-offset fast path (Stage 3 parity):
       If master == embedded AND video_offset_to_master == 0, keep
       argv identical to the legacy exporter: input-side -ss for trim,
       -c:v copy, simple filter for embedded audio.
    2. Re-encode path (Stage 6B):
       When video_offset_to_master != 0, shift video onto the master
       timeline via a filter graph (tpad for positive, trim+setpts for
       negative), then apply project trim after the shift. Re-encode
       video with libx264. Embedded audio is shifted with adelay/atrim
       to stay aligned with the shifted video.
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
    assert project.video_asset is not None
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
    Pure command builder — no I/O, no probing.

    Branches on video_offset_to_master:
        - 0.0  → Stage 3 fast path (byte-parity with legacy exporter)
        - != 0 → video re-encode with shift + trim filter chain
    """
    _validate_scope(project)

    video = project.video_asset
    embedded = project.embedded_audio_track()
    assert video is not None and embedded is not None

    externals = [
        t for t in project.audio_tracks
        if t.source_kind is SourceKind.EXTERNAL
    ]

    trim_start = project.project_trim_start
    trim_end = project.project_trim_end
    video_offset = project.video_offset_to_master
    reencode = video_offset != 0.0

    filter_parts: list[str] = []

    if reencode:
        filter_parts.append(_video_shift_filter(video_offset, trim_start, trim_end))

    embedded_volume = volumes.get(embedded.id, 1.0)
    va_labels: list[str] = []
    for k, j in enumerate(video_audio_indices):
        label = f"[va{k}_out]"
        if reencode:
            # Embedded audio shares the video's source timeline; apply the
            # same shift (via its effective offset) + master-timeline trim.
            eff_offset = video_offset - (trim_start or 0.0)
            filter_parts.append(
                _audio_shift_filter(f"[0:{j}]", embedded_volume, eff_offset, label)
            )
        else:
            filter_parts.append(f"[0:{j}]volume={embedded_volume:.6f}{label}")
        va_labels.append(label)

    ex_labels: list[str] = []
    for i, ext in enumerate(externals):
        input_idx = i + 1
        label = f"[ex{i}_out]"
        vol = volumes.get(ext.id, 1.0)
        offset = (ext.offset_to_master or 0.0) - (trim_start or 0.0)
        filter_parts.append(
            _audio_shift_filter(f"[{input_idx}:a]", vol, offset, label)
        )
        ex_labels.append(label)

    filter_complex = ";".join(filter_parts)

    out = _ensure_extension(output_path)
    ext_lower = Path(out).suffix.lower()
    force_aac_for_video_audio = ext_lower in MP4_FAMILY

    if reencode:
        codec_args: list[str] = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        for k in range(len(video_audio_indices)):
            codec_args += [f"-c:a:{k}", "aac"]
    else:
        codec_args = ["-c:v", "copy"]
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
    if reencode:
        # Video trim is done in the filter; cap output duration so externals
        # don't extend past trim_end.
        if trim_end is not None:
            duration = trim_end - (trim_start or 0.0)
            output_trim_args = ["-t", f"{duration}"]
    else:
        if trim_start is not None:
            input_seek_args = ["-ss", str(trim_start)]
            if trim_end is not None:
                output_trim_args = ["-t", str(trim_end - trim_start)]
        elif trim_end is not None:
            output_trim_args = ["-to", str(trim_end)]

    input_args: list[str] = ["-i", video.path]
    for ext in externals:
        input_args += ["-i", ext.source_path]

    video_map = ["[v_out]"] if reencode else ["0:v"]

    return [
        ffmpeg, "-y",
        *input_seek_args,
        *input_args,
        "-filter_complex", filter_complex,
        "-map", *video_map,
        *[a for lbl in va_labels for a in ("-map", lbl)],
        *[a for lbl in ex_labels for a in ("-map", lbl)],
        *codec_args,
        *output_trim_args,
        "-avoid_negative_ts", "make_zero",
        out,
    ]


# ---------------------------------------------------------------------------


def _video_shift_filter(
    video_offset: float,
    trim_start: float | None,
    trim_end: float | None,
) -> str:
    """
    Build the [0:v] → [v_out] chain: first shift the video onto the master
    timeline (tpad for positive offset, trim+setpts for negative), then
    apply the project trim on the already-shifted master timeline.
    """
    chain: list[str] = []
    if video_offset > 0:
        chain.append(
            f"tpad=start_duration={video_offset:.6f}:start_mode=add:color=black"
        )
    elif video_offset < 0:
        chain.append(f"trim=start={abs(video_offset):.6f}")
        chain.append("setpts=PTS-STARTPTS")

    if trim_start is not None and trim_end is not None:
        chain.append(f"trim=start={trim_start:.6f}:end={trim_end:.6f}")
        chain.append("setpts=PTS-STARTPTS")
    elif trim_start is not None:
        chain.append(f"trim=start={trim_start:.6f}")
        chain.append("setpts=PTS-STARTPTS")
    elif trim_end is not None:
        chain.append(f"trim=end={trim_end:.6f}")
        chain.append("setpts=PTS-STARTPTS")

    return f"[0:v]{','.join(chain)}[v_out]"


def _audio_shift_filter(
    input_label: str, volume: float, offset: float, out_label: str
) -> str:
    """Apply volume, then adelay (offset >= 0) or atrim+asetpts (offset < 0)."""
    vol = f"volume={volume:.6f},"
    if offset >= 0:
        delay_ms = int(round(offset * 1000))
        return f"{input_label}{vol}adelay={delay_ms}:all=1{out_label}"
    start = abs(offset)
    return (
        f"{input_label}{vol}atrim=start={start:.6f},"
        f"asetpts=PTS-STARTPTS{out_label}"
    )


def _validate_scope(project: Project) -> None:
    if project.video_asset is None:
        raise InvalidProjectState("export requires a video asset")
    embedded = project.embedded_audio_track()
    if embedded is None:
        raise InvalidProjectState("export requires an embedded audio track linked")
    for t in project.audio_tracks:
        if t.id == embedded.id:
            continue
        if t.source_kind is not SourceKind.EXTERNAL:
            raise InvalidProjectState(
                "export only supports one embedded track plus external tracks"
            )
