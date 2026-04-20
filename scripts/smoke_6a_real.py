"""
Stage 6A 'real' smoke test: drive the full multi-track user flow through
PreviewPanel + TrackListPanel + MainWindow._can_export, exercising the
UI code paths (under PySide6 stubs) rather than just the data model.

Flow walked:
    1. Single video + 1 external, post-sync.
    2. Add a 2nd and 3rd external; re-sync; preview reconfigured.
    3. Switch master to an external; offsets clear; re-sync.
    4. Verify export gate under 6B semantics:
         - master != embedded + fully synced  → enabled
         - master != embedded + stale offset  → blocked
         - master == embedded + fully synced  → enabled
    5. Verify TrackListPanel row count, master radio, and Remove gating
       (embedded + current master have Remove disabled).
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
from app.core.project_sync import sync_all_to_master
from app.ui.main_window import MainWindow, _build_track_specs
from app.ui.preview_panel import PreviewPanel
from app.ui.track_list_panel import TrackListPanel


# ---------------------------------------------------------------------------

def _make_external(name: str, duration: float = 28.0) -> AudioTrack:
    return AudioTrack(
        display_name=name,
        source_kind=SourceKind.EXTERNAL,
        source_path=f"{name}.wav",
        duration_seconds=duration,
    )


def _fresh_project() -> tuple[Project, AudioTrack, AudioTrack]:
    p = Project()
    p.video_asset = VideoAsset(
        path="video.mp4", duration_seconds=30.0, has_embedded_audio=True
    )
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="video.mp4",
        duration_seconds=30.0,
    )
    ext = _make_external("ext1")
    p.add_track(emb)
    p.add_track(ext)
    p.link_embedded_audio(emb.id)
    p.set_master(emb.id)
    return p, emb, ext


def _identity_resolver(_project: Project):
    return lambda track: track.source_path


def _stub_compute(offsets: dict[str, float], confidence: float = 0.9):
    def _fn(_master_path: str, track_path: str) -> tuple[float, float]:
        return (offsets.get(track_path, 0.0), confidence)
    return _fn


def _reconfigure_preview(preview: PreviewPanel, project: Project) -> None:
    specs = _build_track_specs(project, volumes={})
    preview.configure_tracks(
        project.video_asset.path,
        specs,
        trim_start=project.project_trim_start,
        trim_end=project.project_trim_end,
    )


class _FakeMainWindow:
    def __init__(self, project: Project):
        self._project = project


def _can_export(project: Project) -> bool:
    return MainWindow._can_export(_FakeMainWindow(project))  # type: ignore[attr-defined]


def report(name: str, ok: bool, notes: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {notes}" if notes else ""
    print(f"  [{status}] {name}{suffix}")
    return ok


# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("Stage 6A real smoke test: full multi-track flow via UI panels")
    print("=" * 70)
    all_ok = True

    preview = PreviewPanel()
    track_list = TrackListPanel()

    # -----------------------------------------------------------------------
    print("\n[1] Post-initial-sync: 1 embedded + 1 external")
    project, emb, ext1 = _fresh_project()
    sync_all_to_master(
        project,
        path_resolver=_identity_resolver(project),
        compute_fn=_stub_compute({"ext1.wav": 0.25}),
    )
    _reconfigure_preview(preview, project)
    track_list.refresh(project)

    all_ok &= report("preview has video_path set", preview.video_path == "video.mp4")
    all_ok &= report(
        "preview has 1 audio player (ext1 only)",
        len(preview._audio_players) == 1 and ext1.id in preview._audio_players,
    )
    all_ok &= report("track list has 2 rows", len(track_list._row_widgets) == 2)
    all_ok &= report("export enabled post initial sync", _can_export(project) is True)

    # -----------------------------------------------------------------------
    print("\n[2] Add 2nd + 3rd external; re-sync; multi-track preview")
    ext2 = _make_external("ext2", duration=25.0)
    ext3 = _make_external("ext3", duration=27.0)
    project.add_track(ext2)
    project.add_track(ext3)
    # Newly added tracks have offset=None → export gated until next sync.
    track_list.refresh(project)
    _reconfigure_preview(preview, project)
    all_ok &= report(
        "export blocked before re-sync (ext2/ext3 unsynced)",
        _can_export(project) is False,
    )

    sync_all_to_master(
        project,
        path_resolver=_identity_resolver(project),
        compute_fn=_stub_compute({
            "ext1.wav": 0.25,  # keep the original offset
            "ext2.wav": -0.4,
            "ext3.wav": 0.1,
        }),
    )
    _reconfigure_preview(preview, project)
    track_list.refresh(project)

    all_ok &= report(
        "preview has 3 audio players (all externals)",
        set(preview._audio_players.keys()) == {ext1.id, ext2.id, ext3.id},
    )
    all_ok &= report("track list has 4 rows", len(track_list._row_widgets) == 4)
    all_ok &= report("export enabled post re-sync", _can_export(project) is True)
    # effective_offset for embedded master: all externals' effective = their offset.
    all_ok &= report(
        "preview ext1 offset_ms == 250",
        preview._audio_offset_ms[ext1.id] == 250,
    )
    all_ok &= report(
        "preview ext2 offset_ms == -400",
        preview._audio_offset_ms[ext2.id] == -400,
    )

    # -----------------------------------------------------------------------
    print("\n[3] Switch master to ext1 — offsets cleared, re-sync required")
    project.set_master(ext1.id)
    track_list.refresh(project)
    _reconfigure_preview(preview, project)

    all_ok &= report("master is now ext1", project.master_track_id == ext1.id)
    all_ok &= report("embedded offset cleared", emb.offset_to_master is None)
    all_ok &= report("ext2 offset cleared", ext2.offset_to_master is None)
    all_ok &= report("ext3 offset cleared", ext3.offset_to_master is None)
    all_ok &= report("ext1 (new master) offset == 0.0", ext1.offset_to_master == 0.0)
    all_ok &= report(
        "export blocked immediately after master switch (stale offsets)",
        _can_export(project) is False,
    )

    # Re-sync against new master.
    sync_all_to_master(
        project,
        path_resolver=_identity_resolver(project),
        compute_fn=_stub_compute({
            "video.mp4": -0.25,   # embedded relative to ext1 master
            "ext2.wav": -0.65,
            "ext3.wav": -0.15,
        }),
    )
    _reconfigure_preview(preview, project)
    track_list.refresh(project)

    all_ok &= report(
        "export enabled after re-sync with master=ext1 (6B allows)",
        _can_export(project) is True,
    )
    # Under master=ext1, video_offset_to_master == embedded.offset = -0.25.
    # effective_offset = track.offset - embedded.offset:
    #   embedded: -0.25 - (-0.25) = 0   (always 0 for embedded)
    #   ext1:       0 - (-0.25) = +0.25
    #   ext2:   -0.65 - (-0.25) = -0.40
    #   ext3:   -0.15 - (-0.25) = +0.10
    all_ok &= report(
        "preview ext1 effective offset_ms == 250 (master under new frame)",
        preview._audio_offset_ms[ext1.id] == 250,
    )
    all_ok &= report(
        "preview ext2 effective offset_ms == -400",
        preview._audio_offset_ms[ext2.id] == -400,
    )
    all_ok &= report(
        "preview ext3 effective offset_ms == 100",
        preview._audio_offset_ms[ext3.id] == 100,
    )

    # -----------------------------------------------------------------------
    print("\n[4] Stale offset gates export even with master != embedded")
    saved_offset = ext3.offset_to_master
    ext3.offset_to_master = None
    all_ok &= report("export blocked when any offset is None", _can_export(project) is False)
    ext3.offset_to_master = saved_offset
    all_ok &= report("export restored when offset repopulated", _can_export(project) is True)

    # -----------------------------------------------------------------------
    print("\n[5] Switch master back to embedded — offsets clear, re-sync, export OK")
    project.set_master(emb.id)
    track_list.refresh(project)
    _reconfigure_preview(preview, project)
    all_ok &= report("master back to embedded", project.master_track_id == emb.id)
    all_ok &= report("embedded offset == 0.0", emb.offset_to_master == 0.0)
    all_ok &= report("export blocked until re-sync", _can_export(project) is False)

    sync_all_to_master(
        project,
        path_resolver=_identity_resolver(project),
        compute_fn=_stub_compute({
            "ext1.wav": 0.25,
            "ext2.wav": -0.4,
            "ext3.wav": 0.1,
        }),
    )
    _reconfigure_preview(preview, project)
    track_list.refresh(project)
    all_ok &= report(
        "export enabled with master=embedded after re-sync",
        _can_export(project) is True,
    )
    all_ok &= report(
        "video_offset_to_master back to 0",
        project.video_offset_to_master == 0.0,
    )

    # -----------------------------------------------------------------------
    print("\n[6] TrackListPanel: Remove disabled for embedded and master rows")
    # master is embedded here.
    row_widgets = track_list._row_widgets
    # Each row's last child widget (per _build_row) is the Remove button.
    remove_states: dict[str, bool] = {}
    for track, row in zip(project.audio_tracks, row_widgets):
        # Pull the Remove button via the layout's widget list (stub stores it).
        widgets = row.layout()._widgets
        remove_btn = widgets[-1]
        remove_states[track.display_name] = remove_btn.isEnabled()
    all_ok &= report(
        "embedded Remove disabled",
        remove_states.get("embedded") is False,
    )
    all_ok &= report(
        "ext1 (non-master external) Remove enabled",
        remove_states.get("ext1") is True,
    )

    # Switch master to ext1 and re-check: now ext1 must also be disabled.
    project.set_master(ext1.id)
    track_list.refresh(project)
    row_widgets = track_list._row_widgets
    remove_states = {}
    for track, row in zip(project.audio_tracks, row_widgets):
        widgets = row.layout()._widgets
        remove_btn = widgets[-1]
        remove_states[track.display_name] = remove_btn.isEnabled()
    all_ok &= report(
        "embedded Remove still disabled when master=ext1",
        remove_states.get("embedded") is False,
    )
    all_ok &= report(
        "ext1 Remove disabled when it is master",
        remove_states.get("ext1") is False,
    )
    all_ok &= report(
        "ext2 Remove enabled (non-master external)",
        remove_states.get("ext2") is True,
    )

    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("DONE — {}".format("ALL PASS" if all_ok else "FAILURES ABOVE"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
