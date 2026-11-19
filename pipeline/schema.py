"""episode.json schema. episode.json is the single source of truth for an episode;
every stage reads it and writes its results back into it.

The models accept partially-filled episodes (e.g. no audio before narration).
Stage-dependent completeness is checked in validate.py, not here.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 1


class Status(str, Enum):
    draft = "draft"
    script_approved = "script_approved"
    narrated = "narrated"
    visuals_ready = "visuals_ready"
    draft_rendered = "draft_rendered"
    final_rendered = "final_rendered"
    reviewed = "reviewed"
    packaged = "packaged"

    @property
    def rank(self) -> int:
        return list(Status).index(self)

    def at_least(self, other: "Status") -> bool:
        return self.rank >= other.rank


Purpose = Literal["hook", "problem", "explain", "step", "mistake", "recap", "cta"]
VisualType = Literal["image", "broll", "graphic"]
GraphicTemplate = Literal["TitleCard", "KeyPoints", "BigNumber"]
Format = Literal["long", "short"]  # long = 16:9 landscape, short = 9:16 vertical


class _Model(BaseModel):
    # Forbid unknown keys so typos in hand-edited JSON fail loudly.
    model_config = ConfigDict(extra="forbid")


class VideoSpec(_Model):
    width: int = 1920
    height: int = 1080
    fps: int = 30


class VoiceSpec(_Model):
    preset: str = ""  # key in config.yaml tts.voices
    backend: str = "parler"
    speaker: str = ""
    description: str = ""
    seed: int | None = None
    wpm: float | None = None  # measured speaking pace, used for length estimates


class ImageInspection(_Model):
    """Claude's recorded check of one image file against config images.inspection_checklist."""
    file_sha1: str           # the image file that was inspected; regenerating invalidates the record
    passed: bool
    notes: str = ""          # per-person counts and anything noticed
    inspected_at: str = ""


class Visual(_Model):
    type: VisualType | None = None
    # image
    image_prompt: str | None = None
    seed: int | None = None
    attempts: int = 0
    # broll
    broll_id: str | None = None
    in_sec: float | None = None
    out_sec: float | None = None
    # graphic
    template: GraphicTemplate | None = None
    props: dict[str, Any] | None = None
    inspection: ImageInspection | None = None
    # free-form note from the visuals stage (why this choice, regeneration history)
    notes: str | None = None

    @model_validator(mode="after")
    def _broll_range(self) -> "Visual":
        if self.in_sec is not None and self.out_sec is not None and self.out_sec <= self.in_sec:
            raise ValueError(f"out_sec ({self.out_sec}) must be greater than in_sec ({self.in_sec})")
        return self


class AudioSegment(_Model):
    """One spoken segment (sentence or pause-marked phrase) inside a scene's audio."""
    text: str                 # as shown (narration_display, markup removed)
    start: float = Field(ge=0)  # speech start/end within the scene audio, seconds
    end: float
    style: str = "neutral"    # delivery style used (config narration.styles)


class Audio(_Model):
    file: str
    duration_sec: float = Field(gt=0)
    segments: list[AudioSegment] = Field(default_factory=list)  # empty for scene-mode narration


class Caption(_Model):
    text: str
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _order(self) -> "Caption":
        if self.end <= self.start:
            raise ValueError(f"caption end ({self.end}) must be after start ({self.start})")
        return self


class Scene(_Model):
    id: int = Field(ge=1)
    purpose: Purpose
    narration_display: str = Field(min_length=1)
    narration_spoken: str = ""
    on_screen_text: str | None = None
    visual: Visual = Field(default_factory=Visual)
    sources: list[str] = Field(default_factory=list)
    audio: Audio | None = None
    captions: list[Caption] = Field(default_factory=list)
    image_file: str | None = None


class Package(_Model):
    """YouTube metadata, written by Claude in the package stage; package.py renders youtube.md from it."""
    youtube_title: str = ""            # Hindi, < 70 chars
    description_hi: str = ""           # short Hindi summary (sources + disclaimer are appended automatically)
    tags: list[str] = Field(default_factory=list)   # ~10
    thumbnail_text: str = ""           # 3–5 Hindi words, big on the thumbnail
    thumbnail_image: str | None = None # e.g. "images/scene-03.png"; default: first image scene
    synthetic_content: bool | None = None  # YouTube "altered or synthetic content" disclosure
    sources_list: list[str] = Field(default_factory=list)  # readable source names; default: file names


class Episode(_Model):
    schema_version: int = SCHEMA_VERSION
    id: str
    title_hi: str = ""
    status: Status = Status.draft
    format: Format = "long"
    video: VideoSpec = Field(default_factory=VideoSpec)
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    scenes: list[Scene] = Field(default_factory=list)
    package: Package = Field(default_factory=Package)

    @field_validator("scenes")
    @classmethod
    def _unique_ids(cls, scenes: list[Scene]) -> list[Scene]:
        ids = [s.id for s in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate scene ids: {ids}")
        if ids != sorted(ids):
            raise ValueError(f"scenes must be ordered by id: {ids}")
        return scenes

    @model_validator(mode="after")
    def _orientation(self) -> "Episode":
        portrait = self.video.height > self.video.width
        if portrait != (self.format == "short"):
            raise ValueError(f"format {self.format!r} does not match video size "
                             f"{self.video.width}x{self.video.height}")
        return self

    def scene(self, scene_id: int) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise KeyError(f"no scene with id {scene_id}")
