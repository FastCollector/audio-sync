"""
Stage 6B smoke-test audit.

Walks `build_export_cmd` for three scenarios and prints PASS/FAIL per check:

    1. Zero-offset parity scenario (master == embedded, video_offset == 0):
       must keep -c:v copy, input-side -ss, and no [v_out] — byte-parity
       with the Stage 3 exporter.
    2. Master = external, positive video_offset (embedded lags master):
       must use tpad + re-encode, [v_out] map, output-side -t.
    3. Master = external, negative video_offset (embedded leads master):
       must use trim+setpts + re-encode, embedded audio atrim'd.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from _pyside_stubs import install_pyside6_stubs

install_pyside6_stubs()

from app.core.project import AudioTrack, Project, SourceKind, VideoAsset
from app.core.project_export import build_export_cmd


def _build_project(
    *,
    externals: list[tuple[str, float]] | None = None,
    master: str = "embedded",
    video_offset: float | None = None,
    trim_start: float | None = None,
    trim_end: float | None = None,
) -> tuple[Project, AudioTrack, list[AudioTrack]]:
    p = Project()
    p.video_asset = VideoAsset(
        path="video.mp4", duration_seconds=60.0, has_embedded_audio=True
    )
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="video.mp4",
        duration_seconds=60.0,
    )
    p.add_track(emb)
    p.link_embedded_audio(emb.id)

    ext_tracks: list[AudioTrack] = []
    for name, offset in externals or []:
        t = AudioTrack(
            display_name=name,
            source_kind=SourceKind.EXTERNAL,
            source_path=f"{name}.wav",
            duration_seconds=60.0,
        )
        p.add_track(t)
        ext_tracks.append(t)

    if master == "embedded":
        p.set_master(emb.id)
    else:
        target = next(t for t in ext_tracks if t.display_name == master)
        p.set_master(target.id)

    for t, (_, offset) in zip(ext_tracks, externals or []):
        t.offset_to_master = offset
    if video_offset is not None:
        emb.offset_to_master = video_offset

    p.project_trim_start = trim_start
    p.project_trim_end = trim_end
    return p, emb, ext_tracks


def report(name: str, ok: bool, notes: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {notes}" if notes else ""
    print(f"  [{status}] {name}{suffix}")
    return ok


def main() -> int:
    print("=" * 70)
    print("Stage 6B smoke-test audit: master != embedded export paths")
    print("=" * 70)
    all_ok = True

    # -----------------------------------------------------------------------
    print("\n[1] Zero-offset fast path — byte parity preserved")
    p, emb, (a,) = _build_project(
        externals=[("ext", 0.25)],
        master="embedded",
        trim_start=1.5,
        trim_end=10.0,
    )
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 0.8, a.id: 1.2},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    all_ok &= report("video_offset_to_master == 0", p.video_offset_to_master == 0.0)
    all_ok &= report("-c:v copy (no re-encode)", cmd[cmd.index("-c:v") + 1] == "copy")
    all_ok &= report("no [v_out] label anywhere", "[v_out]" not in cmd)
    all_ok &= report("input-side -ss before -i", cmd.index("-ss") < cmd.index("-i"))
    all_ok &= report("-ss value == 1.5", cmd[cmd.index("-ss") + 1] == "1.5")
    all_ok &= report("-t value == 8.5", cmd[cmd.index("-t") + 1] == "8.5")
    mapped = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-map"]
    all_ok &= report("video mapped as 0:v", "0:v" in mapped)

    # -----------------------------------------------------------------------
    print("\n[2] Master = external, positive video_offset (tpad branch)")
    p, emb, (a,) = _build_project(
        externals=[("ext", 0.0)],
        master="ext",
        video_offset=0.5,
    )
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    all_ok &= report("video_offset_to_master == 0.5", p.video_offset_to_master == 0.5)
    all_ok &= report(
        "filter has tpad shift",
        "tpad=start_duration=0.500000:start_mode=add:color=black" in filt,
    )
    all_ok &= report("filter emits [v_out]", "[v_out]" in filt)
    all_ok &= report("-c:v libx264", cmd[cmd.index("-c:v") + 1] == "libx264")
    all_ok &= report("-pix_fmt yuv420p", cmd[cmd.index("-pix_fmt") + 1] == "yuv420p")
    all_ok &= report("no input-side -ss", "-ss" not in cmd[: cmd.index("-i")])
    all_ok &= report(
        "embedded audio has adelay=500",
        "[0:1]volume=1.000000,adelay=500:all=1[va0_out]" in filt,
    )
    mapped = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-map"]
    all_ok &= report("video mapped as [v_out]", "[v_out]" in mapped and "0:v" not in mapped)

    # -----------------------------------------------------------------------
    print("\n[3] Master = external, negative video_offset (trim+setpts branch)")
    p, emb, (a,) = _build_project(
        externals=[("ext", 0.0)],
        master="ext",
        video_offset=-0.4,
        trim_start=1.0,
        trim_end=5.0,
    )
    cmd = build_export_cmd(
        p, "out.mp4",
        volumes={emb.id: 1.0, a.id: 1.0},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    filt = cmd[cmd.index("-filter_complex") + 1]
    video_chain = filt.split(";")[0]
    all_ok &= report("video_offset_to_master == -0.4", p.video_offset_to_master == -0.4)
    all_ok &= report(
        "video chain begins with trim=start=0.400000",
        video_chain.startswith("[0:v]trim=start=0.400000"),
    )
    all_ok &= report(
        "video chain contains master-timeline trim after shift",
        "trim=start=1.000000:end=5.000000" in video_chain,
    )
    all_ok &= report(
        "shift precedes master trim in chain",
        video_chain.index("trim=start=0.400000") < video_chain.index("trim=start=1.000000"),
    )
    all_ok &= report(
        "video chain has setpts reset",
        "setpts=PTS-STARTPTS" in video_chain,
    )
    all_ok &= report("-c:v libx264", cmd[cmd.index("-c:v") + 1] == "libx264")
    all_ok &= report(
        "output-side -t caps duration to 4.0",
        cmd[cmd.index("-t") + 1] == "4.0",
    )
    # Embedded audio effective offset = -0.4 - 1.0 = -1.4 → atrim=start=1.400000
    all_ok &= report(
        "embedded audio atrim=start=1.400000",
        "[0:1]volume=1.000000,atrim=start=1.400000,asetpts=PTS-STARTPTS[va0_out]" in filt,
    )

    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DONE — {}".format("ALL PASS" if all_ok else "FAILURES ABOVE"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
