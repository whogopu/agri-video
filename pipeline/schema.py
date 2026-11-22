"""episode.json schema. episode.json is the single source of truth for an episode;
every stage reads it and writes its results back into it.

The models accept partially-filled episodes (e.g. no audio before narration).
Stage-dependent completeness is checked in validate.py, not here.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = 2
# v2 (2026-11-19): an image visual holds several `shots` (cut on sentence boundaries), each of
# which may show recurring cast members; episodes declare their `cast`. v1 files are migrated on
# load (the single image becomes shot 1).


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


class Shot(_Model):
    """One still inside an image scene. Shots cut on sentence boundaries of the scene's narration."""
    at_segment: int = Field(0, ge=0)   # the shot starts with this narration segment (0 = scene start)
    # Either a free-text prompt or a scene spec (pipeline/scene_spec.py, slots in bakeoff/shots.yaml);
    # a spec is linted and rendered into the prompt in code. Not both.
    image_prompt: str | None = None
    spec: dict[str, Any] | None = None
    prompt_sent: str | None = None     # the full prompt the current image was generated from (preamble + style)
    characters: list[str] = Field(default_factory=list)  # cast ids shown; their references condition the image
    seed: int | None = None
    attempts: int = 0
    image_file: str | None = None      # current pick, e.g. images/scene-07-s2.png
    # cast id → SHA-1 of the reference image used to generate this shot (stale if a reference changes)
    reference_sha1: dict[str, str] = Field(default_factory=dict)
    inspection: ImageInspection | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _one_prompt_source(self) -> "Shot":
        if self.image_prompt and self.spec:
            raise ValueError("a shot has either image_prompt or spec, not both")
        return self


class Visual(_Model):
    type: VisualType | None = None
    # image: one or more shots
    shots: list[Shot] = Field(default_factory=list)
    # broll
    broll_id: str | None = None
    in_sec: float | None = None
    out_sec: float | None = None
    # graphic
    template: GraphicTemplate | None = None
    props: dict[str, Any] | None = None
    # free-form note from the visuals stage (why this choice, regeneration history)
    notes: str | None = None

    @model_validator(mode="after")
    def _broll_range(self) -> "Visual":
        if self.in_sec is not None and self.out_sec is not None and self.out_sec <= self.in_sec:
            raise ValueError(f"out_sec ({self.out_sec}) must be greater than in_sec ({self.in_sec})")
        return self

    @model_validator(mode="after")
    def _shot_order(self) -> "Visual":
        segs = [sh.at_segment for sh in self.shots]
        if segs and segs[0] != 0:
            raise ValueError(f"the first shot must start at segment 0, got {segs}")
        if any(b <= a for a, b in zip(segs, segs[1:])):
            raise ValueError(f"shot at_segment values must increase: {segs}")
        return self


_V1_IMAGE_KEYS = ("image_prompt", "seed", "attempts", "inspection")


class AudioSegment(_Model):
    """One spoken segment (sentence or pause-marked phrase) inside a scene's audio."""
    text: str                 # as shown (narration_display, markup removed)
    start: float = Field(ge=0)  # speech start/end within the scene audio, seconds
    end: float
    style: str = "neutral"    # delivery style used (config narration.styles)


class AudioWord(_Model):
    """One displayed word and when it is spoken (pipeline/word_align.py)."""
    text: str                 # narration_display spelling, punctuation kept
    start: float = Field(ge=0)
    end: float
    segment: int = Field(ge=0)  # index into Audio.segments
    timed: bool = True        # False = no reliable Whisper match; spread by letter count inside its span


class Audio(_Model):
    file: str
    duration_sec: float = Field(gt=0)
    segments: list[AudioSegment] = Field(default_factory=list)  # empty for scene-mode narration
    words: list[AudioWord] = Field(default_factory=list)        # empty until word timing has run


class CaptionWord(_Model):
    """A word inside a caption chunk, with when it is spoken (scene seconds); drives the highlight."""
    text: str
    start: float = Field(ge=0)
    end: float


class Caption(_Model):
    text: str
    start: float = Field(ge=0)
    end: float
    words: list[CaptionWord] = Field(default_factory=list)  # empty = no word timing (no highlight)

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

    @model_validator(mode="before")
    @classmethod
    def _migrate_v1_image(cls, data: Any) -> Any:
        """v1: one image per scene (visual.image_prompt/seed/attempts/inspection + scene.image_file)."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        image_file = data.pop("image_file", None)
        v = dict(data.get("visual") or {})
        shot = {k: v.pop(k) for k in _V1_IMAGE_KEYS if k in v}
        if image_file is not None:
            shot["image_file"] = image_file
        if any(val not in (None, 0) for val in shot.values()) and not v.get("shots"):
            v["shots"] = [shot]
        if "visual" in data or shot:
            data["visual"] = v
        return data

    def image_files(self) -> list[str]:
        return [sh.image_file for sh in self.visual.shots if sh.image_file] if self.visual.type == "image" else []


class Package(_Model):
    """YouTube metadata, written by Claude in the package stage; package.py renders youtube.md from it."""
    youtube_title: str = ""            # Hindi, < 70 chars
    description_hi: str = ""           # short Hindi summary (sources + disclaimer are appended automatically)
    tags: list[str] = Field(default_factory=list)   # ~10
    thumbnail_text: str = ""           # 3–5 Hindi words, big on the thumbnail
    thumbnail_image: str | None = None # e.g. "images/scene-03.png"; default: first image scene
    synthetic_content: bool | None = None  # YouTube "altered or synthetic content" disclosure
    sources_list: list[str] = Field(default_factory=list)  # readable source names; default: file names


class CastMember(_Model):
    """A recurring character (assets/cast/<id>/character.json). Synthetic people only: never a real
    person's face or name. The approved reference image keeps the face and clothes the same in every shot."""
    id: str
    name_hi: str                      # how the narrator calls him/her, e.g. "रमेश जी"
    name_en: str                      # used in image prompts, e.g. "Ramesh"
    role: str                         # e.g. "farmer, main character of the channel"
    gender: Literal["male", "female"]
    look: str                         # English prompt text: age, build, face, hair, facial hair, skin
    wardrobe: str                     # English prompt text: the fixed costume
    accessories: str = ""             # English, positive: what is on head/wrists/fingers ("bare wrists, bare fingers")
    reference: str | None = None      # approved image, relative to the character folder (ref.png)
    reference_sha1: str | None = None
    approved_at: str | None = None    # set only by `cast approve`, after the USER picked the face
    candidate_seeds: list[int] = Field(default_factory=list)
    notes: str = ""


class Episode(_Model):
    schema_version: int = SCHEMA_VERSION
    id: str
    title_hi: str = ""
    status: Status = Status.draft
    format: Format = "long"
    video: VideoSpec = Field(default_factory=VideoSpec)
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    # recurring characters (ids in assets/cast/) whose story the narrator tells; main character first
    cast: list[str] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    package: Package = Field(default_factory=Package)

    @model_validator(mode="before")
    @classmethod
    def _upgrade_version(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("schema_version", SCHEMA_VERSION) < SCHEMA_VERSION:
            data = {**data, "schema_version": SCHEMA_VERSION}  # scenes migrate themselves
        return data

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
