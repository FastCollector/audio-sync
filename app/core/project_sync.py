"""
Stage 2: multi-track sync orchestration.

Pure function over the Project data model. Given a project with a master
track selected, compute each non-master track's offset/confidence against
the master and write the results back onto the tracks.

This module is deliberately ignorant of:
    - where audio bytes live on disk (caller supplies a path_resolver)
    - extraction / caching policy (Stage 4)
    - UI and threading (Stage 5/6)
    - export (Stage 3)
"""

from __future__ import annotations

from typing import Callable, Optional

from app.core.project import AudioTrack, InvalidProjectState, Project
from app.core.sync_engine import compute_offset

PathResolver = Callable[[AudioTrack], str]
ComputeFn = Callable[[str, str], tuple[float, float]]
ProgressFn = Callable[[AudioTrack], None]


def sync_all_to_master(
    project: Project,
    *,
    path_resolver: PathResolver,
    compute_fn: ComputeFn = compute_offset,
    progress: Optional[ProgressFn] = None,
) -> None:
    """
    Compute offset/confidence for every non-master track against the master.

    Args:
        project: project with a master track already selected.
        path_resolver: maps an AudioTrack to a sync-ready audio path on disk.
            Stage 2 does not care whether that path is an extracted WAV, the
            original source, or something else.
        compute_fn: injection point for the pairwise sync algorithm.
            Signature: (master_path, track_path) -> (offset_seconds, confidence).
        progress: optional callback invoked once per non-master track, AFTER
            that track's offset/confidence have been written. Receives the
            updated AudioTrack.

    Raises:
        InvalidProjectState: if no master is set.

    Side effects:
        Mutates each non-master track's `offset_to_master` and `confidence`.
        The master track is left untouched (offset 0.0, confidence None, as
        set by Project.set_master).
    """
    master = project.master_track()
    if master is None:
        raise InvalidProjectState("No master track set")

    master_path = path_resolver(master)

    for track in project.audio_tracks:
        if track.id == master.id:
            continue
        track_path = path_resolver(track)
        offset, confidence = compute_fn(master_path, track_path)
        track.offset_to_master = float(offset)
        track.confidence = float(confidence)
        if progress is not None:
            progress(track)
