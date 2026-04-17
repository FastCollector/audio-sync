"""
Data model for the multi-track audio-sync project.

Stage 1 deliverable: pure data with invariants. No I/O, no behaviour
beyond state transitions. See docs/plan.md (multi-track migration) for
the full design.

Key concepts:
    - VideoAsset: visual carrier. Its audio (if any) is represented
      separately as an AudioTrack with source_kind=VIDEO_EMBEDDED.
    - AudioTrack: any syncable audio source. The single master is
      identified by Project.master_track_id (single source of truth);
      `is_master` is a derived check, not stored on the track.
    - video_offset_to_master: derived from the embedded audio track's
      offset_to_master — video frames and embedded samples are locked
      in the source file, so they share the same offset.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class SourceKind(Enum):
    VIDEO_EMBEDDED = "video_embedded"
    EXTERNAL = "external"


class InvalidProjectState(Exception):
    """Raised when a Project mutation would violate an invariant."""


@dataclass(kw_only=True)
class AudioTrack:
    display_name: str
    source_kind: SourceKind
    source_path: str
    duration_seconds: float
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    offset_to_master: float | None = None
    confidence: float | None = None
    extracted_wav_path: str | None = None


@dataclass
class VideoAsset:
    path: str
    duration_seconds: float
    has_embedded_audio: bool
    embedded_audio_track_id: str | None = None


@dataclass
class Project:
    video_asset: VideoAsset | None = None
    audio_tracks: list[AudioTrack] = field(default_factory=list)
    master_track_id: str | None = None
    project_trim_start: float | None = None
    project_trim_end: float | None = None

    # ------------------------------------------------------------------
    # Queries

    def find_track(self, track_id: str) -> AudioTrack | None:
        for t in self.audio_tracks:
            if t.id == track_id:
                return t
        return None

    def master_track(self) -> AudioTrack | None:
        if self.master_track_id is None:
            return None
        return self.find_track(self.master_track_id)

    def embedded_audio_track(self) -> AudioTrack | None:
        if self.video_asset is None:
            return None
        tid = self.video_asset.embedded_audio_track_id
        if tid is None:
            return None
        return self.find_track(tid)

    def is_master(self, track: AudioTrack) -> bool:
        return (
            self.master_track_id is not None
            and track.id == self.master_track_id
        )

    @property
    def video_offset_to_master(self) -> float:
        """
        Derived. Video frames and the embedded audio track share the same
        source-time, so the video's offset to master equals the embedded
        track's offset. Returns 0.0 when:
            - there is no video asset
            - the video has no embedded audio track linked
            - the embedded track has no offset computed yet
        """
        embedded = self.embedded_audio_track()
        if embedded is None or embedded.offset_to_master is None:
            return 0.0
        return embedded.offset_to_master

    # ------------------------------------------------------------------
    # Mutations

    def add_track(self, track: AudioTrack) -> None:
        if self.find_track(track.id) is not None:
            raise InvalidProjectState(f"Track id already exists: {track.id}")
        self.audio_tracks.append(track)

    def remove_track(self, track_id: str) -> None:
        track = self.find_track(track_id)
        if track is None:
            raise InvalidProjectState(f"Unknown track id: {track_id}")

        removed_was_master = self.master_track_id == track_id
        self.audio_tracks.remove(track)

        if (
            self.video_asset is not None
            and self.video_asset.embedded_audio_track_id == track_id
        ):
            self.video_asset.embedded_audio_track_id = None

        if removed_was_master:
            self.master_track_id = None
            for t in self.audio_tracks:
                t.offset_to_master = None
                t.confidence = None

    def set_master(self, track_id: str) -> None:
        if self.find_track(track_id) is None:
            raise InvalidProjectState(f"Unknown track id: {track_id}")
        self.master_track_id = track_id
        for t in self.audio_tracks:
            if t.id == track_id:
                t.offset_to_master = 0.0
                t.confidence = None
            else:
                t.offset_to_master = None
                t.confidence = None

    def link_embedded_audio(self, track_id: str) -> None:
        """
        Link an existing AudioTrack as the VideoAsset's embedded audio.
        Enforces the embedded-linkage invariant:
            - video_asset exists
            - track exists
            - track.source_kind == VIDEO_EMBEDDED
            - track.source_path == video_asset.path
        """
        if self.video_asset is None:
            raise InvalidProjectState("No video asset to link")
        track = self.find_track(track_id)
        if track is None:
            raise InvalidProjectState(f"Unknown track id: {track_id}")
        if track.source_kind is not SourceKind.VIDEO_EMBEDDED:
            raise InvalidProjectState(
                "Embedded audio track must have source_kind=VIDEO_EMBEDDED"
            )
        if track.source_path != self.video_asset.path:
            raise InvalidProjectState(
                "Embedded track source_path must match video_asset.path"
            )
        self.video_asset.embedded_audio_track_id = track_id
