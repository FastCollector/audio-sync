"""
Stage 6A smoke-test audit.

Can't drive the Qt UI headless, so this walks the Stage 6A multi-track
code paths with stubbed sync/export and verifies:

    1. Project data model holds multi-external state correctly.
    2. sync_all_to_master computes offsets for every non-master track.
    3. Master change via set_master invalidates offsets (requires re-sync).
    4. Removing a non-master track preserves everyone else's offsets.
    5. _build_track_specs produces the right effective_offset for each
       track regardless of who the master is.
    6. _can_export gating: True only when master == embedded AND all
       non-master offsets are computed.
    7. build_export_cmd handles 2 externals with distinct offsets
       (positive adelay + negative atrim branches).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# PySide6 is not needed for the MainWindow helpers we exercise, but the
# module import pulls Qt. Install the headless stubs.
sys.path.insert(0, str(ROOT / "tests"))
from _pyside_stubs import install_pyside6_stubs

install_pyside6_stubs()

from app.core.project import AudioTrack, Project, SourceKind, VideoAsset
from app.core.project_export import build_export_cmd
from app.core.project_sync import sync_all_to_master
from app.ui.main_window import _build_track_specs
from app.ui.main_window import MainWindow  # noqa: F401 — ensures import path is clean


# ---------------------------------------------------------------------------
# Helpers


def _build_multi_project(
    video_dur: float = 30.0,
    ext1_dur: float = 28.0,
    ext2_dur: float = 25.0,
) -> tuple[Project, AudioTrack, AudioTrack, AudioTrack]:
    p = Project()
    p.video_asset = VideoAsset(
        path="video.mp4", duration_seconds=video_dur, has_embedded_audio=True
    )
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="video.mp4",
        duration_seconds=video_dur,
    )
    ext1 = AudioTrack(
        display_name="ext1",
        source_kind=SourceKind.EXTERNAL,
        source_path="ext1.wav",
        duration_seconds=ext1_dur,
    )
    ext2 = AudioTrack(
        display_name="ext2",
        source_kind=SourceKind.EXTERNAL,
        source_path="ext2.wav",
        duration_seconds=ext2_dur,
    )
    p.add_track(emb)
    p.add_track(ext1)
    p.add_track(ext2)
    p.link_embedded_audio(emb.id)
    p.set_master(emb.id)
    return p, emb, ext1, ext2


def _stub_compute(offsets_by_path: dict[str, float], confidence: float = 0.9):
    """Return a compute_fn that yields deterministic offsets by track_path."""
    def _fn(master_path: str, track_path: str) -> tuple[float, float]:
        return (offsets_by_path.get(track_path, 0.0), confidence)
    return _fn


def _identity_resolver(project: Project):
    def _resolve(track: AudioTrack) -> str:
        return track.source_path
    return _resolve


def report(name: str, ok: bool, notes: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {notes}" if notes else ""
    print(f"  [{status}] {name}{suffix}")
    return ok


# ---------------------------------------------------------------------------


def main() -> int:
    print("=" * 70)
    print("Stage 6A smoke-test audit: multi-track flow code paths")
    print("=" * 70)
    all_ok = True

    # -----------------------------------------------------------------------
    print("\n[1] Project data model holds multi-external state")
    p, emb, ext1, ext2 = _build_multi_project()
    all_ok &= report("3 tracks on project", len(p.audio_tracks) == 3)
    all_ok &= report("embedded linked to video", p.embedded_audio_track() is emb)
    all_ok &= report("master == embedded after set_master", p.master_track_id == emb.id)
    all_ok &= report(
        "externals filter returns 2",
        sum(1 for t in p.audio_tracks if t.source_kind is SourceKind.EXTERNAL) == 2,
    )

    # -----------------------------------------------------------------------
    print("\n[2] sync_all_to_master fills every non-master track")
    offsets = {"ext1.wav": 0.5, "ext2.wav": -0.25}
    sync_all_to_master(
        p,
        path_resolver=_identity_resolver(p),
        compute_fn=_stub_compute(offsets),
    )
    all_ok &= report("ext1 offset written", ext1.offset_to_master == 0.5)
    all_ok &= report("ext2 offset written", ext2.offset_to_master == -0.25)
    all_ok &= report(
        "ext1 confidence written", ext1.confidence is not None and ext1.confidence > 0.8
    )
    all_ok &= report("embedded stays at 0.0 (master)", emb.offset_to_master == 0.0)
    all_ok &= report("embedded confidence stays None (master)", emb.confidence is None)

    # -----------------------------------------------------------------------
    print("\n[3] Master change invalidates offsets")
    p.set_master(ext1.id)
    all_ok &= report("new master is ext1", p.master_track_id == ext1.id)
    all_ok &= report("new master offset == 0.0", ext1.offset_to_master == 0.0)
    all_ok &= report("embedded offset cleared", emb.offset_to_master is None)
    all_ok &= report("ext2 offset cleared", ext2.offset_to_master is None)
    all_ok &= report("ext2 confidence cleared", ext2.confidence is None)

    # Re-sync with a new set of offsets; embedded now needs one too.
    offsets2 = {"video.mp4": -0.5, "ext2.wav": 0.75}
    sync_all_to_master(
        p,
        path_resolver=_identity_resolver(p),
        compute_fn=_stub_compute(offsets2),
    )
    all_ok &= report("re-sync: embedded gets offset", emb.offset_to_master == -0.5)
    all_ok &= report("re-sync: ext2 gets offset", ext2.offset_to_master == 0.75)
    all_ok &= report("re-sync: ext1 (master) stays at 0.0", ext1.offset_to_master == 0.0)

    # video_offset_to_master derives from embedded.offset_to_master
    all_ok &= report(
        "video_offset_to_master == embedded offset", p.video_offset_to_master == -0.5
    )

    # -----------------------------------------------------------------------
    print("\n[4] Remove non-master track preserves others' offsets")
    p.remove_track(ext2.id)
    all_ok &= report("ext2 removed", len(p.audio_tracks) == 2)
    all_ok &= report("embedded offset preserved", emb.offset_to_master == -0.5)
    all_ok &= report("ext1 still master with offset 0.0", ext1.offset_to_master == 0.0)

    # -----------------------------------------------------------------------
    print("\n[5] _build_track_specs effective_offset correctness")
    # Re-add ext2 to get a 3-track project with a non-embedded master.
    p.add_track(ext2)
    # ext2 was just added, offset is None; we need it set for the spec calc.
    sync_all_to_master(
        p,
        path_resolver=_identity_resolver(p),
        compute_fn=_stub_compute({"video.mp4": -0.5, "ext2.wav": 0.75}),
    )
    specs = _build_track_specs(p, volumes={})
    spec_by_id = {s.track_id: s for s in specs}
    # embedded effective = embedded_offset - embedded_offset = 0
    all_ok &= report(
        "embedded effective_offset_sec == 0",
        spec_by_id[emb.id].effective_offset_sec == 0.0,
    )
    # ext1 (master) effective = 0 - (-0.5) = 0.5
    all_ok &= report(
        "ext1 effective_offset_sec == 0.5",
        abs(spec_by_id[ext1.id].effective_offset_sec - 0.5) < 1e-9,
    )
    # ext2 effective = 0.75 - (-0.5) = 1.25
    all_ok &= report(
        "ext2 effective_offset_sec == 1.25",
        abs(spec_by_id[ext2.id].effective_offset_sec - 1.25) < 1e-9,
    )
    all_ok &= report(
        "embedded TrackSpec.is_embedded True",
        spec_by_id[emb.id].is_embedded is True,
    )
    all_ok &= report(
        "ext2 TrackSpec.path is source_path",
        spec_by_id[ext2.id].path == "ext2.wav",
    )

    # -----------------------------------------------------------------------
    print("\n[6] Export gating (_can_export via MainWindow semantics)")

    class _FakeMainWindow:
        def __init__(self, project):
            self._project = project
    _can_export = MainWindow._can_export  # type: ignore[attr-defined]

    fw = _FakeMainWindow(p)
    # 6B relaxation: master != embedded is allowed as long as all offsets
    # are filled. Gate now only requires fully-synced tracks.
    all_ok &= report(
        "master != embedded, all offsets filled → export OK (6B)",
        _can_export(fw) is True,
        notes="master is ext1 here",
    )

    # Flip back to embedded master and resync
    p.set_master(emb.id)
    sync_all_to_master(
        p,
        path_resolver=_identity_resolver(p),
        compute_fn=_stub_compute({"ext1.wav": -0.5, "ext2.wav": 1.25}),
    )
    all_ok &= report("master == embedded and offsets filled → export OK", _can_export(fw) is True)

    # Wipe one offset to simulate stale state — export must be gated.
    ext2.offset_to_master = None
    all_ok &= report(
        "any missing offset → export blocked",
        _can_export(fw) is False,
    )
    ext2.offset_to_master = 1.25  # restore

    # Project with no video at all → blocked
    empty = Project()
    fw_empty = _FakeMainWindow(empty)
    all_ok &= report("no project video → export blocked", _can_export(fw_empty) is False)

    # -----------------------------------------------------------------------
    print("\n[7] build_export_cmd handles 2 externals with mixed offsets")
    # ext1: -0.5 (negative → atrim branch), ext2: 1.25 (positive → adelay)
    cmd = build_export_cmd(
        p,
        "out.mp4",
        volumes={emb.id: 1.0, ext1.id: 0.8, ext2.id: 1.2},
        video_audio_indices=[1],
        ffmpeg="ffmpeg",
    )
    fc_idx = cmd.index("-filter_complex")
    fc = cmd[fc_idx + 1]
    all_ok &= report("filter_complex has ex0_out label", "[ex0_out]" in fc)
    all_ok &= report("filter_complex has ex1_out label", "[ex1_out]" in fc)
    all_ok &= report(
        "ext1 negative offset → atrim branch in filter",
        "atrim=start=0.500000" in fc,
    )
    all_ok &= report(
        "ext2 positive offset → adelay branch in filter",
        "adelay=1250:all=1" in fc,
    )
    # Inputs: video + 2 externals
    input_flags = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    all_ok &= report(
        "3 inputs in argv (video + 2 externals)",
        input_flags == ["video.mp4", "ext1.wav", "ext2.wav"],
    )
    # Per-stream codecs: va0, ex0, ex1
    all_ok &= report("has -c:a:0 for video audio", "-c:a:0" in cmd)
    all_ok &= report("has -c:a:1 for ext0", "-c:a:1" in cmd)
    all_ok &= report("has -c:a:2 for ext1", "-c:a:2" in cmd)

    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DONE — {}".format("ALL PASS" if all_ok else "FAILURES ABOVE"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
