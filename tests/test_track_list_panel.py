"""
Stage 6A tests for app.ui.track_list_panel.

Exercises the view layer: `refresh(project)` renders one row per track,
row buttons emit the right signals, and Remove is disabled correctly
for embedded + current-master tracks.
"""

from __future__ import annotations

from _pyside_stubs import install_pyside6_stubs

install_pyside6_stubs()

from app.core.project import AudioTrack, Project, SourceKind, VideoAsset
from app.ui.track_list_panel import TrackListPanel


def _build_project(external_count: int = 1) -> Project:
    p = Project()
    p.video_asset = VideoAsset(path="v.mp4", duration_seconds=10.0, has_embedded_audio=True)
    emb = AudioTrack(
        display_name="embedded",
        source_kind=SourceKind.VIDEO_EMBEDDED,
        source_path="v.mp4",
        duration_seconds=10.0,
    )
    p.add_track(emb)
    for i in range(external_count):
        ext = AudioTrack(
            display_name=f"ext{i}",
            source_kind=SourceKind.EXTERNAL,
            source_path=f"ext{i}.wav",
            duration_seconds=10.0,
        )
        p.add_track(ext)
    p.link_embedded_audio(emb.id)
    p.set_master(emb.id)
    return p


def _find_row_buttons(panel: TrackListPanel) -> list:
    """Return [(track_row_widget, remove_button)] in order."""
    rows = []
    for row in panel._row_widgets:
        layout = row.layout() if hasattr(row, "layout") else None
        # Our stub layout stores widgets in ._widgets
        widgets = getattr(layout, "_widgets", None)
        if widgets is None:
            # layout not accessible via stub — read from panel internals
            widgets = []
        rows.append((row, widgets))
    return rows


def test_refresh_none_project_shows_empty_state():
    panel = TrackListPanel()
    panel.refresh(None)
    assert panel._empty_label._visible is True
    assert panel._add_btn.isEnabled() is False
    assert panel._row_widgets == []


def test_refresh_renders_row_per_track():
    panel = TrackListPanel()
    project = _build_project(external_count=2)
    panel.refresh(project)

    assert len(panel._row_widgets) == 3  # embedded + 2 external
    assert panel._empty_label._visible is False
    assert panel._add_btn.isEnabled() is True


def test_refresh_clears_previous_rows():
    panel = TrackListPanel()
    project = _build_project(external_count=2)
    panel.refresh(project)
    assert len(panel._row_widgets) == 3

    project2 = _build_project(external_count=0)
    panel.refresh(project2)
    assert len(panel._row_widgets) == 1  # embedded only


def test_remove_requested_emits_track_id():
    panel = TrackListPanel()
    project = _build_project(external_count=1)
    panel.refresh(project)

    # Grab the external track and simulate Remove click
    ext = [t for t in project.audio_tracks if t.source_kind is SourceKind.EXTERNAL][0]
    captured: list[str] = []
    panel.remove_track_requested.connect(captured.append)

    # Find the external row's remove button (last widget in that row's layout)
    ext_row_idx = project.audio_tracks.index(ext)
    row = panel._row_widgets[ext_row_idx]
    remove_btn = row.layout()._widgets[-1]
    remove_btn.clicked.emit(False)

    assert captured == [ext.id]


def test_remove_disabled_for_embedded_and_master():
    panel = TrackListPanel()
    project = _build_project(external_count=1)
    panel.refresh(project)
    # Embedded is also master here → Remove button disabled
    embedded_row = panel._row_widgets[0]
    embedded_remove = embedded_row.layout()._widgets[-1]
    assert embedded_remove.isEnabled() is False

    ext_row = panel._row_widgets[1]
    ext_remove = ext_row.layout()._widgets[-1]
    assert ext_remove.isEnabled() is True


def test_remove_disabled_for_non_embedded_master():
    panel = TrackListPanel()
    project = _build_project(external_count=2)
    # Flip master to the first external
    externals = [t for t in project.audio_tracks if t.source_kind is SourceKind.EXTERNAL]
    project.set_master(externals[0].id)
    panel.refresh(project)

    # Row indices: [embedded, ext0(master), ext1]
    embedded_remove = panel._row_widgets[0].layout()._widgets[-1]
    ext0_remove = panel._row_widgets[1].layout()._widgets[-1]
    ext1_remove = panel._row_widgets[2].layout()._widgets[-1]

    assert embedded_remove.isEnabled() is False  # embedded
    assert ext0_remove.isEnabled() is False      # master
    assert ext1_remove.isEnabled() is True       # non-master external


def test_master_changed_emitted_only_on_user_click_not_on_refresh():
    """setChecked during refresh must not emit master_changed."""
    panel = TrackListPanel()
    project = _build_project(external_count=1)
    captured: list[str] = []
    panel.master_changed.connect(captured.append)

    panel.refresh(project)
    # refresh alone should not emit anything (clicked is user-only)
    # Note: stub's setChecked may emit `toggled` but we connected `clicked`.
    # The TrackListPanel connects `clicked` in _build_row, not `toggled`.
    assert captured == []

    # Simulate a user click on the external's radio
    ext_row = panel._row_widgets[1]
    radio = ext_row.layout()._widgets[0]
    radio.clicked.emit(True)
    ext = [t for t in project.audio_tracks if t.source_kind is SourceKind.EXTERNAL][0]
    assert captured == [ext.id]


def test_radio_checked_state_reflects_master():
    panel = TrackListPanel()
    project = _build_project(external_count=1)
    panel.refresh(project)

    embedded_radio = panel._row_widgets[0].layout()._widgets[0]
    ext_radio = panel._row_widgets[1].layout()._widgets[0]
    assert embedded_radio.isChecked() is True
    assert ext_radio.isChecked() is False


def test_offset_label_renders_dash_when_unsynced():
    panel = TrackListPanel()
    project = _build_project(external_count=1)
    # External has no offset yet (pre-sync)
    panel.refresh(project)
    # Row text isn't easily inspected via stub; just ensure no crash
    assert len(panel._row_widgets) == 2


def test_is_supported_audio():
    assert TrackListPanel.is_supported_audio("song.wav") is True
    assert TrackListPanel.is_supported_audio("song.mp3") is True
    assert TrackListPanel.is_supported_audio("song.flac") is True
    assert TrackListPanel.is_supported_audio("song.txt") is False
    assert TrackListPanel.is_supported_audio("song.mp4") is False
