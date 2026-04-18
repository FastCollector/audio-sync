"""
Stage 4: project-scoped extract cache.

Owns the on-disk tmpdir that holds extracted mono-16k WAVs used by sync.
Thin wrapper over the existing extractor primitive — cache controls the
destination path, naming, reuse, and cleanup; extractor.py is unchanged.

Surface:
    ExtractCache(root)
      .ensure_extracted(project, track) -> str
      .resolver(project) -> Callable[[AudioTrack], str]   # Stage-2 adapter
      .sweep_stale(max_age_hours=24.0) -> list[str]

This module deliberately owns no UI, no threading, no project persistence.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Callable

from app.core.extractor import extract_audio
from app.core.project import AudioTrack, Project


class ExtractCache:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, project: Project, track: AudioTrack) -> Path:
        return self._root / project.id / f"{track.id}.wav"

    def ensure_extracted(self, project: Project, track: AudioTrack) -> str:
        """
        Return the cached WAV path for this track, extracting if needed.

        Cache hit: `track.extracted_wav_path` matches the expected path AND
        the file exists on disk. Otherwise re-extract.
        """
        dest = self.path_for(project, track)
        dest_str = str(dest)
        if track.extracted_wav_path == dest_str and dest.exists():
            return dest_str

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_path, _duration = extract_audio(track.source_path)
        if dest.exists():
            dest.unlink()
        shutil.move(tmp_path, dest_str)
        track.extracted_wav_path = dest_str
        return dest_str

    def resolver(self, project: Project) -> Callable[[AudioTrack], str]:
        """Return a callable matching Stage 2's path_resolver contract."""
        def _resolve(track: AudioTrack) -> str:
            return self.ensure_extracted(project, track)
        return _resolve

    def sweep_stale(self, max_age_hours: float = 24.0) -> list[str]:
        """
        Delete project subdirs under root whose mtime is older than the
        threshold. Returns the list of deleted paths.
        """
        if not self._root.exists():
            return []
        cutoff = time.time() - max_age_hours * 3600.0
        deleted: list[str] = []
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            if child.stat().st_mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                deleted.append(str(child))
        return deleted
